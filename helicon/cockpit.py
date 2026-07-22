"""V2 Cockpit — the opening surface data.

Assembles the agent-output review loop (ORIENT + INSPECT + COMPARE) over a SAFE
allowlist of local terminals into one calm queue. Reuses `review_terminals`
(the wired verify() engine) as the evidence source; adds objective extraction,
an artifact manifest, a change summary, and a needs-human flag.

Privacy is enforced twice: an explicit terminal allowlist (never auto-discover
trading/wallet/personal repos) AND a hard-private substring filter on the repo
path and closeout path. `review_terminals.discover_terminals` auto-includes
rekt-capital (trading) and okx-agent-oracle (wallet); this module drops them.
"""
import hashlib
import os
import re
import subprocess

from helicon.review_terminals import (
    discover_terminals, ingest, extract_claims, verify, _claim_key, _RANK,
)

# Explicit allowlist. Only these terminals ever reach the cockpit. Trading,
# wallet, treasury, oracle, receipt, journal, finance repos are NEVER listed.
SAFE_TERMINALS = {
    "helicon", "world-relay", "taste-machine", "worldcup-agent",
    "x-engine", "glaze", "favour",
}

# Defense-in-depth: even if a name slips the allowlist, a repo/closeout path
# hitting any of these is dropped (mirrors context_policy's default-deny terms).
PRIVATE_RX = re.compile(
    r"journal|diary|financ|wallet|seed.?phrase|private.?key|salary|passport|"
    r"\bssn\b|password|credential|\bbank\b|net.?worth|rekt|treasury|okx|"
    r"oracle|receipt|people-radar|delegated-agent|chain-assessment|booking|"
    r"country.?bounce|taylorwith|oscar-record", re.I)

_H1_RX = re.compile(r"^#\s+(.+?)\s*$")
_HEADING_RX = re.compile(r"^#{1,3}\s+")


def _is_private(path: str) -> bool:
    return bool(PRIVATE_RX.search(path or ""))


CODE_ROOT = os.path.realpath(os.path.expanduser("~/CODE"))


def _safe_repo_root(repo: str, allowed_roots=None) -> str | None:
    """Server-side allowlist for artifact reads (P0-1). A repo is servable only
    if it resolves into the allowed set and is not private. The caller-supplied
    path is never trusted by basename/prefix — that was the confirmed traversal
    hole. Default allow set = DIRECT children of ~/CODE with a safe basename
    (or a helicon* worktree). `allowed_roots` (a set of realpaths) overrides the
    default and is how the server pins the exact repos in scope."""
    if not repo:
        return None
    rr = os.path.realpath(repo)
    if allowed_roots is not None:
        return rr if (rr in allowed_roots and not _is_private(rr)) else None
    if os.path.dirname(rr) != CODE_ROOT:
        return None
    name = os.path.basename(rr).lower()
    if not (name in {s.lower() for s in SAFE_TERMINALS} or name.startswith("helicon")):
        return None
    if _is_private(rr):
        return None
    return rr


def _context_sandbox_dir() -> str:
    return os.path.join(os.getcwd(), "data", "agent-context-sandbox")


def _write_context_sandbox(conn, sandbox: str) -> dict:
    """Compile the CURRENT approved corrections + skills into the sandbox context
    files. Used by both propagate (write) and undo (regenerate, so a reverted
    correction is removed from the files — P0-4). Reflects current DB state only."""
    from helicon.compiler import inject_into_claude_code
    os.makedirs(sandbox, exist_ok=True)
    inj = inject_into_claude_code(conn, output_dir=sandbox)
    rows = conn.execute(
        "SELECT id, title, content, created_at FROM helicon_cubes "
        "WHERE source='output-review' AND review_status='approved' "
        "ORDER BY created_at DESC LIMIT 50").fetchall()
    lines = ["# Helicon — output-review corrections (auto-generated)", "",
             "Rulings you made on agent output. Regenerated from current state.", ""]
    for r in rows:
        lines.append(f"## {r['title']}")
        lines.append(r["content"])
        lines.append("")
    feed = "\n".join(lines)
    with open(os.path.join(sandbox, "helicon-corrections.md"), "w") as fh:
        fh.write(feed)
    return {"files": {**inj.get("files", {}), "helicon-corrections.md": len(feed)},
            "feed": feed, "corrections_written": len(rows)}


def _git(repo, *args):
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                              text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def _objective(atom) -> str:
    """The one-line 'what was this terminal doing'. First real H1 of the
    closeout, else first prose line, else the branch name. Honest fallback:
    a terminal with no closeout shows its branch, not an invented objective."""
    text = atom.get("closeout_text") or ""
    for line in text.splitlines():
        m = _H1_RX.match(line.strip())
        if m and len(m.group(1)) > 3:
            return m.group(1)[:120]
    for line in text.splitlines():
        s = line.strip()
        if s and not _HEADING_RX.match(s) and not s.startswith((">", "|", "```", "-", "*")):
            return s[:120]
    return f"(no closeout — branch {atom.get('branch', '?')})"


def _change_summary(atom) -> dict:
    """What actually changed: commit count + diffstat vs base. Grounded git,
    not the closeout's self-report."""
    repo, base = atom["repo"], atom["base"]
    shortstat = _git(repo, "diff", "--shortstat", f"{base}...HEAD")
    files = ins = dels = 0
    mf = re.search(r"(\d+) files? changed", shortstat)
    mi = re.search(r"(\d+) insertions?", shortstat)
    md = re.search(r"(\d+) deletions?", shortstat)
    if mf:
        files = int(mf.group(1))
    if mi:
        ins = int(mi.group(1))
    if md:
        dels = int(md.group(1))
    return {
        "commits": atom["commits"][:8],
        "commit_count": len(atom["commits"]),
        "files_changed": files, "insertions": ins, "deletions": dels,
        "upstream": atom["upstream"], "ahead": atom["ahead"], "merged": atom["merged"],
    }


def _artifacts(atom) -> list:
    """The manifest of things this terminal PRODUCED that can be inspected
    natively. Each carries a type the frontend renderer dispatches on."""
    arts = []
    if atom.get("closeout_path") and not _is_private(atom["closeout_path"]):
        arts.append({
            "type": "markdown", "label": os.path.basename(atom["closeout_path"]),
            "ref": os.path.basename(atom["closeout_path"]),
            "note": "the closeout the agent wrote (its own account)",
        })
    if atom["commits"]:
        arts.append({
            "type": "diff", "label": f"{atom['base']}…HEAD",
            "ref": f"{atom['base']}...HEAD",
            "note": f"{len(atom['commits'])} commit(s) — what actually changed",
        })
    return arts


def _ruled_keys(conn) -> set:
    """pair_keys already ruled (never-twice) — a ruled claim leaves the queue."""
    import json
    ruled = set()
    try:
        for row in conn.execute(
                "SELECT details FROM audit_log WHERE audit_type='review' "
                "AND human_decision IS NOT NULL"):
            try:
                ruled.add(json.loads(row["details"] or "{}").get("pair_key"))
            except Exception:
                pass
    except Exception:
        pass
    return ruled


def cockpit_view(conn, config=None, only=None, run=False, terminals=None) -> dict:
    """The ORIENT surface: every SAFE terminal with its objective, actual
    changes, produced artifacts, every claim + grounded verdict, and whether a
    human is needed. Verified claims are KEPT (the cockpit shows the full
    picture, unlike the CLI queue which hides them).

    `terminals` (a list of (name, repo) pairs) overrides live discovery — used
    by tests to run the pipeline on a synthetic fixture deterministically."""
    ruled = _ruled_keys(conn)
    allow = {t.lower() for t in (only or SAFE_TERMINALS)}
    discovered = terminals if terminals is not None else discover_terminals(config)
    out_terminals = []
    for name, repo in discovered:
        base = os.path.basename(repo).lower()
        if name.lower() not in allow and base not in allow:
            continue
        if _is_private(repo):
            continue
        atom = ingest(name, repo)
        if atom.get("closeout_path") and _is_private(atom["closeout_path"]):
            atom["closeout_path"] = None
            atom["closeout_text"] = ""
        claims = []
        for claim in extract_claims(atom):
            verdict, receipt = verify(claim, atom, run=run)
            key = _claim_key(atom, claim["kind"], claim["text"])
            claims.append({
                "kind": claim["kind"], "text": claim["text"],
                "origin": claim.get("origin", ""), "verdict": verdict,
                "receipt": receipt, "pair_key": key, "ruled": key in ruled,
            })
        claims.sort(key=lambda c: (_RANK.get(c["verdict"], 3), c["kind"]))
        open_claims = [c for c in claims if not c["ruled"]]
        needs_human = any(c["verdict"] in ("contradicted", "unverified")
                          for c in open_claims)
        worst = min([_RANK.get(c["verdict"], 3) for c in open_claims], default=3)
        out_terminals.append({
            "terminal": name, "repo": os.path.basename(repo), "repo_path": repo,
            "branch": atom["branch"], "objective": _objective(atom),
            "change": _change_summary(atom), "artifacts": _artifacts(atom),
            "claims": claims, "open_claim_count": len(open_claims),
            "needs_human": needs_human,
            "state": {0: "contradicted", 1: "unverified", 2: "clean"}.get(worst, "clean"),
        })
    # rank: terminals that need you first, worst verdict first
    out_terminals.sort(key=lambda t: (not t["needs_human"],
                                      min([_RANK.get(c["verdict"], 3)
                                           for c in t["claims"]], default=3),
                                      t["terminal"]))
    return {
        "terminals": out_terminals,
        "needs_you": sum(1 for t in out_terminals if t["needs_human"]),
        "total": len(out_terminals),
        "safe_set": sorted(SAFE_TERMINALS),
    }


_SEV = {"contradicted": "critical", "unverified": "warning", "verified": "info"}


def _find_finding_id(conn, pair_key):
    """The audit_log id for an already-filed review claim, by pair_key."""
    import json
    for row in conn.execute(
            "SELECT id, details FROM audit_log WHERE audit_type='review'"):
        try:
            if json.loads(row["details"] or "{}").get("pair_key") == pair_key:
                return row["id"]
        except Exception:
            pass
    return None


def file_claim(conn, terminal, repo_path, claim) -> int | None:
    """Ensure a review claim exists as an audit finding (idempotent by
    pair_key) so it can be ruled. Returns the finding id."""
    from helicon.models import AuditResult
    from helicon.db import insert_audit
    existing = _find_finding_id(conn, claim["pair_key"])
    if existing:
        return existing
    res = AuditResult(
        audit_type="review", target_type="terminal", target_id=terminal,
        finding=f"[{terminal}] {claim['verdict'].upper()}: {claim['text']}",
        severity=_SEV.get(claim["verdict"], "warning"),
        proposed_action="verify against reality, then rule",
        details={"pair_key": claim["pair_key"], "receipt": claim.get("receipt", ""),
                 "kind": claim.get("kind", ""), "repo": repo_path,
                 "branch": claim.get("branch", "")})
    fid = insert_audit(conn, res)
    conn.commit()
    return fid or _find_finding_id(conn, claim["pair_key"])


def _delivery_state(conn, cube_id) -> dict:
    """HONEST continuity (P0-3). A ruling RECORDS a correction cube. That is not
    delivery: nothing is delivered to a live run until propagation writes it into
    the agent's context files, and it is NEVER 'obeyed' without a fresh run
    actually loading and following it. Read-only — mutates no retrieval/utility/
    regret state (the old proof called the mutating retrieval path and recorded
    the correction as 'surfaced' before any agent existed)."""
    if not cube_id:
        return {"recorded": False, "delivered_to_files": False,
                "delivered_to_live_run": False, "obeyed": None,
                "note": "no correction cube was written"}
    exists = conn.execute("SELECT 1 FROM helicon_cubes WHERE id=?",
                          (cube_id,)).fetchone() is not None
    # Read the DELIVERY EVIDENCE instead of asserting its absence. This was
    # hardcoded False, which meant that after `helicon hook` genuinely delivered
    # a ruling into a live session — privacy-gated, harness-received, event
    # written — the Cockpit still told the operator "Not yet delivered to any
    # live run." A governance tool understating its own proof teaches the
    # operator to distrust it exactly when it is telling the truth.
    delivered = conn.execute(
        "SELECT COUNT(DISTINCT task_run_id) FROM run_events "
        "WHERE kind='delivered' AND json_extract(detail, '$.cube_id')=?",
        (cube_id,),
    ).fetchone()[0]
    note = ("Correction is RECORDED. Not yet delivered to any live run. Use "
            "'Send to agent context' to stage it into the next agent's files; "
            "even then delivered != obeyed (only a fresh run proves obedience).")
    if delivered:
        note = (f"Correction is RECORDED and DELIVERED into {delivered} live "
                f"session(s) by the UserPromptSubmit hook. Delivered is still "
                f"not obeyed — only the run's own output shows that.")
    return {
        "recorded": exists, "delivered_to_files": False,
        "delivered_to_live_run": bool(delivered), "delivered_count": delivered,
        "obeyed": None,
        "correction_cube": cube_id,
        "note": note,
    }


def rule_claim(conn, config, terminal, pair_key, decision,
               correction="", terminals=None) -> dict:
    """RULE + APPLY: keep / revise / reject one claim, addressed by
    (terminal, pair_key). SERVER-AUTHORITATIVE (P0-2): the claim text, verdict
    and repo_path are re-derived from a fresh server-side discovery — the browser
    payload is never trusted to assert what the claim or its verdict is, so a
    caller cannot manufacture an approved cube. `terminals` is a test-only
    injection (the API never forwards it); production always re-discovers live.
    Revise captures the correction verbatim into a governed correction cube."""
    if decision not in ("keep", "revise", "reject"):
        return {"ok": False, "error": f"unknown decision '{decision}'"}
    if decision == "revise" and not (correction or "").strip():
        return {"ok": False, "error": "revise requires the correction text"}
    # re-derive the claim server-side; never trust a caller-supplied claim/verdict
    view = cockpit_view(conn, config, only={terminal.lower()}, terminals=terminals)
    term = next((t for t in view["terminals"] if t["terminal"] == terminal), None)
    if term is None:
        return {"ok": False, "error": f"terminal '{terminal}' not found in server-verified state"}
    if _is_private(term["repo_path"]):
        return {"ok": False, "error": "private repo — refused"}
    claim = next((c for c in term["claims"] if c["pair_key"] == pair_key), None)
    if claim is None:
        return {"ok": False, "error": "claim not present in server-verified state (stale or forged)"}
    fid = file_claim(conn, terminal, term["repo_path"], claim)
    if not fid:
        return {"ok": False, "error": "could not file the claim"}
    note = {
        "keep": f"kept — verified true ({claim['verdict']}): {correction}".rstrip(": ").rstrip(),
        "revise": correction.strip(),
        "reject": f"rejected — claim is false: {correction}".rstrip(": ").rstrip(),
    }[decision]
    from helicon.review_terminals import resolve_review
    r = resolve_review(conn, fid, note=note)
    if not r.get("ok"):
        return r
    delivery = _delivery_state(conn, r.get("correction_cube"))
    return {
        "ok": True, "finding_id": fid, "decision": decision,
        "server_verdict": claim["verdict"],
        "correction_captured": note if decision != "keep" else "",
        "correction_cube": r.get("correction_cube"),
        "retired_cube": r.get("retired_cube"),
        "continuity": delivery,
        "receipt": [
            {"applied": True, "effect": f"{decision.title()} recorded for [{terminal}] claim",
             "detail": f"finding #{fid} resolved; correction cube {r.get('correction_cube')} "
                       f"recorded (source 'output-review'). NOT yet delivered to a live run."},
        ],
    }


def unrule_claim(conn, finding_id) -> dict:
    """UNDO: reverse a ruling — delete the correction cube it wrote, re-open the
    finding, AND regenerate the agent-context sandbox so the reverted correction
    is removed from the files propagation wrote (P0-4). Only review findings can
    be undone here (P1: don't reopen unrelated audit findings)."""
    row = conn.execute("SELECT id, audit_type FROM audit_log WHERE id=?",
                       (finding_id,)).fetchone()
    if not row:
        return {"ok": False, "error": f"no finding #{finding_id}"}
    if row["audit_type"] != "review":
        return {"ok": False, "error": f"finding #{finding_id} is not an output-review finding"}
    rows = conn.execute(
        "SELECT id, content FROM helicon_cubes WHERE source='output-review' AND source_ref=?",
        (f"audit:{finding_id}",)).fetchall()
    cubes = [r["id"] for r in rows]
    contents = [r["content"] or "" for r in rows]  # captured BEFORE deletion
    for cid in cubes:
        conn.execute("DELETE FROM helicon_cubes WHERE id=?", (cid,))
        try:
            conn.execute("DELETE FROM cube_embeddings WHERE cube_id=?", (cid,))
        except Exception:
            pass
    conn.execute("UPDATE audit_log SET human_decision=NULL, resolved_at=NULL WHERE id=?",
                 (finding_id,))
    conn.commit()
    # P0-4: reverse propagation — regenerate the sandbox from current DB state so
    # the deleted correction no longer sits in the agent-context files.
    reversed_dir = None
    absent = None
    sandbox = _context_sandbox_dir()
    if os.path.isdir(sandbox):
        w = _write_context_sandbox(conn, sandbox)
        reversed_dir = sandbox
        # prove the reverted correction's CONTENT is gone from the regenerated feed
        absent = all((c[:50] not in w["feed"]) for c in contents if c) if contents else True
    return {"ok": True, "finding_id": finding_id, "deleted_cubes": cubes,
            "propagation_reversed": reversed_dir,
            "correction_absent_from_files": absent,
            "note": "ruling reversed; finding re-opened; correction cube removed"
                    + ("; agent-context files regenerated without it." if reversed_dir
                       else " (no propagation to reverse).")}


def propagate_correction(conn, config, correction_cube=None,
                         sandbox_dir=None) -> dict:
    """Stage the corrections into the files a next agent would auto-load. Writes
    to a SANDBOX by default — never Oscar's live ~/.claude/skills without an
    explicit gate. HONEST delivery language (P0-3): `delivered_to_files` proves
    the correction is IN the files; it is NOT delivered to a live run and NEVER
    obeyed until a fresh run loads and follows it. Undo regenerates this same
    sandbox (P0-4)."""
    sandbox = sandbox_dir or _context_sandbox_dir()
    w = _write_context_sandbox(conn, sandbox)
    delivered_to_files = False
    if correction_cube:
        row = conn.execute("SELECT content FROM helicon_cubes WHERE id=?",
                           (correction_cube,)).fetchone()
        delivered_to_files = bool(row and row["content"] and row["content"][:50] in w["feed"])
    return {
        "ok": True, "sandbox_dir": sandbox, "files": w["files"],
        "corrections_written": w["corrections_written"],
        "delivered_to_files": delivered_to_files,
        "contains_correction": delivered_to_files,  # back-compat alias
        "delivered_to_live_run": False, "obeyed": None,
        "real_target": os.path.expanduser("~/.claude/skills"),
        "gate": "Writing to your real ~/.claude/skills is gated on your approval; "
                "the sandbox proves the mechanism without touching your live agent.",
        "distinction": "delivered_to_files = the correction is IN the next agent's "
                       "context files. It is NOT delivered to a live run and NOT "
                       "obeyed until a fresh run loads and follows it.",
    }


_DIFF_REF_RX = re.compile(r"^[\w./-]+\.\.\.HEAD$")


def load_artifact(terminal_repo_path: str, kind: str, ref: str,
                  max_chars: int = 60000, *, allowed_roots=None,
                  expected_hash: str = "") -> dict:
    """INSPECT: the actual artifact content, rendered in native form.

    P0-1: the repo must resolve to an allowed ~/CODE safe root (server-side, not
    by caller-supplied basename/prefix), and the artifact realpath must be TRULY
    contained in that root (== root or startswith root + os.sep) — a sibling
    worktree sharing a name prefix can no longer escape. Diff refs are restricted
    to the `<base>...HEAD` form so a crafted ref can't reach arbitrary git."""
    rr = _safe_repo_root(terminal_repo_path, allowed_roots)
    if rr is None:
        return {"type": "blocked", "text": "", "why": "repo is not an allowed ~/CODE safe root"}
    if kind == "markdown":
        cand = os.path.realpath(os.path.join(rr, ref))
        if not (cand == rr or cand.startswith(rr + os.sep)):
            return {"type": "blocked", "text": "", "why": "path escapes repo"}
        if _is_private(cand) or not os.path.isfile(cand):
            return {"type": "blocked", "text": "", "why": "not found or private"}
        with open(cand, "rb") as fh:
            raw = fh.read()
        actual_hash = hashlib.sha256(raw).hexdigest()[:16]
        if expected_hash and actual_hash != expected_hash:
            return {
                "type": "blocked", "text": "",
                "why": (f"artifact changed since capture "
                        f"(expected {expected_hash}, found {actual_hash})"),
            }
        return {"type": "markdown", "label": os.path.basename(cand),
                "text": raw.decode(errors="ignore")[:max_chars],
                "content_hash": actual_hash}
    if kind == "diff":
        if not _DIFF_REF_RX.match(ref or ""):
            return {"type": "blocked", "text": "", "why": "invalid diff ref (want <base>...HEAD)"}
        text = _git(rr, "diff", ref)
        return {"type": "diff", "label": ref, "text": text[:max_chars]}
    return {"type": "unknown", "text": "", "why": f"no renderer for kind '{kind}'"}
