"""The weekly knowledge-palace read — "is my setup any good THIS WEEK".

One endpoint that answers the SHIP question in a single read: setup health,
what got over-captured, what got learned, and an honest agentic-engineering
review computed from the local transcripts. Every number carries the source
that produced it, and anything that cannot be probed is `wired: false` with the
reason — never a faked zero.

DESIGN NOTES (each one a boundary, not a preference):

  THE ROT EXAM IS NOT COMPOSED HERE. `/api/rot` already runs the R1-R12 exam,
  and its R8 replay costs ~16s. Making it part of this page would turn a "one
  read" into a 20s load, so the client fetches `/api/rot` in parallel and this
  endpoint carries only what does not exist yet. The setup-health section here
  is the fork/contradiction counts (a cheap db read), not the exam.

  ASYNC, MANDATORY. The shared sqlite connection is created on the event-loop
  thread by the app lifespan; a plain `def` endpoint runs in FastAPI's
  threadpool and raises "SQLite objects created in a thread can only be used in
  that same thread". Every router here is async for that reason.

  TRANSCRIPTS ARE READ LOCALLY AND NEVER LEAVE THE MACHINE. The serve app is
  bound to 127.0.0.1 and this response is aggregate-only: turn counts, tool
  names, and error COUNTS by tool. No raw prompt text, no tool-result text, no
  error strings (they carry file paths and content). Nothing computed here is
  written to disk — it is returned to the local browser and discarded.

  THE AUTHORSHIP GATE. Roughly half of `type: user` transcript lines are not a
  human prompt — they are tool results, meta injections, or subagent turns. A
  "human prompts" count that included them would be correct about the wrong
  object, so tool_result / isMeta / isSidechain lines are excluded from it.

  A HELD READING IS STAMPED. Like the rot exam, the result is cached briefly and
  always carries ran_at + cached, so a held number can never pass itself off as
  a live one.
"""
import glob
import os
import time
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter

from helicon.api.app import get_conn, get_config

router = APIRouter()

_TTL_S = 600  # 10 min: this is a weekly page, not a live gauge
_cache: dict = {"res": None, "mono": 0.0, "ran_at": None, "took_s": None}

# Temp / test project dirs whose transcripts are not Oscar's real work.
_EXCLUDE = ("pytest", "cvfit", "scratchpad", "coldtest", "var-folders",
            "private-tmp", "-T-", "tmp")


def _iso_week(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _parse_ts(ts: str):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------- setup health
def _setup_health(conn) -> dict:
    """Fork + contradiction counts, using the SAME WHERE the CLI uses so the
    number here always equals `helicon resolve --list --cards`."""
    def _count(kind: str) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE audit_type = ? "
            "AND human_decision IS NULL AND machine_decision IS NULL",
            (kind,)).fetchone()[0]

    forks = conn.execute(
        "SELECT finding, details FROM audit_log WHERE audit_type = 'identity' "
        "AND human_decision IS NULL AND machine_decision IS NULL "
        "ORDER BY id").fetchall()
    fork_names = []
    for finding, _details in forks:
        # "Identity fork: 'zup' is defined as ..." → zup. Name only, no content.
        name = ""
        if "'" in (finding or ""):
            name = finding.split("'", 2)[1]
        fork_names.append(name or (finding or "")[:32])

    return {
        "identity_forks": {
            "count": len(fork_names),
            "names": fork_names,
            "source": "helicon.db audit_log (audit_type=identity, unruled) "
                      "· helicon resolve --list --cards",
        },
        "contradictions": {
            "count": _count("factual"),
            "source": "helicon.db audit_log (audit_type=factual, unruled) · R1",
        },
        "log_fragments": {
            "count": _count("output"),
            "note": "read-only memory fragments — a LOG, not a human decision "
                    "(BUILD-PLAN S2). Shown for context, not for ruling.",
            "source": "helicon.db audit_log (audit_type=output, unruled)",
        },
    }


# ------------------------------------------------------------------- overboard
def _code_root() -> tuple:
    """The real code root, and an honest note about where it came from."""
    cfg = get_config() or {}
    git = (cfg.get("connectors", {}) or {}).get("git", {}) or {}
    configured = os.path.expanduser(git.get("repos_dir", "") or "")
    if configured and os.path.isdir(configured) and not any(
            m in configured for m in _EXCLUDE):
        return configured, f"config connectors.git.repos_dir ({configured})"
    fallback = os.path.expanduser("~/CODE")
    note = "~/CODE (fallback — config git root is a pytest temp path)" \
        if configured else "~/CODE (fallback — no git root configured)"
    return fallback, note


def _overboard() -> dict:
    """The git-visible over-capture: repos touched this week, one-day sprays,
    branches merged-but-undeleted, and abandoned branches. The git half needs no
    config — the repos under the code root ARE the population. The file-reading
    halves (self-catch blindness, lane churn) stay unwired without their logs."""
    from helicon.overboard import git_churn, repos_under

    root, note = _code_root()
    if not os.path.isdir(root):
        return {"wired": False, "reason": f"code root not found: {root}"}
    try:
        repos = repos_under(root)
        churn = git_churn(repos, days=7)
    except Exception as e:  # a git failure is not a reason to blank the page
        return {"wired": False, "reason": f"git scan failed: {e}"}

    merged = sum(len(r.get("merged_not_deleted", [])) for r in churn["repos"])
    abandoned = sum(len(r.get("abandoned", [])) for r in churn["repos"])
    return {
        "wired": True,
        "code_root": note,
        "repos_scanned": churn["repos_scanned"],
        "repos_touched": len(churn["touched"]),
        "one_day_repos": churn["one_day_repos"],       # AP7 spray
        "merged_not_deleted": merged,
        "abandoned_branches": abandoned,
        "window_days": churn["window_days"],
        "source": "helicon.overboard.git_churn over repos under the code root "
                  "· helicon overboard --code-root <root>",
        "not_wired": ["self-catch blindness (no catch log configured)",
                      "lane churn (no runs dir configured)"],
    }


# -------------------------------------------------------------- learning ledger
def _memory_dirs() -> list:
    return sorted(glob.glob(os.path.expanduser("~/.claude/projects/*/memory")))


def _learning_ledger() -> dict:
    """Lessons distilled in the LAST 7 DAYS = feedback_*.md files in the memory
    dir touched in the trailing week. A trailing window rather than the ISO week
    so the read is the same size whether it is opened on a Monday or a Sunday
    (an ISO-week read is near-empty on a Monday); it matches overboard's 7-day
    window. The WIRED/STAGED enforcement tiers need a catch-log path that is not
    configured, so they stay unwired."""
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - 7 * 86400
    dirs = _memory_dirs()
    fresh, total = [], 0
    for d in dirs:
        for path in glob.glob(os.path.join(d, "feedback_*.md")):
            total += 1
            # CREATED this week, not merely edited. mtime counts a file the
            # weekly compaction rewrote as "distilled this week" — the correct
            # number about the wrong object. st_birthtime is the creation time
            # (macOS); fall back to mtime where the platform lacks it.
            st = os.stat(path)
            created = getattr(st, "st_birthtime", st.st_mtime)
            if created >= cutoff:
                fresh.append(os.path.basename(path))
    return {
        "wired": bool(dirs),
        "window": "last 7 days",
        "distilled_this_week": len(fresh),
        "files": sorted(fresh),        # basenames only, no content
        "total_lessons": total,
        "source": "~/.claude/projects/*/memory/feedback_*.md (created in "
                  "trailing 7 days by st_birthtime, filenames only — read "
                  "locally)",
        "not_wired": ["enforcement tiers WIRED/STAGED/STATED "
                      "(no catch log configured for helicon.ledger)"],
    }


# ------------------------------------------------- agentic review (transcripts)
def _transcript_review() -> dict:
    """An honest week-in-review computed from the local Claude Code transcripts.
    Aggregate numbers only — nothing raw leaves this function. Window is the
    trailing 7 days (matching overboard/ledger), so the read is the same size on
    any day rather than near-empty on a Monday."""
    now = datetime.now(timezone.utc)
    cutoff_ts = now.timestamp() - 7 * 86400        # entry-level window (by ts)
    cutoff = now.timestamp() - 8 * 86400           # cheap mtime file prefilter

    root = os.path.expanduser("~/.claude/projects")
    files = []
    for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
        if any(m in path for m in _EXCLUDE):
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                continue
        except OSError:
            continue
        files.append(path)

    sessions = set()
    human_prompts = 0
    assistant_turns = 0
    tool_calls = 0
    tool_results = 0
    tool_errors = 0
    tools = Counter()
    errors_by_tool = Counter()
    repos = Counter()
    files_counted = 0

    for path in files:
        used = False
        id_to_tool = {}
        try:
            fh = open(path, encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                # The big bytes are file-history snapshots — skip before parsing.
                if line.startswith('{"type":"file-history'):
                    continue
                if '"assistant"' not in line and '"user"' not in line:
                    continue
                try:
                    import json
                    d = json.loads(line)
                except ValueError:
                    continue
                t = d.get("type")
                if t not in ("user", "assistant"):
                    continue
                ts = _parse_ts(d.get("timestamp", ""))
                if ts is not None and ts.timestamp() < cutoff_ts:
                    continue
                used = True
                sid = d.get("sessionId")
                if sid:
                    sessions.add(sid)
                cwd = d.get("cwd") or ""
                if cwd and not any(m in cwd for m in _EXCLUDE):
                    repos[os.path.basename(cwd.rstrip("/"))] += 1
                msg = d.get("message", {}) or {}
                content = msg.get("content")

                if t == "assistant":
                    assistant_turns += 1
                    if isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "tool_use":
                                tool_calls += 1
                                name = b.get("name", "?")
                                tools[name] += 1
                                if b.get("id"):
                                    id_to_tool[b["id"]] = name
                    continue

                # user line — is it a human prompt or a tool result?
                is_tool_result = isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content)
                if is_tool_result:
                    for b in content:
                        if not (isinstance(b, dict)
                                and b.get("type") == "tool_result"):
                            continue
                        tool_results += 1
                        if b.get("is_error"):
                            tool_errors += 1
                            name = id_to_tool.get(b.get("tool_use_id"), "?")
                            errors_by_tool[name] += 1
                elif not d.get("isMeta") and not d.get("isSidechain"):
                    human_prompts += 1
        if used:
            files_counted += 1

    ok = tool_results - tool_errors
    success = round(100 * ok / tool_results) if tool_results else None

    did = [
        f"{human_prompts} human prompts across {len(sessions)} sessions "
        f"and {len([r for r in repos if r])} repos this week",
        f"{tool_calls} tool calls; most-used: " +
        ", ".join(f"{n} ({c})" for n, c in tools.most_common(3)) or "—",
    ]
    worked = []
    if success is not None:
        worked.append(f"{success}% of {tool_results} tool calls succeeded")
    if repos:
        top = ", ".join(f"{r} ({c})" for r, c in repos.most_common(3))
        worked.append(f"work concentrated in: {top}")
    improve = []
    for name, c in errors_by_tool.most_common(3):
        if c >= 2:
            improve.append(f"repeated {name} errors this week ({c}×) — a tool "
                           f"failing the same way is a workflow to fix")
    if not improve and tool_errors:
        improve.append(f"{tool_errors} tool errors across the week, none "
                       f"clustered on one tool")

    return {
        "wired": True,
        "window": "last 7 days",
        "files_scanned": files_counted,
        "sessions": len(sessions),
        "human_prompts": human_prompts,
        "assistant_turns": assistant_turns,
        "tool_calls": tool_calls,
        "tool_success_pct": success,
        "tool_errors": tool_errors,
        "top_tools": [{"name": n, "count": c} for n, c in tools.most_common(8)],
        "errors_by_tool": [{"name": n, "count": c}
                           for n, c in errors_by_tool.most_common(6)],
        "repos_touched": [{"name": r, "turns": c}
                          for r, c in repos.most_common(8) if r],
        "did": did,
        "worked": worked,
        "improve": improve,
        "source": "~/.claude/projects/*/*.jsonl, trailing 7 days — computed "
                  "locally, aggregate only (authorship gate: tool-result / "
                  "meta / subagent lines excluded from prompts)",
    }


# ------------------------------------------------------------- recommendations
def _recommendations(setup: dict, over: dict, learn: dict, tx: dict) -> list:
    recs = []
    forks = setup["identity_forks"]["count"]
    contra = setup["contradictions"]["count"]
    if forks:
        recs.append({
            "text": f"Rule the {forks} identity fork(s): "
                    + ", ".join(setup["identity_forks"]["names"][:6]),
            "basis": "setup_health.identity_forks (the weekly ruling queue)"})
    if contra:
        recs.append({
            "text": f"Resolve {contra} cross-source contradiction(s) — one "
                    f"decision recorded two ways",
            "basis": "setup_health.contradictions (R1)"})
    if over.get("wired") and over.get("one_day_repos"):
        recs.append({
            "text": f"{len(over['one_day_repos'])} repo(s) touched on exactly "
                    f"one day (spray): {', '.join(over['one_day_repos'][:6])} "
                    f"— finish or bin",
            "basis": "overboard.git_churn one_day_repos (AP7)"})
    if over.get("wired") and over.get("abandoned_branches"):
        recs.append({
            "text": f"{over['abandoned_branches']} abandoned branch(es) sitting "
                    f"unmerged — pick up or delete",
            "basis": "overboard.git_churn abandoned"})
    for e in tx.get("errors_by_tool", []):
        if e["count"] >= 3:
            recs.append({
                "text": f"Repeated {e['name']} failures ({e['count']}×) — the "
                        f"same tool erroring is a workflow gap, not luck",
                "basis": "transcript_review.errors_by_tool"})
            break
    if learn.get("wired") and learn.get("distilled_this_week", 0) == 0:
        recs.append({
            "text": "No lessons distilled to memory this week — a week with "
                    "zero captured learnings is a capture gap",
            "basis": "learning_ledger.distilled_this_week"})
    if not recs:
        recs.append({"text": "Setup is clean this week: no open forks, no "
                             "contradictions, no spray.",
                     "basis": "all sections nominal"})
    return recs


def _verdict(setup: dict, tx: dict) -> str:
    forks = setup["identity_forks"]["count"]
    contra = setup["contradictions"]["count"]
    open_decisions = forks + contra
    if open_decisions == 0:
        return "Healthy — nothing open for you to rule this week."
    return (f"{open_decisions} real decision(s) waiting: {forks} identity "
            f"fork(s), {contra} contradiction(s). The rest is a log, not a queue.")


@router.get("/thisweek")
async def this_week():
    """The one-read weekly knowledge-palace payload. The rot exam is fetched by
    the client from /api/rot (already cached); everything here is the cheap,
    not-yet-existing half."""
    if _cache["res"] is not None and (time.monotonic() - _cache["mono"]) < _TTL_S:
        return {**_cache["res"], "ran_at": _cache["ran_at"],
                "took_s": _cache["took_s"], "cached": True}

    t0 = time.monotonic()
    conn = get_conn()
    setup = _setup_health(conn)
    over = _overboard()
    learn = _learning_ledger()
    tx = _transcript_review()
    res = {
        "week": _iso_week(datetime.now(timezone.utc)),
        "setup_health": setup,
        "overboard": over,
        "learning_ledger": learn,
        "transcript_review": tx,
        "recommendations": _recommendations(setup, over, learn, tx),
        "verdict": _verdict(setup, tx),
    }
    took = round(time.monotonic() - t0, 1)
    _cache.update({"res": res, "mono": time.monotonic(), "took_s": took,
                   "ran_at": datetime.now(timezone.utc)
                   .isoformat(timespec="seconds")})
    return {**res, "ran_at": _cache["ran_at"], "took_s": took, "cached": False}
