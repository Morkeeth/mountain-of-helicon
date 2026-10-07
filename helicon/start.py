"""`helicon start`: the first-run review, one card for the whole setup.

Helicon had the parts (review, truth, ask, skills-review, measure) and no front
door. A person who starts it wants one answer: where is my context, what state is
it in, what do I do next. This module asks each part for its reading and prints one
card: which copy is running, five readings, and at most three next steps.

Rules it keeps:
  - Read only. It writes nothing and changes no store.
  - No total. The five readings measure different things and are never summed.
  - A part that found nothing to read says "nothing found". It never prints zero
    as if it had measured.
  - Every row names what it read, so the reader can check it.
"""

import glob
import json
import os
import re
import sqlite3
import subprocess
import sys

ROT_HIGH = 60  # truth score from which a memory file counts as rotten here
SKILL_DIRS = ("~/.claude/skills", "~/.agents/skills", "~/.cursor/skills", "~/.codex/skills")
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", ".cursorrules", ".clinerules")


def _run_json(args, timeout=180):
    """One helicon command with --json, parsed. None when it gave no JSON."""
    try:
        done = subprocess.run(
            [sys.executable, "-m", "helicon", *args, "--json"],
            capture_output=True, text=True, timeout=timeout,
        )
        return json.loads(done.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def read_instructions(path):
    """Do the agent instruction files in this repo match the repo."""
    path = os.path.abspath(path)
    present = [f for f in INSTRUCTION_FILES if os.path.exists(os.path.join(path, f))]
    if not present:
        return {"found": False, "read": path, "why": "no AGENTS.md, CLAUDE.md or rules file here"}
    res = _run_json(["review", path])
    if not res:
        return {"found": False, "read": path, "why": "the review gave no result"}
    return {
        "found": True, "read": path, "files": present, "grade": res.get("grade"),
        "checked": res.get("checked", 0), "broken": res.get("broken", 0),
    }


def memory_stores(home=None):
    """Agent memory folders on this machine, biggest first."""
    home = home or os.path.expanduser("~")
    found = []
    for folder in glob.glob(os.path.join(home, ".claude", "projects", "*", "memory")):
        count = len(glob.glob(os.path.join(folder, "*.md")))
        if count:
            found.append((count, folder))
    return [folder for _, folder in sorted(found, reverse=True)]


def read_memory(stores, limit=2):
    """How many memory files carry a stale or expired claim."""
    if not stores:
        return {"found": False, "why": "no agent memory folder with notes"}
    total = rotten = 0
    read = []
    for folder in stores[:limit]:
        res = _run_json(["truth", folder])
        if not res:
            continue
        total += res.get("total", 0)
        rotten += sum(1 for item in res.get("items", []) if item.get("score", 0) >= ROT_HIGH)
        read.append(folder)
    if not read:
        return {"found": False, "why": "the memory scan gave no result"}
    return {"found": True, "read": read, "files": total, "rotten": rotten, "skipped_stores": max(0, len(stores) - limit)}


def read_decisions():
    """The operator's dated rulings on record."""
    from helicon.dated_rulings import load_rulings, rulings_path

    path = rulings_path()
    if not path:
        return {"found": False, "why": "no ruling log (set HELICON_RULINGS_FILE)"}
    rulings = load_rulings(path)
    if not rulings:
        return {"found": False, "read": path, "why": "the ruling log is empty"}
    dates = sorted(r["date"] for r in rulings if r["date"])
    return {"found": True, "read": path, "rulings": len(rulings), "newest": dates[-1] if dates else ""}


def installed_skills(home=None):
    home = home or os.path.expanduser("~")
    names = set()
    for folder in SKILL_DIRS:
        base = folder.replace("~", home, 1)
        for skill in glob.glob(os.path.join(base, "*", "SKILL.md")):
            names.add(os.path.basename(os.path.dirname(skill)))
    return names


def _trace_db(home=None):
    path = os.path.join(home or os.path.expanduser("~"), ".trace", "trace.db")
    return path if os.path.isfile(path) else None


def read_skills(home=None):
    """Installed skills, and how many were ever opened in the indexed transcripts."""
    names = installed_skills(home)
    if not names:
        return {"found": False, "why": "no installed skills"}
    db = _trace_db(home)
    if not db:
        return {"found": True, "installed": len(names), "opened_known": False,
                "why": "no transcript index, so use is unknown"}
    opened = set()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT text FROM messages WHERE text LIKE 'Launching skill:%' "
            "OR text LIKE '[Skill.%' OR text LIKE '%/skills/%/SKILL.md%'"
        )
        for (text,) in rows:
            head = text[:600]
            for name in re.findall(r"^Launching skill: ([\w:.-]+)", head):
                opened.add(name.split(":")[-1])
            for name in re.findall(r"\[Skill\.skill\]\s*([\w:.-]+)", head):
                opened.add(name.split(":")[-1])
            if re.match(r"\[(Read|Bash)\.", head):
                opened.update(re.findall(r"/skills/([\w.-]+)/SKILL\.md", head))
    except sqlite3.Error:
        return {"found": True, "installed": len(names), "opened_known": False,
                "why": "the transcript index could not be read"}
    finally:
        con.close()
    never = sorted(names - opened)
    return {"found": True, "read": db, "installed": len(names), "opened_known": True,
            "never_opened": len(never), "never_opened_names": never}


def read_index(home=None):
    """The transcript index: how much is in it and how fresh it is."""
    db = _trace_db(home)
    if not db:
        return {"found": False, "why": "no transcript index (run transcripto index)"}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        sessions, newest = con.execute(
            "SELECT COUNT(DISTINCT session_id), MAX(ts) FROM messages"
        ).fetchone()
        try:
            warned = con.execute(
                "SELECT COUNT(*) FROM v_index_health WHERE warnings NOT IN ('[]', '')"
            ).fetchone()[0]
        except sqlite3.Error:
            warned = None
    except sqlite3.Error:
        return {"found": False, "read": db, "why": "the transcript index could not be read"}
    finally:
        con.close()
    return {"found": True, "read": db, "sessions": sessions, "newest": (newest or "")[:10],
            "files_with_warnings": warned}


def read_install():
    """Which copy of Helicon is answering, and how far it is behind its main branch.

    Helicon ran 38 commits stale for 12 days and nothing said so. This row is the
    guard: it reads the tree this code was imported from. It uses what git already
    knows locally and does not fetch, so "behind" means behind the last fetch.
    """
    tree = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def git(*args):
        try:
            done = subprocess.run(["git", "-C", tree, *args], capture_output=True, text=True, timeout=20)
            return done.stdout.strip() if done.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    if git("rev-parse", "--is-inside-work-tree") != "true":
        return {"found": True, "read": tree, "git": False}
    behind = git("rev-list", "--count", "HEAD..origin/main")
    return {
        "found": True, "read": tree, "git": True,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD") or "",
        "behind_main": int(behind) if behind and behind.isdigit() else None,
        "changed_files": len((git("status", "--porcelain") or "").splitlines()),
    }


def next_steps(card):
    """At most three things to do, worst first. Empty when nothing was found wrong."""
    steps = []
    ins, mem, dec, ski, idx = (card[k] for k in ("instructions", "memory", "decisions", "skills", "index"))
    inst = card.get("install", {})
    if inst.get("behind_main"):
        steps.append(f"This Helicon is {inst['behind_main']} commit(s) behind main. Update it before trusting the rows below: {inst['read']}")
    if ins.get("found") and ins.get("broken"):
        steps.append(f"Fix {ins['broken']} instruction line(s) that do not match the repo: helicon review {ins['read']}")
    if mem.get("found") and mem.get("rotten"):
        steps.append(f"Review {mem['rotten']} rotten memory file(s): helicon truth {mem['read'][0]}")
    if ski.get("opened_known") and ski.get("never_opened"):
        steps.append(f"{ski['never_opened']} installed skill(s) were never opened. Route to them or remove them.")
    if not dec.get("found"):
        steps.append("No decisions on record. Without a ruling log an agent cannot know what you decided.")
    if not idx.get("found"):
        steps.append("No transcript index. Index your sessions so use and drift can be measured.")
    return steps[:3]


def build_card(path=".", home=None):
    card = {
        "install": read_install(),
        "instructions": read_instructions(path),
        "memory": read_memory(memory_stores(home)),
        "decisions": read_decisions(),
        "skills": read_skills(home),
        "index": read_index(home),
    }
    card["next"] = next_steps(card)
    return card


def _paint(text, code, colour):
    return f"\033[{code}m{text}\033[0m" if colour else text


def _bar(part, whole, colour, width=28):
    """A strip drawn to scale for the terminal. Zero draws an empty strip."""
    if not whole:
        return ""
    filled = 0 if not part else max(1, round(width * min(1.0, part / whole)))
    return _paint("█" * filled, "38;5;68", colour) + _paint("░" * (width - filled), "38;5;240", colour)


def format_card(card, colour=False):
    """The card as text. With colour it uses blues only: bright for a number, mid for
    a strip, dim for what was read. Without it the same words print plain."""
    ins, mem, dec, ski, idx = (card[k] for k in ("instructions", "memory", "decisions", "skills", "index"))
    head = lambda text: _paint(text, "1;38;5;153", colour)  # noqa: E731
    num = lambda text: _paint(str(text), "1;38;5;117", colour)  # noqa: E731
    dim = lambda text: _paint(text, "38;5;67", colour)  # noqa: E731

    def row(label, part, text, bar=""):
        if not part.get("found"):
            return [f"  {label:<14}{dim('nothing found: ' + part.get('why', ''))}"]
        lines = [f"  {head(label.ljust(14))}{text}"]
        if bar:
            lines.append(f"  {'':<14}{bar}")
        return lines

    lines = ["", f"  {head('HELICON')}  where your context is, and its state", ""]
    inst = card.get("install") or {}
    if inst.get("git"):
        behind = inst.get("behind_main")
        state = "behind main unknown" if behind is None else ("up to date with main" if behind == 0 else f"STALE: {behind} commit(s) behind main")
        if behind:
            state = num(state)
        lines.append(f"  {head('Running from  ')}{dim(inst['read'])}  ·  branch {inst['branch']}  ·  {state}")
    elif inst:
        lines.append(f"  {head('Running from  ')}{dim(inst['read'])}  ·  an installed copy, not a git tree")
    lines.append("")
    lines += row("Instructions", ins, f"grade {ins.get('grade')}  ·  {num(ins.get('broken'))} of {ins.get('checked')} checked lines do not match the repo",
                 _bar(ins.get("broken") or 0, ins.get("checked") or 0, colour))
    lines += row("Memory", mem, f"{num(mem.get('rotten'))} of {mem.get('files')} memory files carry a stale or expired claim",
                 _bar(mem.get("rotten") or 0, mem.get("files") or 0, colour))
    lines += row("Decisions", dec, f"{num(dec.get('rulings'))} rulings on record  ·  newest {dec.get('newest')}")
    if ski.get("found") and ski.get("opened_known"):
        lines += row("Skills", ski, f"{num(ski['never_opened'])} of {ski['installed']} installed skills were never opened",
                     _bar(ski["never_opened"], ski["installed"], colour))
    else:
        lines += row("Skills", ski, f"{num(ski.get('installed'))} installed  ·  {ski.get('why', '')}")
    warned = idx.get("files_with_warnings")
    lines += row("Index", idx, f"{num(idx.get('sessions'))} sessions indexed  ·  newest {idx.get('newest')}"
                 + (f"  ·  {warned} file(s) with warnings" if warned else ""))
    lines.append("")
    if card["next"]:
        lines.append(f"  {head('Do next:')}")
        lines.extend(f"    {num(n)}. {step}" for n, step in enumerate(card["next"], 1))
    else:
        lines.append("  Nothing to fix was found in what could be read.")
    lines.append("")
    lines.append(dim("  Five separate readings. They are not added up."))
    return "\n".join(lines) + "\n"
