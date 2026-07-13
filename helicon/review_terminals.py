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

# Terminal -> repo. Auto-detection covers the rest; this just names the known ones.
DEFAULT_TERMINALS = {
    "Helicon": "helicon",
    "FAVOUR": "world-relay",
    "Rekt": "sample-private",
    "Taste Machine": "taste-machine",
    "KYA/OKX": "sample-oracle",
    "Portfolio": "sample-portfolio",
}
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
TEST_RX = re.compile(
    r"\b(\d+)\s+(?:tests?|specs?)\s+(?:pass|passed|passing|green)\b|"
    r"\b(?:suite|tests?)\s+(?:green|passing|all pass)\b|\ball tests? pass", re.I)
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
    seen, out = set(), []
    for name, rel in DEFAULT_TERMINALS.items():
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
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", ">", "|", "```")):
                continue
            if SHIP_RX.search(line) and not NEG_RX.search(line):
                claims.append({"kind": "ship", "text": line[:140], "origin": origin})
            if TEST_RX.search(line):
                claims.append({"kind": "test", "text": line[:140], "origin": origin})
            for m in ENDPOINT_RX.finditer(line):
                claims.append({"kind": "endpoint", "text": m.group(0),
                               "verb": m.group(1), "path": m.group(2), "origin": origin})
            for m in URL_RX.finditer(line):
                if "localhost" not in m.group(0):
                    claims.append({"kind": "url", "text": m.group(0), "origin": origin})
    # dedup by (kind,text)
    seen, uniq = set(), []
    for c in claims:
        k = (c["kind"], c["text"])
        if k not in seen:
            seen.add(k); uniq.append(c)
    return uniq


def _route_exists(repo, path):
    """A Next.js/Express route for /api/tasks/[id]/boost lives at a matching file."""
    seg = [s for s in path.strip("/").split("/") if s and not s.startswith(":")]
    if not seg:
        return False
    tail = seg[-1].strip("[]")
    hits = _git(repo, "ls-files", "*route.ts", "*route.js", "*.ts", "*.js")
    for f in hits.splitlines():
        low = f.lower()
        if all(s.strip("[]").lower() in low for s in seg[-2:]) or (tail and tail.lower() in low):
            return f
    return False


def verify(claim, atom):
    """Return (verdict, receipt). verdict ∈ verified | unverified | contradicted."""
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
        return ("unverified",
                ("test files present, claimed count NOT re-run - rule after `--run`"
                 if has_tests else "claims tests pass but NO test files found in repo"))
    return ("unverified", "no deterministic check - needs your eyes")


_SEV = {"contradicted": "critical", "unverified": "warning", "verified": "info"}
_RANK = {"contradicted": 0, "unverified": 1, "verified": 2}


def review_terminals(conn, config=None, file=False, only=None):
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
            verdict, receipt = verify(claim, atom)
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
