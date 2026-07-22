"""Auto-governance (V2.4) — every session becomes a reviewable run, unasked.

The problem this exists for, in the operator's words: *"whenever I use an agent
full out, I feel like I lost things because I didn't review it."*

That is not anxiety, it is an accurate description of a missing surface.
Governance you have to REMEMBER is not governance: `helicon run open` only ever
covered the runs he thought to type a command for, which is why five terminals
and four autonomous blog posts have no provenance. So the harness opens the run
instead of the human, via hooks (`SessionStart` / `InstructionsLoaded` / `Stop`).

THE HONESTY LINE, and the reason this module is not just `run open` on a timer:

An auto-opened run has NO frozen acceptance contract. Nobody declared what
"accepted" would mean before the work, because nobody was asked. The product's
central claim — "'verified' can never be hindsight" — holds ONLY for runs a
human opened deliberately. So auto-runs are marked `auto-observed` and carry an
acceptance sentinel that says exactly that, everywhere it is displayed.

  governed run  = objective + acceptance frozen by a human BEFORE work
  observed run  = the ledger caught it; nothing was promised in advance

Conflating those two would make the ledger lie about the one thing it exists to
be trusted on. An observed run therefore NEVER promotes its prompt to the
reusable library — promotion is gated on an accepted outcome against a frozen
contract, and an observed run has no contract to have met.

What the operator gets instead is the thing he actually asked for: a queue of
what ran while he was not watching, with the context it loaded, what it changed,
and what it cost — so "did I lose something?" is answerable rather than felt.
"""
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone

from helicon import taskrun
from helicon.cockpit import _is_private, _safe_repo_root

# Said in full wherever an observed run is rendered. Not a label — a sentence,
# because a label gets skimmed and this is the distinction that matters.
NOT_FROZEN = ("(auto-observed — no acceptance was frozen before this work, "
              "so any 'verified' here is hindsight)")

OBSERVED_CLASS = "auto-observed"


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _git(repo, *args) -> str:
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                              text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def _find_open(conn, session_id: str):
    """The observed run for this session, if one is still open. Keyed on the
    harness's own session id so two terminals in the SAME repo never collide —
    repo alone was not a unique key and would have merged parallel sessions,
    which is precisely the fleet case this is built for."""
    return conn.execute(
        "SELECT id FROM task_runs WHERE task_class=? AND status IN "
        "('opened','executing','artifact_attached') AND objective LIKE ? "
        "ORDER BY opened_at DESC LIMIT 1",
        (OBSERVED_CLASS, f"%[{session_id}]")).fetchone()


def session_start(conn, cwd: str, session_id: str, source: str = "") -> dict:
    """A terminal opened. Open an OBSERVED run against the current commit.

    Privacy-gated identically to every other capture path: a repo outside the
    safe set gets nothing at all, not a redacted row.
    """
    repo = _safe_repo_root(cwd)
    if repo is None or _is_private(cwd):
        return {"ok": False, "reason": "repo not in the safe set"}
    if _find_open(conn, session_id):
        return {"ok": False, "reason": "already observing this session"}

    commit = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    # The objective is unknown at SessionStart — the human has not typed a
    # prompt yet. Naming it after the repo is a placeholder, and it is labelled
    # as one rather than dressed up as an objective the operator never set.
    objective = f"unnamed session in {os.path.basename(repo)} [{session_id}]"
    rid = taskrun.open_run(
        conn, objective, NOT_FROZEN, task_class=OBSERVED_CLASS,
        harness="claude-code", repo_ref=f"{repo}@{commit}")
    taskrun.record_event(conn, rid, "opened", actor="helicon",
                         detail=json.dumps({"auto": True, "branch": branch,
                                            "session": session_id}))
    _record_no_packet(conn, rid)
    return {"ok": True, "task_run_id": rid, "repo": repo, "commit": commit}


def _record_no_packet(conn, task_run_id: str) -> None:
    """An observed run gets an explicitly EMPTY context packet, and that is the
    truthful record — not a lifecycle workaround.

    `build_packet` would retrieve from Helicon's store and file the result as
    "the context this run used". For an observed run that would be fiction:
    Helicon supplied nothing. The harness assembled the context, and the only
    honest account of it is the `context` event that `InstructionsLoaded` writes
    (itself partial — CLAUDE.md and rules files only).

    Filing zero here keeps the lifecycle honest in both directions: the run can
    attach its artifact, and no surface can later claim Helicon governed a
    context it never chose.
    """
    conn.execute(
        "INSERT INTO context_packets (id, task_run_id, created_at, policy_version, "
        "classification_policy_version, packet_hash, token_estimate, excluded_relevant) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ("cp_" + uuid.uuid4().hex[:12], task_run_id, _now(), "observed-v1",
         "observed-v1", "", 0,
         json.dumps([{"category": "not-applicable",
                      "reason": "observed run — Helicon supplied no context; the "
                                "harness did. See the run's 'context' event."}])))
    conn.execute("UPDATE task_runs SET status='executing' WHERE id=? AND status='opened'",
                 (task_run_id,))
    conn.commit()


def instructions_loaded(conn, session_id: str, paths: list) -> dict:
    """`InstructionsLoaded` fired: record WHICH context files entered the run.

    This is the provenance edge the harness gives us and nothing else does. Its
    documented limit matters and is recorded with the event rather than glossed:
    it covers CLAUDE.md and rules files ONLY — not retrieved memory, not MCP tool
    payloads, not file reads, not fetched web content. So this answers "which
    instructions were loaded", never the full "what context produced this".
    """
    row = _find_open(conn, session_id)
    if row is None:
        return {"ok": False, "reason": "no observed run for this session"}
    taskrun.record_event(
        conn, row["id"], "context", actor="harness",
        detail=json.dumps({"instruction_files": paths, "count": len(paths),
                           "covers": "CLAUDE.md/rules only — not memory, MCP, "
                                     "file reads or web content"}))
    return {"ok": True, "task_run_id": row["id"], "files": len(paths)}


def session_stop(conn, session_id: str, transcript_path: str = "") -> dict:
    """The terminal finished. Attach what changed and what it really cost, then
    leave it PENDING a human verdict — never auto-accept.

    Auto-accepting would recreate the exact failure this module exists to fix:
    work that completed without anyone looking at it, now with a machine's
    approval stamped on top. The run lands in the queue and stays there.
    """
    row = _find_open(conn, session_id)
    if row is None:
        return {"ok": False, "reason": "no observed run for this session"}
    rid = row["id"]
    run = conn.execute("SELECT repo_ref FROM task_runs WHERE id=?", (rid,)).fetchone()
    repo, _, base = (run["repo_ref"] or "").partition("@")

    manifest = []
    for line in _git(repo, "diff", "--name-only", f"{base}..HEAD").splitlines():
        p = line.strip()
        if p and not _is_private(os.path.join(repo, p)):
            manifest.append({"path": p, "state": "committed", "observed_at": _now()})
    for line in _git(repo, "status", "--porcelain").splitlines():
        p = line[3:].strip()
        if p and not _is_private(os.path.join(repo, p)):
            manifest.append({"path": p, "state": "uncommitted", "observed_at": _now()})

    # Real cost, from the transcript the harness wrote. Step 3 of the loop was
    # ABSENT because the forward path hardcoded {"status": "unknown"} while a
    # working parser sat unused in runs.py. A missing field stays 'unknown';
    # it is never rendered as 0, which would read as "this run was free".
    cost = {"status": "unknown"}
    if transcript_path and os.path.exists(transcript_path):
        from helicon.runs import parse_session_cost
        parsed = parse_session_cost(transcript_path) or {}
        if parsed.get("total_tokens"):
            cost = {"status": "known", "total_tokens": parsed.get("total_tokens"),
                    "output_tokens": parsed.get("output_tokens"),
                    "model": parsed.get("model"),
                    "duration_min": parsed.get("duration_min")}

    taskrun.attach_artifact(conn, rid, manifest, cost_observation=cost)
    taskrun.record_event(conn, rid, "artifact", actor="helicon",
                         detail=json.dumps({"files": len(manifest),
                                            "cost_status": cost["status"]}))
    return {"ok": True, "task_run_id": rid, "files": len(manifest), "cost": cost}


def unreviewed(conn, limit: int = 50) -> list:
    """What ran while you were not watching, and still has no verdict.

    The answer to "did I lose something?". Ordered oldest first: the run you
    have been ignoring longest is the one most likely to hold the thing you lost.
    """
    rows = conn.execute(
        "SELECT id, objective, task_class, repo_ref, opened_at, status, "
        "artifact_manifest, cost_observation FROM task_runs "
        "WHERE human_acceptance='pending' ORDER BY opened_at ASC LIMIT ?",
        (limit,)).fetchall()
    out = []
    for r in rows:
        try:
            files = len(json.loads(r["artifact_manifest"] or "[]"))
        except Exception:
            files = 0
        try:
            cost = json.loads(r["cost_observation"] or "{}")
        except Exception:
            cost = {}
        out.append({
            "id": r["id"], "objective": r["objective"], "status": r["status"],
            "observed": r["task_class"] == OBSERVED_CLASS,
            "repo": os.path.basename((r["repo_ref"] or "").partition("@")[0]),
            "opened_at": r["opened_at"], "files": files,
            "tokens": cost.get("total_tokens"), "cost_status": cost.get("status", "unknown"),
        })
    return out


def format_unreviewed(rows: list) -> str:
    if not rows:
        return "  nothing ran unreviewed. every run has your verdict."
    lines = [f"  {len(rows)} run(s) finished without your verdict — oldest first", ""]
    for r in rows:
        kind = "observed" if r["observed"] else "governed"
        tok = f"{r['tokens']:,} tok" if r.get("tokens") else "cost unknown"
        lines.append(f"  {r['id']}  [{kind}]  {r['repo']}  ·  {r['files']} file(s)  ·  {tok}")
        lines.append(f"     {r['objective'][:96]}")
    lines.append("")
    lines.append("  rule one:  helicon run close --id <id> --accept | --rework | --reject")
    if any(r["observed"] for r in rows):
        lines.append("  note:      'observed' runs had NO acceptance frozen before the work.")
        lines.append("             Judge the artifact itself; there is no contract to check it against.")
    return "\n".join(lines)
