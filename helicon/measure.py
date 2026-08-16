"""The measurement store — the weekly review, recorded so it becomes a series.

Every surface in the weekly review answers "is my setup any good" *today*. None of
them can answer "is it getting better", because none of them is written down. That
is the whole difference between a reading and a measurement: a reading is a number
someone looked at once, and a measurement is a number with a previous value.

So this module does one thing: take today's reading of every weekly-review
detector, store it as a dated row, and hand back the series.

Three rules, each one learned the hard way in the detectors this records:

  A METRIC CARRIES THE COMMAND THAT REPRODUCES IT. Not "the command that produced
  it" — these are derived from a scan that finished hours ago and no command
  produces them now. What a reader needs is the line they can type to see the
  same number themselves. It is stored WITH the number, in the same row, because
  a number and its provenance kept in different places drift apart.

  AN UNMEASURED METRIC IS NOT A ZERO. A detector that could not run because its
  source is not configured stores NULL and says why. Storing 0 would draw a
  falling line on the chart and read as improvement.

  A FIRST READING IS NOT A TREND. `delta` is None until there is a previous row
  for that metric. The surface must render that as "first reading", never as 0.
"""
import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS weekly_measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    week        TEXT NOT NULL,
    metric      TEXT NOT NULL,
    value       INTEGER,
    population  INTEGER,
    unit        TEXT DEFAULT '',
    command     TEXT NOT NULL,
    unmeasured  TEXT DEFAULT '',
    detail      TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_weekly_metric ON weekly_measurements(metric, week);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _week(now: datetime) -> str:
    """ISO year-week. The unit is the WEEK because the cadence ruling says so:
    a daily surface answers what is next, this one answers whether the setup is
    any good, and running it daily would turn it back into a queue."""
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


class Metric:
    """One measured thing. `value=None` means the detector could not run — that
    is stored as unmeasured, never as zero."""

    def __init__(self, key: str, value, command: str, population=None,
                 unit: str = "", unmeasured: str = "", detail: dict = None):
        self.key, self.value, self.command = key, value, command
        self.population, self.unit = population, unit
        self.unmeasured, self.detail = unmeasured, detail or {}


# THE TARGET. Oscar's own doctrine, encoded so the stack can be graded against
# it instead of merely counted. Every KPI below cites the rule it enforces, and
# that citation is the opinionated part: "21 repos touched one day only" is
# trivia, and "Anti-pattern 7, spray without deadlines, is firing at 21 of 40"
# is a verdict against a rule he already wrote.
#
# Versioned on purpose. A model upgrade changes what a good stack looks like —
# what belongs in standing context, how much routing is worth doing, which layer
# earns its keep — so the target carries a date and a provenance, and bumping it
# re-grades everything underneath.
STACK_TARGET = {
    "version": "1.0",
    "date": "2026-08-16",
    "derived_from": "Obsidian 02 Content/agentic-engineering-stack-and-taste.md",
    # Where the doc names a specific host or repo, the probe reads the LIVE
    # thing. A doctrine document is a claim with an author, like any other.
    "layers": {
        "L0": "Source of truth: if it survived two conversations, it is in the vault",
        "L3": "Bridge: bagelHQ is the controlled handoff, and a bridge nobody writes to is closed",
        "L4": "Every tool is a source; only the vault is a destination — nothing stays trapped",
        "L5": "Content flows out; the strategy lives in the OS but the posts live on platforms",
    },
    "taste": {
        "T2": "Proof over narrative",
        "T7": "Structure over repeated prompting",
    },
    "anti_patterns": {
        "AP7": "Do not spray without deadlines: many projects, few completions",
    },
    # Doctrine that is real and NOT graded here, listed so its absence is a
    # stated choice rather than a silent gap. Same discipline as the ledger's
    # PROSE tier: forcing judgement into a number rebuilds the pile.
    "judgment_not_graded": [
        "AP1 do not mock data — a CI and review matter, not a weekly count",
        "AP2 do not pad timelines · AP3 do not build wrappers · AP4 do not inflate difficulty",
        "AP5 do not bulk rewrite — visible in review, not in a metric",
        "T1 bounded authority · T3 interoperability · T4 one non-obvious insight",
        "T5 upside-first review · T6 anti-convergence · T8 personal data stays personal",
        "Quality Score and Cost Per Useful Output — need a RECEIPT; every number "
        "available today is self-reported, so they are not shipped",
    ],
}


def collect(conn: sqlite3.Connection, catches_path: str = "", runs_dir: str = "",
            code_root: str = "", repo: str = "", vault: str = "",
            bridge: str = "") -> list:
    """Today's reading, graded against STACK_TARGET.

    Seven KPIs, each naming the doctrine rule it enforces. Anything the doctrine
    asserts that cannot be probed is in `judgment_not_graded` rather than forced
    into a number."""
    from helicon.overboard import git_churn, repos_under

    out = []

    # T2 · proof over narrative — a forked definition is the stack disagreeing
    # with itself, and each one is rulable in the queue today.
    forks = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE audit_type = 'identity' "
        "AND human_decision IS NULL AND machine_decision IS NULL").fetchone()[0]
    out.append(Metric("identity_forks", forks, "helicon resolve --list --cards",
                      unit="forks", detail={"rule": "T2"}))

    repos = repos_under(code_root) if code_root else []

    # AP7 · do not spray without deadlines. A repo touched on exactly one day in
    # the window is a project opened and left, which is the anti-pattern's own
    # definition made measurable.
    if repos:
        g = git_churn(repos)
        out.append(Metric("spray_repos", len(g["one_day_repos"]),
                          "helicon overboard --code-root <root>",
                          population=len(g["touched"]), unit="repos",
                          detail={"rule": "AP7"}))
        # L4 · nothing stays trapped. A commit that exists only on this machine
        # is work no one else can reach. Push it or bin it.
        ahead, no_upstream = _unpushed(repos)
        out.append(Metric("unpushed_commits", ahead,
                          "git log @{u}..HEAD --oneline | wc -l  (per repo)",
                          population=len(repos), unit="commits",
                          detail={"rule": "L4", "no_upstream": no_upstream}))
    else:
        for key, rule in (("spray_repos", "AP7"), ("unpushed_commits", "L4")):
            out.append(Metric(key, None, "helicon measure --code-root <root>",
                              unmeasured="no code root configured",
                              detail={"rule": rule}))

    # L3 · the bridge. A handoff layer nobody has written to is a closed one,
    # and the doc's claim that it is the firewall says nothing about whether it
    # is running — so this reads the repo, never the document.
    days = _days_since_commit(bridge) if bridge else None
    out.append(Metric("bridge_idle_days", days,
                      "git -C <bagelHQ> log -1 --format=%ad",
                      unit="days", detail={"rule": "L3"},
                      unmeasured="" if days is not None else
                      ("bridge repo not found" if bridge else "no bridge configured")))

    # L0 · if it survived two conversations it is in the vault. A vault nobody
    # has written to is a source of truth going stale.
    vdays = _days_since_write(vault) if vault else None
    out.append(Metric("vault_idle_days", vdays,
                      "find <vault> -name '*.md' -newermt -1day",
                      unit="days", detail={"rule": "L0"},
                      unmeasured="" if vdays is not None else "no vault configured"))

    # L5 · content flows out. THE SCOREBOARD: did anything reach a person who is
    # not Oscar. Read from the lane ledger's own outward flag, never inferred.
    if runs_dir:
        n, total = _outward(runs_dir)
        out.append(Metric("outward", n, "grep '\"outward\": true' <runs>/*-lanes.jsonl | wc -l",
                          population=total, unit="artifacts", detail={"rule": "L5"}))
    else:
        out.append(Metric("outward", None, "helicon measure --runs <dir>",
                          unmeasured="no lane ledger configured",
                          detail={"rule": "L5"}))

    # T7 · structure over repeated prompting. A learning with a gate behind it
    # is structure; a learning in prose is a repeated prompt waiting to happen.
    from helicon.ledger import learning_ledger
    if catches_path:
        ll = learning_ledger(catches_path)
        out.append(Metric("learnings_wired", ll["counts"].get("WIRED", 0),
                          "helicon ledger --catches <log> --live <config>",
                          population=ll["with_check"], unit="learnings",
                          detail={"rule": "T7"}))
    else:
        out.append(Metric("learnings_wired", None, "helicon ledger --catches <log>",
                          unmeasured="no catch log configured",
                          detail={"rule": "T7"}))
    return out


def _unpushed(repos: list) -> tuple:
    """Commits ahead of upstream, and how many repos have no upstream at all.

    A repo with no upstream is NOT counted as zero unpushed work — it is the
    worst case, not the clean one, so it is reported as its own number."""
    from helicon.overboard import _git
    ahead, no_upstream = 0, 0
    for r in repos:
        up = _git(r, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]).strip()
        if not up:
            no_upstream += 1
            continue
        n = _git(r, ["rev-list", "--count", "@{u}..HEAD"]).strip()
        ahead += int(n) if n.isdigit() else 0
    return ahead, no_upstream


def _days_since_commit(repo: str) -> int:
    import os as _os
    from helicon.overboard import _age_days, _git
    repo = _os.path.expanduser(repo or "")
    if not _os.path.isdir(_os.path.join(repo, ".git")):
        return None
    when = _git(repo, ["log", "-1", "--format=%ad", "--date=short"]).strip()
    return _age_days(when) if when else None


def _days_since_write(vault: str) -> int:
    """Age of the most recently modified markdown file in the vault."""
    import os as _os
    from datetime import date
    vault = _os.path.expanduser(vault or "")
    if not _os.path.isdir(vault):
        return None
    newest = 0.0
    for dirpath, dirnames, filenames in _os.walk(vault):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".md"):
                try:
                    newest = max(newest, _os.path.getmtime(_os.path.join(dirpath, fn)))
                except OSError:
                    continue
    if not newest:
        return None
    from datetime import datetime as _dt
    return (datetime.now(timezone.utc).replace(tzinfo=None)
            - _dt.utcfromtimestamp(newest)).days


def _outward(runs_dir: str) -> tuple:
    """Artifacts the lane ledger marked as having reached someone else."""
    import os as _os
    if not _os.path.isdir(runs_dir):
        return 0, 0
    out = total = 0
    for fn in sorted(_os.listdir(runs_dir)):
        if not fn.endswith("-lanes.jsonl"):
            continue
        for row in _read_jsonl_local(_os.path.join(runs_dir, fn)):
            total += 1
            if row.get("outward") is True or row.get("verdict") == "OUTWARD":
                out += 1
    return out, total


def _read_jsonl_local(path: str) -> list:
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []
    return rows


def record(conn: sqlite3.Connection, metrics: list, now: datetime = None) -> dict:
    """Write one dated row per metric. Re-running in the same week REPLACES that
    week's rows rather than appending: a week with four readings is not four
    weeks of data, and letting it look like that would fake the trend this table
    exists to hold."""
    ensure_schema(conn)
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    week, stamp = _week(now), now.isoformat(timespec="seconds")
    for m in metrics:
        conn.execute("DELETE FROM weekly_measurements WHERE week = ? AND metric = ?",
                     (week, m.key))
        conn.execute(
            "INSERT INTO weekly_measurements (recorded_at, week, metric, value, "
            "population, unit, command, unmeasured, detail) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (stamp, week, m.key, m.value, m.population, m.unit, m.command,
             m.unmeasured, json.dumps(m.detail)))
    conn.commit()
    return {"week": week, "recorded_at": stamp, "metrics": len(metrics)}


def series(conn: sqlite3.Connection, weeks: int = 12) -> dict:
    """Every metric with its history, newest week last.

    `delta` is None on a first reading and stays None across an unmeasured week —
    a gap is not a change, and drawing one as flat would claim a reading nobody
    took."""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT week, metric, value, population, unit, command, unmeasured, "
        "recorded_at FROM weekly_measurements ORDER BY week, metric").fetchall()
    by_metric: dict = {}
    for week, metric, value, pop, unit, command, unmeasured, read_at in rows:
        m = by_metric.setdefault(metric, {"metric": metric, "unit": unit,
                                          "command": command, "points": []})
        m["command"] = command
        m["points"].append({"week": week, "value": value, "population": pop,
                            "unmeasured": unmeasured, "read_at": read_at})
    out = []
    for m in by_metric.values():
        m["points"] = m["points"][-weeks:]
        measured = [p for p in m["points"] if p["value"] is not None]
        m["latest"] = measured[-1]["value"] if measured else None
        m["read_at"] = m["points"][-1]["read_at"] if m["points"] else ""
        m["unmeasured"] = m["points"][-1]["unmeasured"] if m["points"] else ""
        m["delta"] = (measured[-1]["value"] - measured[-2]["value"]
                      if len(measured) >= 2 else None)
        m["readings"] = len(measured)
        out.append(m)
    out.sort(key=lambda x: x["metric"])
    return {"metrics": out, "weeks": sorted({p["week"] for m in out
                                             for p in m["points"]})}


# How each metric reads: whether a rise is good, so the surface can color a
# delta without every call site re-deciding. `None` means neither direction is
# an improvement on its own and the number is context, not a score.
DIRECTION = {
    "identity_forks": "down", "spray_repos": "down", "unpushed_commits": "down",
    "bridge_idle_days": "down", "vault_idle_days": "down",
    "outward": "up", "learnings_wired": "up",
}

LABELS = {
    "outward": "Reached someone who is not you",
    "spray_repos": "Projects opened and left this week",
    "unpushed_commits": "Commits only on this machine",
    "bridge_idle_days": "Days since the bridge moved",
    "vault_idle_days": "Days since the vault was written to",
    "identity_forks": "Things the stack defines two ways",
    "learnings_wired": "Learnings with a gate behind them",
}

# The doctrine rule each KPI enforces. This is what turns a count into a verdict:
# "21 repos touched one day only" is trivia, "AP7 spray without deadlines is
# firing" is a finding against a rule Oscar already wrote.
RULES = {
    "outward": ("L5", "Content flows out — the posts live on platforms"),
    "spray_repos": ("AP7", "Do not spray without deadlines: many projects, few completions"),
    "unpushed_commits": ("L4", "Nothing stays trapped; only the destination counts"),
    "bridge_idle_days": ("L3", "A handoff layer nobody writes to is a closed one"),
    "vault_idle_days": ("L0", "If it survived two conversations, it is in the vault"),
    "identity_forks": ("T2", "Proof over narrative"),
    "learnings_wired": ("T7", "Structure over repeated prompting"),
}

# Metrics that were shipped and then retired. Kept by name so a stored series
# can be cleaned deliberately rather than rendering dead rows forever — and so
# the retirement is a recorded decision, not a silent disappearance.
RETIRED = {
    "open_findings": "duplicated identity_forks; no ruling followed from the total",
    "dead_branches": "repo hygiene, not a doctrine rule — no ruling changed behaviour",
    "abandoned_branches": "same",
    "one_day_repos": "renamed to spray_repos and re-cited to AP7",
    "scattered_homes": "hygiene; the ruling is a rename, not a change of practice",
    "rules_stated": "a count with no direction — true, and never actionable",
    "rules_gated": "folded into learnings_wired, which cites T7 directly",
}


def retire(conn: sqlite3.Connection) -> dict:
    """Delete stored rows for metrics that are no longer shipped.

    Called deliberately, never on read. A metric that stops being collected
    would otherwise sit in the series forever at its last value, which reads as
    a flat line rather than as a metric that was withdrawn."""
    ensure_schema(conn)
    removed = {}
    for key in RETIRED:
        n = conn.execute("DELETE FROM weekly_measurements WHERE metric = ?",
                         (key,)).rowcount
        if n:
            removed[key] = n
    conn.commit()
    return removed


def render_series(data: dict, read_at: str = "") -> str:
    metrics = data.get("metrics", [])
    if not metrics:
        return ("MEASUREMENT — nothing recorded yet.\n"
                "  helicon measure --record   starts the series.\n"
                "  A first reading is not a trend; the second one is where this "
                "becomes useful.")
    out = ["MEASUREMENT — the weekly review, as a series", ""]
    weeks = data.get("weeks", [])
    out.append(f"  {len(weeks)} week(s) recorded: {', '.join(weeks)}")
    out.append("")
    for m in metrics:
        label = LABELS.get(m["metric"], m["metric"])
        rule = RULES.get(m["metric"])
        if m["latest"] is None:
            out.append(f"  {label:<38}  unmeasured — {m['unmeasured']}")
            if rule:
                out.append(f"  {'':<38}  {rule[0]} · {rule[1]}")
            out.append(f"  {'':<38}  {m['command']}")
            continue
        if m["delta"] is None:
            trend = "first reading"
        else:
            direction = DIRECTION.get(m["metric"])
            sign = "+" if m["delta"] > 0 else ""
            good = (direction == "down" and m["delta"] < 0) or \
                   (direction == "up" and m["delta"] > 0)
            mark = "" if m["delta"] == 0 else ("  better" if good else "  worse")
            trend = f"{sign}{m['delta']} vs last{mark}"
        out.append(f"  {label:<38}  {m['latest']:>6}   {trend}")
        if rule:
            out.append(f"  {'':<38}  {rule[0]} · {rule[1]}")
        out.append(f"  {'':<38}  {m['command']}")
    out += ["", f"  target v{STACK_TARGET['version']} ({STACK_TARGET['date']}) "
            f"from {STACK_TARGET['derived_from']}",
            f"  not graded, by choice: {len(STACK_TARGET['judgment_not_graded'])} "
            f"doctrine rules that need judgement, not a number",
            "", f"read {read_at}  ·  helicon measure"]
    return "\n".join(out)
