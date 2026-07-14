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


def run_yield(conn) -> dict:
    """Slice 1.3: the verified YIELD of the current output, read from route_evidence
    (the verdicts `review --terminals` produced). verified = passed reality,
    contradicted = failed, unverified = uncheckable (excluded from the ratio).

    Honest scope: route_evidence reflects the CURRENT repo state, so this yield is
    valid for the LATEST/active run (its output IS the current state). Per-run
    historical yield needs commit-window verification (a later slice)."""
    counts = {"verified": 0, "contradicted": 0, "unverified": 0}
    for r in conn.execute(
            "SELECT verdict, COUNT(*) c FROM route_evidence GROUP BY verdict"):
        if r["verdict"] in counts:
            counts[r["verdict"]] = r["c"]
    checkable = counts["verified"] + counts["contradicted"]
    return {
        "verified": counts["verified"],
        "contradicted": counts["contradicted"],
        "uncheckable": counts["unverified"],
        "checkable": checkable,
        "verified_ratio": round(counts["verified"] / checkable, 3) if checkable else None,
    }


def score_run(run: dict, yld: dict, damage: float = 0.0) -> dict:
    """Slice 1.5: score = verified yield / cost - damage. Every term is real and
    shown on the card, nothing hidden:
      yield = count of verified deliverables (reality-passed output)
      cost  = output_Mtok * hours   (a run that is both long AND token-heavy costs more)
      score = yield / cost - damage  (verified deliverables per Mtok-hour, minus incident)
    The combination is a disclosed design choice; the inputs are not invented."""
    out_mtok = run["output_tokens"] / 1_000_000
    hours = run["duration_min"] / 60
    cost = max(round(out_mtok * hours, 3), 0.01)
    verified = yld["verified"]
    raw = round(verified / cost, 2)
    return {
        "yield_verified": verified,
        "out_mtok": round(out_mtok, 2),
        "hours": round(hours, 2),
        "cost": cost,
        "raw": raw,
        "damage": damage,
        "score": round(raw - damage, 2),
    }


def build_run_card(conn, run: dict, damage: float = 0.0) -> dict:
    """One real run card: identity + cost (from transcripts) + yield (from review
    verdicts) + score. Every field traces to a real source."""
    yld = run_yield(conn)
    sc = score_run(run, yld, damage)
    return {
        "run_id": run["run_id"], "start": run["start"], "end": run["end"],
        "duration_min": run["duration_min"], "model": run["model"],
        "session_count": run["session_count"], "output_tokens": run["output_tokens"],
        "total_tokens": run["total_tokens"], **yld, **sc,
    }


def format_run_card(card: dict) -> str:
    vr = card["verified_ratio"]
    vr_s = f"{vr}" if vr is not None else "n/a (nothing checkable)"
    dmg = f"  -  damage {card['damage']}" if card["damage"] else ""
    return "\n".join([
        "",
        f"  RUN CARD  {card['run_id']}",
        f"  {'span':14} {(card['start'] or '')[:16].replace('T',' ')} -> "
        f"{(card['end'] or '')[:16].replace('T',' ')}  ({card['duration_min']}m, "
        f"{card['session_count']} session(s))",
        f"  {'model':14} {card['model'].replace('claude-','')}",
        f"  {'cost':14} {_fmt_tok(card['output_tokens'])} output tokens "
        f"({card['out_mtok']}M) x {card['hours']}h  =  {card['cost']} Mtok-h",
        f"  {'yield':14} {card['verified']}/{card['checkable']} verified "
        f"(ratio {vr_s}; {card['uncheckable']} uncheckable, excluded)",
        f"  {'score':14} {card['yield_verified']} verified / {card['cost']} cost "
        f"= {card['raw']}{dmg}  ->  SCORE {card['score']}",
        "",
        "  (yield = review --terminals verdicts on current output; every term is real)",
        "",
    ])


def persist_run_card(conn, card: dict) -> None:
    """Slice 1.6: write a scored card to run_cards (upsert by run_id). The card is
    persisted when its run is current, so its yield is valid as-of scored_at. Over
    time this table IS the 'Latest runs' history."""
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO run_cards (run_id,start,end,duration_min,model,session_count,"
        "output_tokens,total_tokens,verified,checkable,verified_ratio,cost,damage,"
        "score,scored_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(run_id) DO UPDATE SET end=excluded.end, "
        "duration_min=excluded.duration_min, session_count=excluded.session_count, "
        "output_tokens=excluded.output_tokens, total_tokens=excluded.total_tokens, "
        "verified=excluded.verified, checkable=excluded.checkable, "
        "verified_ratio=excluded.verified_ratio, cost=excluded.cost, "
        "damage=excluded.damage, score=excluded.score, scored_at=excluded.scored_at",
        (card["run_id"], card["start"], card["end"], card["duration_min"],
         card["model"], card["session_count"], card["output_tokens"],
         card["total_tokens"], card["verified"], card["checkable"],
         card["verified_ratio"], card["cost"], card["damage"], card["score"],
         datetime.now(timezone.utc).replace(tzinfo=None).isoformat()))
    conn.commit()


def latest_run_cards(conn, limit: int = 15) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM run_cards ORDER BY start DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def format_latest(cards: list[dict]) -> str:
    if not cards:
        return ("\n  No scored runs yet. Cut one:  helicon score-runs --card --persist\n")
    out = ["", f"  LATEST RUNS — scored history ({len(cards)})", ""]
    out.append(f"  {'when':16}  {'sess':>4}  {'out':>6}  {'dur':>7}  "
               f"{'verified':>9}  {'score':>6}")
    for c in cards:
        when = (c["start"] or "")[:16].replace("T", " ")
        vr = f"{c['verified']}/{c['checkable']}" if c["checkable"] else "n/a"
        out.append(f"  {when:16}  {c['session_count']:>4}  "
                   f"{_fmt_tok(c['output_tokens']):>6}  {str(c['duration_min'])+'m':>7}  "
                   f"{vr:>9}  {c['score']:>6}")
    out.append("")
    return "\n".join(out)


def suggest_runs(conn, config=None, min_runs: int = 3) -> dict:
    """Slice 1.7: suggestions read off real history, nothing invented.
      (a) best run SHAPE: avg score by focused (<=2 sess) vs fleet (3+ sess),
          only when there are >= min_runs scored cards; else insufficient.
      (b) model/route: the top recommendation from the route read of the eval store.
      (c) next run: needs an open-next-steps source (dashboard/todo); not wired to
          one yet, so it is flagged as roadmap rather than faked."""
    from helicon.route import route
    cards = latest_run_cards(conn, limit=1000)
    shape = None
    if len(cards) >= min_runs:
        buckets: dict = {}
        for c in cards:
            if c["score"] is None:
                continue
            k = "focused (<=2 sess)" if (c["session_count"] or 0) <= 2 else "fleet (3+ sess)"
            buckets.setdefault(k, []).append(c["score"])
        shape = {k: round(sum(v) / len(v), 2) for k, v in buckets.items() if v}
    routed = route(conn, min_n=5)
    return {"scored_runs": len(cards), "min_runs": min_runs,
            "best_shape": shape, "route": routed}


def format_suggestions(s: dict) -> str:
    out = ["", "  SUGGESTED RUNS — read off your real history", ""]
    # (a) shape
    if s["best_shape"]:
        best = max(s["best_shape"], key=lambda k: s["best_shape"][k])
        out.append(f"  ▸ shape: best-scoring is {best} "
                   f"(avg scores: {s['best_shape']})")
    else:
        out.append(f"  ▸ shape: insufficient scored runs "
                   f"({s['scored_runs']}/{s['min_runs']}) to compare focused vs fleet")
    # (b) route
    picks = [r for r in s["route"]["results"] if r.get("recommendation") or r.get("lean")]
    if picks:
        r = picks[0]
        who = r.get("recommendation") or r.get("lean")
        tag = "route" if r.get("recommendation") else "lean"
        out.append(f"  ▸ model: {tag} {r['task_class']} to {who} "
                   f"(verified {r['best']['pass']}/{r['best']['n']})")
    else:
        out.append("  ▸ model: no task-class has enough verified evidence yet")
    # (c) next run
    out.append("  ▸ next run: wire a next-steps source (dashboard/todo) to rank the "
               "highest-leverage next run  [roadmap]")
    out.append("")
    return "\n".join(out)


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
