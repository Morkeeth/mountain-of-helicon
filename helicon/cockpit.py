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


def _continuity_proof(conn, config, terminal, claim, cube_id) -> dict:
    """PROVE CONTINUITY (pull side): after a ruling writes a correction cube,
    show the next agent's context read now surfaces it. 'included' is NOT
    'obeyed' — a database write alone never proves propagation."""
    if not cube_id:
        return {"included": False, "why": "no correction cube written"}
    query = f"{terminal} {(claim.get('text') or '')[:80]}"
    try:
        from helicon.mcp_server import _proactive_context
        ctx = _proactive_context(conn, query, limit=8, max_tokens=1500)
    except Exception as e:
        return {"included": None, "query": query,
                "why": f"context reader unavailable: {type(e).__name__}"}
    # the pull path (_proactive_context) returns ranked cubes under
    # 'relevant_memories' — this is the exact list a real agent receives.
    items = (ctx.get("relevant_memories") or ctx.get("cubes")
             or ctx.get("items") or ctx.get("results") or [])
    ids = [(c.get("id") if isinstance(c, dict) else None) for c in items]
    return {
        "included": cube_id in ids, "query": query,
        "context_size": len(ids), "correction_cube": cube_id,
        "note": "correction is now RETRIEVABLE by the next agent (pull path). "
                "'included in context' != 'the model obeyed it'.",
    }


def rule_claim(conn, config, terminal, repo_path, claim, decision,
               correction="") -> dict:
    """RULE + APPLY: keep / revise / reject one claim. Revise CAPTURES the
    correction verbatim (Oscar's words) into a governed correction cube — the
    write-back seed. Returns a receipt + a continuity proof."""
    if _is_private(repo_path):
        return {"ok": False, "error": "private repo — refused"}
    if decision not in ("keep", "revise", "reject"):
        return {"ok": False, "error": f"unknown decision '{decision}'"}
    if decision == "revise" and not (correction or "").strip():
        return {"ok": False, "error": "revise requires the correction text"}
    fid = file_claim(conn, terminal, repo_path, claim)
    if not fid:
        return {"ok": False, "error": "could not file the claim"}
    note = {
        "keep": f"kept — verified true: {correction}".rstrip(": ").rstrip(),
        "revise": correction.strip(),
        "reject": f"rejected — claim is false: {correction}".rstrip(": ").rstrip(),
    }[decision]
    from helicon.review_terminals import resolve_review
    r = resolve_review(conn, fid, note=note)
    if not r.get("ok"):
        return r
    proof = _continuity_proof(conn, config, terminal, claim, r.get("correction_cube"))
    return {
        "ok": True, "finding_id": fid, "decision": decision,
        "correction_captured": note if decision != "keep" else "",
        "correction_cube": r.get("correction_cube"),
        "retired_cube": r.get("retired_cube"),
        "continuity": proof,
        "receipt": [
            {"applied": True, "effect": f"{decision.title()} recorded for [{terminal}] claim",
             "detail": f"finding #{fid} resolved; correction cube {r.get('correction_cube')} written "
                       f"(source 'output-review'), retrievable by the next agent."},
        ],
    }


def unrule_claim(conn, finding_id) -> dict:
    """UNDO: reverse a ruling — delete the correction cube it wrote and
    re-open the finding, so the record is exactly back to before."""
    row = conn.execute("SELECT id FROM audit_log WHERE id=?", (finding_id,)).fetchone()
    if not row:
        return {"ok": False, "error": f"no finding #{finding_id}"}
    cubes = [r["id"] for r in conn.execute(
        "SELECT id FROM helicon_cubes WHERE source='output-review' AND source_ref=?",
        (f"audit:{finding_id}",)).fetchall()]
    for cid in cubes:
        conn.execute("DELETE FROM helicon_cubes WHERE id=?", (cid,))
        try:
            conn.execute("DELETE FROM cube_embeddings WHERE cube_id=?", (cid,))
        except Exception:
            pass
    conn.execute("UPDATE audit_log SET human_decision=NULL, resolved_at=NULL WHERE id=?",
                 (finding_id,))
    conn.commit()
    return {"ok": True, "finding_id": finding_id, "deleted_cubes": cubes,
            "note": "ruling reversed; finding re-opened; correction cube removed."}


def propagate_correction(conn, config, correction_cube=None,
                         sandbox_dir=None) -> dict:
    """PROVE CONTINUITY (write-back edge): compile the corrections into the
    files the next agent auto-loads. Writes to a SANDBOX by default — never
    Oscar's live ~/.claude/skills without an explicit gate. Proof = the
    correction's content is present in the written files. 'contains' proves
    INCLUSION, never OBEDIENCE."""
    import os
    from helicon.compiler import inject_into_claude_code
    sandbox = sandbox_dir or os.path.join(os.getcwd(), "data", "agent-context-sandbox")
    os.makedirs(sandbox, exist_ok=True)
    # 1) the general compiled write-back (skills + core memory) to the sandbox
    inj = inject_into_claude_code(conn, output_dir=sandbox)
    # 2) the targeted correction feed — the rulings the next agent must receive
    rows = conn.execute(
        "SELECT id, title, content, created_at FROM helicon_cubes "
        "WHERE source='output-review' AND review_status='approved' "
        "ORDER BY created_at DESC LIMIT 50").fetchall()
    lines = ["# Helicon — output-review corrections (auto-generated)", "",
             "Rulings you made on agent output. The next agent loads these "
             "before it writes.", ""]
    for r in rows:
        lines.append(f"## {r['title']}")
        lines.append(r["content"])
        lines.append("")
    feed = "\n".join(lines)
    with open(os.path.join(sandbox, "helicon-corrections.md"), "w") as fh:
        fh.write(feed)
    # 3) prove the specific correction is present in the written context
    contains = False
    if correction_cube:
        row = conn.execute("SELECT content FROM helicon_cubes WHERE id=?",
                           (correction_cube,)).fetchone()
        contains = bool(row and row["content"] and row["content"][:50] in feed)
    return {
        "ok": True, "sandbox_dir": sandbox,
        "files": {**inj.get("files", {}), "helicon-corrections.md": len(feed)},
        "corrections_written": len(rows), "contains_correction": contains,
        "real_target": os.path.expanduser("~/.claude/skills"),
        "gate": "Writing to your real ~/.claude/skills is gated on your approval; "
                "the sandbox proves the mechanism without touching your live agent.",
        "distinction": "'contains' proves the correction is IN the next agent's "
                       "context files. It does NOT prove the model obeyed it — "
                       "that needs a live run.",
    }


def load_artifact(terminal_repo_path: str, kind: str, ref: str,
                  max_chars: int = 60000) -> dict:
    """INSPECT: the actual artifact content, rendered in native form. Re-checks
    privacy on every load (never serve a private path even if asked)."""
    repo = terminal_repo_path
    if _is_private(repo):
        return {"type": "blocked", "text": "", "why": "private repo — not served"}
    if kind == "markdown":
        path = os.path.join(repo, ref)
        if _is_private(path) or not os.path.isfile(path):
            return {"type": "blocked", "text": "", "why": "not found or private"}
        # keep inside the repo (no path traversal)
        if os.path.realpath(path).startswith(os.path.realpath(repo)) is False:
            return {"type": "blocked", "text": "", "why": "path escapes repo"}
        with open(path, errors="ignore") as fh:
            return {"type": "markdown", "label": os.path.basename(path),
                    "text": fh.read()[:max_chars]}
    if kind == "diff":
        base = ref if "..." in ref else f"{ref}...HEAD"
        text = _git(repo, "diff", base)
        return {"type": "diff", "label": base, "text": text[:max_chars]}
    return {"type": "unknown", "text": "", "why": f"no renderer for kind '{kind}'"}
