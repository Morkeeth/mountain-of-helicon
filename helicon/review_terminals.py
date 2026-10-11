"""helicon review --terminals - the verifier-with-a-memory pointed at AGENT OUTPUT.

Oscar runs ~6 terminals whose agents produce closeouts, diffs and "done" claims
faster than he can review. This ingests each terminal's latest output, extracts
the claims it asserts, and VERIFIES each against reality - git push/merge state,
referenced paths, test files - not vibes. Unverified or contradicted claims are
ranked into one queue and filed as audit_log findings, so a ruled claim is never
re-surfaced (never-twice via `helicon resolve`).

Ingest atom (one terminal's output):
    closeout md  (latest NIGHTRUN*/closeout*/god-mode* in the repo - what it CLAIMS)
  + branch diff  (commits vs base + diffstat - what actually CHANGED)
  + claimed tests (test lines in the closeout - what it SAYS is green)

Reuses claims.py (extraction) + the audit_log/resolve engine (never-twice). No
new gate engine.
"""
import hashlib
import os
import re
import subprocess

from helicon.models import AuditResult
from helicon.claims import extract_status_claims, insert_audit

# Machine-specific terminal names belong in the local config, not the package.
DEFAULT_TERMINALS = {}
CODE_DIR = os.path.expanduser("~/CODE")
CLOSEOUT_RX = re.compile(r"(nightrun|closeout|god-?mode|status|sesh)", re.I)

# Claims that assert the work LEFT the terminal / is externally true. If the
# branch is unpushed these are contradicted by git (the highest-signal catch).
# A negated line ("not pushed", "un-deployed", "nothing shipped") asserts the
# OPPOSITE and agrees with git, so it must NOT be read as a ship claim: the
# fleet is honest about its gate, and flagging that honesty would invert reality.
SHIP_RX = re.compile(
    r"\b(shipped|pushed|merged|deployed|in production|is live|now live|released|"
    r"went live|rolled out|available at)\b", re.I)
NEG_RX = re.compile(
    r"\b(not|no|never|neither|nothing|without|un-?|not-?yet|pending|gate|gated|"
    r"todo|wip|scaffold|un-?deployed|un-?pushed|isn't|aren't|wasn't|won't|don't)\b|"
    r"\bNOT\b", re.I)
# A test claim worth verifying asserts a COUNT ("173 passed", "40 tests green").
# A bare "suite green" / "keep the suite green" is prose or an instruction, not a
# checkable claim, so it must carry a number to qualify.
TEST_RX = re.compile(
    r"\b(\d+)\s+(?:tests?|specs?|passed|passing)\b(?:[^.\n]{0,20}?"
    r"(?:pass|passed|passing|green))?|"
    r"\b(?:tests?|suite)\b[^.\n]{0,20}?\b(\d+)\s+(?:pass|passed|passing|green)\b", re.I)
ENDPOINT_RX = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[\w\[\]\-/.:]+)", re.I)
URL_RX = re.compile(r"https?://[\w.\-]+(?:/[\w\-./]*)?")
METRIC_RX = re.compile(r"\b\d+(?:\.\d+)?%|\b\d+x\b|\bmainnet\b.*\bproven\b", re.I)


def _git(repo, *args):
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                              text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def _base_ref(repo):
    if _git(repo, "rev-parse", "--verify", "-q", "origin/main"):
        return "origin/main"
    return "main"


def discover_terminals(config=None):
    """Known terminals + any ~/CODE repo on a non-main branch with commits ahead
    of base (an unreviewed working branch = a terminal with pending output)."""
    if config is None:
        from helicon.config import load_config
        config = load_config()
    configured = (config or {}).get("review_terminals", {})
    known = configured.get("named_repos", DEFAULT_TERMINALS)
    if not isinstance(known, dict):
        known = DEFAULT_TERMINALS
    seen, out = set(), []
    for name, rel in known.items():
        if not isinstance(name, str) or not isinstance(rel, str) or os.path.basename(rel) != rel:
            continue
        repo = os.path.join(CODE_DIR, rel)
        if os.path.isdir(os.path.join(repo, ".git")):
            out.append((name, repo)); seen.add(os.path.realpath(repo))
    try:
        for rel in sorted(os.listdir(CODE_DIR)):
            repo = os.path.join(CODE_DIR, rel)
            if os.path.realpath(repo) in seen or not os.path.isdir(os.path.join(repo, ".git")):
                continue
            branch = _git(repo, "branch", "--show-current")
            if not branch or branch in ("main", "master"):
                continue
            base = _base_ref(repo)
            if _git(repo, "rev-list", "--count", f"{base}..HEAD") not in ("", "0"):
                out.append((rel, repo))
    except FileNotFoundError:
        pass
    return out


def ingest(name, repo):
    """One terminal's output atom."""
    branch = _git(repo, "branch", "--show-current") or "(detached)"
    base = _base_ref(repo)
    commits = [l for l in _git(repo, "log", "--oneline", f"{base}..HEAD").splitlines()][:15]
    upstream = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ahead = _git(repo, "rev-list", "--count", "@{u}..HEAD") if upstream else ""
    merged = branch in _git(repo, "branch", base, "--merged").replace("*", "").split() if base else False
    # latest closeout doc in the repo root
    closeout_path, closeout_text = None, ""
    try:
        mds = [f for f in os.listdir(repo) if f.endswith(".md") and CLOSEOUT_RX.search(f)]
        mds.sort(key=lambda f: os.path.getmtime(os.path.join(repo, f)), reverse=True)
        if mds:
            closeout_path = os.path.join(repo, mds[0])
            with open(closeout_path, errors="ignore") as fh:
                closeout_text = fh.read()
    except OSError:
        pass
    return {
        "terminal": name, "repo": repo, "branch": branch, "base": base,
        "commits": commits, "upstream": upstream, "ahead": ahead, "merged": merged,
        "closeout_path": closeout_path, "closeout_text": closeout_text,
    }


def _claim_key(atom, kind, text):
    h = hashlib.sha1(f"{kind}|{text.lower().strip()}".encode()).hexdigest()[:10]
    return f"review|{atom['terminal']}|{h}"


def extract_claims(atom):
    """Every assertion the terminal makes, from closeout text + commit subjects."""
    claims = []
    sources = [("closeout", atom["closeout_text"])] + \
              [("commit", c.split(" ", 1)[-1]) for c in atom["commits"]]
    for origin, text in sources:
        in_fence = False
        for line in text.splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence  # skip pasted output inside code fences
                continue
            line = line.strip()
            # a claim is a PROSE assertion; fenced blocks are pasted evidence, not claims
            if in_fence or not line or line.startswith(("#", ">", "|")):
                continue
            if origin == "closeout" and SHIP_RX.search(line) and not NEG_RX.search(line):
                claims.append({"kind": "ship", "text": line[:140], "origin": origin})
            mt = TEST_RX.search(line)
            if mt:
                count = next((g for g in mt.groups() if g and g.isdigit()), None)
                claims.append({"kind": "test", "text": line[:140], "origin": origin,
                               "count": int(count) if count else None})
            for m in ENDPOINT_RX.finditer(line):
                claims.append({"kind": "endpoint", "text": m.group(0),
                               "verb": m.group(1), "path": m.group(2), "origin": origin})
            for m in URL_RX.finditer(line):
                if "localhost" not in m.group(0):
                    claims.append({"kind": "url", "text": m.group(0), "origin": origin})
    # dedup by (kind,text)
    seen, uniq = set(), []
    for c in claims:
        key = (c["kind"], c["text"])
        if key not in seen:
            seen.add(key); uniq.append(c)
    # test claims collapse to the single HEADLINE (highest count) per terminal:
    # one "does the suite hold" question, not one per quoted line.
    tests = [c for c in uniq if c["kind"] == "test"]
    if tests:
        headline = max(tests, key=lambda c: (c.get("count") or 0))
        uniq = [c for c in uniq if c["kind"] != "test"] + [headline]
    return uniq


def _route_exists(repo, path):
    """Is a handler for this route grounded anywhere in source? Language-agnostic:
    a Python FastAPI/Flask decorator (@app.get('/verify')), a Next.js route file,
    an Express router. Grep the path literal across tracked source; if the exact
    path is absent, try the last dynamic-free segment. Returns 'file:line' or None."""
    literal = "/" + path.strip("/")
    for needle in (literal, "/" + "/".join(
            s for s in path.strip("/").split("/") if not s.startswith((":", "[")))):
        if not needle or needle == "/":
            continue
        hit = _git(repo, "grep", "-n", "-I", "--fixed-strings", needle,
                   "--", "*.py", "*.ts", "*.js", "*.tsx", "*.jsx", "*.go", "*.rb")
        if hit:
            first = hit.splitlines()[0]
            return ":".join(first.split(":")[:2])
    # Next.js file-based routing: /api/tasks/[id]/boost -> a matching route file
    seg = [s.strip("[]:") for s in path.strip("/").split("/") if s and not s.startswith((":", "["))]
    if seg:
        for f in _git(repo, "ls-files", "*route.ts", "*route.js", "*/page.tsx").splitlines():
            if seg[-1].lower() in f.lower():
                return f
    return None


_PASS_RX = re.compile(r"(\d+)\s+passed", re.I)
_FAIL_RX = re.compile(r"(\d+)\s+(?:failed|error)", re.I)


def run_tests(repo):
    """Actually run the repo's test suite (opt-in, guarded). Only runs a clear,
    fast, local runner: pytest for Python, the npm test script when node_modules
    is already installed. Never runs if no config. Returns a receipt dict."""
    has_py = bool(_git(repo, "ls-files", "test_*.py", "*/test_*.py", "tests/*.py",
                       "conftest.py", "pytest.ini", "pyproject.toml"))
    has_node = os.path.isfile(os.path.join(repo, "package.json")) and \
        os.path.isdir(os.path.join(repo, "node_modules"))
    cmd = None
    if has_py:
        cmd = ["python3", "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"]
    elif has_node:
        cmd = ["npm", "test", "--silent"]
    elif os.path.isfile(os.path.join(repo, "package.json")):
        return {"ran": False, "why": "node_modules not installed - run `npm i` to enable"}
    else:
        return {"ran": False, "why": "no recognized test runner"}
    try:
        r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=150)
        out = (r.stdout + "\n" + r.stderr)
        passed = int(_PASS_RX.search(out).group(1)) if _PASS_RX.search(out) else None
        failed = int(_FAIL_RX.search(out).group(1)) if _FAIL_RX.search(out) else 0
        return {"ran": True, "passed": passed, "failed": failed,
                "ok": r.returncode == 0 and not failed, "cmd": " ".join(cmd)}
    except subprocess.TimeoutExpired:
        return {"ran": False, "why": "test run exceeded 150s (skipped)"}
    except Exception as e:
        return {"ran": False, "why": f"could not run: {type(e).__name__}"}


def verify(claim, atom, run=False):
    """Return (verdict, receipt). verdict in verified | unverified | contradicted."""
    k = claim["kind"]
    if k == "ship":
        if not atom["upstream"]:
            return ("contradicted",
                    f"claims shipped, but branch '{atom['branch']}' has NO upstream - "
                    f"{len(atom['commits'])} commit(s) never left this machine")
        if "merged" in claim["text"].lower() and not atom["merged"]:
            return ("contradicted",
                    f"claims merged, but '{atom['branch']}' is not merged into {atom['base']}")
        if atom["ahead"] not in ("", "0"):
            return ("unverified",
                    f"pushed to {atom['upstream']}, but {atom['ahead']} local commit(s) still ahead")
        return ("verified", f"branch pushed to {atom['upstream']}, not ahead")
    if k == "endpoint":
        r = _route_exists(atom["repo"], claim["path"])
        return ("verified", f"route file: {r}") if r else \
               ("contradicted", f"no route file backs {claim['verb']} {claim['path']}")
    if k == "url":
        return ("unverified", "external URL - reachability not checked (needs you / --probe)")
    if k == "test":
        has_tests = bool(_git(atom["repo"], "ls-files", "*test*", "*spec*", "test/*", "tests/*"))
        if not has_tests:
            return ("contradicted", "claims tests pass but NO test files found in repo")
        if not run:
            return ("unverified", "test files present, claimed count NOT re-run - add --run")
        res = atom.get("_test_result")
        if res is None:
            res = atom["_test_result"] = run_tests(atom["repo"])
        if not res.get("ran"):
            return ("unverified", f"could not verify: {res.get('why', 'unknown')}")
        claimed = claim.get("count")
        if res["failed"]:
            return ("contradicted",
                    f"ran `{res['cmd']}`: {res['failed']} FAILED, {res['passed']} passed")
        if claimed and res["passed"] is not None and res["passed"] < claimed:
            return ("contradicted",
                    f"claimed {claimed} pass, but only {res['passed']} passed on re-run")
        return ("verified", f"ran `{res['cmd']}`: {res['passed']} passed, 0 failed")
    return ("unverified", "no deterministic check - needs your eyes")


_SEV = {"contradicted": "critical", "unverified": "warning", "verified": "info"}
_RANK = {"contradicted": 0, "unverified": 1, "verified": 2}


def review_terminals(conn, config=None, file=False, only=None, run=False):
    """Ingest every terminal, verify its claims, return a ranked queue. If
    file=True, persist unverified/contradicted claims as audit_log findings with a
    per-claim pair_key so a ruled claim is skipped on the next run (never-twice)."""
    ruled = set()
    for row in conn.execute(
            "SELECT details FROM audit_log WHERE audit_type='review' "
            "AND human_decision IS NOT NULL"):
        import json
        try:
            ruled.add(json.loads(row["details"] or "{}").get("pair_key"))
        except Exception:
            pass

    queue = []
    for name, repo in discover_terminals(config):
        if only and name.lower() not in only and os.path.basename(repo).lower() not in only:
            continue
        atom = ingest(name, repo)
        for claim in extract_claims(atom):
            verdict, receipt = verify(claim, atom, run=run)
            if verdict == "verified":
                continue
            key = _claim_key(atom, claim["kind"], claim["text"])
            if key in ruled:
                continue
            item = {"terminal": name, "repo": repo, "branch": atom["branch"],
                    "kind": claim["kind"], "claim": claim["text"], "origin": claim["origin"],
                    "verdict": verdict, "receipt": receipt, "severity": _SEV[verdict],
                    "pair_key": key, "closeout": atom["closeout_path"]}
            queue.append(item)

    queue.sort(key=lambda x: (_RANK[x["verdict"]], x["terminal"]))

    if file:
        for it in queue:
            res = AuditResult(
                audit_type="review", target_type="terminal", target_id=it["terminal"],
                finding=f"[{it['terminal']}] {it['verdict'].upper()}: {it['claim']}",
                severity=it["severity"],
                proposed_action="verify against reality, then rule",
                details={"pair_key": it["pair_key"], "receipt": it["receipt"],
                         "kind": it["kind"], "branch": it["branch"], "repo": it["repo"]})
            fid = insert_audit(conn, res)
            if fid:
                it["id"] = fid
        conn.commit()
    return queue


def resolve_review(conn, audit_id, note="", retire_cube_id=None):
    """Close the loop: ruling an output-review finding writes the reality-checked
    verdict back into memory as an approved correction cube (source
    'output-review', full provenance), so the next retrieval serves the truth
    instead of the agent's unverified claim. This is the OUTPUT -> memory edge:
    output evaluation improves the store, not just a review queue.

    With retire_cube_id (from `helicon attribute`), it also RETIRES the
    pre-existing memory that caused the bad output - superseded, pointed at the
    correction - so the rot is removed at its source, not just papered over. That
    is the output -> attribute -> rule -> law path closed in one call."""
    import json
    from datetime import datetime, timezone
    row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (audit_id,)).fetchone()
    if row is None:
        return {"ok": False, "error": f"no audit finding #{audit_id}"}
    if row["audit_type"] != "review":
        return {"ok": False, "error": f"finding #{audit_id} is not an output-review finding"}
    if row["human_decision"]:
        return {"ok": False, "error": f"finding #{audit_id} already decided: {row['human_decision']}"}
    try:
        d = json.loads(row["details"] or "{}")
    except (json.JSONDecodeError, TypeError):
        d = {}
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    conn.execute("UPDATE audit_log SET human_decision = ?, resolved_at = ? WHERE id = ?",
                 (f"resolved:{note or 'ruled'}", now, audit_id))
    from helicon.models import HeliconCube
    from helicon.scanner import make_id, content_hash as _hash
    from helicon.db import insert_cube
    tgt, receipt = row["target_id"], d.get("receipt", "")
    content = (f"Output review of terminal '{tgt}' ({d.get('repo','')}, branch "
               f"{d.get('branch','')}): the claim \"{row['finding']}\" was checked "
               f"against reality on {now[:10]}. Verdict: {row['finding'].split(':')[0]}. "
               f"Reality: {receipt}."
               + (f" Human ruling: {note}." if note else ""))
    cube = HeliconCube(
        id=make_id(), source="output-review", source_ref=f"audit:{audit_id}",
        type="decision", title=f"Output-checked: {tgt} - {d.get('kind','claim')}",
        content=content, summary="", content_hash=_hash(content),
        created_at=now, valid_from=now, last_reinforced=now,
        confidence=1.0, review_status="approved")
    insert_cube(conn, cube)
    retired = None
    if retire_cube_id:
        from helicon.attribution import retire_cube as _retire
        if _retire(conn, retire_cube_id, superseded_by=cube.id,
                   reason=f"caused contradicted output, ruled #{audit_id}"):
            retired = retire_cube_id
    conn.commit()
    return {"ok": True, "audit_id": audit_id, "correction_cube": cube.id,
            "terminal": tgt, "retired_cube": retired}


def format_queue(queue, filed=False):
    if not queue:
        return "\n  No unverified claims across your terminals. The board is clean.\n"
    mark = {"contradicted": "✗", "unverified": "?"}
    out = ["", f"  AGENT-OUTPUT REVIEW - {len(queue)} claim(s) need you "
           "(verified claims hidden)", ""]
    cur = None
    for it in queue:
        if it["terminal"] != cur:
            cur = it["terminal"]
            out.append(f"  ┌─ {cur}  ({os.path.basename(it['repo'])} · {it['branch']})")
        tag = f"#{it['id']}" if filed and it.get("id") else ""
        out.append(f"  │ {mark.get(it['verdict'],'?')} [{it['verdict']}] {tag} {it['claim']}")
        out.append(f"  │     ↳ {it['receipt']}")
    out.append("")
    if filed:
        out.append("  Rule top-to-bottom:  helicon resolve <id> --dismiss \"verified: <how>\"")
        out.append("  (a ruled claim is never re-surfaced - never-twice)")
    else:
        out.append("  Persist + rule:  helicon review --terminals --file")
    out.append("")
    return "\n".join(out)
