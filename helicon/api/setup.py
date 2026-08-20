"""The SETUP surface — the census of the stack and the two-axis score.

Ruled 2026-08-20 (PRODUCT-SURFACE-PROPOSAL.md v3): axis 1 PRIMARY is you-vs-you
(a dated snapshot per explicit recording, the score is a trend, never a lone
number); axis 2 SECONDARY is you-vs-the-frontier (each check cites a source —
docs/memory-context-frontier-2026-08.md is the reference corpus).

Two doctrines inherited from siblings, on purpose:
  - measure.py: a page load must not write a row. GET reads; POST /snapshot
    records, and re-recording inside one day REPLACES that day's row.
  - rot.py: a cached read is never silent — every response carries ran_at +
    cached, and ?fresh=1 forces a real walk.

Every census cell is {value, measured, how}. A cell this machine cannot see
(cloud routines, skills last-fired) says measured: false with the reason —
a zero rendered as a green is the exact rot this product exists to catch.
"""
import os
import subprocess
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from helicon.api.app import get_conn, get_config

router = APIRouter()

_TTL_S = 120
_cache: dict = {"res": None, "mono": 0.0, "ran_at": None, "took_s": None}

# Live = a memory a reader could still be handed. The statuses are printed in
# the cell's `how` so the number is auditable against the store directly.
_LIVE_SQL = ("SELECT COUNT(*) FROM helicon_cubes WHERE review_status IN "
             "('approved','pending','revised') AND merged_into IS NULL")
_RETIRED_SQL = ("SELECT COUNT(*) FROM helicon_cubes WHERE review_status IN "
                "('killed','superseded')")


def _cell(value, how: str, measured: bool = True):
    return {"value": value, "measured": measured, "how": how}


def _unmeasured(reason: str):
    return {"value": None, "measured": False, "how": reason}


def _file_stat(label: str, path: str) -> dict:
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


def _census(conn, cfg: dict) -> dict:
    home = os.path.expanduser("~")
    connectors = cfg.get("connectors") or {}

    # Skills: same privacy gate as findings._skill_findings — only count what
    # the operator wired via the connector; never scan a hardcoded path.
    sk = connectors.get("skills") or {}
    if sk.get("enabled"):
        roots = [os.path.expanduser(r) for r in (sk.get("skill_roots") or
                 ["~/.claude/skills"])]
        roots = [r for r in roots if os.path.isdir(r)]
        names = sorted({d for r in roots for d in os.listdir(r)
                        if os.path.isdir(os.path.join(r, d))})
        skills = _cell(len(names), f"directories under {', '.join(roots) or 'no root'}")
        skills["names"] = names
    else:
        skills = _unmeasured("skills connector not enabled in config.json")

    # Routines: local crontab + launchd are measurable from this machine.
    # Cloud routines are not — and the cell says so instead of reading 0.
    # Crontab is counted RAW here, not via stackwatch._cron_routines(): that
    # helper is a liveness monitor and skips any job without a .log redirect,
    # which made this census read 2 on a crontab of 3 (caught 2026-08-20).
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
        routines = _cell(
            len(cron_jobs) + len(agents),
            f"{len(cron_jobs)} crontab lines + {len(agents)} launchd agents (local only)")
        routines["unmeasured_note"] = ("cloud/scheduled agents are not visible "
                                       "from this machine")
    except Exception as e:  # crontab may not exist at all
        routines = _unmeasured(f"routine probe failed: {e}")

    memories = {
        "live": _cell(conn.execute(_LIVE_SQL).fetchone()[0],
                      "helicon_cubes: approved+pending+revised, not merged"),
        "retired": _cell(conn.execute(_RETIRED_SQL).fetchone()[0],
                         "helicon_cubes: killed+superseded"),
    }

    # Sessions: a filesystem walk, which is why GET is cached with a TTL.
    projects_dir = os.path.join(home, ".claude", "projects")
    if os.path.isdir(projects_dir):
        n = sum(1 for _, _, files in os.walk(projects_dir)
                for f in files if f.endswith(".jsonl"))
        sessions = _cell(n, f"*.jsonl transcripts under {projects_dir}")
    else:
        sessions = _unmeasured(f"{projects_dir} does not exist")

    cc = connectors.get("claude-code") or {}
    memory_dir = os.path.expanduser(cc.get("memory_dir") or "")
    context_files = [
        _file_stat("global CLAUDE.md", "~/.claude/CLAUDE.md"),
        _file_stat("GOLDEN_RULES.md", "~/.claude/GOLDEN_RULES.md"),
    ]
    if memory_dir and os.path.isdir(memory_dir):
        context_files.append(_file_stat(
            "MEMORY.md (auto-memory index)", os.path.join(memory_dir, "MEMORY.md")))
        mem_files = [f for f in os.listdir(memory_dir) if f.endswith(".md")]
        memories["files"] = _cell(len(mem_files), f"*.md files in {memory_dir}")
    else:
        memories["files"] = _unmeasured(
            "claude-code connector has no valid memory_dir")

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


def _axis2(conn, census: dict) -> list[dict]:
    """You-vs-the-frontier. Each chip is a deterministic probe + a citation.
    Verdicts are PASS / FAIL / UNMEASURED — a chip that cannot run never
    pretends to pass. Reference corpus: docs/memory-context-frontier-2026-08.md."""
    chips = []

    claude_md = next((f for f in census["context_files"]
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

    idx = next((f for f in census["context_files"]
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

    mem_files = census["memories"].get("files") or {}
    if mem_files.get("measured"):
        cc = (get_config().get("connectors") or {}).get("claude-code") or {}
        mdir = os.path.expanduser(cc.get("memory_dir") or "")
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
                           "UNMEASURED", "memory_dir not readable",
                           "Zep/Graphiti (arXiv 2501.13956)"))

    row = conn.execute("SELECT MAX(created_at) FROM consolidations").fetchone()
    last = row[0] if row else None
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
                           "UNMEASURED", "consolidations table is empty",
                           "Letta sleep-time compute; Anthropic Dreams (May 2026)"))

    always = [f for f in census["context_files"]
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
    return chips


_SNAP_DDL = """CREATE TABLE IF NOT EXISTS setup_snapshots (
    day TEXT PRIMARY KEY,
    taken_at TEXT NOT NULL,
    skills INTEGER, routines INTEGER,
    memories_live INTEGER, memories_retired INTEGER,
    sessions INTEGER, context_bytes INTEGER,
    chips_pass INTEGER, chips_fail INTEGER, chips_unmeasured INTEGER
)"""


def _snapshots(conn) -> list[dict]:
    conn.execute(_SNAP_DDL)
    rows = conn.execute(
        "SELECT * FROM setup_snapshots ORDER BY day DESC LIMIT 60").fetchall()
    return [dict(r) for r in rows]


@router.get("/setup")
async def setup(fresh: int = 0):
    if not fresh and _cache["res"] is not None and \
            (time.monotonic() - _cache["mono"]) < _TTL_S:
        return {**_cache["res"], "ran_at": _cache["ran_at"],
                "took_s": _cache["took_s"], "cached": True,
                "snapshots": _snapshots(get_conn())}
    conn = get_conn()
    t0 = time.monotonic()
    census = _census(conn, get_config() or {})
    chips = _axis2(conn, census)
    res = {"census": census, "axis2": chips}
    took = round(time.monotonic() - t0, 2)
    _cache.update({"res": res, "mono": time.monotonic(), "took_s": took,
                   "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {**res, "ran_at": _cache["ran_at"], "took_s": took, "cached": False,
            "snapshots": _snapshots(conn)}


@router.post("/setup/snapshot")
async def take_snapshot():
    """Record today's reading. Re-running inside one day REPLACES that day's
    row — a day glanced at four times is still one day (measure.py doctrine)."""
    conn = get_conn()
    conn.execute(_SNAP_DDL)
    census = _census(conn, get_config() or {})
    chips = _axis2(conn, census)

    def _v(cell):
        return cell.get("value") if cell.get("measured") else None

    always = sum(f["bytes"] for f in census["context_files"] if f.get("exists"))
    verdicts = [c["verdict"] for c in chips]
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT OR REPLACE INTO setup_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (now.date().isoformat(), now.isoformat(timespec="seconds"),
         _v(census["skills"]), _v(census["routines"]),
         _v(census["memories"]["live"]), _v(census["memories"]["retired"]),
         _v(census["sessions"]), always,
         verdicts.count("PASS"), verdicts.count("FAIL"),
         verdicts.count("UNMEASURED")))
    conn.commit()
    return {"recorded": now.date().isoformat(), "snapshots": _snapshots(conn)}
