"""The inert-rule class — a rule nobody ever acted on.

PROTOTYPE. Not wired into the rot exam: the exam's class count is a product
claim and belongs to Oscar, not to this module.

Every class R1-R13 asks whether a rule is still TRUE. None asks whether it
CHANGED WHAT ANYONE DID. A rule that is correct, current, unambiguous and that
no code, comment, commit message or non-instruction doc has ever referenced is
invisible to all thirteen — and it is the most common way a CLAUDE.md rots,
because nothing about it ever looks wrong.

The signal, stated so it can be argued with: a rule names things. Identifiers,
paths, flags, tools, quoted terms. If none of the things a rule names appears
anywhere in the repo except the instruction files that state it, nothing has
enacted it. That is a CANDIDATE for inert, not a verdict — the rule may be
enacted by a name it does not use, and this module cannot see that.

Two deliberate abstentions, both learned today:

  A rule with no distinctive token ("Be careful.") is skipped rather than
  flagged. Flagging it would be a verdict manufactured from the absence of a
  probe, which is the empty-set defect in a new coat.

  A rule referenced only by ANOTHER instruction file is still inert. Two docs
  agreeing is not evidence that anything was done, and this is the failure mode
  the class exists for: a rule that reads as well-supported because it is
  repeated, and that no code has ever obeyed.
"""
import os
import re
import subprocess

# Files that STATE rules. A hit inside one of these is not evidence of enactment.
RULE_FILES = ("CLAUDE.md", "AGENTS.md", ".cursorrules", ".clinerules",
              "copilot-instructions.md")

# Things worth searching for: backticked spans, dotted/underscored identifiers,
# paths, flags, CamelCase. Ordinary prose words are not tokens — "timestamps"
# appearing in a comment proves nothing about the rule that used the word.
_BACKTICKED = re.compile(r"`([^`\n]{2,60})`")
_IDENTIFIER = re.compile(r"\b([a-z][a-z0-9]*(?:[._][a-z0-9]+)+)\b")
_CAMEL = re.compile(r"\b([a-z]+(?:[A-Z][a-z0-9]+)+|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+)\b")
_FLAG = re.compile(r"(--[a-z][a-z0-9-]{2,})")
_PATH = re.compile(r"\b([\w./-]+/[\w.-]+\.\w{1,6})\b")

# A token this common says nothing about whether a specific rule was obeyed.
_TOO_COMMON = {"i.e", "e.g", "etc", "readme.md", "index.js", "main.py",
               "package.json", "self.assert"}


def _tokens(sentence: str) -> list[str]:
    """The searchable things a rule names, most distinctive first."""
    found: list[str] = []
    raw: list[str] = []
    for pattern in (_BACKTICKED, _PATH, _FLAG, _IDENTIFIER, _CAMEL):
        for m in pattern.finditer(sentence):
            raw.append(m.group(1))
    # A multi-word backticked span is a phrase, not a string the repo contains.
    # Measured on openai/codex 2026-08-14: `just argument-comment-lint` was
    # reported inert while argument-comment-lint sits in .bazelrc and two GitHub
    # workflow files — a false positive produced entirely by searching for the
    # sentence's phrasing instead of the thing it names. Each span also
    # contributes its component identifiers.
    for span in list(raw):
        if re.search(r"\s", span):
            raw.extend(w for w in re.split(r"[\s()\[\]{},]+", span)
                       if re.fullmatch(r"[\w.\-/]{4,}", w or ""))
    for tok in raw:
            tok = tok.strip().strip("`'\"(),.;:")
            # `iso_utc()` and iso_utc are the same thing to a grep.
            tok = re.sub(r"\(\s*\)$", "", tok)
            low = tok.lower()
            if len(tok) < 4 or low in _TOO_COMMON:
                continue
            # A glob or an elision is not a string the repo contains. `ev_*`
            # and `#[tracing::instrument(...)]` were both reported inert on
            # openai/codex while fn ev_* constructors and tracing::instrument
            # are both really there — the token was the doc's shorthand, not
            # the thing. Same discipline as skipping a rule with no token:
            # do not manufacture a verdict from a probe that cannot run.
            if "*" in tok or "..." in tok:
                inner = re.sub(r"[*]|\.\.\.", "", tok).strip("_-.:()[]{}#@$ ")
                if len(inner) >= 4 and inner not in found:
                    found.append(inner)
                continue
            # A sigil is the doc's citation style, not part of the name.
            tok = tok.lstrip("$").strip()
            low = tok.lower()
            if len(tok) < 4:
                continue
            if tok not in found:
                found.append(tok)
    return found


def _rule_lines(repo: str) -> list[dict]:
    """Every instruction line that states something, with where it came from."""
    out = []
    for name in RULE_FILES:
        path = os.path.join(repo, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            for n, raw in enumerate(fh, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                text = re.sub(r"^(?:[-*+]\s|\d+[.)]\s|>\s)", "", line).strip()
                if len(text) < 12:
                    continue
                out.append({"file": name, "line": n, "rule": text})
    return out


def _searchable_files(repo: str) -> list[str]:
    """Everything in the repo that is NOT a file whose job is stating rules.

    Deliberately uncapped. The first version took files[:4000]; openai/codex has
    6,217, so codex-rs/tui/src/chatwidget.rs fell off the end and four rules
    naming real, tracked files were reported inert. A silent cap reads as
    coverage. Content reading IS capped below, and says so in the receipt.
    """
    code, _ = _run(["git", "ls-files"], repo)
    files = [f for f in code.splitlines() if f.strip()]
    if not files:                              # not a git repo, or empty index
        for root, dirs, names in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv")]
            for f in names:
                files.append(os.path.relpath(os.path.join(root, f), repo))
    return [f for f in files if os.path.basename(f) not in RULE_FILES]


def _run(cmd: list[str], cwd: str) -> tuple[str, int]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return p.stdout, p.returncode
    except (OSError, subprocess.SubprocessError):
        return "", 1


def _enacted(repo: str, token: str, files: list[str], log: str) -> str | None:
    """Where the repo acts on this token, or None. Commit messages count: a
    decision recorded in history acted on something, unlike one only stated."""
    # A rule that names a FILE is enacted by that file existing. Searching only
    # file contents missed this: on openai/codex, AGENTS.md:60 points at
    # codex-rs/tui/src/chatwidget.rs, which R13 had already confirmed tracked,
    # and the inert detector called the rule unreferenced because no file
    # happened to contain that string. The path IS the reference.
    low = token.lower().rstrip("/")
    for rel in files:
        r = rel.lower()
        if r == low or r.endswith("/" + low) or os.path.basename(r) == low:
            return rel
    if token.lower() in log.lower():
        return "commit message"
    for rel in files:
        full = os.path.join(repo, rel)
        try:
            if os.path.getsize(full) > 400_000:
                continue
            with open(full, encoding="utf-8", errors="replace") as fh:
                if token.lower() in fh.read().lower():
                    return rel
        except OSError:
            continue
    return None


def find_inert_rules(repo: str) -> list[dict]:
    """Rules whose named things appear nowhere but the files that state them.

    Returns one record per candidate: the rule, where it is written, the tokens
    that were searched for, and the fact that none of them was found. Rules with
    no searchable token are omitted entirely rather than reported — see module
    docstring.
    """
    files = _searchable_files(repo)
    log, _ = _run(["git", "log", "--format=%B", "-n", "500"], repo)

    findings = []
    for rule in _rule_lines(repo):
        tokens = _tokens(rule["rule"])
        if not tokens:
            continue                            # nothing to probe, so no verdict
        hits = {t: _enacted(repo, t, files, log) for t in tokens}
        if any(hits.values()):
            continue                            # something acts on it
        findings.append({
            **rule,
            "tokens": tokens,
            "probe": (f"searched {len(files)} tracked file(s) and 500 commit "
                      f"messages for: " + ", ".join(tokens)),
            "why": ("nothing outside the instruction files references what this "
                    "rule names, so no code, comment or commit has enacted it"),
        })
    return findings


def format_inert(findings: list[dict]) -> str:
    if not findings:
        return "No inert-rule candidates: every rule that names something is referenced somewhere."
    lines = [f"Inert-rule candidates ({len(findings)}) — written down, never acted on:", ""]
    for f in findings:
        lines.append(f"  {f['file']}:{f['line']}")
        lines.append(f"     rule    \"{f['rule'][:110]}\"")
        lines.append(f"     probe   {f['probe']}")
        lines.append(f"     why     {f['why']}")
        lines.append("")
    lines.append("  A candidate is not a verdict: a rule can be enacted under a "
                 "name it does not use, and this cannot see that.")
    return "\n".join(lines)
