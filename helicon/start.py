"""`helicon start`: the first-run review, one card for the whole setup.

Helicon had the parts (review, truth, ask, skills-review, measure) and no front
door. A person who starts it wants one answer: where is my context, what state is
it in, what do I do next. This module asks each part for its reading and prints one
card: which copy is running, five readings, and at most three next steps.

Rules it keeps:
  - It changes no store. The one thing it writes is its own reading, one line per
    run, in ~/.helicon/start-history.jsonl, so a trend can exist.
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


def history_path():
    return os.path.join(os.path.expanduser("~"), ".helicon", "start-history.jsonl")


def _numbers(card):
    """The few numbers worth following over time. Missing readings stay missing."""
    ins, mem, dec, ski, idx = (card[k] for k in ("instructions", "memory", "decisions", "skills", "index"))
    return {
        "instructions_broken": ins.get("broken") if ins.get("found") else None,
        "memory_rotten": mem.get("rotten") if mem.get("found") else None,
        "rulings": dec.get("rulings") if dec.get("found") else None,
        "skills_never_opened": ski.get("never_opened") if ski.get("opened_known") else None,
        "sessions": idx.get("sessions") if idx.get("found") else None,
    }


def record_reading(card, when, path=None):
    """Append this reading to the local history. One line per run, never rewritten.
    This is the only thing `helicon start` writes, and only when asked to record."""
    path = path or history_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row = {"at": when, "repo": card["instructions"].get("read"), **_numbers(card)}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    return row


def load_history(path=None, limit=30):
    """Past readings, oldest first, one per day (the last run of a day wins)."""
    path = path or history_path()
    if not os.path.isfile(path):
        return []
    by_day = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("at"):
                by_day[str(row["at"])[:10]] = row
    return [by_day[day] for day in sorted(by_day)][-limit:]


def trend(history, key):
    """Change since the first stored reading, or None with fewer than two days."""
    values = [row.get(key) for row in history if row.get(key) is not None]
    return None if len(values) < 2 else values[-1] - values[0]


def _day(iso):
    """2026-10-07 as 7 Oct. Anything else comes back as it was."""
    from datetime import datetime

    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%-d %b")
    except (TypeError, ValueError):
        return iso or ""


def _short(path):
    home = os.path.expanduser("~")
    path = str(path or "")
    return "~" + path[len(home):] if path.startswith(home) else path


def _n(count, one, many=None):
    """3 notes, 1 note."""
    return f"{count} {one if count == 1 else (many or one + 's')}"


def plain(card):
    """The card in words a person reads once and understands. No file paths, branch
    names or tool words in a sentence; those live in `detail` for whoever wants them.

    Returns {"status": (sentence, is_problem), "rows": [...], "steps": [(sentence, command)]}.
    Each row: label, found, number, unit, text, part, whole, detail.
    """
    ins, mem, dec, ski, idx = (card[k] for k in ("instructions", "memory", "decisions", "skills", "index"))
    inst = card.get("install") or {}
    behind = inst.get("behind_main")
    if behind:
        status = (f"This copy of Helicon is out of date, {_n(behind, 'update')} behind. Update it before you trust the numbers below.", True)
    elif inst.get("git") and behind == 0:
        status = ("Helicon is up to date.", False)
    else:
        status = ("", False)

    def row(label, part, number=None, unit="", text="", share=None, detail=""):
        if not part.get("found"):
            return {"label": label, "found": False, "text": part.get("why", ""), "detail": ""}
        return {"label": label, "found": True, "number": number, "unit": unit, "text": text,
                "part": share[0] if share else None, "whole": share[1] if share else None, "detail": detail}

    rows = []
    checked, broken = ins.get("checked") or 0, ins.get("broken") or 0
    where = f"instruction files in {_short(ins.get('read'))}"
    if not checked:
        rows.append(row("Instructions", ins, 0, "checks", "possible. Your instruction files point to nothing that can be checked."))
    elif not broken:
        rows.append(row("Instructions", ins, checked, f"of {checked}",
                        "things your agent instructions point to exist. Nothing is wrong.", None, where))
    else:
        rows.append(row("Instructions", ins, broken, f"of {checked}",
                        "things your agent instructions point to are missing or wrong.", (broken, checked), where))
    rows.append(row(
        "Memory", mem, mem.get("rotten"), f"of {mem.get('files')}",
        "notes your agents remember are out of date.",
        (mem.get("rotten") or 0, mem.get("files") or 0), "agent memory in " + ", ".join(_short(p) for p in mem.get("read", []))))
    rows.append(row(
        "Decisions", dec, dec.get("rulings"), "decisions",
        f"saved in your own words. The latest is from {_day(dec.get('newest'))}.",
        None, f"decision log {_short(dec.get('read'))}"))
    if ski.get("found") and ski.get("opened_known"):
        never = ski["never_opened"]
        rows.append(row("Skills", ski, never, f"of {ski['installed']}",
                        "skills you installed have never been used.",
                        (never, ski["installed"]), "work history " + _short(ski.get("read"))))
    else:
        rows.append(row("Skills", ski, ski.get("installed"), "installed",
                        "Their use is unknown, because your work history is not searchable yet."))
    warned = idx.get("files_with_warnings")
    rows.append(row("History", idx, idx.get("sessions"), "sessions",
                    f"of your work with agents can be searched. The latest is from {_day(idx.get('newest'))}."
                    + (f" {warned} could not be read in full." if warned else ""),
                    None, "work history " + _short(idx.get("read"))))

    steps = []
    if behind:
        steps.append(("Update Helicon first. It is out of date.", f"git -C {_short(inst.get('read'))} pull"))
    if ins.get("found") and broken:
        steps.append((f"Fix the {_n(broken, 'thing')} your instructions point to that {'is' if broken == 1 else 'are'} missing or wrong.", f"helicon review {_short(ins['read'])}"))
    if mem.get("found") and mem.get("rotten"):
        steps.append((f"Look at the {_n(mem['rotten'], 'out-of-date note')} and fix or delete {'it' if mem['rotten'] == 1 else 'them'}.", f"helicon truth {_short(mem['read'][0])}"))
    if ski.get("opened_known") and ski.get("never_opened"):
        steps.append((f"Decide on the {_n(ski['never_opened'], 'skill')} you have never used: connect or remove {'it' if ski['never_opened'] == 1 else 'them'}.", ""))
    if not dec.get("found"):
        steps.append(("Start saving your decisions. Without them an agent cannot know what you decided.", ""))
    if not idx.get("found"):
        steps.append(("Make your work history searchable, so use and drift can be measured.", ""))
    return {"status": status, "rows": rows, "steps": steps[:3]}


def share(card):
    """The card as numbers another person may see: counts and rates, nothing else.

    No path, no file name, no skill name, no text from any note or session. This is
    what a person sends when ten setups are compared. A reading that was not found is
    null, never zero. Rates are shares between 0 and 1, so a setup with 20 notes and
    one with 400 can sit side by side.
    """
    ins, mem, dec, ski, idx = (card[k] for k in ("instructions", "memory", "decisions", "skills", "index"))

    def rate(part, whole):
        return round(part / whole, 4) if whole else None

    out = {"helicon_share": 1, "helicon_behind": (card.get("install") or {}).get("behind_main")}
    out["instructions"] = (
        {"checked": ins.get("checked", 0), "wrong": ins.get("broken", 0),
         "true_rate": rate(ins.get("checked", 0) - ins.get("broken", 0), ins.get("checked", 0))}
        if ins.get("found") else None)
    out["memory"] = (
        {"notes": mem.get("files", 0), "out_of_date": mem.get("rotten", 0),
         "fresh_rate": rate(mem.get("files", 0) - mem.get("rotten", 0), mem.get("files", 0))}
        if mem.get("found") else None)
    out["decisions"] = {"saved": dec.get("rulings", 0)} if dec.get("found") else None
    out["skills"] = (
        {"installed": ski["installed"], "never_used": ski["never_opened"],
         "used_rate": rate(ski["installed"] - ski["never_opened"], ski["installed"])}
        if ski.get("opened_known") else ({"installed": ski.get("installed")} if ski.get("found") else None))
    out["history"] = (
        {"sessions": idx.get("sessions", 0), "not_fully_read": idx.get("files_with_warnings")}
        if idx.get("found") else None)
    out["readings_found"] = sum(1 for key in ("instructions", "memory", "decisions", "skills", "history") if out[key])
    return out


def next_steps(card):
    """At most three things to do, worst first, in plain words."""
    return [text for text, _ in plain(card)["steps"]]


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
    """The card as text, in plain words. With colour it uses blues only."""
    view = plain(card)
    head = lambda text: _paint(text, "1;38;5;153", colour)  # noqa: E731
    num = lambda text: _paint(str(text), "1;38;5;117", colour)  # noqa: E731
    dim = lambda text: _paint(text, "38;5;67", colour)  # noqa: E731

    lines = ["", f"  {head('HELICON')}  where your context is, and its state", ""]
    sentence, problem = view["status"]
    if sentence:
        lines += [f"  {num(sentence) if problem else dim(sentence)}", ""]
    for row in view["rows"]:
        label = head(row["label"].ljust(14))
        if not row["found"]:
            lines.append(f"  {label}{dim('nothing found: ' + row['text'])}")
            continue
        number = f"{row['number']:,}" if isinstance(row["number"], int) else row["number"]
        lines.append(f"  {label}{num(number)} {row['unit']} {row['text']}".rstrip())
        if row["whole"]:
            lines.append(f"  {'':<14}{_bar(row['part'], row['whole'], colour)}")
    lines.append("")
    if view["steps"]:
        lines.append(f"  {head('Do next')}")
        for n, (text, command) in enumerate(view["steps"], 1):
            lines.append(f"    {num(n)}. {text}")
            if command:
                lines.append(dim(f"       run: {command}"))
    else:
        lines.append("  Nothing to fix was found in what could be read.")
    days = card.get("days")
    if days:
        lines.append("")
        if days < 2:
            lines.append(dim("  This is the first saved reading. Changes show from the second day."))
        else:
            moved = [f"{label} {value:+d}" for label, key in (
                ("out-of-date notes", "memory_rotten"), ("unused skills", "skills_never_opened"),
                ("wrong instructions", "instructions_broken"), ("decisions", "rulings"))
                if (value := (card.get("trend") or {}).get(key))]
            lines.append(dim(f"  Since the first of {days} days: " + (", ".join(moved) or "no change")))
    lines.append("")
    lines.append(dim("  Five separate readings. They are not added up."))
    return "\n".join(lines) + "\n"
