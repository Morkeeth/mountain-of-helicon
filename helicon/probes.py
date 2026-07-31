"""R13 — document vs live system: the claim that carries an executable probe.

Every other class in this exam settles a claim against another CLAIM. R1 pairs
two files that disagree; R2 pairs a number in prose against a number counted
from source; R11 pairs two definitions. A sentence that asserts a fact about
the RUNNING system has no counterparty at all, so it is believed forever.

The FAVOUR case (Jul 28-30, 2026) is the shape of the failure. `CLAUDE.md`
told every agent that the on-chain USDC escrow was a current capability and
that user self-funding must stay closed *until* the upgrade authority moved
off the hot wallet. Reality: custody was retired at d746996, the funding
routes answer 410, and the feature is not pending — it is gone. Both sides
were in git. Nothing compared them, so every agent that read the file planned
around a contract that no longer takes money.

The binding is derived, never declared. A per-repo list of probes would just
be a fixture wearing a config hat, and the point is to be pointed at a repo
nobody wrote probes for. Four deterministic shapes, each resolving its own
target out of the sentence:

  killswitch  The running code contains an ENFORCED retirement — a constant
              set true, a route answering 410 — and a doc sentence still
              asserts that subject as available. Scope is the intersection of
              the switch's own module vocabulary and the identifiers at the
              sites it gates, so a switch cannot claim territory it does not
              actually close.
  command     The doc quotes a command AND its result (`git log -S"x"` = 0
              commits). That sentence is self-probing: run it, compare.
  path        The doc names a file as present. Ask git whether it is.
  chain       The doc asserts on-chain authority (`owner()` = 0x...). Reading
              that needs an RPC, and usually the address is elided in prose.

Verdicts are three, never two:

  CONTRADICTED  the probe ran and disagrees; its stdout is the receipt
  UPHELD        the probe ran and agrees
  UNVERIFIABLE  the probe could not run — no RPC, no network, elided address

A probe that cannot run reports UNVERIFIABLE. It never reports UPHELD, and it
never guesses. A fabricated green is the only outcome that makes this
worthless: an agent that trusts a green it did not earn is worse off than one
that was never told anything.

Read-only by construction: git plumbing and file reads. Network probes are
opt-in (allow_network) and answer UNVERIFIABLE when off. Nothing here writes
to the repo it examines.
"""
import json
import os
import re
import subprocess
from datetime import datetime, timezone

from helicon.models import AuditResult
from helicon.db import insert_audit

CONTRADICTED = "CONTRADICTED"
UPHELD = "UPHELD"
UNVERIFIABLE = "UNVERIFIABLE"

# Source files a kill switch can live in. node_modules and friends are not
# "the running system" — they are somebody else's.
_CODE_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".go", ".rs",
             ".sol", ".rb", ".java", ".kt", ".php")
_SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "coverage",
              "__pycache__", ".venv", "venv", "vendor", ".turbo", "out"}
# A test is not a gate. `custody-retired.guard.test.ts` proves the switch works,
# but its fixtures quote whole product sentences, and letting those into the
# scope let CUSTODY_RETIRED claim "real money moves through this" — a sentence
# the same retirement explicitly protects (campaign cash still pays out).
_TEST_PATH = re.compile(r"(?:^|/)(?:__tests__|tests?|spec)/|\.(?:test|spec)\.[a-z]+$"
                        r"|(?:^|/)test_[^/]+\.py$|(?:^|/)conftest\.py$")

# A committed CORPUS is not the running code either. HELICON-BENCH ships whole
# miniature repos under bench/repos/ so memory can be scored against commands
# that execute; one of them declares `CUSTODY_RETIRED = true` because that is
# the fixture's entire point. Nothing excluded it, so the switch was treated as
# a live retirement in THIS repo, and it then contradicted seven unrelated
# sentences of AGENTS.md prose about a flaky test. A fixture proving a probe
# works must never become evidence about its host.
_FIXTURE_PATH = re.compile(
    r"(?:^|/)(?:bench/repos|fixtures?|testdata|golden|__fixtures__|"
    r"examples?|samples?|\.worktrees|demo-repos)(?:/|$)")


def _is_fixture(rel: str) -> bool:
    return bool(_FIXTURE_PATH.search(rel or ""))

# A retirement that is ENFORCED, not announced. A comment saying "deprecated"
# changes no behaviour; a constant the code branches on does.
_SWITCH_DECL = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+"
    r"([A-Z][A-Z0-9_]*(?:RETIRED|DISABLED|DEPRECATED|CLOSED|REMOVED|SUNSET|KILLED))"
    r"\s*(?::\s*[\w<>\[\]|\s]+)?\s*=\s*(?:true|True)\b")
_GONE_STATUS = re.compile(r"status:\s*410|HTTPStatus\.GONE|\b410\b\s*[,)]|"
                          r"HTTPException\(\s*(?:status_code\s*=\s*)?410")

# Does this sentence assert the subject is available / in use right now?
_AVAILABILITY = re.compile(
    r"\b(?:is|are|remains?|stays?)\s+(?:currently\s+|still\s+)?"
    r"(?:live|active|enabled|available|deployed|running|open|in production)\b"
    r"|\bmoves?\s+through\b|\bonly real when\b|\bruns? on\b"
    r"|\bwe (?:use|run|take|hold)\b|\bin production\b", re.I)
# A hold placed on a feature pending some condition — the class of sentence
# that keeps agents waiting for a door that was bricked up.
_GATED = re.compile(
    r"\b(?:do\s*not|don'?t|never)\b[^.]{0,120}?\b(?:until|before|pending)\b"
    r"|\bmust stay (?:closed|shut|off|disabled)\b"
    r"|\bblocked (?:on|until|pending)\b|\bnot (?:until|before)\b", re.I)
# Headings under which a bare noun phrase IS a present-tense capability claim.
_CAPABILITY_HEADINGS = ("context", "stack", "architecture", "overview",
                        "what it does", "how it works", "components", "system")
# The sentence already knows. Do not tell it what it just said.
_ACK = re.compile(r"\b(?:retired|no longer|closed|deprecated|removed|sunset|"
                  r"disabled|gone|shut down|killed off|discontinued)\b", re.I)

# A quoted command with its stated result: `git log ...` = 0 commits
_CMD_RESULT = re.compile(r"`([^`]+)`\s*(?:=|==|→|->|returns?|gives?|yields?)\s*"
                         r"([^.,;\n]{1,60})")
_SAFE_GIT = {"log", "grep", "show", "rev-parse", "ls-files", "diff",
             "status", "branch", "tag", "describe", "cat-file"}

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{4,}(?:[…]|\.\.\.)[0-9a-fA-F]{2,}|0x[0-9a-fA-F]{40}")
_AUTHORITY = re.compile(r"\b(?:owner\(\)|upgrade authority|admin(?:istrator)?|"
                        r"controlled by|proxy admin|implementation\(\))\b", re.I)
_PATH_TOKEN = re.compile(r"`([A-Za-z0-9_./\[\]-]+\.(?:ts|tsx|js|jsx|mjs|py|go|rs|"
                         r"sol|rb|java|md|json|toml|ya?ml))`")

# A backticked filename is an EXISTENCE CLAIM only when the sentence asserts the
# file is THERE — "lives in", "the entry point is `x`", "defined in `x`", "see
# `x`". A sentence that merely names a file (the schema for `items.json`, an
# example `foo.ln.json`, "generates `graph.json`", "create a new file
# `2026-01-01.md`", or a negation like "there is no `.eleventy.js`") names no
# present file; probing git for it manufactures a contradiction. This was the
# dominant false-positive class in the first public sweep (2026-08). Precision
# over recall: fire only on an explicit presence cue, never on a negation /
# example / generation, and never on a relative-escape or glob token.
_PATH_PRESENT = re.compile(
    r"\b(?:lives?\s+in|located\s+(?:in|at)|found\s+(?:in|at)|(?:is|are)\s+(?:in|at|located|defined|stored)"
    r"|defined\s+in|entry\s*point|config(?:uration)?\s+(?:file\s+)?is|stored\s+in|configured\s+in"
    r"|(?:config|entry|main|source)\s+(?:file\s+)?is|see\s+`|read\s+`|imported\s+from)\b", re.I)
_PATH_NOT_ASSERTION = re.compile(
    r"\b(?:there\s+is\s+no|isn'?t|is\s+not|no\s+longer|instead\s+of|rather\s+than|e\.?g\.?"
    r"|for\s+example|such\s+as|creates?|created|generates?|generated|will\s+(?:write|create|generate)"
    r"|written|outputs?\s+to|template|placeholder|example|new\s+(?:file|changelog|entry)|renamed?"
    r"|moved?|schema\s+for|following\s+schema)\b|(?:^|\W)no\s+`|not\s+`", re.I)


def _asserts_path_present(sentence: str, token: str) -> bool:
    if ".." in token or "*" in token or token.endswith("/"):
        return False
    if _PATH_NOT_ASSERTION.search(sentence):
        return False
    return bool(_PATH_PRESENT.search(sentence))

# Tokens too generic to bind a subject. Same discipline as claims.py: a single
# shared generic word is coincidence, not the same fact.
_GENERIC = {
    "task", "data", "key", "name", "type", "get", "set", "creat", "updat",
    "delet", "rout", "api", "app", "src", "lib", "index", "config", "enabl",
    "check", "auth", "error", "statu", "messag", "detail", "request",
    "respons", "next", "server", "file", "path", "valu", "string", "number",
    "const", "export", "import", "return", "function", "class", "test",
    "spec", "util", "helper", "main", "node", "module", "package", "json",
    "true", "fals", "null", "undefin", "this", "that", "with", "from",
    "have", "been", "will", "were", "into", "must", "never", "alway",
    "befor", "after", "when", "then", "else", "code", "line", "doc",
    "read", "write", "chang", "commit", "branch", "push", "pull", "handler",
    "async", "await", "await", "public", "private", "static", "default",
    "object", "array", "list", "item", "count", "total", "text", "body",
    "post", "store", "feed", "component", "bound", "hash", "omit", "cannot",
    "possible", "side", "field", "param", "endpoint", "callback", "webhook",
}


# --------------------------------------------------------------------------
# tokens — the subject binding
# --------------------------------------------------------------------------

def _split_ident(text: str) -> list[str]:
    """camelCase / snake_case / kebab-case / prose -> word parts."""
    out = []
    for chunk in re.split(r"[^A-Za-z0-9]+", text or ""):
        out.extend(re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+", chunk))
    return out


def _norm(word: str) -> str:
    w = word.lower()
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("es") and not w.endswith("ses"):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s"):
        w = w[:-1]
    return w


def content_tokens(text: str) -> set:
    """Normalised content words: >=4 chars, not generic, not a bare number."""
    return {t for t in (_norm(w) for w in _split_ident(text))
            if len(t) >= 4 and t not in _GENERIC and not t.isdigit()}


# --------------------------------------------------------------------------
# the repo under probe
# --------------------------------------------------------------------------

def _run(cmd: list[str], cwd: str, timeout: int = 20) -> tuple[int, str]:
    """Read-only subprocess. Returns (rc, combined output). Never raises."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return -1, f"{type(e).__name__}: {e}"


def _is_git(repo: str) -> bool:
    rc, _ = _run(["git", "rev-parse", "--git-dir"], repo, timeout=10)
    return rc == 0


def _source_files(repo: str, limit: int = 4000) -> list[str]:
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".venv")]
        for f in files:
            if not f.endswith(_CODE_EXT):
                continue
            rel = os.path.relpath(os.path.join(root, f), repo)
            if _TEST_PATH.search(rel) or _is_fixture(rel):
                continue
            out.append(rel)
            if len(out) >= limit:
                return out
    return out


def _read(repo: str, rel: str, cap: int = 400_000) -> str:
    try:
        with open(os.path.join(repo, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read(cap)
    except OSError:
        return ""


# --------------------------------------------------------------------------
# probe 1 — the kill switch: an enforced retirement in the running code
# --------------------------------------------------------------------------

# The gate's own words, minus the part that exists to protect what it did NOT
# kill. `custody.ts` says "Points favours are unaffected" precisely so nobody
# rips those out; reading that clause as territory the switch closed is how a
# retirement starts flagging the features it was written to spare.
_STRING_LIT = re.compile(r'"([^"\n]{4,180})"|\'([^\'\n]{4,180})\'|`([^`\n]{4,180})`')
_PROTECTED = re.compile(
    r"\b(?:unaffected|untouched|unchanged|not killed|not affected|still (?:work|works|"
    r"move|moves|pay|pays|run|runs)|does not kill|deliberately left|read-only)\b", re.I)


def _gate_words(text: str, line_no: int, span: int = 4) -> str:
    """The sentence the gate returns to a caller — and only that.

    A literal near a 410 qualifies only if it says a closure happened. An
    OpenAPI route is one long block of description strings; without this the
    switch would inherit the vocabulary of every endpoint it documents and
    bind sentences about webhooks and World ID."""
    lines = text.splitlines()
    lo, hi = max(0, line_no - 1 - span), min(len(lines), line_no + span)
    out = []
    for chunk in lines[lo:hi]:
        for m in _STRING_LIT.finditer(chunk):
            lit = next(g for g in m.groups() if g is not None)
            if not _ACK.search(lit):
                continue
            for sentence in re.split(r"(?<=[.;])\s+", lit):
                if _PROTECTED.search(sentence):
                    continue
                out.append(sentence)
    return " ".join(out)


def find_kill_switches(repo: str) -> list[dict]:
    """Retirements the code ENFORCES, and the territory each one actually closes.

    Scope is the switch's own vocabulary: its constant name, the paths of the
    routes it gates, and the message the gate returns to a caller. Not the
    surrounding module's prose — a docblock explaining a retirement discusses
    the whole domain, and a scope built from it will bind sentences the switch
    never touched ("real money moves through this" is still true here: the
    campaign unlock pays by plain ERC-20 transfer, which is exactly what the
    retirement docblock says it spared).
    """
    switches: dict = {}
    for rel in _source_files(repo):
        text = _read(repo, rel)
        if not text:
            continue
        for m in _SWITCH_DECL.finditer(text):
            name = m.group(1)
            line = text.count("\n", 0, m.start()) + 1
            switches.setdefault(name, {
                "name": name, "decl_file": rel, "decl_line": line,
                "decl_text": text[m.start():m.end()].strip(),
                "words": name, "sites": []})

    # Where each switch is actually consulted, plus 410s that stand alone.
    named = set(switches)
    for rel in _source_files(repo):
        text = _read(repo, rel)
        if not text:
            continue
        lines = text.splitlines()
        gone_hits = [(i + 1, ln.strip()) for i, ln in enumerate(lines)
                     if _GONE_STATUS.search(ln)]
        gate_words = " ".join(_gate_words(text, n) for n, _ln in gone_hits)
        for name in named:
            if rel == switches[name]["decl_file"]:
                continue
            hits = [(i + 1, ln.strip()) for i, ln in enumerate(lines) if name in ln]
            if not hits:
                continue
            switches[name]["sites"].append({"file": rel, "hits": hits,
                                            "gone": gone_hits})
            switches[name]["words"] += " " + rel + " " + gate_words
        if gone_hits and not any(name in text for name in named):
            # A 410 with no named constant is still an enforced retirement.
            key = f"410:{rel}"
            switches[key] = {
                "name": f"HTTP 410 in {rel}", "decl_file": rel,
                "decl_line": gone_hits[0][0], "decl_text": gone_hits[0][1],
                "words": rel + " " + gate_words,
                "sites": [{"file": rel, "hits": gone_hits, "gone": gone_hits}]}

    out = []
    for sw in switches.values():
        scope = content_tokens(sw["words"])
        if not scope:
            continue
        sw["scope"] = scope
        out.append(sw)
    return out


def _grep(repo: str, needle: str, git: bool, paths: list[str] | None = None,
          limit: int = 5) -> tuple[str, str]:
    """One real grep. The pasted output is stdout, not a reconstruction."""
    if git:
        cmd = ["git", "grep", "-n", "--", needle] + (paths or [])
        shown = f'git grep -n -- "{needle}"' + (" " + " ".join(paths) if paths else "")
    else:
        cmd = ["grep", "-rn", needle] + (paths or ["."])
        shown = f'grep -rn "{needle}" ' + " ".join(paths or ["."])
    rc, out = _run(cmd, repo)
    keep = [ln for ln in out.splitlines()
            if ln.strip()
            and not any(f"/{d}/" in ln or ln.startswith(f"{d}/") for d in _SKIP_DIRS)
            and not _TEST_PATH.search(ln.split(":", 1)[0])
            and not _is_fixture(ln.split(":", 1)[0])
            and ln.split(":", 1)[0].endswith(_CODE_EXT)]
    if not keep and rc not in (0, 1):
        keep = [f"(exit {rc}) {out.strip()[:200]}"]
    return shown, "\n".join(ln[:180] for ln in keep[:limit])


def _switch_evidence(repo: str, sw: dict, git: bool) -> list[dict]:
    """What the running system does, in its own words: the switch and the
    gates it closes. Docs are excluded on purpose — a second document agreeing
    with the first is exactly the evidence this class exists to replace."""
    ev = []
    if not sw["name"].startswith("HTTP 410"):
        cmd, out = _grep(repo, sw["name"], git)
        ev.append({"cmd": cmd, "output": out or
                   f"{sw['decl_file']}:{sw['decl_line']}: {sw['decl_text']}"})
    gate_files = sorted({s["file"] for s in sw["sites"] if s.get("gone")})[:4]
    if gate_files:
        cmd, out = _grep(repo, "410", git, gate_files)
        if out:
            ev.append({"cmd": cmd, "output": out})
    if not ev:
        ev.append({"cmd": f"(read) {sw['decl_file']}:{sw['decl_line']}",
                   "output": sw["decl_text"]})
    return ev


# --------------------------------------------------------------------------
# probe 2 — the self-probing sentence: a quoted command WITH its result
# --------------------------------------------------------------------------

def _safe_git_command(cmd: str) -> list[str] | None:
    import shlex
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return None
    if not parts or parts[0] != "git" or len(parts) < 2:
        return None
    if parts[1] not in _SAFE_GIT:
        return None
    if any(p.startswith(("--output", "--exec", "-o")) for p in parts):
        return None
    return parts


def _probe_command(repo: str, cmd: str, stated: str) -> dict:
    parts = _safe_git_command(cmd)
    if parts is None:
        return {"verdict": UNVERIFIABLE, "probe": cmd, "output": "",
                "why": "not a read-only git command this probe is allowed to run"}
    counted = parts[1] in ("log", "grep", "ls-files")
    run_parts = parts + (["--format=%H"] if parts[1] == "log" else [])
    shown = " ".join(parts) + (" --format=%H | wc -l" if counted and parts[1] == "log"
                               else " | wc -l" if counted else "")
    rc, out = _run(run_parts, repo)
    if rc not in (0, 1):
        return {"verdict": UNVERIFIABLE, "probe": shown, "output": out.strip()[:300],
                "why": f"command exited {rc} in this checkout"}
    lines = [ln for ln in out.splitlines() if ln.strip()]
    actual = len(lines)
    m = re.search(r"-?\d+", stated)
    if not m:
        return {"verdict": UNVERIFIABLE, "probe": shown, "output": str(actual),
                "why": f"stated result {stated!r} is not a number this probe can compare"}
    claimed = int(m.group(0))
    return {"verdict": UPHELD if claimed == actual else CONTRADICTED,
            "probe": shown, "output": str(actual),
            "why": (f"doc says {claimed}, the command returns {actual}"
                    if claimed != actual else
                    f"doc says {claimed}, the command returns {actual}")}


# --------------------------------------------------------------------------
# probe 3 — a named file, asked of git
# --------------------------------------------------------------------------

def _probe_path(repo: str, path: str, git: bool) -> dict:
    if git:
        rc, out = _run(["git", "ls-files", "--error-unmatch", "--", path], repo)
        shown = f"git ls-files -- {path}"
        if rc == 0 and out.strip():
            return {"verdict": UPHELD, "probe": shown, "output": out.strip()[:200],
                    "why": "tracked in the repo"}
        # not tracked under that exact path — try the basename before judging
        rc2, out2 = _run(["git", "ls-files", "--", f"*{os.path.basename(path)}"], repo)
        if rc2 == 0 and out2.strip():
            return {"verdict": UPHELD, "probe": f"git ls-files -- *{os.path.basename(path)}",
                    "output": out2.strip().splitlines()[0][:200],
                    "why": "tracked (matched on basename)"}
        # Untracked is not disproved. `config-demo.json` is WRITTEN by
        # scripts/demo_seed.py and gitignored, so "git tracks no such file" was
        # exactly what the doc predicted — and this probe called the doc a liar
        # three times over. Git is the wrong witness for a generated file; ask
        # the filesystem, and ask whether the repo deliberately ignores it.
        on_disk = os.path.exists(os.path.join(repo, path))
        rc3, _ = _run(["git", "check-ignore", "-q", "--", path], repo)
        ignored = rc3 == 0
        if on_disk or ignored:
            why = ("present on disk but deliberately untracked"
                   if on_disk and ignored else
                   "present on disk, untracked" if on_disk else
                   "gitignored by this repo, so its absence from git proves nothing")
            return {"verdict": UNVERIFIABLE, "probe": shown,
                    "output": "(not tracked)",
                    "why": f"{path}: {why} — git cannot settle this claim"}
        return {"verdict": CONTRADICTED, "probe": shown, "output": "(no output)",
                "why": f"the doc names {path}; git tracks no such file "
                       f"and it is not on disk"}
    exists = os.path.exists(os.path.join(repo, path))
    return {"verdict": UPHELD if exists else CONTRADICTED,
            "probe": f"test -f {path}", "output": "exists" if exists else "missing",
            "why": "present on disk" if exists else f"the doc names {path}; it is not there"}


# --------------------------------------------------------------------------
# probe 4 — on-chain authority. Usually unverifiable, and says so.
# --------------------------------------------------------------------------

def _probe_chain(address: str, rpc_url: str | None, allow_network: bool) -> dict:
    elided = "…" in address or "..." in address
    shown = f"eth_call owner() -> {address}"
    if elided:
        return {"verdict": UNVERIFIABLE, "probe": shown, "output": "",
                "why": f"the doc elides the address ({address}); nothing to call. "
                       "Write it in full to make this checkable."}
    if not rpc_url or not allow_network:
        return {"verdict": UNVERIFIABLE, "probe": shown, "output": "",
                "why": "no RPC available — set claims.probes.rpc_url and pass "
                       "--net to let this probe reach the chain"}
    import urllib.request
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                          "params": [{"to": address, "data": "0x8da5cb5b"},
                                     "latest"]}).encode()
    req = urllib.request.Request(rpc_url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
    except Exception as e:  # noqa: BLE001 — any RPC failure is unverifiable, not false
        return {"verdict": UNVERIFIABLE, "probe": shown, "output": "",
                "why": f"RPC call failed: {type(e).__name__}: {e}"}
    result = (body or {}).get("result")
    if not result or len(result) < 42:
        return {"verdict": UNVERIFIABLE, "probe": shown, "output": str(body)[:200],
                "why": "RPC returned no owner() value"}
    return {"verdict": UPHELD, "probe": shown, "output": "0x" + result[-40:],
            "why": "read from chain; compare against the doc's stated owner"}


# --------------------------------------------------------------------------
# assertions — the sentences a probe can hang off
# --------------------------------------------------------------------------

def split_assertions(text: str) -> list[dict]:
    """Markdown -> logical assertions, each carrying the heading it sits under.

    The heading is not decoration: under `## Context` or `## Stack`, a bare
    noun phrase ("on-chain USDC escrow") IS a present-tense capability claim,
    with no verb to detect. That is the exact sentence shape FAVOUR's CLAUDE.md
    used to tell every agent the escrow was live."""
    blocks, buf, fenced, heading = [], [], False, ""
    buf_heading = ""

    def flush():
        if buf:
            blocks.append({"text": " ".join(buf), "heading": buf_heading})

    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        stripped = line.strip()
        m = re.match(r"^#{1,6}\s+(.*)", line)
        if m:
            flush()
            buf, buf_heading = [], ""
            heading = m.group(1).strip()
            continue
        starts = bool(re.match(r"^(?:[-*+]\s|\d+[.)]\s|>\s)", stripped))
        if not stripped or starts:
            flush()
            buf, buf_heading = [], heading
            if starts:
                buf = [re.sub(r"^(?:[-*+]\s|\d+[.)]\s|>\s)", "", stripped)]
            continue
        if not buf:
            buf_heading = heading
        buf.append(stripped)
    flush()

    out = []
    for block in blocks:
        body = block["text"].strip()
        if len(body) < 12:
            continue
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z*`\-])", body):
            part = part.strip()
            if len(part) >= 12:
                out.append({"text": part, "heading": block["heading"]})
    return out


def _line_of(haystack: str, needle: str) -> int | None:
    """Where the assertion actually sits in the file (prose is re-wrapped)."""
    probe = re.sub(r"\s+", " ", re.sub(r"[*`]", "", needle))[:48].strip()
    if not probe:
        return None
    for i, line in enumerate(haystack.splitlines(), 1):
        flat = re.sub(r"\s+", " ", re.sub(r"[*`]", "", line))
        if probe[:32] and probe[:32] in flat:
            return i
    head = probe.split(" ")[0]
    for i, line in enumerate(haystack.splitlines(), 1):
        if head and head in line:
            return i
    return None


def _rule_docs(repo: str) -> list[tuple[str, str]]:
    """(relative path, text) for every agent-rules file this repo commits."""
    from helicon.connectors.agent_rules import KNOWN_RULE_FILES, KNOWN_RULE_PATHS
    from glob import glob
    out = []
    for name in KNOWN_RULE_FILES:
        if os.path.isfile(os.path.join(repo, name)):
            out.append((name, _read(repo, name)))
    for rel in KNOWN_RULE_PATHS:
        if os.path.isfile(os.path.join(repo, rel)):
            out.append((rel, _read(repo, rel)))
    for mdc in sorted(glob(os.path.join(repo, ".cursor", "rules", "*.mdc"))):
        rel = os.path.relpath(mdc, repo)
        out.append((rel, _read(repo, rel)))
    return [(rel, text) for rel, text in out if text.strip()]


def _cube_index(conn, repo_name: str) -> dict:
    """source_ref -> stored provenance, so a probed sentence carries the same
    source + freshness the rest of the store gives a claim. Absent (unscanned
    repo) is fine: the probe still runs, it just says the claim is unstored."""
    if conn is None:
        return {}
    try:
        rows = conn.execute(
            "SELECT id, source_ref, title, created_at, last_reinforced, "
            "confidence, review_status, content FROM helicon_cubes "
            "WHERE source = 'agent-rules' AND source_ref LIKE ? "
            "AND merged_into IS NULL", (f"{repo_name}/%",)).fetchall()
    except Exception:
        return {}
    return {r["source_ref"]: dict(r) for r in rows}


def _cube_for(cubes: dict, repo_name: str, rel: str, assertion: str) -> dict | None:
    """The stored claim this sentence belongs to, when the repo has been
    scanned. That is where the sentence's source and freshness already live —
    the probe hangs off it rather than inventing a second provenance."""
    flat = re.sub(r"\s+", " ", assertion)[:24]
    for ref, row in cubes.items():
        if not ref.startswith(f"{repo_name}/{rel}#"):
            continue
        if flat and re.sub(r"\s+", " ", row["content"] or "").find(flat) >= 0:
            return row
    return None


# --------------------------------------------------------------------------
# the pass
# --------------------------------------------------------------------------

def probe_docs(conn, repo_path: str, config: dict | None = None,
               allow_network: bool = False) -> list[dict]:
    """Every probe-able sentence in a repo's instruction docs, with a verdict.

    conn may be None: the probes read the repo either way, and the store only
    supplies provenance for sentences it has already ingested."""
    repo = os.path.abspath(os.path.expanduser(repo_path))
    repo_name = os.path.basename(os.path.normpath(repo))
    git = _is_git(repo)
    probes_cfg = ((config or {}).get("claims", {}) or {}).get("probes", {}) or {}
    rpc_url = probes_cfg.get("rpc_url") or os.environ.get("HELICON_RPC_URL")

    switches = find_kill_switches(repo)
    evidence: dict = {}
    cubes = _cube_index(conn, repo_name)
    results = []

    docs = _rule_docs(repo)
    # A word that saturates the docs cannot name a subject. The product's own
    # name is in every third sentence ("FAVOUR no longer holds funds"), and a
    # gate message that mentions it would otherwise let one retirement bind
    # the entire corpus. Same instinct as the stoplist in claims.py, learned
    # per-repo instead of hardcoded.
    blocks = [(rel, b) for rel, text in docs for b in split_assertions(text)]
    freq: dict = {}
    for _rel, b in blocks:
        for t in content_tokens(b["text"]):
            freq[t] = freq.get(t, 0) + 1
    # A frequency estimate off eight sentences is noise, not a corpus: in a
    # short doc "fund" appears twice and looks saturated. Needs both a corpus
    # worth measuring and a real count before it can silence a token.
    saturated = {t for t, n in freq.items()
                 if len(blocks) >= 20 and n >= 4 and n / len(blocks) > 0.20}
    # The product's own name is not a subject. It appears in the gate message
    # ("FAVOUR no longer holds funds in escrow") because the gate is polite,
    # and binding on it would let one retirement flag every sentence that says
    # the product's name — including a rebrand note. The docs name the product
    # in their own title; take it from there and from the repo directory.
    product = content_tokens(repo_name)
    for _rel, text in docs:
        for line in text.splitlines():
            if line.startswith("# "):
                product |= content_tokens(line)
                break
    saturated |= product

    for rel, text in docs:
        for block in split_assertions(text):
            assertion, heading = block["text"], block["heading"]
            cube = _cube_for(cubes, repo_name, rel, assertion)
            line = _line_of(text, assertion)
            base = {"file": rel, "line": line, "sentence": assertion,
                    "heading": heading, "cube_id": (cube or {}).get("id"),
                    "claim_age": (cube or {}).get("created_at"),
                    "stored": cube is not None}
            for res in _derive_and_run(repo, git, assertion, heading, switches,
                                       evidence, rpc_url, allow_network,
                                       saturated):
                results.append({**base, **res})
    return results


def _derive_and_run(repo, git, assertion, heading, switches, evidence,
                    rpc_url, allow_network, saturated=frozenset()) -> list[dict]:
    """Sentence -> the probes its own shape earns. Order matters: an on-chain
    authority claim is answered by the chain, not by a grep that would happen
    to agree with it."""
    out = []
    tokens = content_tokens(assertion)

    # chain — an authority claim about an address
    addr = _ADDRESS.search(assertion)
    if addr and _AUTHORITY.search(assertion):
        res = _probe_chain(addr.group(0), rpc_url, allow_network)
        out.append({"kind": "chain", **res})
        return out  # the chain is the only witness that counts here

    # command — the sentence quotes a command and its result
    for m in _CMD_RESULT.finditer(assertion):
        cmd, stated = m.group(1).strip(), m.group(2).strip()
        if cmd.split(" ")[0] in ("git",):
            out.append({"kind": "command", **_probe_command(repo, cmd, stated)})

    # killswitch — the code enforces a retirement this sentence ignores
    availability = bool(_AVAILABILITY.search(assertion)) or bool(_GATED.search(assertion))
    if not availability and heading:
        h = heading.lower()
        availability = any(k in h for k in _CAPABILITY_HEADINGS)
    if availability and not _ACK.search(assertion):
        for sw in switches:
            bound = sorted((tokens & sw["scope"]) - set(saturated))
            if not bound:
                continue
            key = sw["name"]
            if key not in evidence:
                evidence[key] = _switch_evidence(repo, sw, git)
            ev = evidence[key]
            out.append({
                "kind": "killswitch", "verdict": CONTRADICTED,
                "probe": ev[0]["cmd"], "output": ev[0]["output"], "evidence": ev,
                "why": (f"the running code retires this: {sw['decl_file']}:"
                        f"{sw['decl_line']} {sw['decl_text']} — the sentence "
                        f"still presents it as available (bound on: "
                        f"{', '.join(bound)})"),
                "switch": sw["name"]})
            break  # one switch per sentence; the first is the closest binding

    # path — a file the doc asserts is PRESENT (not merely names: a schema
    # subject, an example, a generated/created file, or a "there is no `x`"
    # negation are mentions, not existence claims).
    for m in _PATH_TOKEN.finditer(assertion):
        token = m.group(1)
        if _asserts_path_present(assertion, token):
            out.append({"kind": "path", **_probe_path(repo, token, git)})

    return out


# --------------------------------------------------------------------------
# rendering + filing
# --------------------------------------------------------------------------

def format_probes(results: list[dict], repo_path: str) -> str:
    repo_name = os.path.basename(os.path.normpath(os.path.abspath(repo_path)))
    order = {CONTRADICTED: 0, UNVERIFIABLE: 1, UPHELD: 2}
    lines = [f"Document vs live system — {repo_name}", ""]
    if not results:
        lines.append("  No probe-able assertion found in this repo's instruction "
                     "docs. That is UNMEASURED, not clean.")
        return "\n".join(lines)

    counts = {v: sum(1 for r in results if r["verdict"] == v)
              for v in (CONTRADICTED, UNVERIFIABLE, UPHELD)}
    docs = sorted({r["file"] for r in results})
    lines.append(f"  {len(results)} probe(s) over {len(docs)} doc(s): "
                 f"{', '.join(docs)}")
    lines.append("")

    for r in sorted(results, key=lambda x: (order.get(x["verdict"], 9),
                                            x["file"], x["line"] or 0)):
        if r["verdict"] == UPHELD:
            continue
        where = f"{r['file']}:{r['line']}" if r["line"] else r["file"]
        sentence = re.sub(r"\s+", " ", r["sentence"])
        if len(sentence) > 150:
            sentence = sentence[:147] + "..."
        lines.append(f"  {r['verdict']:<13} {where}   [{r['kind']}]")
        lines.append(f'     claim   "{sentence}"')
        for ev in (r.get("evidence") or [{"cmd": r["probe"], "output": r.get("output", "")}]):
            lines.append(f"     probe   $ {ev['cmd']}")
            for i, ln in enumerate(str(ev.get("output") or "").splitlines()[:5]):
                lines.append(f"     {'output ' if i == 0 else '       '} {ln}")
        lines.append(f"     why     {r['why']}")
        if not r.get("stored"):
            lines.append("     note    not in the store yet — probed from the "
                         "file, so it carries no ingest freshness")
        lines.append("")

    upheld = [r for r in results if r["verdict"] == UPHELD]
    if upheld:
        lines.append(f"  UPHELD ({len(upheld)}) — the probe ran and the doc is right:")
        for r in upheld[:12]:
            where = f"{r['file']}:{r['line']}" if r["line"] else r["file"]
            lines.append(f"     {where:<18} [{r['kind']:<9}] $ {r['probe']}  ->  "
                         f"{str(r.get('output', '')).splitlines()[0][:60] if r.get('output') else 'ok'}")
        if len(upheld) > 12:
            lines.append(f"     … {len(upheld) - 12} more")
        lines.append("")

    lines.append(f"  {counts[CONTRADICTED]} contradicted · "
                 f"{counts[UNVERIFIABLE]} unverifiable · {counts[UPHELD]} upheld")
    if counts[UNVERIFIABLE]:
        lines.append("  An unverifiable claim is not a passing claim. It is a "
                     "probe you have not made runnable yet.")
    return "\n".join(lines)


def probe_scan(conn, repo_path: str, config: dict | None = None,
               allow_network: bool = False) -> dict:
    """File each contradicted sentence once (idempotent by pair_key), in the
    same audit shape as claim_scan so FINDINGS / resolve work unchanged."""
    results = probe_docs(conn, repo_path, config, allow_network)
    existing = set()
    for row in conn.execute(
        "SELECT details FROM audit_log WHERE audit_type = 'factual' "
        "AND details LIKE '%probe_key%'"
    ):
        try:
            k = json.loads(row["details"]).get("probe_key")
            if k:
                existing.add(k)
        except (json.JSONDecodeError, TypeError):
            pass

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    filed, skipped = [], []
    for r in results:
        if r["verdict"] != CONTRADICTED:
            continue
        key = f"probe|{r['file']}:{r['line']}|{r['kind']}"
        if key in existing:
            skipped.append(key)
            continue
        sentence = re.sub(r"\s+", " ", r["sentence"])[:180]
        finding = AuditResult(
            audit_type="factual", target_type="cube",
            target_id=r.get("cube_id") or f"{r['file']}:{r['line']}",
            finding=(f"Document contradicted by the running system: "
                     f"{r['file']}:{r['line']} — \"{sentence}\" ({r['why']})"),
            severity="critical", proposed_action="flag",
            details={"probe_key": key, "kind": r["kind"], "file": r["file"],
                     "line": r["line"], "sentence": sentence,
                     "probe": r["probe"], "probe_output": r.get("output", ""),
                     "why": r["why"], "cube_id": r.get("cube_id"),
                     "judged_by": "probe"},
            audited_at=now)
        insert_audit(conn, finding)
        filed.append({"probe_key": key, "finding": finding.finding})
    conn.commit()
    return {"results": results, "filed": filed, "already_filed": skipped,
            "contradicted": sum(1 for r in results if r["verdict"] == CONTRADICTED),
            "unverifiable": sum(1 for r in results if r["verdict"] == UNVERIFIABLE),
            "upheld": sum(1 for r in results if r["verdict"] == UPHELD)}
