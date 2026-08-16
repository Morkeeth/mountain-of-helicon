"""B — the learning ledger: every learning from the week, and whether anything
acted on it.

Not R14. R14 (`helicon.inert`) asks whether a rule stated in an INSTRUCTION FILE
was ever enacted, and reads enactment as the rule's tokens appearing in repo code.
This asks whether a learning recorded in the CATCH LOG — an incident, with the
check its author prescribed — was ever turned into something that runs. Same
question one level up: R14 grades the rules you wrote down, this grades the
lessons you learned.

The measured shape of the failure: a day produced roughly ten rules, every one of
them written by someone who had just been burned and meant it. Ten documents. The
question nobody asked was which of them could stop the next occurrence without a
human remembering to. That question has an answer and it is close to zero, and it
is invisible on the day each rule is written, because on that day the rule is
fresh and obviously right.

So the ledger sorts every learning into what it actually is:

  PROSE    no command at all. It depends on someone remembering it. That is not
           a failure — some lessons are judgement — but it must be counted
           separately, because a shelf of prose reads like a control system and
           is not one.
  STATED   a runnable command, written in the log and referenced nowhere else.
           Nothing can execute it.
  STAGED   a runnable artifact for it exists in a repo, but no live config
           reaches that artifact. This is the trap state: the work was done and
           the gate is still not a gate.
  WIRED    a live config references the artifact. Execution is still unverified
           — an artifact reachable from a config is not proof it ever ran, and
           this module says so rather than implying otherwise.

The ruling it forces, per tier: for PROSE, pick which lessons deserve a gate; for
STATED, write the artifact or drop the rule; for STAGED, install it or admit it
is a document.
"""
import collections
import json
import os
import re

# Words that are never English verbs in this context, so their presence at the
# head of a check is decisive.
STRONG_COMMANDS = {
    "grep", "rg", "git", "gh", "jq", "python", "python3", "npm", "npx", "pytest",
    "curl", "wget", "sed", "awk", "wc", "ls", "cat", "date", "diff", "make",
    "helicon", "sqlite3", "docker", "pip", "node", "bash", "sh", "xargs", "du",
}
# Words that are BOTH an English verb and a command name. "open the post URL" is
# an instruction to a human; `open -a Safari` is a command. The word alone cannot
# tell them apart, so these count only when the next token looks like an argument.
AMBIGUOUS_COMMANDS = {"open", "read", "find", "test", "touch", "tail", "head",
                      "sort", "uniq", "which", "time", "kill", "echo", "printf"}
_ARGISH = re.compile(r"^(-|['\"$]|.*[/=.])")

# Runnable things: a file that some runtime can execute or that a config can
# point at. A markdown file describing a check is not one of these, and that
# distinction is the whole point of the module.
RUNNABLE_SUFFIXES = (".sh", ".py", ".js", ".ts", ".mjs", ".yml", ".yaml",
                     ".toml", ".mk")
RUNNABLE_NAMES = ("Makefile", "makefile", "justfile", "Justfile")
# JSON is the awkward one: a settings file is a gate, and a data dump is not.
# Including every .json graded a 389KB prompt corpus as the artifact enacting a
# learning, because the corpus happened to contain the words the check greps for.
# So JSON counts only when its NAME says it configures something.
RUNNABLE_JSON = ("settings.json", "settings.local.json", "package.json",
                 "config.json", "tsconfig.json", "claude.json", "mcp.json",
                 "pyproject.json", "hooks.json")


def is_command(check: str) -> bool:
    """Does this check name something a machine can run?

    Reads the head of the check, and the head of whatever follows a colon — the
    log's own convention for "here is the rule, and here is the command":
    `resolve every cited id ...: grep -o 'C-[0-9a-f]\\{6\\}' <doc> | ...`.

    A first-token allowlist alone gets this wrong, which is why the two lists are
    separate: `for every self-declared marker, replace its payload ...` opens with
    a real shell keyword and is a paragraph, while `gh pr diff 2` carries no flag,
    no path and no quote and is a command."""
    for segment in _segments(check):
        tokens = segment.split()
        if not tokens:
            continue
        head = tokens[0].lower().strip("`$(")
        if head in STRONG_COMMANDS:
            return True
        if head in AMBIGUOUS_COMMANDS and len(tokens) > 1 \
                and _ARGISH.match(tokens[1]):
            return True
    return False


def _segments(check: str) -> list:
    """The check itself, plus anything after a colon or a backtick fence."""
    out = [check.strip()]
    if ":" in check:
        out += [part.strip() for part in check.split(":")[1:]]
    out += re.findall(r"`([^`]+)`", check)
    return [s for s in out if s]


def anchors(check: str) -> set:
    """The distinctive strings a wiring probe can search for: paths, script
    names, quoted literals, dotted identifiers. Bare words are excluded — finding
    the word "count" in a shell script proves nothing about whether this check
    was wired."""
    found = set()
    found |= set(re.findall(r"[\w.-]*/[\w./-]+\.\w{1,5}", check))
    found |= set(re.findall(r"\b([\w-]+\.(?:py|sh|js|ts|json|jsonl|md|yml|yaml))\b",
                            check))
    found |= {m for m in re.findall(r"'([^']{4,60})'", check) if "<" not in m}
    found |= {m for m in re.findall(r"\b([a-zA-Z][\w]*\([\w]*\))", check)}
    found |= {m for m in re.findall(r"\b([a-z][a-z0-9]+(?:[A-Z][a-z0-9]+)+)\b", check)}
    return {f for f in found if len(f) >= 4}


# --- the wiring probe ------------------------------------------------------

def runnable_index(roots: list, max_depth: int = 3) -> dict:
    """path -> text, for every file something could actually execute."""
    index = {}
    for root in roots:
        root = os.path.expanduser(root or "")
        if not root or not os.path.isdir(root):
            continue
        base = root.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") or d == ".github"]
            dirnames[:] = [d for d in dirnames
                           if d not in ("node_modules", "__pycache__", "dist",
                                        "build", ".venv", "venv")]
            if dirpath.count(os.sep) - base >= max_depth:
                dirnames[:] = []
            for fn in filenames:
                if not (fn.endswith(RUNNABLE_SUFFIXES) or fn in RUNNABLE_NAMES
                        or fn in RUNNABLE_JSON):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        index[path] = f.read()
                except OSError:
                    continue
    return index


def live_reachable(index: dict, live_configs: list) -> set:
    """Which runnable files a live config actually names.

    A repo full of hooks proves nothing: the question is whether the running
    system points at any of them. This is the difference between STAGED and
    WIRED, and it is the difference between having done the work and having a
    gate."""
    texts = []
    for cfg in live_configs:
        cfg = os.path.expanduser(cfg or "")
        if cfg and os.path.isfile(cfg):
            try:
                with open(cfg, encoding="utf-8", errors="replace") as f:
                    texts.append(f.read())
            except OSError:
                continue
    if not texts:
        return set()
    blob = "\n".join(texts)
    return {path for path in index
            if os.path.basename(path) in blob or path in blob}


def learning_ledger(catches_path: str, repo_roots: list = (),
                    live_configs: list = ()) -> dict:
    """Every learning that carries a check, sorted by what it actually is."""
    rows = _read_jsonl(catches_path)
    index = runnable_index(list(repo_roots))
    reachable = live_reachable(index, list(live_configs))

    entries, no_check = [], 0
    for r in rows:
        check = (r.get("check") or "").strip()
        if not check:
            no_check += 1
            continue
        if not is_command(check):
            tier = "PROSE"
            where = []
        else:
            found = anchors(check)
            hits = sorted({p for p in index
                           if any(a in index[p] for a in found)
                           and not _is_a_record_of(index[p], r, check)}) \
                if found else []
            live_hits = [p for p in hits if p in reachable]
            if live_hits:
                tier, where = "WIRED", live_hits
            elif hits:
                tier, where = "STAGED", hits
            else:
                tier, where = "STATED", []
        entries.append({"day": r.get("day", ""), "check": check, "tier": tier,
                        "artifacts": where[:3],
                        "claimed": (r.get("claimed") or "")[:90]})

    counts = collections.Counter(e["tier"] for e in entries)
    return {"population": len(rows), "no_check": no_check,
            "with_check": len(entries), "entries": entries,
            "counts": dict(counts), "runnables_scanned": len(index),
            "live_configs": [c for c in live_configs
                             if os.path.isfile(os.path.expanduser(c or ""))],
            "live_reachable": len(reachable)}


def _is_a_record_of(text: str, row: dict, check: str) -> bool:
    """Is this artifact enacting the check, or just holding a copy of the log?

    The first version of this probe graded 14 learnings STAGED, and nearly every
    hit was one file: the script that BACKFILLED the catch log. It contained the
    checks because it wrote them down. Counting it as enactment is the
    self-generated-evidence defect (R9) reproduced inside the detector built to
    catch unenacted rules — the log vouching for itself.

    The marker is the catch's own id or CLAIM — never the check text itself. A
    script that contains the prescribed command verbatim is the strongest possible
    enactment, and an earlier version excluded exactly that case: it treated
    "contains the check" as evidence of copying, so a gate that ran the check word
    for word was graded as not existing. The claim is what only the log has."""
    for marker in (row.get("id") or "", row.get("claimed") or ""):
        if marker and len(marker) >= 12 and marker in text:
            return True
    return False


def gate_inventory(repo_roots: list = (), live_configs: list = ()) -> dict:
    """Hook and gate scripts that exist, against the ones a live config names.

    Written because of one instance worth stating plainly: the week's single best
    learning had a real script AND a settings diff prepared for it, and the live
    config referenced neither — the diff was a proposal and a proposal is not an
    installation. Nothing in the catch log could show that, because the log
    records what was decided, not what was installed."""
    index = runnable_index(list(repo_roots))
    hooks = {p: t for p, t in index.items()
             if "hook" in p.lower() or "gate" in p.lower() or "check" in p.lower()}
    reachable = live_reachable(hooks, list(live_configs))
    return {"found": sorted(hooks), "installed": sorted(reachable),
            "orphaned": sorted(set(hooks) - reachable)}


# --- the same question, from a source every stranger has -------------------

# Surfaces that ACTUALLY STOP THINGS. A script sitting in a repo is not one; a
# workflow, an installed git hook, a package script and a pre-commit config all
# run without anyone remembering to run them. Every one of these is a file a
# stranger already has, which is the whole point of re-pointing here.
ENFORCEMENT_GLOBS = (
    ".github/workflows", ".gitlab-ci.yml", ".git/hooks", ".pre-commit-config.yaml",
    "package.json", "Makefile", "justfile", "noxfile.py", "tox.ini",
    ".circleci", "pyproject.toml", ".husky",
)


def enforcement_surfaces(repo: str) -> dict:
    """path -> text for the things in this repo that can refuse a change.

    `.git/hooks` is filtered to installed hooks: git ships a directory of
    `.sample` files in every clone, and counting those would grade every repo on
    earth as having eleven gates it does not have."""
    out = {}
    for rel in ENFORCEMENT_GLOBS:
        path = os.path.join(repo, rel)
        if os.path.isfile(path):
            out.update(_read_text(path))
        elif os.path.isdir(path):
            for dirpath, _dirnames, filenames in os.walk(path):
                for fn in filenames:
                    if fn.endswith(".sample"):
                        continue
                    out.update(_read_text(os.path.join(dirpath, fn)))
    return out


def _read_text(path: str) -> dict:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return {path: f.read()}
    except OSError:
        return {}


def rule_ledger(repo: str, live_configs: list = ()) -> dict:
    """Every rule this repo states, and whether anything would stop its violation.

    SAME POPULATION AS R14, DIFFERENT QUESTION. `helicon.inert` reads these exact
    files and asks whether anything ever MENTIONED the rule — its verdict is that
    a rule nothing references is dead, and the ruling is to delete it. This asks
    whether anything would STOP the rule being broken. A rule can be mentioned
    all over the codebase and still have no gate, and then it is alive, obeyed by
    hand, and one tired afternoon from being broken silently.

    Because the population is identical, the rule extraction is IMPORTED from
    `helicon.inert` rather than rewritten. Two extractors over one population is
    an identity fork (R11) with this module as its author, and shipping one
    inside the tool that detects them would be the joke writing itself.

    Tiers, using the enforcement surfaces every repo has:
      PROSE   the rule names nothing searchable, so no gate could check it. Not
              a failure — judgement does not compile — but counted apart.
      STATED  it names things, and nothing in the repo references them.
      STAGED  a runnable file references them, but nothing that runs by itself.
      WIRED   an enforcement surface references them: a workflow, an installed
              git hook, a package script, a pre-commit config. Execution stays
              unverified — reachable is not the same as ran."""
    from helicon.inert import _rule_lines, _tokens

    rules = _rule_lines(repo)
    gates = enforcement_surfaces(repo)
    for cfg in live_configs:
        cfg = os.path.expanduser(cfg or "")
        if cfg and os.path.isfile(cfg):
            gates.update(_read_text(cfg))
    staged = runnable_index([repo], max_depth=3)

    # A token that is everywhere carries no information about any ONE rule. The
    # repo is called helicon, so `helicon` appears in every workflow file, and a
    # naive any-token match graded 13 rules WIRED on that word alone — including
    # "~3,800 live memories of ~6,900 total", which is a statistic, not a rule
    # anything could enforce. Same defect as basename-scatter and the backfill
    # script: the detector found what it searched for, and what it searched for
    # was not the thing. So a token must be DISTINCTIVE within the corpus it is
    # searched against.
    corpus = dict(gates)
    corpus.update(staged)
    repo_name = os.path.basename(repo.rstrip(os.sep)).lower()
    common = _too_common(corpus, repo_name)

    entries = []
    for r in rules:
        tokens = [t for t in _tokens(r["rule"])
                  if len(t) >= 4 and t.lower() not in common]
        if not tokens:
            entries.append({**r, "tier": "PROSE", "tokens": [], "gates": []})
            continue
        hit_gates = sorted({p for p, text in gates.items()
                            if any(t in text for t in tokens)})
        hit_runnable = sorted({p for p, text in staged.items()
                               if p not in gates
                               and any(t in text for t in tokens)})
        if hit_gates:
            tier, where = "WIRED", hit_gates
        elif hit_runnable:
            tier, where = "STAGED", hit_runnable
        else:
            tier, where = "STATED", []
        entries.append({**r, "tier": tier, "tokens": tokens[:4],
                        "gates": where[:3]})

    counts = collections.Counter(e["tier"] for e in entries)
    return {"repo": repo, "population": len(rules), "entries": entries,
            "counts": dict(counts), "surfaces": sorted(gates),
            "runnables_scanned": len(staged)}


def _too_common(corpus: dict, repo_name: str, ceiling: float = 0.25) -> set:
    """Tokens too widespread in this corpus to be evidence about one rule.

    Document frequency, computed over the files actually being searched rather
    than a hand-written stoplist — a stoplist only ever lags the next project's
    vocabulary, and the token that broke this was the repo's own name."""
    if not corpus:
        return {repo_name} if repo_name else set()
    df: collections.Counter = collections.Counter()
    for text in corpus.values():
        for word in set(re.findall(r"[A-Za-z][\w.\-/]{3,}", text)):
            df[word.lower()] += 1
    limit = max(2, int(len(corpus) * ceiling))
    common = {w for w, n in df.items() if n > limit}
    if repo_name:
        common.add(repo_name)
        common |= set(repo_name.split("-"))
    return common


def render_rule_ledger(report: dict, read_at: str = "", top: int = 8) -> str:
    if not report.get("population"):
        return (f"RULE LEDGER — {report.get('repo', '?')} states no rules "
                f"(no CLAUDE.md / AGENTS.md / .cursorrules found).\n"
                f"  Nothing stated is not the same as nothing to check.")
    c = report["counts"]
    n = report["population"]
    out = [
        f"RULE LEDGER — {os.path.basename(report['repo'].rstrip('/'))}: "
        f"every rule stated, and whether anything would stop it being broken",
        "",
        f"  {n} rules stated · graded against {len(report['surfaces'])} "
        f"enforcement surfaces and {report['runnables_scanned']} runnable files",
        "",
        f"  PROSE   {c.get('PROSE', 0):>3}   names nothing a gate could check",
        f"  STATED  {c.get('STATED', 0):>3}   names things; nothing in the repo "
        f"references them",
        f"  STAGED  {c.get('STAGED', 0):>3}   a runnable references them; nothing "
        f"that runs by itself",
        f"  WIRED   {c.get('WIRED', 0):>3}   an enforcement surface references "
        f"them (execution unverified)",
        "",
    ]
    wired = [e for e in report["entries"] if e["tier"] == "WIRED"]
    if wired:
        out.append("  WIRED:")
        for e in wired[:top]:
            out.append(f"     {e['file']}:{e['line']}  {e['rule'][:76]}")
            for g in e["gates"]:
                out.append(f"        -> {g}")
        out.append("")
    if report["surfaces"]:
        out.append("  enforcement surfaces found:")
        for s in report["surfaces"][:top]:
            out.append(f"     {s}")
    else:
        out.append("  NO enforcement surface in this repo: no workflow, no "
                   "installed git hook, no package script.")
        out.append("  Every rule above is held by memory alone.")
    out += [
        "",
        "  rule: PROSE -> leave it, judgement does not compile. STATED -> write "
        "the gate or drop the rule.",
        "        STAGED -> a script nothing runs is a document with a shebang.",
        "",
        f"read {read_at}  ·  helicon ledger --rules <repo>",
    ]
    return "\n".join(out)


def _read_jsonl(path: str) -> list:
    if not path or not os.path.isfile(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def render_ledger(report: dict, inventory: dict = None, read_at: str = "",
                  top: int = 8) -> str:
    if not report.get("population"):
        return ("LEARNING LEDGER — no catch log configured.\n"
                "  An unread week is not a clean one, so nothing is graded here.")
    c = report["counts"]
    out = [
        "LEARNING LEDGER — every learning, and whether anything can act on it",
        "",
        f"  {report['population']} logged learnings, {report['no_check']} with no "
        f"check at all, {report['with_check']} carrying one",
        f"  graded against {report['runnables_scanned']} runnable files; "
        f"{report['live_reachable']} of them are named by a live config",
        "",
        f"  PROSE   {c.get('PROSE', 0):>3}   depends on someone remembering it",
        f"  STATED  {c.get('STATED', 0):>3}   a command, written in the log and "
        f"nowhere else",
        f"  STAGED  {c.get('STAGED', 0):>3}   an artifact exists; no live config "
        f"reaches it",
        f"  WIRED   {c.get('WIRED', 0):>3}   a live config names the artifact "
        f"(execution unverified)",
        "",
    ]
    for tier in ("WIRED", "STAGED", "STATED"):
        rows = [e for e in report["entries"] if e["tier"] == tier]
        if not rows:
            continue
        out.append(f"  {tier}:")
        for e in rows[:top]:
            out.append(f"     {e['day']}  {e['check'][:88]}")
            for a in e["artifacts"]:
                out.append(f"        -> {a}")
        out.append("")

    if inventory is not None:
        out.append(f"  GATES ON DISK   {len(inventory['found'])} hook/gate scripts "
                   f"found, {len(inventory['installed'])} named by a live config")
        for p in inventory["orphaned"][:top]:
            out.append(f"     orphaned: {p}")
        out.append("")
    out += [
        "  rule: PROSE -> pick which lessons deserve a gate. STATED -> write the "
        "artifact or drop the rule.",
        "        STAGED -> install it, or say plainly that it is a document.",
        "",
        f"read {read_at}  ·  helicon ledger",
    ]
    return "\n".join(out)
