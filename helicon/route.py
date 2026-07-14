"""helicon route - a routing recommendation as a READ of the eval store.

The thesis, applied to model selection: Helicon already verifies agent OUTPUT
against reality (`review --terminals`). "Which model should I route this task to"
is then not a new capability - it is a ranked read of verified outcomes already
in the store. Route ships a recommendation ONLY where real evidence supports it;
below a sample threshold it says "insufficient evidence", never a fabricated
number.

Honesty rules (enforced, not aspirational):
  - Outcome is a real reality-check verdict from the review engine, never a guess.
    verified = pass, contradicted = fail. `unverified` (couldn't check) is NOT a
    fail - it is excluded from the pass/fail denominator entirely.
  - The model is attributed from the git Co-authored-by trailer of the commits
    that produced the output (the dominant model across the branch). No trailer
    -> "unknown", never invented.
  - Ranking is Wilson lower-bound on the verified-rate, so a 1/1 never outranks a
    47/50. Sample size and confidence travel WITH every recommendation.

This module adds no verification engine: it reuses review_terminals (discover /
ingest / extract / verify) as the single source of ground truth.
"""
import hashlib
import re
from datetime import datetime, timezone
from math import sqrt

# Claim kind (what review_terminals extracts) -> task-class (what you route).
TASK_CLASS_OF_KIND = {
    "test": "testing",
    "ship": "delivery",
    "url": "delivery",
    "endpoint": "api-surface",
    "metric": "claims",
}

_TRAILER_RX = re.compile(r"Claude [A-Za-z0-9.\- ]+(?:\([^)]*\))?", re.I)


def normalize_model(raw: str) -> str:
    """'Claude Opus 4.8 (1M context) <noreply@anthropic.com>' -> 'Opus 4.8 (1M context)'.
    Strips the 'Claude ' vendor prefix and any trailing email; keeps the model
    name (and a real variant qualifier like '(1M context)') verbatim."""
    s = re.sub(r"<[^>]*>", "", raw or "").strip()
    s = re.sub(r"^claude\s+", "", s, flags=re.I).strip()
    return re.sub(r"\s+", " ", s) or "unknown"


def harness_of(raw: str) -> str:
    """Infer the harness from the commit signature. The 'Claude … <noreply@
    anthropic.com>' co-author trailer is Claude Code's signature; Cursor/Codex
    sign differently. Inference from evidence, never assumed."""
    low = (raw or "").lower()
    if "cursor" in low:
        return "cursor"
    if "codex" in low or "openai" in low:
        return "codex"
    if "copilot" in low:
        return "copilot"
    if "claude" in low and "anthropic.com" in low:
        return "claude-code"
    return "unknown"


def _trailers(repo: str, base: str) -> list[str]:
    """Co-authored-by values across base..HEAD (the branch's own output). Falls
    back to the last 25 commits of HEAD when the branch is level with base."""
    from helicon.review_terminals import _git
    rng = f"{base}..HEAD"
    if _git(repo, "rev-list", "--count", rng) in ("", "0"):
        rng = "-25"
    fmt = "%(trailers:key=Co-authored-by,valueonly)"
    out = _git(repo, "log", f"--format={fmt}", rng)
    vals = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            vals.append(line)
    return vals


def terminal_attribution(repo: str, base: str) -> tuple[str, str, int, int]:
    """(model, harness, support, total) - the dominant model that authored this
    terminal's output, by co-author trailer count. ('unknown','unknown',0,0) when
    no trailer exists (we do not invent an author)."""
    raws = _trailers(repo, base)
    counts: dict[str, int] = {}
    harnesses: dict[str, str] = {}
    for raw in raws:
        m = normalize_model(raw)
        counts[m] = counts.get(m, 0) + 1
        harnesses.setdefault(m, harness_of(raw))
    if not counts:
        return ("unknown", "unknown", 0, 0)
    model = max(counts, key=lambda k: counts[k])
    return (model, harnesses.get(model, "unknown"), counts[model], sum(counts.values()))


def wilson_lower(pos: int, n: int, z: float = 1.96) -> float:
    """Wilson score lower bound of a binomial proportion. This is the ranking key:
    it discounts small samples so 1/1 (LB 0.21) never outranks 9/10 (LB 0.59)."""
    if n <= 0:
        return 0.0
    p = pos / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def record_evidence(conn, config=None, run: bool = False, only=None) -> dict:
    """Run the review engine across every terminal, tag each real verdict with the
    model + harness that produced it and the task-class of the claim, and upsert
    it into route_evidence (idempotent per claim+model). This is the instrument:
    it turns output-verification into routing evidence, no new checks."""
    import os
    from helicon.review_terminals import (
        discover_terminals, ingest, extract_claims, verify)
    rows, by_verdict, models = 0, {}, {}
    for name, repo in discover_terminals(config):
        if only and name.lower() not in only and os.path.basename(repo).lower() not in only:
            continue
        atom = ingest(name, repo)
        model, harness, support, total = terminal_attribution(repo, atom["base"])
        for claim in extract_claims(atom):
            verdict, receipt = verify(claim, atom, run=run)
            tc = TASK_CLASS_OF_KIND.get(claim["kind"], "other")
            h = hashlib.sha1(f"{claim['kind']}|{claim['text'].lower().strip()}".encode()).hexdigest()[:10]
            pair_key = f"route|{name}|{h}|{model}"
            conn.execute(
                "INSERT INTO route_evidence "
                "(model,harness,task_class,verdict,terminal,repo,claim,receipt,created_at,pair_key) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(pair_key) DO UPDATE SET "
                "verdict=excluded.verdict, receipt=excluded.receipt, "
                "created_at=excluded.created_at, model=excluded.model, harness=excluded.harness",
                (model, harness, tc, verdict, name, repo, claim["text"][:200],
                 receipt[:300], _now(), pair_key))
            rows += 1
            by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
            models[model] = models.get(model, 0) + 1
    conn.commit()
    return {"rows": rows, "by_verdict": by_verdict, "models": models}


def route(conn, task_class: str | None = None, min_n: int = 5, z: float = 1.96) -> dict:
    """Rank models by Wilson-scored verified-rate per task-class, reading only real
    verdicts. verified=pass, contradicted=fail, unverified excluded. A task-class
    whose best model has fewer than min_n pass/fail samples returns
    'insufficient_evidence' with the raw counts, never a fabricated pick."""
    where = "WHERE verdict IN ('verified','contradicted')"
    params: list = []
    if task_class:
        where += " AND task_class = ?"
        params.append(task_class)
    agg: dict = {}
    uncheckable: dict = {}
    for r in conn.execute(
            f"SELECT task_class, model, harness, verdict FROM route_evidence {where}",
            params):
        key = (r["task_class"], r["model"], r["harness"])
        a = agg.setdefault(key, {"pos": 0, "n": 0})
        a["n"] += 1
        if r["verdict"] == "verified":
            a["pos"] += 1
    # count uncheckable (unverified) per class for honest context
    uw = "WHERE verdict = 'unverified'" + (" AND task_class = ?" if task_class else "")
    for r in conn.execute(f"SELECT task_class, COUNT(*) c FROM route_evidence {uw} GROUP BY task_class",
                          params[:1] if task_class else []):
        uncheckable[r["task_class"]] = r["c"]

    by_class: dict = {}
    for (tc, model, harness), a in agg.items():
        cand = {
            "model": model, "harness": harness,
            "pass": a["pos"], "fail": a["n"] - a["pos"], "n": a["n"],
            "rate": round(a["pos"] / a["n"], 3),
            "wilson_lb": round(wilson_lower(a["pos"], a["n"], z), 3),
        }
        by_class.setdefault(tc, []).append(cand)

    results = []
    for tc, cands in by_class.items():
        cands.sort(key=lambda c: (c["wilson_lb"], c["n"]), reverse=True)
        best = cands[0]
        enough = best["n"] >= min_n
        # A provisional lean: below the firm threshold but real, positive evidence
        # exists (some verified, none-to-few failures). Directional, NOT a firm
        # route - the numbers travel with it so it can never read as confidence.
        lean = (not enough and best["n"] >= 2 and best["pass"] >= 2
                and best["rate"] >= 0.6)
        results.append({
            "task_class": tc,
            "recommendation": best["model"] if enough else None,
            "sufficient": enough,
            "lean": (best["model"] if lean else None),
            "min_n": min_n,
            "best": best,
            "candidates": cands,
            "models_compared": len(cands),
            "uncheckable": uncheckable.get(tc, 0),
        })
    results.sort(key=lambda r: (r["sufficient"], r["best"]["n"]), reverse=True)
    return {"task_class_filter": task_class, "min_n": min_n, "results": results,
            "total_classes": len(results)}


def format_route(routed: dict) -> str:
    res = routed["results"]
    min_n = routed["min_n"]
    if not res:
        return ("\n  No routing evidence yet. Build it:  helicon route --record [--run]\n"
                "  (it reads verified outcomes from `review --terminals`.)\n")
    out = ["", "  MODEL ROUTING - ranked read of verified agent output "
           f"(Wilson LB, min n={min_n})", ""]
    for r in res:
        tc = r["task_class"]
        if r["sufficient"]:
            b = r["best"]
            tag = "" if r["models_compared"] > 1 else "  (only model with evidence)"
            out.append(f"  ▸ {tc}:  route to  {b['model']}  [{b['harness']}]{tag}")
            out.append(f"      verified {b['pass']}/{b['n']}  ·  Wilson LB {b['wilson_lb']}  "
                       f"·  raw rate {b['rate']}")
            for c in r["candidates"][1:]:
                out.append(f"        vs {c['model']}: {c['pass']}/{c['n']} (LB {c['wilson_lb']})")
        elif r["lean"]:
            b = r["best"]
            out.append(f"  ▸ {tc}:  leaning  {b['model']}  "
                       f"(verified {b['pass']}/{b['n']})  — provisional, n<{min_n}, not a firm route")
            out.append(f"      Wilson LB {b['wilson_lb']}  ·  raw rate {b['rate']}  "
                       f"·  need {min_n - b['n']} more sample(s) to confirm")
        else:
            b = r["best"]
            out.append(f"  ▸ {tc}:  insufficient evidence  "
                       f"(best: {b['model']} {b['pass']}/{b['n']}, need n≥{min_n})")
        if r["uncheckable"]:
            out.append(f"      ({r['uncheckable']} claim(s) uncheckable - excluded, not counted as fail)")
    out.append("")
    return "\n".join(out)
