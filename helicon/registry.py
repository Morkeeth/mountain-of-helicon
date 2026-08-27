"""The registry gate — every project you own should have a row, and every row a project.

The same check as `helicon consistency`, pointed one level out. There the index is
a MEMORY.md and the population is a directory of notes. Here the index is the
registry table in the vault and the population is what Oscar actually owns:
GitHub repos and ~/CODE directories.

WHY THIS IS A GATE AND NOT A REPORT
-----------------------------------
Measured 2026-08-27: 67 registry rows, 88 GitHub repos, 108 directories under
~/CODE. The Aug-31 hackathon submission had no row until someone noticed by hand.
His words: "we have so many of these items I actively have to think to catch."
A thing you have to remember to check is not covered.

THREE STRENGTHS OF EVIDENCE, NOT TWO
------------------------------------
A registry row is mostly prose, and that prose names other repos constantly. So a
naive "is this string anywhere in the file" would mark almost everything covered
and the gate would find nothing — a green light that means the matcher is broken,
which is worse than a red one. Instead:

  ROW    the repo is named in the Initiative column. It has a row.
  PROSE  it is mentioned somewhere in the table but owns no row. Weak coverage:
         real, worth counting, not the same as being tracked.
  NONE   nothing in the registry mentions it at all. This is the gap.

Reporting PROSE separately is what keeps the check honest in both directions: it
neither cries wolf on a repo that is genuinely discussed, nor lets a mention
inside someone else's paragraph pass as ownership.

WHAT IS NOT A GAP
-----------------
An archived repo needs no row — archiving IS the decision. A fork of someone
else's code needs no row; it is not a project. Both are excluded and both counts
are printed, because a denominator you cannot see is the defect this whole
product is about.
"""
import json
import os
import re
import subprocess

_ROW = re.compile(r"^\|\s*(\d{3})\s*\|([^|]*)\|")
_TICK = re.compile(r"`([^`]+)`")
_CODE_PATH = re.compile(r"~/CODE/([A-Za-z0-9._-]+)")
_GH_PATH = re.compile(r"(?:github\.com/)?Morkeeth/([A-Za-z0-9._-]+)", re.I)

# Directories under ~/CODE that are not projects.
_NOT_A_PROJECT = {"node_modules", "__pycache__", ".venv", "venv", "tmp", "scratch"}


def slug(text: str) -> str:
    """Fold a human name and a repo name onto the same key.

    'REKT Capital' and 'rekt-capital' are the same project. Markdown, emoji,
    arrows and punctuation are noise here. A leading article is dropped because
    row titles carry one and repo names never do.
    """
    s = re.sub(r"[^a-z0-9]", "", (text or "").lower())
    return s[3:] if s.startswith("the") and len(s) > 6 else s


# Containment is how a row title and a repo name usually differ: row 056 reads
# 'THE AGENT WORK RECORD WITNESS' and the repo is 'agent-work-record-witness-ata'.
# Exact equality reports that as a gap, which is a false alarm on a row somebody
# just wrote. The floor is high on purpose -- a short slug inside a longer one is
# a coincidence, and over-matching HIDES real gaps, which is the failure that
# matters more here.
_CONTAIN_FLOOR = 8


def matches(repo_slug: str, index_slugs: set) -> bool:
    if repo_slug in index_slugs:
        return True
    for cand in index_slugs:
        short, long = sorted((repo_slug, cand), key=len)
        if len(short) >= _CONTAIN_FLOOR and short in long:
            return True
    return False


def _row_names(cell: str) -> list[str]:
    """Every name a single Initiative cell offers, including aliases.

    A row reads like `HL tool _(dashboard = a detail)_ / **REKT Capital**` or
    `People Radar -> **context-radar**`. Matching only the first name reports a
    false gap for the majority of them, because the repo is usually named by the
    alias, not by the title.
    """
    names = []
    for tick in _TICK.findall(cell):
        names.append(tick)
    cleaned = _TICK.sub(" ", cell)
    cleaned = cleaned.replace("**", " ").replace("__", " ")
    # aliases live in _( ... )_ or ( ... ); both are names, not prose
    for alias in re.findall(r"[_(]\(?([^)_]+)\)?[_)]", cleaned):
        names.append(alias)
    cleaned = re.sub(r"[_(][^)_]*[)_]", " ", cleaned)
    # a cell can carry several names joined by / or an arrow
    for part in re.split(r"/|→|->|,", cleaned):
        names.append(part)
    return [n.strip() for n in names if n and n.strip()]


def parse_registry(path: str) -> dict:
    """Row numbers, the names each row claims, and the full text for prose lookup."""
    text = open(path, encoding="utf-8").read()
    rows = []
    for line in text.splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        num, cell = m.group(1), m.group(2)
        names = _row_names(cell)
        rows.append({
            "num": num,
            "cell": cell.strip(),
            # The Initiative cell is the NAME column only. A row's repo pointer
            # lives in the prose column, so ghost detection has to read the whole
            # line -- scanning `cell` returned 0 ghosts on the real registry and
            # that zero was a false negative, caught only by watching the control
            # fail. Nobody audits a check that says no.
            "line": line,
            "names": names,
            "slugs": {s for s in (slug(n) for n in names) if len(s) >= 3},
        })
    mentioned = set()
    for tick in _TICK.findall(text):
        mentioned.add(slug(tick))
    for m in _CODE_PATH.finditer(text):
        mentioned.add(slug(m.group(1)))
    for m in _GH_PATH.finditer(text):
        mentioned.add(slug(m.group(1)))
    return {"rows": rows, "text": text, "mentioned": {s for s in mentioned if len(s) >= 3}}


def github_repos(limit: int = 300) -> list[dict]:
    """Live repos via gh. Returns [] when gh is absent — never a fabricated list."""
    try:
        out = subprocess.run(
            ["gh", "repo", "list", "--limit", str(limit), "--json",
             "name,isArchived,isFork,updatedAt,description"],
            capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    try:
        return json.loads(out.stdout or "[]")
    except json.JSONDecodeError:
        return []


def code_dirs(code_root: str) -> list[str]:
    root = os.path.expanduser(code_root or "~/CODE")
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d))
                  and not d.startswith(".")
                  and d not in _NOT_A_PROJECT)


def audit_registry(index_path: str, code_root: str = "~/CODE",
                   repos: list[dict] | None = None) -> dict:
    index_path = os.path.abspath(os.path.expanduser(index_path))
    if not os.path.isfile(index_path):
        return {"ok": False, "reason": f"no registry at {index_path}"}

    reg = parse_registry(index_path)
    row_slugs = set()
    for r in reg["rows"]:
        row_slugs |= r["slugs"]

    repos = github_repos() if repos is None else repos
    dirs = code_dirs(code_root)
    local = {slug(d) for d in dirs}

    excluded_archived = [r["name"] for r in repos if r.get("isArchived")]
    excluded_forks = [r["name"] for r in repos
                      if r.get("isFork") and not r.get("isArchived")]
    live = [r for r in repos if not r.get("isArchived") and not r.get("isFork")]

    unlisted, prose_only = [], []
    for r in live:
        s = slug(r["name"])
        if matches(s, row_slugs):
            continue
        entry = {"name": r["name"], "updated": (r.get("updatedAt") or "")[:10],
                 "local": s in local, "description": r.get("description") or ""}
        (prose_only if matches(s, reg["mentioned"]) else unlisted).append(entry)

    # newest first: a repo touched this week with no row is the one that goes missing
    unlisted.sort(key=lambda e: e["updated"], reverse=True)
    prose_only.sort(key=lambda e: e["updated"], reverse=True)

    # The opposite drift, and it has to be narrow. Most rows are not code --
    # 'Journaling + scrapbook', 'Wave Radio', 'Job hunt' own no repo and never
    # should. Flagging those is the 39-row wall that gets the check closed on day
    # two. A row is only drifting when it POINTS AT a repo that is not there:
    # `~/CODE/x` or Morkeeth/x written into the row itself, resolving to nothing.
    known = {slug(r["name"]) for r in repos} | local
    rows_without_project = []
    for r in reg["rows"]:
        claimed = {slug(m) for m in _CODE_PATH.findall(r["line"])}
        claimed |= {slug(m) for m in _GH_PATH.findall(r["line"])}
        ghosts = sorted(c for c in claimed if c and c not in known)
        if ghosts:
            rows_without_project.append(
                {"num": r["num"], "names": r["names"][:2], "ghosts": ghosts})

    # a ~/CODE directory that is neither a repo nor a row is a fourth population
    repo_slugs = {slug(r["name"]) for r in repos}
    local_only = sorted(d for d in dirs
                        if slug(d) not in repo_slugs
                        and slug(d) not in row_slugs
                        and slug(d) not in reg["mentioned"])

    return {
        "ok": True,
        "registry": index_path,
        "rows": len(reg["rows"]),
        "repos_total": len(repos),
        "repos_live": len(live),
        "excluded_archived": len(excluded_archived),
        "excluded_forks": len(excluded_forks),
        "code_dirs": len(dirs),
        "unlisted": unlisted,
        "prose_only": prose_only,
        "rows_without_project": rows_without_project,
        "local_only": local_only,
        "clean": not unlisted and not rows_without_project,
    }
