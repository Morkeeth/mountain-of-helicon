"""The setup census and two-axis score — pure functions, no FastAPI, no app state.

Shared by `GET /api/setup` (helicon.api.setup) and `helicon setup` (cli).
Everything takes (conn, config) explicitly, and BOTH may be missing:

  conn=None    — no ~/.helicon/helicon.db yet. Store-backed cells return
                 measured: False with the reason, never a crash and never a
                 zero-that-reads-as-a-grade. This is the zero-config path a
                 stranger hits on `pip install && helicon setup`, and it is
                 the product's own cold-start law (PRODUCT-SURFACE-PROPOSAL
                 v3): "your stack is thin" and "Helicon has not looked yet"
                 must never render the same.
  config={}    — no config.json. Connector-gated cells (skills) say so.

Axis-2 chips each carry a citation; the reference corpus is
docs/memory-context-frontier-2026-08.md.
"""
import os
import subprocess
import time
from datetime import datetime, timezone

# Live = a memory a reader could still be handed. The statuses are printed in
# the cell's `how` so the number is auditable against the store directly.
LIVE_SQL = ("SELECT COUNT(*) FROM helicon_cubes WHERE review_status IN "
            "('approved','pending','revised') AND merged_into IS NULL")
RETIRED_SQL = ("SELECT COUNT(*) FROM helicon_cubes WHERE review_status IN "
               "('killed','superseded')")


def cell(value, how: str, measured: bool = True):
    return {"value": value, "measured": measured, "how": how}


def unmeasured(reason: str):
    return {"value": None, "measured": False, "how": reason}


def file_stat(label: str, path: str) -> dict:
    p = os.path.expanduser(path)
    if not os.path.isfile(p):
        return {"label": label, "path": path, "exists": False}
    st = os.stat(p)
    with open(p, "rb") as f:
        lines = f.read().count(b"\n")
    return {
        "label": label, "path": path, "exists": True,
        "lines": lines, "bytes": st.st_size,
        "age_days": round((time.time() - st.st_mtime) / 86400, 1),
    }


def census(conn, cfg: dict) -> dict:
    home = os.path.expanduser("~")
    connectors = (cfg or {}).get("connectors") or {}

    # Skills: same privacy gate as the findings surface — only count what the
    # operator wired via the connector; never scan a hardcoded path.
    sk = connectors.get("skills") or {}
    if sk.get("enabled"):
        roots = [os.path.expanduser(r) for r in (sk.get("skill_roots") or
                 ["~/.claude/skills"])]
        roots = [r for r in roots if os.path.isdir(r)]
        names = sorted({d for r in roots for d in os.listdir(r)
                        if os.path.isdir(os.path.join(r, d))})
        skills = cell(len(names), f"directories under {', '.join(roots) or 'no root'}")
        skills["names"] = names
    else:
        skills = unmeasured("skills connector not enabled in config.json")

    # Routines: local crontab + launchd are measurable from this machine.
    # Crontab is counted RAW, not via stackwatch._cron_routines(): that helper
    # is a liveness monitor and skips any job without a .log redirect, which
    # made this census read 2 on a crontab of 3 (caught 2026-08-20).
    try:
        cron_txt = subprocess.run(["crontab", "-l"], capture_output=True,
                                  text=True, timeout=10).stdout
        cron_jobs = [l for l in cron_txt.splitlines()
                     if l.strip() and not l.strip().startswith("#")
                     and not (l.split("=")[0].strip().isidentifier()
                              and "=" in l and not l.strip()[0].isdigit()
                              and not l.strip().startswith(("@", "*")))]
        from helicon.stackwatch import _launchd_routines
        agents = _launchd_routines()
        routines = cell(
            len(cron_jobs) + len(agents),
            f"{len(cron_jobs)} crontab lines + {len(agents)} launchd agents (local only)")
        routines["unmeasured_note"] = ("cloud/scheduled agents are not visible "
                                       "from this machine")
    except Exception as e:  # crontab may not exist at all
        routines = unmeasured(f"routine probe failed: {e}")

    if conn is not None:
        memories = {
            "live": cell(conn.execute(LIVE_SQL).fetchone()[0],
                         "helicon_cubes: approved+pending+revised, not merged"),
            "retired": cell(conn.execute(RETIRED_SQL).fetchone()[0],
                            "helicon_cubes: killed+superseded"),
        }
    else:
        memories = {
            "live": unmeasured("no helicon store yet — run `helicon init && helicon scan` to build one"),
            "retired": unmeasured("no helicon store yet"),
        }

    projects_dir = os.path.join(home, ".claude", "projects")
    if os.path.isdir(projects_dir):
        n = sum(1 for _, _, files in os.walk(projects_dir)
                for f in files if f.endswith(".jsonl"))
        sessions = cell(n, f"*.jsonl transcripts under {projects_dir}")
    else:
        sessions = unmeasured(f"{projects_dir} does not exist")

    cc = connectors.get("claude-code") or {}
    memory_dir = os.path.expanduser(cc.get("memory_dir") or "")
    how_found = "claude-code connector memory_dir"
    if not memory_dir or not os.path.isdir(memory_dir):
        # Zero-config fallback: Claude Code's auto-memory default is one
        # memory/ dir PER PROJECT under ~/.claude/projects. Use the one with
        # the most recently touched MEMORY.md as the active index.
        candidates = []
        projects_root = os.path.join(home, ".claude", "projects")
        if os.path.isdir(projects_root):
            for d in os.listdir(projects_root):
                idx_p = os.path.join(projects_root, d, "memory", "MEMORY.md")
                if os.path.isfile(idx_p):
                    candidates.append((os.path.getmtime(idx_p),
                                       os.path.dirname(idx_p)))
        if candidates:
            candidates.sort(reverse=True)
            memory_dir = candidates[0][1]
            how_found = (f"most recently touched of {len(candidates)} "
                         "auto-memory dirs under ~/.claude/projects")
        else:
            memory_dir = ""
    context_files = [
        file_stat("global CLAUDE.md", "~/.claude/CLAUDE.md"),
        file_stat("GOLDEN_RULES.md", "~/.claude/GOLDEN_RULES.md"),
    ]
    if memory_dir:
        context_files.append(file_stat(
            "MEMORY.md (auto-memory index)", os.path.join(memory_dir, "MEMORY.md")))
        mem_files = [f for f in os.listdir(memory_dir) if f.endswith(".md")]
        memories["files"] = cell(
            len(mem_files), f"*.md files in {memory_dir} ({how_found})")
        memories["dir"] = memory_dir
    else:
        memories["files"] = unmeasured(
            "no memory dir found (connector unset; no MEMORY.md under "
            "~/.claude/projects/*/memory)")

    return {
        "skills": skills,
        "routines": routines,
        "memories": memories,
        "sessions": sessions,
        "context_files": context_files,
        "connectors": {k: bool((v or {}).get("enabled"))
                       for k, v in connectors.items()},
    }


def _chip(cid, claim, verdict, probe, source):
    return {"id": cid, "claim": claim, "verdict": verdict,
            "probe": probe, "source": source}


def axis2(conn, cen: dict, cfg: dict) -> list[dict]:
    """You-vs-the-frontier. Each chip is a deterministic probe + a citation.
    Verdicts are PASS / FAIL / UNMEASURED — a chip that cannot run never
    pretends to pass."""
    chips = []

    claude_md = next((f for f in cen["context_files"]
                      if f["label"] == "global CLAUDE.md"), None)
    if claude_md and claude_md.get("exists"):
        n = claude_md["lines"]
        chips.append(_chip(
            "rules-file-size", "Always-loaded rules file stays under ~200 lines",
            "PASS" if n <= 200 else "FAIL", f"global CLAUDE.md is {n} lines",
            "Anthropic, Effective Context Engineering (Sept 2025)"))
    else:
        chips.append(_chip("rules-file-size",
                           "Always-loaded rules file stays under ~200 lines",
                           "UNMEASURED", "no global CLAUDE.md found",
                           "Anthropic, Effective Context Engineering (Sept 2025)"))

    idx = next((f for f in cen["context_files"]
                if f["label"].startswith("MEMORY.md")), None)
    if idx and idx.get("exists"):
        n = idx["lines"]
        chips.append(_chip(
            "memory-index-pointer",
            "Memory index stays a pointer layer (≤200 lines; bodies on disk)",
            "PASS" if n <= 200 else "FAIL", f"MEMORY.md is {n} lines",
            "Claude Code auto-memory docs; Skills progressive disclosure"))
    else:
        chips.append(_chip("memory-index-pointer",
                           "Memory index stays a pointer layer (≤200 lines)",
                           "UNMEASURED", "no MEMORY.md found",
                           "Claude Code auto-memory docs"))

    mem_files = cen["memories"].get("files") or {}
    mdir = cen["memories"].get("dir") or ""
    if mem_files.get("measured") and mdir:
        hits = 0
        for f in os.listdir(mdir):
            if f.endswith(".md"):
                try:
                    with open(os.path.join(mdir, f), errors="ignore") as fh:
                        if "valid_until" in fh.read():
                            hits += 1
                except OSError:
                    pass
        chips.append(_chip(
            "validity-windows",
            "Superseded facts carry validity windows instead of being deleted",
            "PASS" if hits > 0 else "FAIL",
            f"{hits} of {mem_files['value']} memory files contain 'valid_until'",
            "Zep/Graphiti bi-temporal edges (arXiv 2501.13956)"))
    else:
        chips.append(_chip("validity-windows",
                           "Superseded facts carry validity windows",
                           "UNMEASURED", "no memory dir readable",
                           "Zep/Graphiti (arXiv 2501.13956)"))

    if conn is not None:
        row = conn.execute("SELECT MAX(created_at) FROM consolidations").fetchone()
        last = row[0] if row else None
    else:
        last = None
    if last:
        try:
            age_d = (datetime.now(timezone.utc).replace(tzinfo=None)
                     - datetime.fromisoformat(last.split("+")[0].rstrip("Z"))
                     ).total_seconds() / 86400
            chips.append(_chip(
                "consolidation-cadence",
                "Memory consolidation ran within the last 14 days",
                "PASS" if age_d <= 14 else "FAIL",
                f"last consolidation {age_d:.0f} days ago ({last[:10]})",
                "Letta sleep-time compute; Anthropic Dreams (May 2026)"))
        except ValueError:
            chips.append(_chip("consolidation-cadence",
                               "Memory consolidation ran within the last 14 days",
                               "UNMEASURED", f"unparseable timestamp: {last!r}",
                               "Letta; Anthropic Dreams"))
    else:
        chips.append(_chip("consolidation-cadence",
                           "Memory consolidation ran within the last 14 days",
                           "UNMEASURED",
                           "no consolidation history" + ("" if conn is not None
                            else " (no helicon store yet)"),
                           "Letta sleep-time compute; Anthropic Dreams (May 2026)"))

    always = [f for f in cen["context_files"]
              if f.get("exists") and f["label"] in ("global CLAUDE.md",)]
    if idx and idx.get("exists"):
        always.append(idx)
    if always:
        total = sum(f["bytes"] for f in always)
        chips.append(_chip(
            "context-weight",
            "Always-loaded context stays light (≤40KB; rest read on demand)",
            "PASS" if total <= 40_000 else "FAIL",
            f"{total:,} bytes always loaded ({' + '.join(f['label'] for f in always)})",
            "Manus KV-cache lessons; index-in-context/bodies-on-disk"))
    else:
        chips.append(_chip("context-weight",
                           "Always-loaded context stays light (≤40KB)",
                           "UNMEASURED", "no always-loaded context files found",
                           "Manus KV-cache lessons"))
    return chips
