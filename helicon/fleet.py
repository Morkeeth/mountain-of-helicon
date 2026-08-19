"""The Fleet — one screen for five terminals (V2.4).

The operator's actual problem, in his words: five terminals deep, three or four
projects, "no clue what context was used", "lose track of what each terminal is
doing", no top agenda, no read on spend. Every existing surface here answers a
question about ONE run. None answers "what is my fleet doing right now".

Shape borrowed deliberately:
  · k9s / lazygit — a live resource view you leave open, not a report you run
  · Vercel        — state at a glance, one line per unit, colourless until wrong
  · Linear        — ONE triage queue, never a dashboard of dashboards

Four questions, in the order they actually matter to someone with five terminals
open. Anything that does not answer one of them does not belong on this screen:

  RUNNING    what is live right now, and has any of it drifted off its objective
  SPEND      where the tokens went, by project
  REVIEW     what finished without your eyes on it
  EFFICIENCY do your accepted runs cost less than your rejected ones

DRIFT is the novel one and the one to be most careful about. The deep-research
pass found ZERO published, verified techniques for detecting that an agent has
wandered off-objective. So this ships a heuristic and calls it a heuristic:
term overlap between the frozen objective and the paths actually touched. It
CANNOT prove drift. A refactor legitimately touches files sharing no vocabulary
with its objective. So the label is "worth a look", never "off-objective", and
it is only ever computed for runs with a REAL frozen objective — an auto-
observed run has no objective to drift from, and flagging one would be inventing
a contract that never existed.
"""
import glob
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

# Where Claude Code keeps its transcripts. The only local record of which
# terminals exist and when each last did anything.
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

# A session that has not emitted a line in this long is not thinking.
IDLE_AFTER_MIN = 20
# Older than this and it is not a terminal someone still has open, it is history.
STALE_AFTER_H = 12

# Words that appear in every objective and every path, so they can only create
# false agreement. Kept small on purpose: an over-eager stoplist manufactures
# drift by deleting the very terms that matched.
_NOISE = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
          "that", "this", "is", "it", "be", "as", "at", "by", "from", "src",
          "lib", "test", "tests", "py", "ts", "tsx", "js", "md", "json", "helicon"}

DRIFT_MIN_FILES = 4     # below this, "no shared vocabulary" is just a small diff


def _terms(text: str) -> set:
    out = set()
    for w in "".join(c if c.isalnum() else " " for c in (text or "").lower()).split():
        if len(w) > 2 and w not in _NOISE:
            out.add(w)
    return out


def _loads(raw, default):
    try:
        return json.loads(raw) if raw else default
    except (ValueError, TypeError):
        return default


def drift_signal(objective: str, manifest: list) -> dict:
    """Heuristic ONLY. Returns a signal, never a verdict.

    Honest failure modes, stated because a drift alarm nobody trusts is worse
    than no alarm: a rename touches everything and shares nothing; a refactor
    named for behaviour touches files named for structure. Both look like drift
    and are not. So this reports the overlap and lets the human look.
    """
    # A TRUNCATED manifest cannot be drift-checked, and this is not theoretical:
    # the first live run of this feature flagged "harden the valuation gate" as
    # off-objective because the manifest had been cut at 40 files and
    # helicon/valuation.py fell off the end. Against the complete 99-file
    # manifest the same objective goes quiet on the shared term 'valuation'.
    # Absence of evidence in a truncated list is not evidence of drift.
    if any(a.get("state") == "truncated" for a in manifest if isinstance(a, dict)):
        return {"checkable": False, "reason": "manifest was truncated — cannot rule on drift"}
    paths = [a.get("path", "") for a in manifest
             if isinstance(a, dict) and a.get("state") != "truncated"]
    if len(paths) < DRIFT_MIN_FILES:
        return {"checkable": False, "reason": "too few files to say anything"}
    want = _terms(objective)
    if not want:
        return {"checkable": False, "reason": "no objective to compare against"}
    touched = set()
    for p in paths:
        touched |= _terms(p.replace("/", " ").replace("_", " ").replace("-", " "))
    shared = want & touched
    return {
        "checkable": True,
        "shared": sorted(shared),
        "files": len(paths),
        # "Worth a look", not "drifted". The distinction is the whole design.
        "worth_a_look": not shared,
    }


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(days=days_ago)).isoformat()


def running(conn) -> list:
    """Runs that are open right now — the live fleet."""
    rows = conn.execute(
        "SELECT id, objective, task_class, repo_ref, opened_at, status, "
        "artifact_manifest FROM task_runs "
        "WHERE status IN ('opened','executing','artifact_attached') "
        "ORDER BY opened_at ASC").fetchall()
    out = []
    for r in rows:
        observed = r["task_class"] == "auto-observed"
        manifest = _loads(r["artifact_manifest"], [])
        # An observed run never had an objective, so it can never have drifted
        # from one. Computing a signal here would fabricate a contract.
        drift = ({"checkable": False, "reason": "observed run — no objective was frozen"}
                 if observed else drift_signal(r["objective"], manifest))
        out.append({
            "id": r["id"], "objective": r["objective"], "observed": observed,
            "repo": os.path.basename((r["repo_ref"] or "").partition("@")[0]),
            "status": r["status"], "opened_at": r["opened_at"],
            "files": len(manifest), "drift": drift,
        })
    return out


def spend_by_project(conn, days: int = 7) -> list:
    """Where the tokens went. Real observations only — a run whose cost was never
    captured is counted separately as 'unmeasured' rather than silently as 0,
    because a fleet that looks cheap because it was unmeasured is the worst
    possible answer to 'how is my token spending going'."""
    rows = conn.execute(
        "SELECT repo_ref, cost_observation FROM task_runs WHERE opened_at >= ?",
        (_iso(days),)).fetchall()
    agg = {}
    for r in rows:
        repo = os.path.basename((r["repo_ref"] or "").partition("@")[0]) or "unknown"
        cost = _loads(r["cost_observation"], {})
        e = agg.setdefault(repo, {"repo": repo, "tokens": 0, "runs": 0, "unmeasured": 0})
        e["runs"] += 1
        if cost.get("status") == "known" and cost.get("total_tokens"):
            e["tokens"] += int(cost["total_tokens"])
        else:
            e["unmeasured"] += 1
    return sorted(agg.values(), key=lambda e: -e["tokens"])


def efficiency(conn) -> dict:
    """Do accepted runs cost less than rejected ones?

    An open question with no published answer — the research pass found nothing
    measured on prompt efficiency beyond outcome. This is the cheapest honest
    version: mean observed tokens per outcome. It reports n every time, because
    at this sample size the number is a direction and not a finding.
    """
    out = {}
    for verdict in ("accepted", "rework", "rollback"):
        rows = conn.execute(
            "SELECT cost_observation FROM task_runs WHERE human_acceptance=?",
            (verdict,)).fetchall()
        tokens = [int(_loads(r["cost_observation"], {}).get("total_tokens") or 0)
                  for r in rows]
        measured = [t for t in tokens if t > 0]
        out[verdict] = {
            "runs": len(rows), "measured": len(measured),
            "mean_tokens": int(sum(measured) / len(measured)) if measured else None,
        }
    return out


# -------------------------------------------------------- per-project, derived
#
# The screen was per-RUN and it showed 36 auto-observed imports stuck at
# artifact_attached under a heading that said RUNNING. Nothing on it was a
# terminal and nothing on it was a project. The unit a person thinks in is the
# PROJECT, so that is the unit here.
#
# Every field below is DERIVED from a source named in its own docstring. Nothing
# is hand-typed, because a hand-typed "next step" is stale in a week and then you
# have rebuilt the dashboard problem one layer down. Where no source exists the
# field says `unmeasured` and names what would fill it — never a plausible guess.

def _git(repo: str, *args) -> str:
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def git_state(repo: str) -> dict:
    """Where a project STANDS, straight from git. Source: the repo itself."""
    if not os.path.isdir(os.path.join(repo, ".git")):
        return {}
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    dirty = [l for l in _git(repo, "status", "--porcelain").splitlines() if l.strip()]
    return {
        "branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "head": _git(repo, "rev-parse", "--short", "HEAD"),
        "subject": _git(repo, "log", "-1", "--format=%s"),
        "last_commit_rel": _git(repo, "log", "-1", "--format=%cr"),
        "commits_24h": len([l for l in _git(
            repo, "log", f"--since={since}", "--format=%h").splitlines() if l]),
        "dirty": len(dirty),
        "unpushed": len([l for l in _git(
            repo, "log", "--branches", "--not", "--remotes", "--format=%h").splitlines() if l]),
    }


def _sessions() -> list[dict]:
    """Every local transcript with its cwd and last-activity time.

    The transcript's own `.cwd` is authoritative; the directory name is a mangled
    path and lies about repos with dashes in them.
    """
    out = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for path in glob.glob(os.path.join(PROJECTS_DIR, "*", "*.jsonl")):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path),
                                           timezone.utc).replace(tzinfo=None)
        except OSError:
            continue
        age_h = (now - mtime).total_seconds() / 3600
        if age_h > STALE_AFTER_H:
            continue
        cwd, human = "", False
        try:
            with open(path, errors="ignore") as fh:
                for line in fh:
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    if not cwd and entry.get("cwd"):
                        cwd = entry["cwd"]
                    # A TERMINAL is a session a person typed into. A headless
                    # run has `sdk`/`system` turns and never a `typed` one.
                    if (entry.get("type") == "user"
                            and entry.get("promptSource") in ("typed", "queued")):
                        human = True
                    if cwd and human:
                        break
        except OSError:
            continue
        out.append({"path": path, "cwd": cwd, "idle_min": age_h * 60,
                    "human": human, "session": os.path.basename(path)[:8],
                    "session_id": os.path.basename(path)[:-6]})
    return sorted(out, key=lambda s: -s["idle_min"])


def alive_session_ids() -> set:
    """Session ids with a process still running, read from the process table.

    A transcript's mtime cannot tell an idle terminal from a CLOSED one — the
    file stays exactly where it was either way. So the mtime says "silent since",
    and only this says "still open". A Claude Code session started or resumed by
    id carries that id in its argv, so the process table is the liveness record.

    Coverage is partial by construction: a session whose id never reaches argv is
    unprovable, not dead. It is reported separately and never counted, because
    the whole point of making this number speak unprompted is that nobody will
    re-check something that announces itself.
    """
    try:
        out = subprocess.run(["ps", "-eo", "args"], capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {sid for sid in _RECENT_IDS if sid and sid in out}


_RECENT_IDS: set = set()


def idle_terminals() -> dict:
    """The number this screen exists to produce.

    Eight terminals sat idle for two hours while prompts were hand-written for a
    human to paste, and nothing on this machine noticed or said so. Sixteen
    wasted terminal-hours is a measurement, and an unmeasured waste is one nobody
    argues with. Source: mtime of each live transcript — the last moment that
    session emitted anything.

    It is a FLOOR, not a total. A session thinking hard writes nothing for
    minutes and reads as idle; a closed terminal keeps its file. So this counts
    sessions that are recent enough to plausibly still be open and quiet enough
    to certainly not be working, and says which assumption it made.

    ONLY sessions a human typed into. The first version counted every transcript
    and reported 241 idle hours across 74 "terminals" — 68 of which were
    ephemeral `cvfit-judge-*` processes that had run to completion and exited. A
    finished job is not an idle terminal, and a proof number inflated fifteenfold
    is not a proof, it is the thing this repo exists to catch.
    """
    quiet = [s for s in _sessions()
             if s["idle_min"] >= IDLE_AFTER_MIN and s["human"]]

    # Liveness, second gate. The first gate (a human typed here) removed dead
    # judge processes; it did NOT remove terminals that were simply closed, whose
    # transcripts sit at the same mtime forever and look identical to a terminal
    # someone is ignoring. Counting a closed terminal as idle time is the same
    # inflation as counting a finished job, one step subtler.
    _RECENT_IDS.clear()
    _RECENT_IDS.update(s["session_id"] for s in quiet if s["session_id"])
    alive = alive_session_ids()

    sessions = [s for s in quiet if s["session_id"] in alive]
    unprovable = [s for s in quiet if s["session_id"] not in alive]
    total_h = sum(s["idle_min"] for s in sessions) / 60
    return {"sessions": sessions, "count": len(sessions),
            "terminal_hours": round(total_h, 1),
            "unprovable": len(unprovable),
            "basis": f"a human typed there, the process is still running, and it has "
                     f"been silent {IDLE_AFTER_MIN}m+"}


# A metric nobody looks at is the same failure as a capability nobody remembers,
# which is the problem this screen was built for. So the number does not wait to
# be asked: the doorway hook speaks it into the arriving session, once.
#
# Two thresholds, both deliberately high. This fires on somebody's real prompt,
# uninvited, and a notice that arrives when it does not matter is a notice that
# gets muted — after which it may as well not exist.
IDLE_NOTICE_MIN_SESSIONS = 2
IDLE_NOTICE_MIN_HOURS = 1.0


def idle_notice(exclude_session: str = "") -> str:
    """One sentence for an arriving agent, or "" when there is nothing to say.

    Excludes the session being spoken to: the terminal receiving this message is,
    by definition, the one that is not idle.

    A wrong number is worse than a silent one here, because nobody re-checks
    something that announces itself. So this rides on the same two gates the
    screen uses — a human typed there, AND the process is still running — and it
    stays quiet rather than guess.
    """
    idle = idle_terminals()
    sessions = [s for s in idle["sessions"] if not exclude_session
                or not s["session_id"].startswith(exclude_session)]
    if len(sessions) < IDLE_NOTICE_MIN_SESSIONS:
        return ""
    hours = sum(s["idle_min"] for s in sessions) / 60
    if hours < IDLE_NOTICE_MIN_HOURS:
        return ""
    where = ", ".join(sorted({os.path.basename(s["cwd"] or "") or "?"
                              for s in sessions})[:4])
    return (
        f"{len(sessions)} other terminal(s) on this machine are open, were typed "
        f"in by a human, and have been silent for {hours:.1f} terminal-hours "
        f"between them ({where}). You can reach them directly — ListAgents, then "
        f"SendMessage — without asking anyone to carry a prompt between windows."
    )


def capabilities(conn) -> list[str]:
    """What an ARRIVING agent can do here that it probably does not know it can.

    Oscar's ruling, after eight terminals idled for two hours: stop calling
    ListAgents a native function, because no instance remembers it, and a
    capability nobody recalls is not a capability. So the screen states them.
    This is the one section that is not about state — an agent should leave this
    screen holding an ability it walked in without.
    """
    lines = [
        "ListAgents + SendMessage reach every peer session on this machine "
        "directly — you do not need a human to carry a prompt between terminals.",
        "`helicon brief complaints` is the only eval here the machine cannot fake; "
        "read it before deciding what to do next.",
        "`helicon run open` is the ONLY door into the Work Graph. Work closed "
        "any other way leaves no card.",
    ]
    pending = conn.execute(
        "SELECT COUNT(*) FROM work_wagers WHERE status='open'").fetchone()[0]
    if pending:
        lines.append(f"{pending} Work Card(s) are open and waiting on an outcome "
                     f"ruling — `helicon workgraph` shows what each one needs.")
    return lines


def projects(conn, roots=("~/CODE",)) -> list[dict]:
    """One row per project someone actually worked in, all of it derived.

    The project list itself is derived too: the cwds of live transcripts, which
    is where work is really happening, rather than a directory listing of every
    repo that has ever existed.
    """
    from helicon import complaints as _complaints

    seen: dict[str, dict] = {}

    def _add(repo):
        return seen.setdefault(repo, {"repo": repo, "name": os.path.basename(repo),
                                      "sessions": 0, "idle_min": 0.0})

    # A project is live if it has RECENT COMMITS, not only if a terminal is
    # sitting in it. Oscar runs terminals from $HOME and drives repos from there,
    # so keying on cwd alone showed "no project had a live session" on a day with
    # four commits in this very repo. Git is the honest record of where work
    # landed; the session count is an extra fact layered on when it is knowable.
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    for root in roots:
        base = os.path.expanduser(root)
        try:
            candidates = sorted(os.scandir(base), key=lambda e: -e.stat().st_mtime)
        except OSError:
            continue
        for item in candidates[:60]:
            if not item.is_dir() or not os.path.isdir(os.path.join(item.path, ".git")):
                continue
            if _git(item.path, "log", f"--since={since}", "--format=%h"):
                _add(item.path)

    for session in _sessions():
        cwd = session["cwd"]
        if not cwd or not session["human"]:
            continue
        repo = cwd
        while repo and repo != "/" and not os.path.isdir(os.path.join(repo, ".git")):
            repo = os.path.dirname(repo)
        if not repo or repo == "/":
            continue
        if not any(repo.startswith(os.path.expanduser(r)) for r in roots):
            continue
        entry = _add(repo)
        entry["sessions"] += 1
        entry["idle_min"] = max(entry["idle_min"], session["idle_min"])

    for entry in seen.values():
        entry["git"] = git_state(entry["repo"])
        # NEEDS YOU — runs that finished and never got a verdict. Source: task_runs.
        entry["unreviewed"] = conn.execute(
            "SELECT COUNT(*) FROM task_runs WHERE human_acceptance IS NULL "
            "AND status IN ('artifact_attached','verified') AND repo_ref LIKE ?",
            (f"{entry['repo']}@%",)).fetchone()[0]
        # FRICTION — what he pushed back on here. Source: the complaint log.
        entry["complaints"] = _complaints.by_project(conn, entry["name"])
        # NEXT PROMPT — only ever a prompt he ACCEPTED, and only when it actually
        # matches THIS project. Source: prompt_library, via capture.suggest_prompt.
        #
        # The first version took the newest accepted prompt globally and printed
        # it under every project, so all four rows recommended "wire the doorway
        # gate into a live Claude Code session" regardless of what the project
        # was. That is the hand-typed field wearing a derived field's clothes:
        # confidently relevant, actually unrelated. suggest_prompt scores term
        # overlap and returns nothing rather than a weak match, which is the
        # right answer here almost every time — the library has one row.
        from helicon.capture import suggest_prompt
        topic = f"{entry['name']} {(entry['git'] or {}).get('subject', '')}"
        matches = suggest_prompt(conn, topic)
        entry["next_prompt"] = matches[0] if matches else None
        entry["steps"] = next_steps(entry)
    return sorted(seen.values(), key=lambda e: (-e["sessions"], e["name"]))


# The asked-for fields: "next steps, possible needed research, next prompts,
# feature, steps". Every one of them is a CONDITION READ OFF THE REPO, never a
# sentence someone wrote into a field. That is the whole constraint — a typed
# "next step" is stale within a week, and then the vault dashboard problem has
# been rebuilt inside the tool that replaces it.
#
# So each rule below is (condition observed in derived state) -> (the action that
# condition implies). It cannot invent a step, and when no condition fires it
# says so rather than filling the line with something plausible. The cost is that
# it will never suggest the clever thing; the benefit is that it is never stale
# and never wrong about the repo, which is what makes it worth reading at all.
_STEP_RULES = (
    (lambda p, g: g.get("dirty", 0) > 20,
     lambda p, g: f"{g['dirty']} uncommitted files — commit or stash before this "
                  f"branch becomes unreviewable"),
    (lambda p, g: g.get("unpushed", 0) > 0,
     lambda p, g: f"{g['unpushed']} commit(s) never pushed — nobody else can see this work"),
    (lambda p, g: (g.get("branch") or "main") not in ("main", "master"),
     lambda p, g: f"work is on {g['branch']}, not the default branch — open a PR or merge, "
                  f"or it ships to nobody"),
    (lambda p, g: p["unreviewed"] > 0,
     lambda p, g: f"{p['unreviewed']} run(s) finished with no verdict — "
                  f"`helicon unreviewed` then rule them"),
    (lambda p, g: bool(p["complaints"]),
     lambda p, g: f"you pushed back {sum(n for _, n in p['complaints'])}× here — "
                  f"`helicon brief complaints --label {p['complaints'][0][0]}` before deciding"),
    (lambda p, g: g.get("commits_24h", 0) == 0 and p["sessions"] > 0,
     lambda p, g: "a terminal is open here and nothing has landed in 24h — "
                  "the session is stuck or the work is unscoped"),
)


def next_steps(entry: dict) -> list[str]:
    """Derived steps for one project. Empty is a legal, honest answer."""
    git = entry.get("git") or {}
    return [render(entry, git) for cond, render in _STEP_RULES if cond(entry, git)]


# ------------------------------------------------------------------ rendering

def _fmt_tokens(n) -> str:
    if not n:
        return "—"
    for unit, div in (("M", 1_000_000), ("K", 1_000)):
        if n >= div:
            return f"{n / div:.1f}{unit}"
    return str(n)


def _idle_str(minutes: float) -> str:
    return f"{minutes/60:.1f}h" if minutes >= 60 else f"{int(minutes)}m"


def format_projects(rows: list, idle: dict, caps: list,
                    spend: list, unrev: list, eff: dict) -> str:
    """The screen, project-first.

    Order is deliberate and is the order a person actually needs: what is WASTED
    right now, then per project where it stands / what blocks it / what needs
    him, then what an arriving agent can do. Spend and efficiency follow, because
    nobody has ever opened this screen to read a token count first.
    """
    L = []

    # First, because it is the only line that costs money while you read it.
    L.append("IDLE")
    if not idle["count"]:
        L.append("  no idle terminals.")
    else:
        L.append(f"  {idle['terminal_hours']}h of terminal time idle across "
                 f"{idle['count']} session(s) — a FLOOR, not a total")
        L.append(f"  basis: {idle['basis']}")
        if idle.get("unprovable"):
            L.append(f"  ({idle['unprovable']} more went quiet but their process could not "
                     f"be found — not counted, they may simply be closed)")
        for s in idle["sessions"][:6]:
            where = os.path.basename(s["cwd"] or "") or "?"
            L.append(f"    {_idle_str(s['idle_min']):>6} silent   {where:<26} {s['session']}")
        if idle["count"] > 6:
            L.append(f"    … and {idle['count'] - 6} more")
        L.append("  they are addressable: ListAgents, then SendMessage.")
    L.append("")

    L.append("PROJECTS — every field derived, none typed")
    if not rows:
        L.append("  no project had a live session in the window.")
    for p in rows:
        g = p.get("git") or {}
        flags = []
        if g.get("dirty"):
            flags.append(f"{g['dirty']} uncommitted")
        if g.get("unpushed"):
            flags.append(f"{g['unpushed']} unpushed")
        state = "  ".join(flags) if flags else "clean"
        L.append("")
        L.append(f"  {p['name']}")
        L.append(f"    stands     {g.get('branch','?')} @{g.get('head','?')}  {state}"
                 f"   ·  {g.get('commits_24h', 0)} commit(s) in 24h, "
                 f"last {g.get('last_commit_rel') or '—'}")
        if g.get("subject"):
            L.append(f"               \"{g['subject'][:74]}\"")
        needs = []
        if p["unreviewed"]:
            needs.append(f"{p['unreviewed']} run(s) finished with no verdict")
        if p["sessions"]:
            needs.append(f"{p['sessions']} session(s), quietest {_idle_str(p['idle_min'])}")
        L.append(f"    needs you  {' · '.join(needs) if needs else 'nothing'}")
        if p["complaints"]:
            friction = ", ".join(f"{n}× {k}" for k, n in p["complaints"])
            L.append(f"    friction   {friction}   (helicon brief complaints --label ...)")
        for i, step in enumerate(p.get("steps") or []):
            L.append(f"    {'steps' if i == 0 else '':<10} {'·' if i else '1.'} {step}"
                     if i == 0 else f"               · {step}")
        if not p.get("steps"):
            L.append("    steps      nothing the repo state implies — "
                     "clean, pushed, on default, nothing unreviewed")
        if p["next_prompt"]:
            L.append(f"    next       reuse the prompt accepted for "
                     f"\"{p['next_prompt']['objective'][:52]}\"")
        else:
            # Named, not guessed. The library has one row; pretending otherwise
            # would be the hand-typed field this screen exists to avoid.
            L.append("    next       unmeasured — no accepted prompt yet "
                     "(`helicon run close --accept` promotes one)")
    L.append("")

    L.append("YOU CAN")
    for line in caps:
        L.append(f"  · {line}")
    L.append("")

    L.append(f"SPEND — last 7 days")
    if not spend:
        L.append("  no runs in the window.")
    for s in spend:
        note = f"   ({s['unmeasured']} unmeasured)" if s["unmeasured"] else ""
        L.append(f"  {s['repo']:<24} {_fmt_tokens(s['tokens']):>8}   "
                 f"{s['runs']} run(s){note}")
    L.append("")

    L.append("NEEDS YOU")
    if not unrev:
        L.append("  nothing ran unreviewed.")
    else:
        L.append(f"  {len(unrev)} run(s) finished without your verdict — oldest first")
        for r in unrev[:5]:
            L.append(f"  {r['id']}  {r['repo']:<20} {r['files']:>3} file(s)  "
                     f"{_fmt_tokens(r.get('tokens'))}")
        if len(unrev) > 5:
            L.append(f"  … and {len(unrev) - 5} more")
    L.append("")

    L.append("EFFICIENCY — tokens per outcome")
    any_measured = any(v["measured"] for v in eff.values())
    if not any_measured:
        L.append("  not measurable yet: no closed run has an observed cost.")
        L.append("  wire the Stop hook and this fills in on its own.")
    else:
        for verdict in ("accepted", "rework", "rollback"):
            v = eff[verdict]
            mean = _fmt_tokens(v["mean_tokens"]) if v["mean_tokens"] else "—"
            L.append(f"  {verdict:<10} {mean:>8}   "
                     f"(n={v['measured']} measured of {v['runs']})")
        L.append("  small n — read this as a direction, not a finding.")
    return "\n".join(L)
