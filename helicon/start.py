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
    # The scan reads every message, which takes seconds. The answer only changes when
    # the index or the installed set changes, so it is kept until one of them does.
    stat = os.stat(db)
    key = [stat.st_size, int(stat.st_mtime), sorted(names)]
    cache = os.path.join(os.path.expanduser("~"), ".helicon", "skills-cache.json") if home is None else None
    if cache:
        try:
            saved = json.load(open(cache, encoding="utf-8"))
            if saved.get("key") == key:
                return saved["result"]
        except (OSError, ValueError, KeyError):
            pass
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
    result = {"found": True, "read": db, "installed": len(names), "opened_known": True,
              "never_opened": len(never), "never_opened_names": never}
    if cache:
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            json.dump({"key": key, "result": result}, open(cache, "w", encoding="utf-8"))
        except OSError:
            pass
    return result


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


WORK_DAYS = 30


def _work_cache_path():
    return os.path.join(os.path.expanduser("~"), ".helicon", "work-cache.json")


def _spend(days, today):
    """Token spend from Transcripto, the tool that owns that number. None when it is
    not installed or gives nothing. Cached for the day: it takes about ten seconds."""
    import shutil

    command = os.environ.get("HELICON_TRANSCRIPTO") or shutil.which("transcripto")
    if not command:
        return None
    cache = _work_cache_path()
    try:
        saved = json.load(open(cache, encoding="utf-8"))
        if saved.get("day") == today and saved.get("days") == days:
            return saved["spend"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        done = subprocess.run([command, "cost", "--days", str(days), "--json"],
                              capture_output=True, text=True, timeout=120)
        raw = json.loads(done.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    tokens = raw.get("tokens") or {}
    messages, unpriced = raw.get("agent_messages") or 0, raw.get("unpriced_messages") or 0
    spend = {
        "usd": raw.get("usd"), "typed": raw.get("decisions"),
        "agent_messages": messages, "unpriced_messages": unpriced,
        "tokens": tokens.get("total"), "tokens_reread": tokens.get("cache_read"),
    }
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump({"day": today, "days": days, "spend": spend}, open(cache, "w", encoding="utf-8"))
    except OSError:
        pass
    return spend


def read_work(home=None, days=WORK_DAYS, today=None, with_spend=True):
    """What the person did with agents in the last `days` days: things typed, sessions,
    and what it cost. Typed turns and sessions come from the transcript index; spend
    comes from Transcripto. Counts only, never the text of a turn."""
    from datetime import date, timedelta

    db = _trace_db(home)
    if not db:
        return {"found": False, "why": "no searchable work history yet"}
    today = today or date.today().isoformat()
    since = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(messages)")}
        if "is_human" not in columns:
            return {"found": False, "read": db, "why": "the work history does not say which turns were typed"}
        typed = "is_human=1 AND text!='' AND ts>=?"
        if "harness" in columns:
            by_tool = dict(con.execute(
                f"SELECT COALESCE(harness, 'unknown'), COUNT(*) FROM messages WHERE {typed} GROUP BY 1", (since,)))
        else:
            by_tool = {"all": con.execute(f"SELECT COUNT(*) FROM messages WHERE {typed}", (since,)).fetchone()[0]}
        sessions = con.execute(f"SELECT COUNT(DISTINCT session_id) FROM messages WHERE {typed}", (since,)).fetchone()[0]
        per_day = dict(con.execute(
            f"SELECT substr(ts, 1, 10), COUNT(*) FROM messages WHERE {typed} GROUP BY 1", (since,)))
    except sqlite3.Error:
        return {"found": False, "read": db, "why": "the work history could not be read"}
    finally:
        con.close()
    start = date.fromisoformat(today) - timedelta(days=13)
    series = [per_day.get((start + timedelta(days=n)).isoformat(), 0) for n in range(14)]
    out = {"found": True, "read": db, "days": days, "typed": sum(by_tool.values()), "by_tool": by_tool,
           "sessions": sessions, "last_14_days": series}
    out["spend"] = _spend(days, today) if with_spend and home is None else None
    return out


_NOT_YOURS = ("com.apple.", "com.google.", "com.microsoft.", "com.docker.", "com.adobe.", "homebrew.")


def read_routines(home=None):
    """The scheduled work on this machine: jobs the system starts by itself, the classic
    cron table, and cloud routines when an agent has left a reading of them.

    A plain program cannot ask a cloud account what is scheduled there, so cloud
    routines come from `~/.helicon/cloud-routines.json`, written by an agent that can.
    The row says when that reading was taken."""
    import plistlib

    real_home = home is None
    home = home or os.path.expanduser("~")
    folder = os.path.join(home, "Library", "LaunchAgents")
    files = [f for f in glob.glob(os.path.join(folder, "*.plist"))
             if not os.path.basename(f).startswith(_NOT_YOURS)]
    backups = len([f for f in glob.glob(os.path.join(folder, "*")) if ".bak" in os.path.basename(f)])
    state = {}
    if real_home and files:
        try:
            listing = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=20).stdout
            for line in listing.splitlines()[1:]:
                parts = line.split("\t")
                if len(parts) == 3:
                    state[parts[2]] = parts[1]
        except (OSError, subprocess.TimeoutExpired):
            state = {}
    running = failed = missing = idle = 0
    for path in files:
        try:
            with open(path, "rb") as handle:
                job = plistlib.load(handle)
        except Exception:
            continue
        label = job.get("Label", "")
        program = next((a for a in (job.get("ProgramArguments") or [job.get("Program", "")]) if str(a).startswith("/")), "")
        if program and not os.path.exists(program):
            missing += 1
        if label in state:
            running += 1
            if state[label] not in ("0", "-"):
                failed += 1
        else:
            idle += 1
    cron = 0
    if real_home:
        try:
            table = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10).stdout
            cron = sum(1 for line in table.splitlines() if line.strip() and not line.lstrip().startswith("#"))
        except (OSError, subprocess.TimeoutExpired):
            cron = 0
    cloud = None
    try:
        saved = json.load(open(os.path.join(home, ".helicon", "cloud-routines.json"), encoding="utf-8"))
        rows = saved.get("routines") or []
        cloud = {"on": sum(1 for r in rows if r.get("on")), "off": sum(1 for r in rows if not r.get("on")),
                 "read_at": saved.get("read_at", "")}
    except (OSError, ValueError):
        cloud = None
    if not files and not cron and not cloud:
        return {"found": False, "why": "no scheduled jobs on this machine"}
    return {"found": True, "read": folder, "jobs": len(files), "running": running, "failed": failed,
            "missing_program": missing, "not_running": idle, "backups": backups, "cron_lines": cron,
            "known": bool(state) or not files, "cloud": cloud}


def read_size(home=None):
    """How much there is: what every session reads first, how many notes, how long the
    longest are. Large is not wrong; the row is here so growth is seen."""
    home = home or os.path.expanduser("~")
    always = [os.path.join(home, ".claude", "CLAUDE.md")] + glob.glob(os.path.join(home, ".claude", "rules", "*.md"))
    stores = memory_stores(home)
    notes = glob.glob(os.path.join(stores[0], "*.md")) if stores else []
    index = os.path.join(stores[0], "MEMORY.md") if stores else ""
    if index:
        always.append(index)
    loaded = sum(os.path.getsize(f) for f in always if os.path.isfile(f))
    if not loaded and not notes:
        return {"found": False, "why": "no rules or notes found"}
    return {"found": True, "always_loaded_chars": loaded, "always_loaded_files": sum(1 for f in always if os.path.isfile(f)),
            "notes": len(notes), "long_notes": sum(1 for f in notes if os.path.getsize(f) > 15000)}


def read_stalled(home=None, code_root=None, days=30, today=None):
    """Projects with unfinished changes and no commit for `days` days. Cached for the
    day, because it asks git about every project folder."""
    from datetime import date

    if home is not None and code_root is None:
        return {"found": False, "why": "no project folder given"}
    code_root = code_root or os.environ.get("HELICON_CODE_ROOT") or os.path.join(os.path.expanduser("~"), "CODE")
    if not os.path.isdir(code_root):
        return {"found": False, "why": "no project folder found"}
    today = today or date.today().isoformat()
    cache = os.path.join(os.path.expanduser("~"), ".helicon", "stalled-cache.json") if home is None else None
    if cache:
        try:
            saved = json.load(open(cache, encoding="utf-8"))
            if saved.get("day") == today and saved.get("root") == code_root and saved.get("days") == days:
                return saved["result"]
        except (OSError, ValueError, KeyError):
            pass
    import time

    now, projects, stalled = time.time(), 0, 0
    for entry in sorted(os.listdir(code_root)):
        path = os.path.join(code_root, entry)
        if not os.path.isdir(os.path.join(path, ".git")):
            continue
        projects += 1
        try:
            last = subprocess.run(["git", "-C", path, "log", "-1", "--format=%ct"], capture_output=True, text=True, timeout=15).stdout.strip()
            dirty = subprocess.run(["git", "-C", path, "status", "--porcelain"], capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            continue
        if last.isdigit() and dirty and (now - int(last)) > days * 86400:
            stalled += 1
    result = {"found": bool(projects), "why": "no git projects in the project folder", "read": code_root,
              "projects": projects, "stalled": stalled, "days": days}
    if cache:
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            json.dump({"day": today, "root": code_root, "days": days, "result": result}, open(cache, "w", encoding="utf-8"))
        except OSError:
            pass
    return result


def system_plain(card):
    """The operating system around the agents, in plain words: what runs by itself,
    what was left behind, how much there is, and what stalled."""
    rows = []
    rt, size, stall = (card.get(k) or {} for k in ("routines", "size", "stalled"))
    if rt.get("found"):
        if rt.get("jobs"):
            bits = []
            if rt.get("known"):
                bits.append(f"{rt['failed']} failed their last run." if rt["failed"] else "None failed its last run.")
            if rt.get("missing_program"):
                bits.append(f"{_n(rt['missing_program'], 'job')} point at something that no longer exists.")
            number, unit = (rt["running"], f"of {rt['jobs']}") if rt.get("known") else (rt["jobs"], "jobs")
            lead = "scheduled jobs are running." if rt.get("known") else "scheduled job files were found. Which ones run is unknown here."
            rows.append({"label": "Routines", "number": number, "unit": unit, "text": " ".join([lead] + bits),
                         "part": rt["failed"] if rt.get("known") else None, "whole": rt["running"] if rt.get("known") else None})
            left = rt.get("not_running", 0) + rt.get("backups", 0)
            if rt.get("known") and left:
                rows.append({"label": "Left behind", "number": left, "unit": "files",
                             "text": f"sit unused in the same folder: {rt['not_running']} job files that are not running and {_n(rt['backups'], 'backup copy', 'backup copies')}."})
        if rt.get("cron_lines"):
            rows.append({"label": "Cron", "number": rt["cron_lines"], "unit": "lines",
                         "text": "in the classic timer table. Helicon counts them and does not check them yet."})
        cloud = rt.get("cloud")
        if cloud:
            rows.append({"label": "Cloud", "number": cloud["on"], "unit": f"of {cloud['on'] + cloud['off']}",
                         "text": f"cloud routines are switched on. Read by an agent on {_day(cloud['read_at'])}; Helicon cannot read the cloud by itself."})
    if size.get("found"):
        rows.append({"label": "Every session", "number": f"{size['always_loaded_chars']:,}", "unit": "characters",
                     "text": f"of your rules are read at the start of each session, from {_n(size['always_loaded_files'], 'file')}."})
        if size.get("notes"):
            long_notes = size["long_notes"]
            rows.append({"label": "Notes", "number": size["notes"], "unit": "notes",
                         "text": (f"in your agents' memory. {long_notes} of them {'is' if long_notes == 1 else 'are'} longer than a chapter."
                                  if long_notes else "in your agents' memory. None is longer than a chapter.")})
    if stall.get("found"):
        rows.append({"label": "Stalled", "number": stall["stalled"], "unit": f"of {stall['projects']}",
                     "text": f"projects have unfinished changes and no commit in {stall['days']} days.",
                     "part": stall["stalled"], "whole": stall["projects"]})
    return rows


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

    work_rows = work_plain(card.get("work") or {})

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
    routines = card.get("routines") or {}
    if routines.get("known") and (routines.get("failed") or routines.get("missing_program")):
        broken = max(routines.get("failed", 0), routines.get("missing_program", 0))
        steps.append((f"Look at the {_n(broken, 'scheduled job')} that failed or point at nothing, and remove or repair them.", ""))
    return {"status": status, "rows": rows, "work": work_rows, "system": system_plain(card), "steps": steps[:3]}


def work_plain(work):
    """The work of the last weeks in plain words. Each row: label, number, unit, text,
    and for the first row the last 14 days as a series."""
    if not work.get("found"):
        return []
    days = work["days"]
    tools = ", ".join(f"{name.capitalize()} {count:,}" for name, count in
                      sorted(work["by_tool"].items(), key=lambda item: -item[1]))
    rows = [
        {"label": "Prompts", "number": work["typed"], "unit": "typed",
         "text": f"to your agents in {days} days. {tools}.", "series": work["last_14_days"]},
        {"label": "Sessions", "number": work["sessions"], "unit": "sessions",
         "text": f"of work with agents in {days} days."},
    ]
    spend = work.get("spend")
    if not spend or spend.get("usd") is None:
        rows.append({"label": "Spend", "number": None, "unit": "",
                     "text": "nothing found: the tool that reads token spend is not installed."})
        return rows
    messages, unpriced = spend.get("agent_messages") or 0, spend.get("unpriced_messages") or 0
    more = "or more, " if unpriced else ""
    gap = (f" {round(100 * unpriced / messages)}% of agent replies have no price on record, so the real figure is higher."
           if messages and unpriced else "")
    rows.append({"label": "Spend", "number": f"${spend['usd']:,.0f}", "unit": f"{more}at list price",
                 "text": f"in {days} days, Claude Code only. On a subscription this is not a bill.{gap}"})
    if spend.get("typed"):
        per = spend["usd"] / spend["typed"]
        steps_each = round(messages / spend["typed"]) if messages else None
        rows.append({"label": "Per prompt", "number": f"${per:,.2f}", "unit": f"{more}each",
                     "text": (f"and about {steps_each} agent replies for each thing you typed." if steps_each
                              else "for each thing you typed.")})
    if spend.get("tokens") and spend.get("tokens_reread") is not None:
        share = round(100 * spend["tokens_reread"] / spend["tokens"])
        rows.append({"label": "Re-reading", "number": f"{share}%", "unit": "of all tokens",
                     "text": "were the agent reading earlier context again. A token is a small piece of text the model reads or writes.",
                     "part": spend["tokens_reread"], "whole": spend["tokens"]})
    return rows


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
    work = card.get("work") or {}
    if work.get("found"):
        spend = work.get("spend") or {}
        out["work"] = {"days": work["days"], "typed": work["typed"], "sessions": work["sessions"],
                       "by_tool": work["by_tool"], "list_price_usd": spend.get("usd"),
                       "agent_replies": spend.get("agent_messages"), "replies_without_price": spend.get("unpriced_messages"),
                       "tokens": spend.get("tokens"), "tokens_reread": spend.get("tokens_reread")}
    else:
        out["work"] = None
    rt, size, stall = (card.get(k) or {} for k in ("routines", "size", "stalled"))
    out["routines"] = ({k: rt.get(k) for k in ("jobs", "running", "failed", "missing_program", "not_running", "backups", "cron_lines")}
                       | {"cloud_on": (rt.get("cloud") or {}).get("on"), "cloud_off": (rt.get("cloud") or {}).get("off")}) if rt.get("found") else None
    out["size"] = {k: size.get(k) for k in ("always_loaded_chars", "notes", "long_notes")} if size.get("found") else None
    out["stalled"] = {k: stall.get(k) for k in ("projects", "stalled", "days")} if stall.get("found") else None
    out["readings_found"] = sum(1 for key in ("instructions", "memory", "decisions", "skills", "history") if out[key])
    return out


def menu_line(card):
    """One line for the menu bar, and how many things need a person. Problems only,
    worst first, in plain words; "All in order" when none was found."""
    ins, mem = card.get("instructions") or {}, card.get("memory") or {}
    rt, inst = card.get("routines") or {}, card.get("install") or {}
    parts = []
    if inst.get("behind_main"):
        parts.append("Helicon is out of date")
    if ins.get("found") and ins.get("broken"):
        parts.append(f"{_n(ins['broken'], 'instruction')} wrong")
    if mem.get("found") and mem.get("rotten"):
        parts.append(f"{_n(mem['rotten'], 'note')} out of date")
    if rt.get("known") and rt.get("failed"):
        parts.append(f"{_n(rt['failed'], 'job')} failing")
    if not parts:
        return "All in order", 0
    return " · ".join(parts[:3]), len(parts)


def line_path():
    return os.path.join(os.path.expanduser("~"), ".helicon", "start-line.json")


def save_line(card, when, path=None):
    """Keep the one line on disk, so a session start or a menu bar can show it
    without building the card. Overwritten on each build; holds no path or name."""
    path = path or line_path()
    line, to_fix = menu_line(card)
    row = {"at": when, "line": line, "to_fix": to_fix}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(row, handle)
    except OSError:
        pass
    return row


def saved_line(path=None, now=None):
    """The last saved line as one sentence with its age, or None when there is none."""
    from datetime import datetime

    try:
        row = json.load(open(path or line_path(), encoding="utf-8"))
        then = datetime.fromisoformat(row["at"])
        line = row["line"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    now = now or datetime.now().astimezone()
    minutes = max(0, int((now - then).total_seconds() // 60))
    if minutes < 60:
        age = "just now" if minutes < 2 else f"{minutes} minutes ago"
    elif minutes < 48 * 60:
        age = _n(minutes // 60, "hour") + " ago"
    else:
        age = _n(minutes // 1440, "day") + " ago"
    return f"Helicon: {line} (read {age})"


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
        "work": read_work(home),
        "routines": read_routines(home),
        "size": read_size(home),
        "stalled": read_stalled(home),
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
    if view.get("work"):
        lines += ["", f"  {head('YOUR WORK')}"]
        for row in view["work"]:
            number = f"{row['number']:,}" if isinstance(row["number"], int) else (row["number"] or "")
            lines.append(f"  {head(row['label'].ljust(14))}{num(number)} {row['unit']} {row['text']}".replace("  nothing", " nothing").rstrip())
            if row.get("series") and any(row["series"]):
                top = max(row["series"])
                marks = "".join(" ▁▂▃▄▅▆▇█"[round(8 * value / top)] for value in row["series"])
                lines.append(f"  {'':<14}{_paint(marks, '38;5;68', colour)}  the last 14 days")
            elif row.get("whole"):
                lines.append(f"  {'':<14}{_bar(row['part'], row['whole'], colour)}")
    if view.get("system"):
        lines += ["", f"  {head('WHAT RUNS AROUND YOUR AGENTS')}"]
        for row in view["system"]:
            number = f"{row['number']:,}" if isinstance(row["number"], int) else row["number"]
            lines.append(f"  {head(row['label'].ljust(14))}{num(number)} {row['unit']} {row['text']}")
            if row.get("whole"):
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
