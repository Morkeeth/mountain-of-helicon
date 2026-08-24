"""Execute-and-compare: RUN a documented command and grade its claimed outcome.

THE WEDGE (PRD-2026-08 §4-6). The existence tier (pointers.py, commands.py) proves a
path resolves and a command NAME is defined — that is commoditized (ctxlint, agents-lint,
cclint all ship it). The uncrowded lane is proving the claim is TRUE: a context file that
says "`pytest -q` passes" or "`npm run build` succeeds" is only honest if the command
still exits 0. Nobody else RUNS the documented command. 75.9% of context files carry
test/build procedures (arXiv:2511.12884) — this is the surface that rots silently.

    doc says "`pytest -q` passes"   →   run it   →   exit 0 = UPHELD, exit != 0 = CONTRADICTED

SAFETY — read before changing anything here.
- Execution is OPT-IN. `check_execution(repo, execute=False)` is the default and runs
  NOTHING; it lists the claims it FOUND as UNVERIFIABLE. A stranger's repo is never
  executed unless the caller explicitly asks (review.py gates it behind HELICON_EXECUTE=1).
- A strict ALLOWLIST gates the verb class: only test/build/lint verbs (pytest, npm test,
  npm run build|lint, yarn/pnpm equivalents, make test|lint, vitest, tsc, tox). Anything
  else — and every install/deploy/publish/rm/curl/wget/git-push/sudo/ssh token — is
  UNVERIFIABLE and NEVER executed. The denylist is checked twice: on the command itself
  and (for npm/yarn/pnpm) on the resolved package.json script BODY, so `npm test` whose
  script shells out to `curl … | sh` is refused rather than run.
- HONEST LIMIT: the allowlist gates the verb, but running ANY test/build command executes
  arbitrary repo code (conftest.py, the package.json script body, a Makefile recipe). No
  allowlist can prevent that — opt-in is the mitigation, not a sandbox. We add best-effort
  hardening (timeout, process-group kill, stdin closed, proxies pointed at a dead port,
  CI=1) but the real gate is: the human opted in to run THIS repo's tests.

Run standalone:  python3 -m helicon.execute <repo_root> --execute
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys

from helicon.pointers import DEFAULT_INSTRUCTION_FILES, _NEGATION

# Per-command verdicts (match probes.py vocabulary).
UPHELD = "UPHELD"
CONTRADICTED = "CONTRADICTED"
UNVERIFIABLE = "UNVERIFIABLE"

DEFAULT_TIMEOUT = 120  # seconds; a hung test suite must not hang the review.

# --------------------------------------------------------------------------
# claim parsing
# --------------------------------------------------------------------------

# A claimed outcome sitting NEAR a command in code font. Two orders are accepted:
#   "`pytest -q` passes"            (command then claim)
#   "All tests pass: `pytest -q`"   (claim then command)
# The claim vocabulary is deliberately narrow — words that assert SUCCESS, plus a
# "N/N" count shape. A sentence with no success word yields no runnable claim.
_PASS_WORD = (
    r"passes|pass|passing|succeeds|succeed|succeeding|green|all green|works|working|"
    r"exits?\s+0|exit\s+code\s+0|clean|ok\b|✓|✅"
)
_COUNT = r"\d+\s*/\s*\d+|\d+\s+of\s+\d+|all\s+\d+"
_CLAIM_AFTER = re.compile(
    r"`([^`\n]+)`[^\n.;]{0,40}?\b(?:" + _PASS_WORD + r"|" + _COUNT + r")",
    re.I,
)
_CLAIM_BEFORE = re.compile(
    r"\b(?:" + _PASS_WORD + r"|" + _COUNT + r")\b[^\n`]{0,40}?`([^`\n]+)`",
    re.I,
)


def _claims_in_line(line: str) -> list[str]:
    """The distinct commands on this line that carry a success/count claim nearby."""
    found: list[str] = []
    for rx in (_CLAIM_AFTER, _CLAIM_BEFORE):
        for m in rx.finditer(line):
            cmd = m.group(1).strip()
            if cmd and cmd not in found:
                found.append(cmd)
    return found


# --------------------------------------------------------------------------
# allowlist / denylist
# --------------------------------------------------------------------------

# The allowlist is expressed as command PREFIXES (tokenized). A parsed command is
# runnable only if, after stripping a leading `python[3] -m`, its head matches one of
# these verb shapes. Nothing here mutates state, publishes, or reaches outward.
_ALLOW_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("pytest",),
    ("py.test",),
    ("tox",),
    ("vitest",),
    ("tsc",),
    ("jest",),
    ("npm", "test"),
    ("npm", "run", "test"),
    ("npm", "run", "build"),
    ("npm", "run", "lint"),
    ("npm", "run", "typecheck"),
    ("npm", "run", "check"),
    ("yarn", "test"),
    ("yarn", "build"),
    ("yarn", "lint"),
    ("pnpm", "test"),
    ("pnpm", "run", "test"),
    ("pnpm", "run", "build"),
    ("pnpm", "run", "lint"),
    ("make", "test"),
    ("make", "lint"),
    ("make", "check"),
    ("cargo", "test"),
    ("cargo", "build"),
    ("go", "test"),
)

# Hard denylist — a token that means state-change, install, or reaching outward. If any
# appears ANYWHERE in the command string (or a resolved npm script body), the command is
# UNVERIFIABLE and is NEVER executed, even if its head somehow matched the allowlist.
_DENY_TOKENS = (
    "install", "deploy", "publish", "release", "push", "curl", "wget", "ssh", "scp",
    "sudo", "rm ", "rm\t", "rmdir", "mkfs", "dd ", "chmod", "chown", "npx", "pip",
    "pipx", "uv ", "poetry", "brew", "apt", "yum", "docker", "kubectl", "terraform",
    "git ", "gh ", "> /", ">/", "sh -c", "bash -c", "eval ", "source ", "&&", "||",
    ";", "|", "`", "$(",
)


def _denied(text: str) -> str | None:
    """Return the first denylist token present in `text`, or None if clean."""
    low = text.lower()
    for tok in _DENY_TOKENS:
        if tok in low:
            return tok.strip()
    return None


def _tokenize(cmd: str) -> list[str] | None:
    try:
        return shlex.split(cmd)
    except ValueError:
        return None


def _strip_python_m(toks: list[str]) -> list[str]:
    # `python -m pytest -q` / `python3 -m pytest` -> `pytest -q`
    if toks and toks[0] in ("python", "python3") and len(toks) >= 3 and toks[1] == "-m":
        return toks[2:]
    return toks


def _match_allow(toks: list[str]) -> tuple[str, ...] | None:
    core = _strip_python_m(toks)
    for pref in _ALLOW_PREFIXES:
        if len(core) >= len(pref) and tuple(core[: len(pref)]) == pref:
            return pref
    return None


def _npm_script_name(toks: list[str]) -> str | None:
    """For npm/yarn/pnpm, the script whose body we must inspect for denied tokens."""
    core = _strip_python_m(toks)
    if not core:
        return None
    if core[0] in ("npm", "pnpm"):
        if len(core) >= 3 and core[1] == "run":
            return core[2]
        if len(core) >= 2 and core[1] == "test":
            return "test"
    if core[0] == "yarn" and len(core) >= 2:
        return core[1]
    return None


def _pkg_script_body(repo_root: str, name: str) -> str | None:
    import json
    try:
        with open(os.path.join(repo_root, "package.json"), encoding="utf-8") as fh:
            return (json.load(fh).get("scripts", {}) or {}).get(name)
    except Exception:
        return None


def _build_argv(toks: list[str]) -> list[str]:
    """The argv we actually exec. Normalize bare `pytest` -> `sys.executable -m pytest`
    so it resolves even when the tool is only importable in the active venv (this repo
    runs from a .venv and bare `pytest` is not always on the subprocess PATH)."""
    core = _strip_python_m(toks)
    if core and core[0] in ("pytest", "py.test"):
        return [sys.executable, "-m", "pytest", *core[1:]]
    return list(toks)


# --------------------------------------------------------------------------
# sandboxed run
# --------------------------------------------------------------------------

def _sandbox_env() -> dict:
    env = dict(os.environ)
    # CI=1 keeps vitest/jest/npm test out of interactive WATCH mode (which would hang
    # until the timeout on every run).
    env["CI"] = "1"
    env["NPM_CONFIG_YES"] = "true"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Best-effort network denial: point every proxy var at a dead local port. This is
    # NOT a hard sandbox — a command that opens a raw socket bypasses it. The allowlist
    # is the real gate; this only trims the easy outward calls.
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "all_proxy", "ftp_proxy"):
        env[var] = "http://127.0.0.1:9"
    env["NO_PROXY"] = ""
    return env


def _run_sandboxed(argv: list[str], cwd: str, timeout: int) -> tuple[int, str]:
    """Run argv in `cwd`, capped at `timeout`s, stdin closed, in its own process group
    so a timeout kills the whole tree (npm spawns node grandchildren that outlive a
    plain child-kill). Returns (exit_code, combined stdout+stderr). Never raises;
    a timeout is exit code 124 (the shell convention), a spawn failure is -1."""
    try:
        p = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=_sandbox_env(), start_new_session=True,
        )
    except (OSError, ValueError) as e:
        return -1, f"{type(e).__name__}: {e}"
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out or ""
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        try:
            out, _ = p.communicate(timeout=5)
        except Exception:
            out = ""
        return 124, (out or "") + f"\n[helicon] killed after {timeout}s timeout"


def _kill_tree(p: subprocess.Popen) -> None:
    import signal
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            p.kill()
        except Exception:
            pass


def _tail(text: str, n: int = 900) -> str:
    text = (text or "").strip()
    return text[-n:] if len(text) > n else text


# --------------------------------------------------------------------------
# grade one claim
# --------------------------------------------------------------------------

def _gate(repo_root: str, cmd: str) -> tuple[list[str] | None, str]:
    """Decide whether `cmd` is safe to run. Returns (argv_or_None, reason).
    argv is None => UNVERIFIABLE with the reason; else argv is what to exec."""
    toks = _tokenize(cmd)
    if not toks:
        return None, "command does not parse as a shell token list"
    deny = _denied(cmd)
    if deny:
        return None, f"contains a non-runnable token ({deny!r}); allowlist blocks it"
    if _match_allow(toks) is None:
        return None, "not on the test/build/lint allowlist (never executed)"
    # npm/yarn/pnpm: the verb is allowed, but the SCRIPT BODY is arbitrary. Refuse if it
    # shells out to something denied.
    sname = _npm_script_name(toks)
    if sname is not None:
        body = _pkg_script_body(repo_root, sname)
        if body is None:
            return None, f"no '{sname}' script in package.json to run"
        bdeny = _denied(body)
        if bdeny:
            return None, (f"package.json script {sname!r} body contains {bdeny!r} — "
                          "refused, not run")
    return _build_argv(toks), "allowlisted"


def _grade_claim(repo_root: str, cmd: str, line_no: int, rel: str, line: str,
                 execute: bool, timeout: int) -> dict:
    where = f"{rel}:{line_no}"
    base = {"kind": "execute", "raw": cmd, "file": rel, "line_no": line_no,
            "claim_line": line.strip()[:160]}
    argv, reason = _gate(repo_root, cmd)
    if argv is None:
        return {**base, "verdict": UNVERIFIABLE, "exit": None, "output": "",
                "receipt": f"{where} — `{cmd}` not run: {reason}"}
    if not execute:
        return {**base, "verdict": UNVERIFIABLE, "exit": None, "output": "",
                "receipt": f"{where} — `{cmd}` claims success but was not run "
                           "(set HELICON_EXECUTE=1 to verify)"}
    rc, out = _run_sandboxed(argv, repo_root, timeout)
    tail = _tail(out)
    if rc == 0:
        return {**base, "verdict": UPHELD, "exit": rc, "output": tail,
                "receipt": f"{where} — `{cmd}` claimed success and exited 0 (UPHELD)"}
    return {**base, "verdict": CONTRADICTED, "exit": rc, "output": tail,
            "receipt": f"{where} — `{cmd}` claims success but exited {rc} "
                       f"(CONTRADICTED)\n      $ {' '.join(argv)}\n      "
                       + (tail.replace('\n', '\n      ') if tail else "(no output)")}


# --------------------------------------------------------------------------
# public entry
# --------------------------------------------------------------------------

def check_execution(repo_root: str, files: list[str] | None = None, *,
                    execute: bool = False, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Find documented commands that carry a success claim, and (opt-in) RUN the
    allowlisted ones to grade the claim against reality.

    Returns a rot.py-shaped dict (rid, verdict, checked, broken, receipts). Per-command
    verdicts live on each receipt: UPHELD / CONTRADICTED / UNVERIFIABLE, each with the
    real exit code and an output tail as the receipt. Top-level:
      verdict  = ROT FOUND (any CONTRADICTED) / CLEAN (some UPHELD, none contradicted)
                 / UNMEASURED (nothing executed — not opted in, or none allowlisted)
      checked  = commands actually executed (UPHELD + CONTRADICTED)
      broken   = CONTRADICTED count (feeds review.py's headline + grade)

    execute=False (default) runs NOTHING and reports every found claim UNVERIFIABLE — a
    stranger's repo is never executed without an explicit opt-in.
    """
    targets = [f for f in (files or DEFAULT_INSTRUCTION_FILES)
               if os.path.exists(os.path.join(repo_root, f))]

    receipts: list[dict] = []
    read_files: list[str] = []
    seen: set[str] = set()
    for rel in targets:
        try:
            with open(os.path.join(repo_root, rel), encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        read_files.append(rel)
        for i, line in enumerate(lines, 1):
            for cmd in _claims_in_line(line):
                if cmd in seen:
                    continue
                # A DESCRIBED failure ("`npm run old` no longer passes") is not a claim
                # to run or convict — the doc already says it does not pass.
                prose = line.replace(f"`{cmd}`", " ")
                if _NEGATION.search(prose):
                    continue
                seen.add(cmd)
                receipts.append(
                    _grade_claim(repo_root, cmd, i, rel, line, execute, timeout))

    executed = [r for r in receipts if r["verdict"] in (UPHELD, CONTRADICTED)]
    contradicted = [r for r in receipts if r["verdict"] == CONTRADICTED]
    if not executed:
        verdict = "UNMEASURED"
    else:
        verdict = "ROT FOUND" if contradicted else "CLEAN"

    return {
        "rid": "R15",
        "name": "Documented command RAN vs its claim",
        "verdict": verdict,
        "checked": len(executed),
        "broken": len(contradicted),
        "files": read_files,
        "executed": execute,
        "receipts": receipts,          # all: upheld, contradicted, unverifiable
    }


def format_execution(res: dict) -> str:
    head = f"[{res['rid']}] {res['name']}: {res['verdict']}"
    if res["verdict"] == "UNMEASURED" and not res.get("executed"):
        found = len(res["receipts"])
        if found:
            return head + (f"  ({found} claim{'' if found == 1 else 's'} found; not run"
                           " — set HELICON_EXECUTE=1 to verify)")
        return head + "  (no documented command carries a success claim)"
    head += f"  ({res['checked']} ran, {res['broken']} contradicted)"
    lines = [head]
    for r in res["receipts"]:
        mark = {"UPHELD": "✓", "CONTRADICTED": "✗", "UNVERIFIABLE": "·"}[r["verdict"]]
        lines.append(f"  {mark} {r['verdict']} {r['receipt']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python3 -m helicon.execute <repo_root> [--execute] "
              "[instruction_file ...]")
        return 2
    execute = "--execute" in args
    rest = [a for a in args if a != "--execute"]
    repo = rest[0]
    files = rest[1:] or None
    res = check_execution(repo, files, execute=execute)
    print(format_execution(res))
    return 1 if res["verdict"] == "ROT FOUND" else 0


if __name__ == "__main__":
    raise SystemExit(main())
