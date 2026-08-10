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


BOUNDARY — this module is NOT the Workgraph capture protocol.
Here: OBSERVE work that already happened. Reads Claude Code transcripts
into run_captures (discover_sessions, capture_session, sync_sessions).
There: RECORD work as it happens. helicon/workgraph_capture.py opens a
TaskRun against a Wager and closes it with a verification receipt
(launch, close, CaptureError).
Two modules said "capture" and meant different things; mcp_server.py
imported launch/close from HERE and crashed only when the tool was called.
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


def govern_from_capture(conn, capture_id, objective, acceptance,
                        task_class: str | None = None) -> dict:
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
            conn, objective, acceptance, task_class=task_class,
            model=cap["model"] or "",
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


def hook_gate(conn, cwd, session="", prompt="", mode="block") -> dict | None:
    """The doorway, live. Called by the UserPromptSubmit hook BEFORE anything is
    delivered: if this repo's loaded context contains claims the running code
    disproves, the operator sees the configured warning/block intervention.

    This is the line between analysis and control. `helicon board` and the
    Intervention Gate already produce this verdict; until now it only ever
    landed in a CLI someone had to remember to type.

    Returns None to allow (nothing is printed, nothing changes about the run),
    or a dict the CLI turns into Claude Code's block payload.

    Privacy: the gate never probes a path PRIVATE_RX matches (journal, finance,
    wallet, …). It is a wider net than `hook_deliver`'s safe-repo allowlist —
    blocking leaks nothing, so it governs every ordinary repo — but a private
    tree is neither probed nor quoted, in the terminal or in the event log.

    Fail-open is deliberate and total: every failure path here returns None.
    """
    from helicon import doorway
    repo = _repo_root(cwd)
    if repo is None or _is_private(repo):
        return None

    v = doorway.verdict(conn, repo, config=None)
    d = doorway.decide(v, prompt)
    if d["action"] == "allow":
        return None

    task_run_id = _hook_run_id(conn, session)
    refs = [f"{b['file']}:{b['line']}" if b.get("line") else b["file"]
            for b in d["contradicted"]]
    detail = {"repo": v["repo"], "fingerprint": v["fingerprint"],
              "contradicted": refs, "session": session,
              "cached": v["cached"]}

    if d["action"] == "override":
        # The one human moment the product law allows — and it is logged, with
        # the operator's own words, against the blockers it waved through.
        detail["reason"] = d["reason"]
        detail["who"] = (os.environ.get("HELICON_OPERATOR")
                         or os.environ.get("USER") or "operator")
        _record_gate_event(conn, task_run_id, "gate_override", detail)
        return {"action": "override", "verdict": v, "decision": d,
                "message": (f"⚠ HELICON — gate OVERRIDDEN by {detail['who']}: "
                            f"{d['reason']}\n  waved through: {', '.join(refs)}\n"
                            f"  logged on the run.")}

    # The event names what actually happened to the run. A warn logged as
    # `gate_blocked` would make the gate's own evidence trail claim a refusal
    # that never occurred — the exact failure class this product audits for.
    _record_gate_event(conn, task_run_id,
                       "gate_warned" if mode == "warn" else "gate_blocked", detail)
    return {"action": "block", "verdict": v, "decision": d,
            "message": doorway.format_block(v, d, mode=mode)}


def _repo_root(cwd: str) -> str | None:
    """The git repo `cwd` sits in, or None. Unlike `_safe_repo_root` this is not
    an allowlist — the gate governs any repo, because refusing a run publishes
    nothing. Delivery keeps the stricter check."""
    if not cwd or not os.path.isdir(cwd):
        return None
    top = _git(cwd, "rev-parse", "--show-toplevel")
    return os.path.realpath(top) if top else None


def _hook_run_id(conn, session: str) -> str:
    """Attach a gate event to the session's open auto-observed run when there is
    one, so the block sits on the run it stopped rather than floating free."""
    if session:
        try:
            from helicon.autogov import _find_open
            observed = _find_open(conn, session)
            if observed:
                return observed["id"]
        except (ImportError, sqlite3.Error):
            pass
    return f"hook:{session}"[:40]


def _record_gate_event(conn, task_run_id: str, kind: str, detail: dict) -> None:
    conn.execute(
        "INSERT INTO run_events (task_run_id, ts, kind, actor, detail) "
        "VALUES (?,?,?,?,?)",
        (task_run_id, _now(), kind, "helicon", json.dumps(detail)))
    conn.commit()


# The trailer stamped on every injection. It is a markdown comment so it is
# inert to the agent reading it, and a fixed string so `receipt` can find it in
# a transcript without parsing the harness's private JSON shape.
RECEIPT_MARK = "<!-- helicon-receipt:"


def receipt_token(ctx: str) -> str:
    """A short, content-derived id for one injection. Content-derived on purpose:
    a random id would prove only that *something* was injected, while this proves
    that THESE bytes were."""
    return hashlib.sha256((ctx or "").encode()).hexdigest()[:16]


def _budget_of(text: str) -> dict:
    from helicon.context_budget import assess
    return assess(len(text or "") // 4)


def _fit_rulings(rows: list, packet_text: str = "") -> tuple[list, list]:
    """Keep as many rulings as the context-rot budget allows, newest first.

    Helicon's own guard says a session degrades past ~32k tokens. Injecting past
    that to deliver more rulings would make this tool a cause of context rot
    while it advertises itself as the cure. Rows are already newest-first, so
    the ones that give way are the oldest — and they are returned, not dropped
    in silence.
    """
    from helicon.context_budget import ONSET_TOKENS
    kept, trimmed = [], []
    used = len(packet_text or "") // 4
    for r in rows:
        cost = (len(r["content"] or "") + 3) // 4
        if used + cost > ONSET_TOKENS:
            trimmed.append(r)
            continue
        kept.append(r)
        used += cost
    return kept, trimmed


def receipt(conn, session: str) -> dict:
    """Did the harness actually receive what Helicon injected?

    Every other part of this loop can be satisfied by a row this process wrote.
    This one cannot: it opens the transcript the HARNESS wrote and looks for the
    receipt token. Three verdicts, and the third is a verdict:

      RECEIVED     — the token is in the harness's transcript, at a known line
      NOT_FOUND    — the transcript exists and does not contain it (a real miss)
      UNVERIFIABLE — no injection logged, or no transcript to read

    UNVERIFIABLE is never rounded up to RECEIVED. A delivery we cannot check is
    a delivery we have not proven.
    """
    row = conn.execute(
        "SELECT ts, detail FROM run_events WHERE kind='injected' "
        "ORDER BY ts DESC").fetchall()
    hit = None
    for r in row:
        d = json.loads(r["detail"])
        if not session or d.get("session") == session:
            hit = (r["ts"], d)
            break
    if hit is None:
        return {"verdict": "UNVERIFIABLE", "session": session,
                "why": "no injection logged for this session — nothing to verify"}
    ts, d = hit
    token, path = d.get("receipt_token", ""), d.get("transcript_path", "")
    base = {"verdict": "UNVERIFIABLE", "session": d.get("session", session),
            "token": token, "transcript": path, "injected_at": ts,
            "bytes": d.get("bytes"), "budget_status": d.get("budget_status"),
            "rulings_kept": d.get("rulings_kept"),
            "rulings_trimmed": len(d.get("rulings_trimmed") or [])}
    if not path:
        base["why"] = ("the harness gave no transcript_path on this hook call — "
                       "the injection cannot be checked against its own record")
        return base
    if not os.path.exists(path):
        base["why"] = f"transcript not found at {path} (session may have been cleared)"
        return base
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                if token and token in line:
                    base.update({"verdict": "RECEIVED", "line": n,
                                 "why": "the harness's own transcript contains "
                                        "the exact injected bytes"})
                    return base
    except OSError as e:
        base["why"] = f"transcript unreadable: {e}"
        return base
    base.update({"verdict": "NOT_FOUND",
                 "why": "the transcript exists and does not contain the token — "
                        "the injection did not reach this session"})
    return base


def format_receipt(r: dict) -> str:
    mark = {"RECEIVED": "✓", "NOT_FOUND": "✗", "UNVERIFIABLE": "?"}
    out = ["", f"  {mark.get(r['verdict'], ' ')} {r['verdict']} — "
               f"session {r.get('session') or '(any)'}"]
    if r.get("token"):
        at = f" at transcript line {r['line']}" if r.get("line") else ""
        out.append(f"    packet {r['token']}{at}")
    out.append(f"    {r['why']}")
    if r.get("budget_status"):
        out.append(f"    budget: {r['budget_status']} · {r.get('rulings_kept')} ruling(s) "
                   f"injected, {r.get('rulings_trimmed')} trimmed to stay under the rot onset")
    if r.get("transcript"):
        out.append(f"    transcript: {r['transcript']}")
    out.append("")
    return "\n".join(out)


def hook_deliver(conn, cwd, session="", transcript_path="") -> str | None:
    """The delivery edge, made real (closes the Codex P0-3 gap honestly). A
    Claude Code UserPromptSubmit hook calls this: it returns the approved
    output-review rulings as text that the harness injects into a LIVE session,
    and records a 'delivered' event. Privacy-gated: a non-safe repo gets
    nothing. Still not 'obeyed' — only the run's output shows that.

    Two things this now does that a DB write alone could not:

    - It stamps the injected text with a RECEIPT TOKEN and records the session's
      transcript path. `helicon receipt <session>` then reads the harness's own
      transcript and rules RECEIVED / NOT_FOUND / UNVERIFIABLE. Until that read
      happens, "delivered" was a row this process wrote vouching for itself.
    - It checks the injection against the context-rot budget before sending it.
      A memory tool that quietly pushes a session past the ~32k onset is causing
      the degradation it exists to detect. Over budget, the rulings are trimmed
      oldest-first and the trim is RECORDED — never silently dropped.
    """
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

    # The frozen packet is governed and is never trimmed; the rulings are the
    # elastic part, so they are what gives way when the budget is tight.
    kept, trimmed = _fit_rulings(list(rows), packet["text"] if packet else "")

    parts = []
    if packet:
        parts.append(packet["text"])
    if kept:
        parts.append(
            "## Helicon — rulings to obey before you write (delivered live)\n"
            + "\n".join(f"- {r['content']}" for r in kept)
        )
    if not parts:
        return None
    ctx = "\n\n".join(parts)

    # The receipt token. Derived from the exact bytes injected, so finding it in
    # the harness's transcript proves THIS text arrived — not that something did.
    token = receipt_token(ctx)
    ctx = f"{ctx}\n\n{RECEIPT_MARK} {token}"

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
         for r in kept],
    )
    # One row per injection, carrying everything `helicon receipt` needs to go
    # and check the harness's own transcript rather than trust this write.
    budget = _budget_of(ctx)
    conn.execute(
        "INSERT INTO run_events (task_run_id, ts, kind, actor, detail) "
        "VALUES (?,?,?,?,?)",
        (task_run_id, now, "injected", "helicon",
         json.dumps({"repo": os.path.basename(repo), "session": session,
                     "receipt_token": token, "bytes": len(ctx),
                     "transcript_path": transcript_path or "",
                     "budget_status": budget["status"],
                     "budget_tokens": budget["tokens"],
                     "rulings_kept": len(kept),
                     "rulings_trimmed": [r["id"] for r in trimmed]})))
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


def captured_session_ids(conn) -> set[str]:
    """Every session_id already in run_captures, flattened out of the JSON column.

    A daemon that re-reads the transcript directory must be able to answer "have I
    seen this one" without a UNIQUE constraint on a JSON array. This is that answer.
    """
    out: set[str] = set()
    for (blob,) in conn.execute("SELECT session_ids FROM run_captures").fetchall():
        try:
            out.update(json.loads(blob or "[]"))
        except json.JSONDecodeError:
            continue
    return out


def sync_sessions(conn, *, limit: int | None = None, provenance: str = "observed",
                  dry_run: bool = False) -> dict:
    """Observe every safe session on disk that has not been captured yet.

    This is the ingestion the suite was missing. `capture.py` could already read a
    transcript into a RunRecord, but nothing ever called it: on 2026-08-10 there
    were 337 transcripts on disk, 36 of them safe, and `run_captures` held ZERO
    rows. Every starved surface downstream — lift, next-prompt, the work graph —
    was starved by this one gap, not by a missing feature.

    Idempotent by session id, so it is safe to run on a timer. Sessions outside a
    ~/CODE safe root or classified private are skipped by `_session_is_safe` and
    counted, never captured: the privacy boundary is not a performance problem to
    optimise away.
    """
    seen = captured_session_ids(conn)
    found = discover_sessions(safe_only=False)
    result = {"on_disk": len(found), "already_captured": 0, "unsafe": 0,
              "captured": 0, "failed": 0, "errors": [], "dry_run": dry_run}
    for meta in found:
        if meta["session_id"] in seen:
            result["already_captured"] += 1
            continue
        # discover_sessions() exposes the working directory as "repo"; reading it
        # as "cwd" silently rejected all 337 sessions as out-of-boundary.
        if not _session_is_safe(meta.get("repo", ""), meta["path"], meta.get("branch")):
            result["unsafe"] += 1
            continue
        if dry_run:
            result["captured"] += 1
            continue
        res = capture_session(conn, meta["path"], provenance=provenance)
        if res.get("ok"):
            result["captured"] += 1
            seen.add(meta["session_id"])
        else:
            result["failed"] += 1
            if len(result["errors"]) < 5:
                result["errors"].append(f"{meta['session_id'][:8]}: {res.get('error')}")
        if limit and result["captured"] >= limit:
            break
    return result


def render_sync(r: dict) -> str:
    head = "  CAPTURE" + ("  (dry run — nothing written)" if r["dry_run"] else "")
    lines = [head, "",
             f"    on disk           {r['on_disk']}",
             f"    already captured  {r['already_captured']}",
             f"    outside boundary  {r['unsafe']}   (not under a ~/CODE safe root, or private)",
             f"    captured now      {r['captured']}"]
    if r["failed"]:
        lines.append(f"    failed            {r['failed']}")
        lines += [f"      · {e}" for e in r["errors"]]
    return "\n".join(lines)


# An observed session never declared an acceptance test before work started, so
# one is stamped after the fact with this exact marker. It exists so the run is
# reachable in the graph — never so it can be mistaken for a governed run. Any
# analysis that compares declared-before-work runs must exclude these.
OBSERVED_ACCEPTANCE = "OBSERVED-AFTER-THE-FACT: no acceptance test was declared before this work"


def _objective_from_capture(cap) -> str:
    """The session's own first prompt, truncated. Never invented.

    A capture with no readable prompt gets a description of what it is, not a
    guess about what it was for.
    """
    try:
        prompts = json.loads(cap["prompt_chain"] or "[]")
    except json.JSONDecodeError:
        prompts = []
    for p in prompts:
        text = (p.get("text") or p.get("prompt") or "").strip() if isinstance(p, dict) else str(p).strip()
        if text:
            return " ".join(text.split())[:200]
    repo = (cap["repo"] or "unknown").rstrip("/").split("/")[-1]
    return f"observed session in {repo} ({cap['branch'] or 'no branch'}) — no prompt recorded"


def govern_captures(conn, *, limit: int | None = None, dry_run: bool = False) -> dict:
    """Bridge observed captures into the work graph as TaskRuns.

    run_captures was the ingestion; this is the edge that makes those rows part of
    the graph instead of a parallel log. Idempotent: a capture whose task_run_id is
    already set is skipped, so this is safe on the same timer as the capture itself.
    """
    rows = conn.execute(
        "SELECT * FROM run_captures WHERE task_run_id IS NULL ORDER BY captured_at"
    ).fetchall()
    out = {"ungoverned": len(rows), "governed": 0, "failed": 0, "errors": [],
           "dry_run": dry_run}
    for cap in rows:
        if dry_run:
            out["governed"] += 1
        else:
            res = govern_from_capture(conn, cap["id"], _objective_from_capture(cap),
                                      OBSERVED_ACCEPTANCE,
                                      task_class="auto-observed")
            if res.get("ok", True) and not res.get("error"):
                out["governed"] += 1
            else:
                out["failed"] += 1
                if len(out["errors"]) < 5:
                    out["errors"].append(f"{cap['id']}: {res.get('error')}")
        if limit and out["governed"] >= limit:
            break
    return out


def link_captures_to_run_cards(conn, *, dry_run: bool = False) -> dict:
    """Stamp task_runs.run_id by SESSION IDENTITY, never by time window.

    run_cards cluster session cost records (runs.py:_finalize_run) and
    run_captures store the session ids they were built from, so the same session
    appears on both sides and the join is an equality, not a guess. This is the
    key that db.py's ALTER created and that nothing had yet been able to fill for
    an imported run.

    The rejected alternative is still rejected: matching task_runs.execution_
    started_at inside run_cards[start, end] would have produced a number from
    proximity. A session id is the thing that actually produced both rows.
    """
    from helicon.runs import scan_session_costs, group_runs
    import os as _os
    projects = _os.path.expanduser("~/.claude/projects")
    session_to_run: dict[str, str] = {}
    if _os.path.isdir(projects):
        for proj in sorted(_os.listdir(projects)):
            pdir = _os.path.join(projects, proj)
            if not _os.path.isdir(pdir):
                continue
            for run in group_runs(scan_session_costs(pdir)):
                # _finalize_run exposes the cluster's members as session_ids;
                # the private _members key does not survive it.
                for sid in run.get("session_ids", []):
                    session_to_run[sid] = run["run_id"]

    known = {r[0] for r in conn.execute("SELECT run_id FROM run_cards")}
    rows = conn.execute(
        "SELECT id, task_run_id, session_ids FROM run_captures "
        "WHERE task_run_id IS NOT NULL").fetchall()
    out = {"captures": len(rows), "linked": 0, "no_session_match": 0,
           "no_card": 0, "dry_run": dry_run}
    for cap in rows:
        try:
            sids = json.loads(cap["session_ids"] or "[]")
        except json.JSONDecodeError:
            sids = []
        rid = next((session_to_run[s] for s in sids if s in session_to_run), None)
        if rid is None:
            out["no_session_match"] += 1
            continue
        if rid not in known:
            # The session is real but no card was ever cut for its run. Counted
            # and left NULL — an unjoinable run is reported, never estimated.
            out["no_card"] += 1
            continue
        if not dry_run:
            conn.execute("UPDATE task_runs SET run_id=? WHERE id=? AND run_id IS NULL",
                         (rid, cap["task_run_id"]))
        out["linked"] += 1
    if not dry_run:
        conn.commit()
    return out
