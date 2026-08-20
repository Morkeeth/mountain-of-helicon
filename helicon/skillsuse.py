"""Skills reviewed from USE, not prose: which installed skills actually fire.

Two invocation channels in local Claude Code transcripts, both collected:
  1. tool_use blocks: {"name": "Skill", "input": {"skill": "<name>"}}
  2. user slash commands: <command-name>/<name></command-name>

Honesty rules (the same discipline as setupcheck):
  - the window is stated: a skill absent from N days of LOCAL transcripts is
    "not seen fired in the window", never "dead" — older sessions, other
    machines, and cloud runs are invisible from here;
  - last-seen dates come from file mtimes (session-level resolution), and
    say so.
"""
import os
import re
import time

_CMD_RX = re.compile(r"<command-name>/([\w:-]+)</command-name>")
_SKILL_LINE = '"name":"Skill"'


def installed_skills(roots=None):
    roots = [os.path.expanduser(r) for r in (roots or ["~/.claude/skills"])]
    out = {}
    for r in roots:
        if not os.path.isdir(r):
            continue
        for d in sorted(os.listdir(r)):
            p = os.path.join(r, d)
            if not os.path.isdir(p):
                continue
            desc = ""
            skill_md = os.path.join(p, "SKILL.md")
            if os.path.isfile(skill_md):
                try:
                    with open(skill_md, errors="ignore") as f:
                        head = f.read(2000)
                    m = re.search(r"^description:\s*(.+)$", head, re.M)
                    desc = (m.group(1).strip() if m else "")
                except OSError:
                    pass
            out[d] = {"path": p, "desc_len": len(desc)}
    return out


def scan_usage(days=30, projects_root="~/.claude/projects"):
    """{skill_name: {count, last_day}} from local transcripts in the window."""
    root = os.path.expanduser(projects_root)
    cutoff = time.time() - days * 86400
    usage, files_scanned = {}, 0
    if not os.path.isdir(root):
        return usage, 0
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".jsonl"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                m = os.path.getmtime(p)
            except OSError:
                continue
            if m < cutoff:
                continue
            files_scanned += 1
            day = time.strftime("%Y-%m-%d", time.localtime(m))
            try:
                with open(p, errors="ignore") as f:
                    for line in f:
                        names = []
                        if _SKILL_LINE in line.replace(" ", ""):
                            mm = re.search(r'"skill"\s*:\s*"([\w:-]+)"', line)
                            if mm:
                                names.append(mm.group(1))
                        if "<command-name>" in line:
                            names.extend(_CMD_RX.findall(line))
                        for n in names:
                            u = usage.setdefault(n, {"count": 0, "last_day": day})
                            u["count"] += 1
                            if day > u["last_day"]:
                                u["last_day"] = day
            except OSError:
                continue
    return usage, files_scanned


def review(days=30, roots=None):
    skills = installed_skills(roots)
    usage, files_scanned = scan_usage(days)
    fired, quiet = [], []
    for name, meta in skills.items():
        u = usage.get(name)
        row = {"name": name, "desc_len": meta["desc_len"]}
        if u:
            fired.append({**row, **u})
        else:
            quiet.append(row)
    fired.sort(key=lambda r: -r["count"])
    # slash commands used that are NOT installed skills (built-ins, typos)
    foreign = sorted(n for n in usage if n not in skills)
    return {"days": days, "files_scanned": files_scanned,
            "fired": fired, "quiet": quiet, "foreign": foreign,
            "installed": len(skills)}


def render_review(r) -> str:
    out = [f"SKILLS REVIEW — {r['installed']} installed · "
           f"{r['files_scanned']} local transcripts scanned, last {r['days']} days",
           "(window truth: 'quiet' means not seen fired in THESE transcripts — "
           "older sessions, other machines and cloud runs are invisible from here; "
           "dates are session-file dates)", ""]
    out.append(f"FIRED IN WINDOW ({len(r['fired'])}):")
    for f in r["fired"]:
        thin = "  · THIN DESCRIPTION" if f["desc_len"] < 40 else ""
        out.append(f"  {f['name']:<28} {f['count']:>4}×  last {f['last_day']}{thin}")
    out.append("")
    out.append(f"NOT SEEN IN WINDOW ({len(r['quiet'])}):")
    for q in r["quiet"]:
        thin = "  · THIN DESCRIPTION" if q["desc_len"] < 40 else ""
        out.append(f"  {q['name']}{thin}")
    if r["foreign"]:
        out.append("")
        out.append(f"INVOKED BUT NOT AN INSTALLED SKILL ({len(r['foreign'])}, "
                   "built-ins/plugins/typos): " + ", ".join(r["foreign"][:20]))
    return "\n".join(out)
