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
