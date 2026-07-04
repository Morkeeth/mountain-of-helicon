"""Context-quality battery — named tests on what an agent retrieves.

Ported from Taste Machine's filter pattern (named test + fail_signal +
verdict). Where snapshots catch *change* (regression vs a baseline), the
battery catches *quality*: for a given task, is the context an agent would
retrieve actually good — relevant, fresh, non-contradictory, specific,
non-redundant?

Two layers, the same split Taste Machine uses:
  - deterministic checks (run_battery): freshness, relevance, redundancy,
    thinness — computed from the cubes + retrieval. No LLM, non-circular.
  - LLM-judged checks (format_battery_prompt): contradiction, grounding —
    subjective, handed to a model the way Taste Machine hands drafts to Claude.

Verdict: HEALTHY / DEGRADED / BROKEN (mirrors SHIP / REVISE / KILL).
"""
import re
import sqlite3

from helicon.snapshots import _retrieve

# Test catalogue — name / question / fail_signal, like TASTE_TESTS.
# `mode` is "auto" (deterministic here) or "llm" (needs a model).
CONTEXT_TESTS = [
    {
        "name": "Relevance", "mode": "auto",
        "question": "Do the retrieved memories actually address the task?",
        "fail_signal": "Top-K shares no terms with the task; retrieval returned noise.",
    },
    {
        "name": "Freshness", "mode": "auto",
        "question": "Is any retrieved memory stale, decayed, or killed?",
        "fail_signal": "A retrieved cube is killed or confidence has decayed near zero.",
    },
    {
        "name": "Redundancy", "mode": "auto",
        "question": "Is the same thing retrieved more than once?",
        "fail_signal": "Duplicate content_hash or near-identical titles waste the context window.",
    },
    {
        "name": "Thinness", "mode": "auto",
        "question": "Is the retrieved context substantive?",
        "fail_signal": "Cubes are tiny stubs with no specifics (no names, numbers, detail).",
    },
    {
        "name": "Expiry", "mode": "auto",
        "question": "Is any retrieved memory past its type's half-life without reinforcement?",
        "fail_signal": "A cube older than its stability window is served as current context.",
    },
    {
        "name": "Contradiction", "mode": "llm",
        "question": "Do any retrieved memories contradict each other?",
        "fail_signal": "Two cubes assert incompatible facts for the same subject.",
    },
    {
        "name": "Grounding", "mode": "llm",
        "question": "Are the retrieved claims specific and verifiable?",
        "fail_signal": "Vague platitudes instead of concrete, checkable statements.",
    },
]

_WORD = re.compile(r"[A-Za-z0-9]+")


def _terms(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "") if len(w) > 2}


def _fetch(conn: sqlite3.Connection, ids: list[str]) -> dict:
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id, title, content, content_hash, confidence, review_status, "
        f"type, created_at, last_reinforced "
        f"FROM helicon_cubes WHERE id IN ({q})", ids
    ).fetchall()
    return {r["id"]: dict(r) for r in rows}


def run_llm_tests(client, task: str, hits: list[dict], model: str = "qwen3.6-plus") -> list[dict]:
    """The subjective (llm-mode) tests, judged by Qwen. Returns [] if no client
    or the call fails — the battery then falls back to deterministic-only, never
    fabricating a verdict."""
    if client is None or not hits:
        return []
    from helicon.qwen import complete_json
    llm = [t for t in CONTEXT_TESTS if t["mode"] == "llm"]
    lines = [f"Task the agent retrieves context for:\n  {task}\n", "Retrieved memories:"]
    for i, h in enumerate(hits, 1):
        lines.append(f"  {i}. {h.get('title','')}")
    lines.append("\nRun each test on the retrieved set. Be honest; default to FAIL if unsure.")
    for t in llm:
        lines.append(f"- {t['name']}: {t['question']} (fail signal: {t['fail_signal']})")
    lines.append('\nReturn ONLY JSON: '
                 '{"Contradiction":{"status":"PASS|FAIL","reason":"..."},'
                 '"Grounding":{"status":"PASS|FAIL","reason":"..."}}')
    system = "You are a strict memory-quality auditor for an AI agent's retrieved context."
    data = complete_json(client, system, "\n".join(lines), model=model, operation="battery")
    if not isinstance(data, dict):
        return []
    out = []
    for t in llm:
        v = data.get(t["name"]) or data.get(t["name"].lower())
        if isinstance(v, dict) and v.get("status") in ("PASS", "FAIL"):
            out.append({"name": t["name"], "status": v["status"],
                        "reason": str(v.get("reason", ""))[:200],
                        "critical": False, "judged_by": "qwen"})
    return out


def run_battery(conn: sqlite3.Connection, task: str, k: int = 5, client=None,
                model: str = "qwen3.6-plus", stale_after_hours: float | None = None) -> dict:
    """Run the battery on what `task` retrieves. Deterministic tests always run;
    if a Qwen `client` is given, Contradiction/Grounding are judged live by Qwen
    and folded into the verdict (non-critical: they degrade, never break).

    Every verdict carries `last_scan` (age of the last completed ingest): a
    DEGRADED verdict is uninterpretable without knowing whether memory is stale
    or the scan is. Annotation only — it never flips the verdict."""
    hits = _retrieve(conn, task, k)
    # Ghost pass: a benchmark task matching retired memory is a regret event
    try:
        from helicon.regret import record_ghost_hits
        record_ghost_hits(conn, task, source="battery")
    except Exception:
        pass
    ids = [h["id"] for h in hits]
    cubes = _fetch(conn, ids)
    task_terms = _terms(task)
    results = []

    def add(name, ok, reason, critical=False):
        results.append({"name": name, "status": "PASS" if ok else "FAIL",
                        "reason": reason, "critical": critical})

    # Relevance (critical): at least one retrieved cube shares a task term.
    if not hits:
        add("Relevance", False, "retrieval returned nothing for the task", critical=True)
    else:
        overlaps = [len(task_terms & _terms(f"{c.get('title','')} {c.get('content','')}"))
                    for c in cubes.values()]
        shared = sum(1 for o in overlaps if o > 0)
        add("Relevance", shared > 0,
            f"{shared}/{len(hits)} retrieved cubes share terms with the task",
            critical=True)

    # Freshness (critical): no retrieved cube is killed or decayed near zero.
    bad = [c for c in cubes.values()
           if c.get("review_status") in ("killed", "superseded") or (c.get("confidence") or 1.0) < 0.10]
    add("Freshness", not bad,
        "all retrieved cubes are live" if not bad
        else f"{len(bad)} retrieved cube(s) killed/decayed: {[c['title'][:40] for c in bad]}",
        critical=True)

    # Redundancy: no duplicate content_hash or identical titles in top-K.
    hashes = [c.get("content_hash") for c in cubes.values() if c.get("content_hash")]
    titles = [(c.get("title") or "").strip().lower() for c in cubes.values()]
    dup = len(hashes) != len(set(hashes)) or len(titles) != len(set(titles))
    add("Redundancy", not dup,
        "no duplicates in top-K" if not dup else "duplicate content/title in top-K")

    # Thinness: flag only genuine stubs. Section-level rules can be terse (a dev
    # command is short but useful), so this fails only when context is mostly
    # empty — >half the retrieved cubes under 40 chars of content.
    if cubes:
        stubs = sum(1 for c in cubes.values() if len(c.get("content") or "") < 40)
        add("Thinness", stubs <= len(cubes) // 2,
            f"{stubs}/{len(cubes)} retrieved cubes are stubs (<40 chars)")
    else:
        add("Thinness", False, "no cubes to measure")

    # Expiry: a cube older than its type's half-life, served without any
    # reinforcement since, is suspect context even if nobody killed it yet.
    # (Benchmark incident 3: a 6.9d-old execution plan — dashboard η=7d — was
    # reused verbatim and rebuilt yesterday's priorities.) Non-critical:
    # expired context degrades, it doesn't break.
    from datetime import datetime as _dt
    from helicon.forgetting import DEFAULT_STABILITY
    expired = []
    now_dt = _dt.utcnow()
    for c in cubes.values():
        eta = DEFAULT_STABILITY.get(c.get("type"))
        if not eta:
            continue
        anchor = c.get("last_reinforced") or c.get("created_at") or ""
        try:
            age = (now_dt - _dt.fromisoformat(anchor.replace("Z", ""))).total_seconds() / 86400
        except ValueError:
            continue
        if age > eta:
            expired.append(f"{(c.get('title') or '')[:40]} ({age:.0f}d > {eta:.0f}d)")
    add("Expiry", not expired,
        "no retrieved cube is past its half-life" if not expired
        else f"{len(expired)} past half-life: {expired[:3]}")

    # Tokens-per-query (BEAM-style): what this retrieval costs in context budget.
    # Accuracy without a token price is a half-finished score.
    context_tokens = sum(
        len(f"{c.get('title','')} {c.get('content','')}") for c in cubes.values()
    ) // 4

    # Qwen-judged tests (Contradiction/Grounding), folded in if a client is given.
    llm_results = run_llm_tests(client, task, hits, model=model)
    results.extend(llm_results)

    fails = [r for r in results if r["status"] == "FAIL"]
    crit_fail = any(r["critical"] for r in fails)
    verdict = "BROKEN" if crit_fail else ("DEGRADED" if fails else "HEALTHY")

    from helicon.db import last_scan_info
    scan = last_scan_info(conn)
    last_scan = {
        "completed_at": scan["completed_at"] if scan else None,
        "hours_ago": scan["hours_ago"] if scan else None,
        "stale_after_hours": stale_after_hours,
        "stale": scan is None or (stale_after_hours is not None
                                  and scan["hours_ago"] > stale_after_hours),
    }

    return {
        "task": task, "top_k": k, "verdict": verdict,
        "results": results,
        "llm_ran": bool(llm_results),
        "llm_tests": [t["name"] for t in CONTEXT_TESTS if t["mode"] == "llm"],
        "retrieved": [h["title"] for h in hits],
        "context_tokens": context_tokens,
        "last_scan": last_scan,
    }


def format_battery_prompt(task: str, hits: list[dict]) -> str:
    """Prompt for the subjective (llm-mode) tests, à la Taste Machine's filter."""
    lines = [f"Task the agent is retrieving context for:\n  {task}\n",
             "Retrieved memories:"]
    for i, h in enumerate(hits, 1):
        lines.append(f"  {i}. {h.get('title','')}")
    lines.append("\nRun each test on the retrieved set. Be honest.\n")
    for i, t in enumerate([t for t in CONTEXT_TESTS if t["mode"] == "llm"], 1):
        lines.append(f"{i}. {t['name'].upper()}: {t['question']}")
        lines.append(f"   Fail signal: {t['fail_signal']}")
    lines.append("\nFor each: PASS or FAIL with a one-line reason.")
    lines.append("Final verdict: HEALTHY / DEGRADED / BROKEN")
    return "\n".join(lines)


def get_test_names() -> list[str]:
    return [t["name"] for t in CONTEXT_TESTS]
