"""helicon runs - score whole RUNS, not just claims.

`review --terminals` verifies a terminal's output; a RUN is that one level up and
made cost-aware. A run has a real yield (verified output) and a real cost (time +
tokens), so it can be scored instead of vibed:

    score = verified yield / cost - damage

Every term traces to a real source (transcript usage, review verdicts, incident
flags); nothing is invented. This module is being built in slices:

  1.1 cost side  - parse Claude Code transcripts into per-session cost (THIS).
  1.2 run identity, 1.3 yield join, 1.4 damage, 1.5 score, 1.6 render, ...

Slice 1.1: the cost table only. Reads ~/.claude/projects/<proj>/*.jsonl, one file
per session (filename = sessionId), and sums the `usage` each assistant message
carries plus the wall-clock span from the line timestamps.
"""
import glob
import json
import os
from datetime import datetime, timedelta


def _parse_ts(s: str):
    """Transcript timestamps are ISO-8601 with a trailing Z. Return a naive
    datetime (UTC) or None."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_session_cost(path: str) -> dict | None:
    """One transcript file -> one session cost record. Sums the top-level usage
    fields per assistant message (NOT the `iterations` sub-list, which repeats
    them and would double-count). Duration is last minus first line timestamp.
    Returns None for a file with no usable assistant/usage lines."""
    out_tok = in_tok = cache_create = cache_read = 0
    assistant_msgs = 0
    models: dict[str, int] = {}
    first_ts = last_ts = None
    session_id = os.path.splitext(os.path.basename(path))[0]

    try:
        fh = open(path, errors="ignore")
    except OSError:
        return None
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(o.get("timestamp"))
            if ts:
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts
            if o.get("sessionId"):
                session_id = o["sessionId"]
            msg = o.get("message")
            if o.get("type") != "assistant" or not isinstance(msg, dict):
                continue
            if msg.get("model"):
                models[msg["model"]] = models.get(msg["model"], 0) + 1
            u = msg.get("usage")
            if isinstance(u, dict):
                assistant_msgs += 1
                out_tok += u.get("output_tokens", 0) or 0
                in_tok += u.get("input_tokens", 0) or 0
                cache_create += u.get("cache_creation_input_tokens", 0) or 0
                cache_read += u.get("cache_read_input_tokens", 0) or 0

    if assistant_msgs == 0:
        return None
    duration_min = round((last_ts - first_ts).total_seconds() / 60, 1) \
        if (first_ts and last_ts) else 0.0
    total_tokens = in_tok + cache_create + cache_read + out_tok
    return {
        "session_id": session_id,
        "path": path,
        "model": max(models, key=lambda k: models[k]) if models else "unknown",
        "models": models,
        "assistant_msgs": assistant_msgs,
        "first_ts": first_ts.isoformat() if first_ts else None,
        "last_ts": last_ts.isoformat() if last_ts else None,
        "duration_min": duration_min,
        "output_tokens": out_tok,
        "input_tokens": in_tok,
        "cache_creation_tokens": cache_create,
        "cache_read_tokens": cache_read,
        "total_tokens": total_tokens,
    }


def scan_session_costs(jsonl_dir: str, since: str | None = None) -> list[dict]:
    """Every transcript in a project dir -> cost records, newest activity first.
    `since` (ISO date/datetime) keeps only sessions whose last line is at/after it."""
    jsonl_dir = os.path.expanduser(jsonl_dir)
    recs = []
    for path in glob.glob(os.path.join(jsonl_dir, "*.jsonl")):
        rec = parse_session_cost(path)
        if rec is None:
            continue
        if since and (rec["last_ts"] or "") < since:
            continue
        recs.append(rec)
    recs.sort(key=lambda r: r["last_ts"] or "", reverse=True)
    return recs


def group_runs(recs: list[dict], gap_min: int = 300) -> list[dict]:
    """Slice 1.2: cluster per-session cost records into RUNS. A run is a burst of
    work Oscar kicked off: sessions whose STARTS fall within `gap_min` of each
    other (parallel terminals start together; the next run begins after a quiet
    gap). Clustering on start time, not activity span, so a long session left
    open cannot bridge two days into one blob.

    Honest temporal grouping only, from the real first_ts of each session; no
    invented boundaries. `gap_min` (default 5h) is the tuning knob; closeout-based
    linkage can refine it later.
    """
    placed, loose = [], []
    for r in recs:
        f = _parse_ts(r.get("first_ts"))
        if f:
            placed.append((f, r))
        else:
            loose.append(r)                     # no timestamps: its own singleton run
    placed.sort(key=lambda t: t[0])

    runs = []
    cur = None
    prev_start = None
    for f, r in placed:
        if cur and prev_start and f <= prev_start + timedelta(minutes=gap_min):
            cur["_members"].append(r)
            l = _parse_ts(r.get("last_ts"))
            if l and l > cur["_end"]:
                cur["_end"] = l
        else:
            if cur:
                runs.append(_finalize_run(cur))
            cur = {"_start": f, "_end": _parse_ts(r.get("last_ts")) or f, "_members": [r]}
        prev_start = f
    if cur:
        runs.append(_finalize_run(cur))
    for r in loose:
        runs.append(_finalize_run({"_start": None, "_end": None, "_members": [r]}))

    runs.sort(key=lambda x: x["end"] or "", reverse=True)
    return runs


def _finalize_run(cur: dict) -> dict:
    members = cur["_members"]
    models: dict[str, int] = {}
    out_tok = total_tok = 0
    for m in members:
        for mdl, c in (m.get("models") or {}).items():
            models[mdl] = models.get(mdl, 0) + c
        out_tok += m.get("output_tokens", 0)
        total_tok += m.get("total_tokens", 0)
    start, end = cur["_start"], cur["_end"]
    dur = round((end - start).total_seconds() / 60, 1) if (start and end) else 0.0
    start_iso = start.isoformat() if start else (members[0].get("first_ts") or "")
    run_id = "run-" + (start_iso[:16] if start_iso else members[0]["session_id"][:8])
    return {
        "run_id": run_id,
        "start": start.isoformat() if start else members[0].get("first_ts"),
        "end": end.isoformat() if end else members[0].get("last_ts"),
        "duration_min": dur,
        "session_ids": [m["session_id"] for m in members],
        "session_count": len(members),
        "model": max(models, key=lambda k: models[k]) if models else "unknown",
        "models": models,
        "output_tokens": out_tok,
        "total_tokens": total_tok,
    }


def _fmt_tok(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)


def format_runs(runs: list[dict], limit: int = 15) -> str:
    if not runs:
        return "\n  No runs found.\n"
    out = ["", f"  RUNS — start-clustered (newest first, top {min(limit, len(runs))} "
           f"of {len(runs)})", ""]
    out.append(f"  {'run':18}  {'span':16}  {'dur':>8}  {'sess':>4}  "
               f"{'out':>6}  {'total':>7}  model")
    for r in runs[:limit]:
        span = (r["start"] or "")[:16].replace("T", " ")
        model = r["model"].replace("claude-", "")
        out.append(f"  {r['run_id'][4:]:18}  {span:16}  "
                   f"{str(r['duration_min'])+'m':>8}  {r['session_count']:>4}  "
                   f"{_fmt_tok(r['output_tokens']):>6}  {_fmt_tok(r['total_tokens']):>7}  {model}")
    out.append("")
    return "\n".join(out)


def format_session_costs(recs: list[dict], limit: int = 20) -> str:
    if not recs:
        return "\n  No Claude Code transcripts found to cost.\n"
    out = ["", f"  RUN COST — per session (newest first, top {min(limit, len(recs))} "
           f"of {len(recs)})", ""]
    out.append(f"  {'session':10}  {'model':16}  {'when':16}  {'dur':>7}  "
               f"{'out':>6}  {'total':>7}  msgs")
    tot_out = tot_all = 0
    for r in recs[:limit]:
        tot_out += r["output_tokens"]
        tot_all += r["total_tokens"]
        when = (r["last_ts"] or "")[:16].replace("T", " ")
        model = r["model"].replace("claude-", "")
        out.append(f"  {r['session_id'][:8]:10}  {model:16}  {when:16}  "
                   f"{str(r['duration_min'])+'m':>7}  {_fmt_tok(r['output_tokens']):>6}  "
                   f"{_fmt_tok(r['total_tokens']):>7}  {r['assistant_msgs']}")
    out.append("")
    out.append(f"  shown: {_fmt_tok(tot_out)} output · {_fmt_tok(tot_all)} total tokens")
    out.append("")
    return "\n".join(out)
