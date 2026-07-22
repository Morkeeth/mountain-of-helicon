"""The Fleet — one screen for five terminals (V2.4).

The operator's actual problem, in his words: five terminals deep, three or four
projects, "no clue what context was used", "lose track of what each terminal is
doing", no top agenda, no read on spend. Every existing surface here answers a
question about ONE run. None answers "what is my fleet doing right now".

Shape borrowed deliberately:
  · k9s / lazygit — a live resource view you leave open, not a report you run
  · Vercel        — state at a glance, one line per unit, colourless until wrong
  · Linear        — ONE triage queue, never a dashboard of dashboards

Four questions, in the order they actually matter to someone with five terminals
open. Anything that does not answer one of them does not belong on this screen:

  RUNNING    what is live right now, and has any of it drifted off its objective
  SPEND      where the tokens went, by project
  REVIEW     what finished without your eyes on it
  EFFICIENCY do your accepted runs cost less than your rejected ones

DRIFT is the novel one and the one to be most careful about. The deep-research
pass found ZERO published, verified techniques for detecting that an agent has
wandered off-objective. So this ships a heuristic and calls it a heuristic:
term overlap between the frozen objective and the paths actually touched. It
CANNOT prove drift. A refactor legitimately touches files sharing no vocabulary
with its objective. So the label is "worth a look", never "off-objective", and
it is only ever computed for runs with a REAL frozen objective — an auto-
observed run has no objective to drift from, and flagging one would be inventing
a contract that never existed.
"""
import json
import os
from datetime import datetime, timedelta, timezone

# Words that appear in every objective and every path, so they can only create
# false agreement. Kept small on purpose: an over-eager stoplist manufactures
# drift by deleting the very terms that matched.
_NOISE = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
          "that", "this", "is", "it", "be", "as", "at", "by", "from", "src",
          "lib", "test", "tests", "py", "ts", "tsx", "js", "md", "json", "helicon"}

DRIFT_MIN_FILES = 4     # below this, "no shared vocabulary" is just a small diff


def _terms(text: str) -> set:
    out = set()
    for w in "".join(c if c.isalnum() else " " for c in (text or "").lower()).split():
        if len(w) > 2 and w not in _NOISE:
            out.add(w)
    return out


def _loads(raw, default):
    try:
        return json.loads(raw) if raw else default
    except (ValueError, TypeError):
        return default


def drift_signal(objective: str, manifest: list) -> dict:
    """Heuristic ONLY. Returns a signal, never a verdict.

    Honest failure modes, stated because a drift alarm nobody trusts is worse
    than no alarm: a rename touches everything and shares nothing; a refactor
    named for behaviour touches files named for structure. Both look like drift
    and are not. So this reports the overlap and lets the human look.
    """
    # A TRUNCATED manifest cannot be drift-checked, and this is not theoretical:
    # the first live run of this feature flagged "harden the valuation gate" as
    # off-objective because the manifest had been cut at 40 files and
    # helicon/valuation.py fell off the end. Against the complete 99-file
    # manifest the same objective goes quiet on the shared term 'valuation'.
    # Absence of evidence in a truncated list is not evidence of drift.
    if any(a.get("state") == "truncated" for a in manifest if isinstance(a, dict)):
        return {"checkable": False, "reason": "manifest was truncated — cannot rule on drift"}
    paths = [a.get("path", "") for a in manifest
             if isinstance(a, dict) and a.get("state") != "truncated"]
    if len(paths) < DRIFT_MIN_FILES:
        return {"checkable": False, "reason": "too few files to say anything"}
    want = _terms(objective)
    if not want:
        return {"checkable": False, "reason": "no objective to compare against"}
    touched = set()
    for p in paths:
        touched |= _terms(p.replace("/", " ").replace("_", " ").replace("-", " "))
    shared = want & touched
    return {
        "checkable": True,
        "shared": sorted(shared),
        "files": len(paths),
        # "Worth a look", not "drifted". The distinction is the whole design.
        "worth_a_look": not shared,
    }


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(days=days_ago)).isoformat()


def running(conn) -> list:
    """Runs that are open right now — the live fleet."""
    rows = conn.execute(
        "SELECT id, objective, task_class, repo_ref, opened_at, status, "
        "artifact_manifest FROM task_runs "
        "WHERE status IN ('opened','executing','artifact_attached') "
        "ORDER BY opened_at ASC").fetchall()
    out = []
    for r in rows:
        observed = r["task_class"] == "auto-observed"
        manifest = _loads(r["artifact_manifest"], [])
        # An observed run never had an objective, so it can never have drifted
        # from one. Computing a signal here would fabricate a contract.
        drift = ({"checkable": False, "reason": "observed run — no objective was frozen"}
                 if observed else drift_signal(r["objective"], manifest))
        out.append({
            "id": r["id"], "objective": r["objective"], "observed": observed,
            "repo": os.path.basename((r["repo_ref"] or "").partition("@")[0]),
            "status": r["status"], "opened_at": r["opened_at"],
            "files": len(manifest), "drift": drift,
        })
    return out


def spend_by_project(conn, days: int = 7) -> list:
    """Where the tokens went. Real observations only — a run whose cost was never
    captured is counted separately as 'unmeasured' rather than silently as 0,
    because a fleet that looks cheap because it was unmeasured is the worst
    possible answer to 'how is my token spending going'."""
    rows = conn.execute(
        "SELECT repo_ref, cost_observation FROM task_runs WHERE opened_at >= ?",
        (_iso(days),)).fetchall()
    agg = {}
    for r in rows:
        repo = os.path.basename((r["repo_ref"] or "").partition("@")[0]) or "unknown"
        cost = _loads(r["cost_observation"], {})
        e = agg.setdefault(repo, {"repo": repo, "tokens": 0, "runs": 0, "unmeasured": 0})
        e["runs"] += 1
        if cost.get("status") == "known" and cost.get("total_tokens"):
            e["tokens"] += int(cost["total_tokens"])
        else:
            e["unmeasured"] += 1
    return sorted(agg.values(), key=lambda e: -e["tokens"])


def efficiency(conn) -> dict:
    """Do accepted runs cost less than rejected ones?

    An open question with no published answer — the research pass found nothing
    measured on prompt efficiency beyond outcome. This is the cheapest honest
    version: mean observed tokens per outcome. It reports n every time, because
    at this sample size the number is a direction and not a finding.
    """
    out = {}
    for verdict in ("accepted", "rework", "rollback"):
        rows = conn.execute(
            "SELECT cost_observation FROM task_runs WHERE human_acceptance=?",
            (verdict,)).fetchall()
        tokens = [int(_loads(r["cost_observation"], {}).get("total_tokens") or 0)
                  for r in rows]
        measured = [t for t in tokens if t > 0]
        out[verdict] = {
            "runs": len(rows), "measured": len(measured),
            "mean_tokens": int(sum(measured) / len(measured)) if measured else None,
        }
    return out


# ------------------------------------------------------------------ rendering

def _fmt_tokens(n) -> str:
    if not n:
        return "—"
    for unit, div in (("M", 1_000_000), ("K", 1_000)):
        if n >= div:
            return f"{n / div:.1f}{unit}"
    return str(n)


def format_fleet(live: list, spend: list, unrev: list, eff: dict) -> str:
    """Zen structure: label, then the answer, then what to do. No chrome, no
    box-drawing, no colour — this is read on a phone over SSH as often as on a
    laptop, and every character of decoration is a character of reading load."""
    L = []

    L.append("RUNNING")
    if not live:
        L.append("  nothing is running.")
    for r in live:
        kind = "observed" if r["observed"] else "governed"
        L.append(f"  {r['repo']:<24} {kind:<9} {r['files']:>3} file(s)   {r['id']}")
        L.append(f"    {r['objective'][:88]}")
        d = r["drift"]
        if d.get("checkable") and d.get("worth_a_look"):
            L.append(f"    ⚠ worth a look: {d['files']} files touched, none sharing "
                     f"a word with the objective")
    L.append("")

    L.append(f"SPEND — last 7 days")
    if not spend:
        L.append("  no runs in the window.")
    for s in spend:
        note = f"   ({s['unmeasured']} unmeasured)" if s["unmeasured"] else ""
        L.append(f"  {s['repo']:<24} {_fmt_tokens(s['tokens']):>8}   "
                 f"{s['runs']} run(s){note}")
    L.append("")

    L.append("NEEDS YOU")
    if not unrev:
        L.append("  nothing ran unreviewed.")
    else:
        L.append(f"  {len(unrev)} run(s) finished without your verdict — oldest first")
        for r in unrev[:5]:
            L.append(f"  {r['id']}  {r['repo']:<20} {r['files']:>3} file(s)  "
                     f"{_fmt_tokens(r.get('tokens'))}")
        if len(unrev) > 5:
            L.append(f"  … and {len(unrev) - 5} more")
    L.append("")

    L.append("EFFICIENCY — tokens per outcome")
    any_measured = any(v["measured"] for v in eff.values())
    if not any_measured:
        L.append("  not measurable yet: no closed run has an observed cost.")
        L.append("  wire the Stop hook and this fills in on its own.")
    else:
        for verdict in ("accepted", "rework", "rollback"):
            v = eff[verdict]
            mean = _fmt_tokens(v["mean_tokens"]) if v["mean_tokens"] else "—"
            L.append(f"  {verdict:<10} {mean:>8}   "
                     f"(n={v['measured']} measured of {v['runs']})")
        L.append("  small n — read this as a direction, not a finding.")
    return "\n".join(L)
