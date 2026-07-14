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
from datetime import datetime


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


def _fmt_tok(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)


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
