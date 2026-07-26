"""Real Run Capture — turn a real Claude Code session into a governed Run.

Discovers actual local sessions dynamically (no hardcoded project list),
captures their VERBATIM prompt chain + real execution facts (model, harness,
tokens, timing, artifacts, repo/branch/commit) without hand-copying, and wires
the governed lifecycle (open with acceptance → packet → artifact → human
accept/rework/reject → receipt → outcome-gated prompt promotion).

Honesty rules:
- A historical transcript had no Helicon-frozen acceptance contract → provenance
  'imported'; its objective/acceptance are NOT reconstructed from prose.
- A missing provider field (cost USD, reasoning tokens) is 'unknown', never 0.
- Privacy: default-deny via context_policy + the cockpit safe-root allowlist.
  Trading/wallet/treasury/journal sessions are never captured.
- Reuses runs.parse_session_cost (never a competing cost system).
"""
import glob
import hashlib
import json
import os
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone

from helicon.runs import parse_session_cost
from helicon.context_policy import classify, eligible_for_local_packet
from helicon.cockpit import _is_private, _safe_repo_root

PROJECTS = os.path.expanduser("~/.claude/projects")


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _git(repo, *args):
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                              text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def _session_meta(path: str) -> dict | None:
    """cwd / branch / session_id / version / first_ts from the transcript's own
    entries (.cwd and .gitBranch are authoritative, not the dir name)."""
    cwd = branch = sid = version = first_ts = None
    try:
        with open(path, errors="ignore") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                cwd = cwd or o.get("cwd")
                branch = branch or o.get("gitBranch")
                sid = sid or o.get("sessionId")
                version = version or o.get("version")
                first_ts = first_ts or o.get("timestamp")
                if cwd and branch is not None and sid:
                    break
    except OSError:
        return None
    if not cwd:
        return None
    return {"cwd": cwd, "branch": branch, "session_id": sid or os.path.basename(path)[:-6],
            "version": version, "first_ts": first_ts, "path": path}


def _session_is_safe(cwd: str, path: str, branch: str | None) -> bool:
    """Default-deny: the session's repo must be an allowed ~/CODE safe root AND
    classify non-private (context_policy) on its cwd/branch."""
    if _safe_repo_root(cwd) is None or _is_private(cwd):
        return False
    sens = classify("claude-code", cwd, path, f"{cwd} {branch or ''}")
    return eligible_for_local_packet(sens)


def discover_sessions(safe_only: bool = True, limit: int | None = None) -> list[dict]:
    """Every real local Claude Code session (privacy-gated), with real token/
    model/timing facts. Walks projects/*/ (the flat glob caveat: transcripts
    live one level down)."""
    out = []
    if not os.path.isdir(PROJECTS):
        return out
    for proj in sorted(os.listdir(PROJECTS)):
        pdir = os.path.join(PROJECTS, proj)
        if not os.path.isdir(pdir):
            continue
        for f in sorted(glob.glob(os.path.join(pdir, "*.jsonl"))):
            meta = _session_meta(f)
            if meta is None:
                continue
            if safe_only and not _session_is_safe(meta["cwd"], f, meta["branch"]):
                continue
            cost = parse_session_cost(f) or {}
            out.append({
                "session_id": meta["session_id"], "path": f, "project_dir": proj,
                "repo": meta["cwd"], "branch": meta["branch"],
                "harness": f"claude-code{(' ' + meta['version']) if meta.get('version') else ''}",
                "model": cost.get("model"), "models": cost.get("models"),
                "first_ts": cost.get("first_ts") or meta.get("first_ts"),
                "last_ts": cost.get("last_ts"),
                "duration_min": cost.get("duration_min"),
                "total_tokens": cost.get("total_tokens"),
                "assistant_msgs": cost.get("assistant_msgs"),
            })
            if limit and len(out) >= limit:
                return out
    # newest first
    out.sort(key=lambda s: s.get("last_ts") or "", reverse=True)
    return out


def read_prompts(path: str, max_prompts: int = 60) -> list[dict]:
    """Verbatim user prompts in order. Only real prompts (string content); tool-
    result entries (list content) are skipped."""
    prompts = []
    try:
        with open(path, errors="ignore") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") != "user":
                    continue
                msg = o.get("message") or {}
                if msg.get("role") != "user":
                    continue
                content = msg.get("content")
                if not isinstance(content, str) or not content.strip():
                    continue
                prompts.append({"ts": o.get("timestamp"), "text": content,
                                "source": o.get("promptSource", "")})
                if len(prompts) >= max_prompts:
                    break
    except OSError:
        pass
    return prompts


def _hash_file(p: str) -> str | None:
    try:
        with open(p, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:16]
    except Exception:
        return None


def _artifacts(repo: str, limit: int = 40) -> list[dict]:
    """Changed files with content hashes + observation time. For an imported
    (historical) session this is the repo state observed AT CAPTURE TIME, not a
    reconstruction of what existed at session end — labelled accordingly."""
    seen, out = set(), []
    for line in _git(repo, "status", "--porcelain").splitlines():
        p = line[3:].strip()
        if not p or p in seen:
            continue
        full = os.path.join(repo, p)
        if os.path.isfile(full) and not _is_private(full):
            out.append({"path": p, "content_hash": _hash_file(full),
                        "observed_at": _now(), "state": "uncommitted"})
            seen.add(p)
        if len(out) >= limit:
            # Say so. A silently capped list reads downstream as "these are all
            # the files", which made the fleet drift signal fire on a run that
            # had not drifted.
            out.append({"path": "", "state": "truncated", "observed_at": _now()})
            return out
    for p in _git(repo, "show", "--name-only", "--pretty=format:", "HEAD").splitlines():
        p = p.strip()
        if not p or p in seen:
            continue
        full = os.path.join(repo, p)
        out.append({"path": p, "content_hash": _hash_file(full) if os.path.isfile(full) else None,
                    "observed_at": _now(), "state": "last-commit"})
        seen.add(p)
        if len(out) >= limit:
            out.append({"path": "", "state": "truncated", "observed_at": _now()})
            break
    return out


def capture_session(conn, path: str, provenance: str = "imported") -> dict:
    """Persist one real session as a RunRecord (run_captures). No hand-copy; all
    fields are read from the transcript + git."""
    meta = _session_meta(path)
    if meta is None:
        return {"ok": False, "error": "unreadable session"}
    if not _session_is_safe(meta["cwd"], path, meta["branch"]):
        return {"ok": False, "error": "session repo is not a safe local project"}
    repo = meta["cwd"]
    cost = parse_session_cost(path) or {}
    prompts = read_prompts(path)
    tokens = {"input": cost.get("input_tokens"), "output": cost.get("output_tokens"),
              "cache_read": cost.get("cache_read_tokens"),
              "cache_creation": cost.get("cache_creation_tokens"),
              "total": cost.get("total_tokens")}
    cid = "rc_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO run_captures (id, task_run_id, provenance, session_ids, repo, "
        "branch, worktree, start_commit, prompt_chain, prompt_count, model, models, "
        "harness, tokens, cost_status, first_ts, last_ts, duration_min, "
        "artifact_manifest, captured_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, None, provenance, json.dumps([meta["session_id"]]), repo,
         meta["branch"], repo, _git(repo, "rev-parse", "HEAD"),
         json.dumps(prompts), len(prompts), cost.get("model"),
         json.dumps(cost.get("models") or {}),
         f"claude-code{(' ' + meta['version']) if meta.get('version') else ''}",
         json.dumps(tokens), "unknown",  # no cost USD in Claude Code transcripts
         cost.get("first_ts"), cost.get("last_ts"), cost.get("duration_min"),
         json.dumps(_artifacts(repo)), _now()))
    conn.commit()
    return {"ok": True, "capture_id": cid, "repo": repo, "branch": meta["branch"],
            "prompts": len(prompts), "total_tokens": tokens["total"],
            "provenance": provenance}


def _capture_row(conn, capture_id):
    return conn.execute("SELECT * FROM run_captures WHERE id=?", (capture_id,)).fetchone()


def list_captures(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM run_captures ORDER BY captured_at DESC").fetchall()
    return [dict(r) for r in rows]


def govern_from_capture(conn, capture_id, objective, acceptance) -> dict:
    """Wrap a captured session in the governed lifecycle: open (objective +
    acceptance frozen NOW — honestly after the fact for an imported session) →
    packet → attach the real captured artifact → link. Human accept/reject is a
    separate step (accept_run)."""
    from helicon import taskrun
    cap = _capture_row(conn, capture_id)
    if cap is None:
        return {"ok": False, "error": f"no capture {capture_id}"}
    try:
        rid = taskrun.open_run(
            conn, objective, acceptance, model=cap["model"] or "",
            harness=cap["harness"] or "claude-code",
            repo_ref=f"{cap['repo']}@{cap['start_commit']}")
        taskrun.record_event(conn, rid, "opened", actor="human", detail=objective)
        taskrun.build_packet(conn, rid, query=objective[:40])
        taskrun.record_event(conn, rid, "packet", actor="helicon")
        manifest = json.loads(cap["artifact_manifest"] or "[]")
        taskrun.attach_artifact(
            conn, rid, manifest,
            cost_observation={"status": cap["cost_status"],
                              "tokens": json.loads(cap["tokens"] or "{}")})
        taskrun.record_event(conn, rid, "artifact", actor="helicon",
                             detail=f"{len(manifest)} artifact(s) from capture {capture_id}")
    except taskrun.TaskRunError as e:
        return {"ok": False, "error": str(e)}
    # Linking a historical capture to a TaskRun does not move its acceptance
    # contract back in time. Preserve `imported` so the UI cannot present a
    # retrospective wrapper as work governed before execution.
    conn.execute("UPDATE run_captures SET task_run_id=? WHERE id=?",
                 (rid, capture_id))
    conn.commit()
    return {"ok": True, "task_run_id": rid, "capture_id": capture_id}


def hook_deliver(conn, cwd, session="") -> str | None:
    """The delivery edge, made real (closes the Codex P0-3 gap honestly). A
    Claude Code UserPromptSubmit hook calls this: it returns the approved
    output-review rulings as text that the harness injects into a LIVE session,
    and records a 'delivered' event — so delivery is PROVEN (the harness received
    it), not asserted from a DB write. Privacy-gated: a non-safe repo gets
    nothing. Still not 'obeyed' — only the run's output shows that."""
    repo = _safe_repo_root(cwd)
    if repo is None:
        return None
    rows = conn.execute(
        "SELECT id, content FROM helicon_cubes WHERE source='output-review' "
        "AND review_status='approved' ORDER BY created_at DESC LIMIT 20").fetchall()

    # A deliberate forward-governed run has exactly one open packet for this
    # repo. Ambiguity fails closed: two open runs means Helicon cannot know which
    # packet belongs to this session, so it delivers neither rather than guessing.
    forward = conn.execute(
        "SELECT id FROM task_runs WHERE status='executing' "
        "AND task_class!='auto-observed' AND human_acceptance='pending' "
        "AND repo_ref LIKE ? ORDER BY opened_at DESC",
        (f"{repo}@%",),
    ).fetchall()
    packet = None
    if len(forward) == 1:
        from helicon import taskrun
        try:
            candidate = taskrun.render_packet(conn, forward[0]["id"])
            if candidate["items"]:
                packet = candidate
        except taskrun.TaskRunError:
            packet = None

    parts = []
    if packet:
        parts.append(packet["text"])
    if rows:
        parts.append(
            "## Helicon — rulings to obey before you write (delivered live)\n"
            + "\n".join(f"- {r['content']}" for r in rows)
        )
    if not parts:
        return None
    ctx = "\n\n".join(parts)

    task_run_id = f"hook:{session}"[:40]
    if packet:
        task_run_id = forward[0]["id"]
    elif session:
        try:
            from helicon.autogov import _find_open
            observed = _find_open(conn, session)
            if observed:
                task_run_id = observed["id"]
        except (ImportError, sqlite3.Error):
            pass
    now = _now()
    conn.executemany(
        "INSERT INTO run_events (task_run_id, ts, kind, actor, detail) "
        "VALUES (?,?,?,?,?)",
        [(task_run_id, now, "delivered", "helicon",
          json.dumps({"repo": os.path.basename(cwd), "cube_id": r["id"],
                      "session": session, "bytes": len(r["content"])}))
         for r in rows],
    )
    if packet:
        conn.execute(
            "INSERT INTO run_events (task_run_id, ts, kind, actor, detail) "
            "VALUES (?,?,?,?,?)",
            (task_run_id, now, "context_delivered", "helicon",
             json.dumps({"repo": os.path.basename(repo),
                         "packet_id": packet["packet_id"],
                         "packet_hash": packet["packet_hash"],
                         "items": packet["items"], "session": session,
                         "bytes": len(packet["text"])})),
        )
    conn.commit()
    return ctx


_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
         "that", "this", "is", "it", "be", "so", "as", "at", "by", "from"}


def _terms(text: str) -> set:
    return {w for w in "".join(c if c.isalnum() else " " for c in (text or "").lower()).split()
            if len(w) > 2 and w not in _STOP}


def suggest_prompt(conn, objective: str, limit: int = 1) -> list[dict]:
    """THE READER (V2.4). Closes the loop the whole product rests on.

    `promote_prompt` has been writing accepted prompts into `prompt_library`
    since V2.2 — and until now NOTHING read that table. Not a CLI command, not
    an API route, not the UI, not an MCP tool. The Accept button truthfully said
    "prompt promoted to the reusable library" and the promotion was inert: a
    write with no reader. Two tests asserted the row count went up, which is
    precisely why a green suite did not catch it.

    "Only accepted learning improves the next run" is only true if the next run
    can SEE it. This is that edge: given a new objective, return the prompts from
    runs the operator actually accepted, ranked by term overlap.

    Deliberately dumb matching — term overlap, no embeddings. A wrong suggestion
    that looks confidently relevant is worse than no suggestion, and the operator
    reads the objective it came from before reusing it. Returns [] rather than a
    weak match, and every result carries the objective it was accepted for so the
    human judges the transfer, not the ranker.
    """
    want = _terms(objective)
    if not want:
        return []
    rows = conn.execute(
        "SELECT p.id, p.prompt, p.objective, p.task_class, p.model, p.harness, "
        "p.promoted_at, p.task_run_id FROM prompt_library p "
        "WHERE p.outcome = 'accepted' ORDER BY p.promoted_at DESC").fetchall()
    scored = []
    for r in rows:
        have = _terms(r["objective"])
        if not have:
            continue
        overlap = len(want & have)
        if overlap < 2:          # one shared word is a coincidence, not a match
            continue
        scored.append((overlap / len(want | have), overlap, dict(r)))
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return [{**d, "similarity": round(sim, 3), "shared_terms": n}
            for sim, n, d in scored[:limit]]


def promote_prompt(conn, task_run_id, by="accepted-outcome") -> dict:
    """Outcome gate: only an ACCEPTED run promotes its prompt into the reusable
    library. Rejected/rework prompts stay history and never rank as good.
    Auto-observed runs have no frozen contract — accepting them must never
    teach the next run (see helicon.autogov honesty line)."""
    run = conn.execute("SELECT * FROM task_runs WHERE id=?", (task_run_id,)).fetchone()
    if run is None:
        return {"ok": False, "error": "no such run"}
    if run["task_class"] == "auto-observed":
        return {"ok": False,
                "error": "observed run has no frozen contract — prompt not promoted"}
    if run["human_acceptance"] != "accepted":
        return {"ok": False, "error": "only an accepted outcome promotes a prompt"}
    existing = conn.execute(
        "SELECT id, prompt FROM prompt_library WHERE task_run_id=? "
        "AND outcome='accepted' ORDER BY promoted_at LIMIT 1",
        (task_run_id,),
    ).fetchone()
    if existing:
        return {"ok": True, "prompt_id": existing["id"],
                "prompt": existing["prompt"][:120], "existing": True}
    cap = conn.execute("SELECT prompt_chain FROM run_captures WHERE task_run_id=?",
                       (task_run_id,)).fetchone()
    prompts = json.loads(cap["prompt_chain"] or "[]") if cap else []
    prompt_text = prompts[0]["text"] if prompts else run["objective"]
    pid = "pl_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO prompt_library (id, task_run_id, prompt, objective, task_class, "
        "model, harness, outcome, promoted_at, promoted_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (pid, task_run_id, prompt_text, run["objective"], run["task_class"],
         run["model"], run["harness"], "accepted", _now(), by))
    conn.commit()
    return {"ok": True, "prompt_id": pid, "prompt": prompt_text[:120]}
