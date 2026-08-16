"""A — the overboard detector: defects that exist only in aggregate.

Every other class in the rot catalogue judges one thing against another thing:
this memory against that memory, this doc against the running system. R1 through
R15 can all fire on a single pair. This one cannot, and that is the point.

The measured shape, from one real day: a fleet moved every terminal to a new
object three times, ran one lane under two names on the same day, and kept four
copies of one document in four repos. **Not one of those was wrong when it
happened.** Every reassignment was locally defensible, every rename had a reason,
every copy was made deliberately. A daily surface sees a defensible decision and
passes it. Only a window wide enough to hold the whole week sees the churn.

So each detector here is the same shape: a count that is unremarkable at n=1 and
a defect at n=N inside the window. The finding is never "this was wrong", it is
"this happened N times and nobody was holding the count".

Three detectors, and each one names its population. The fourth candidate — lane
message volume — is not here on purpose: the only number available for it is
self-reported, and shipping a self-reported number is the defect this product
exists to catch.
"""
import collections
import hashlib
import json
import os
from datetime import datetime, timezone

# Basenames that live in every repo by convention. A README in sixty repos is
# how repos work, not a defect, and grading it would rebuild the 449-finding pile
# the gate exists to prevent.
CONVENTIONAL = {
    "readme.md", "claude.md", "agents.md", "license.md", "changelog.md",
    "contributing.md", "task.md", "tasks.md", "skill.md", "index.md",
    "notes.md", "todo.md", "roadmap.md", "architecture.md", "product.md",
    "vision.md", "setup.md", "install.md", "usage.md", "api.md", "config.md",
    "plan.md", "summary.md", "report.md", "results.md", "prompt.md",
}
SKIP_DIRS = {"node_modules", "dist", "build", "__pycache__", ".venv", "venv",
             "site-packages", ".next", "target", "vendor", "coverage"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="minutes")


# --- D1: self-catch blindness ---------------------------------------------

def self_catch_blindness(catches_path: str) -> dict:
    """Who authored the errors, and who caught their own.

    The catch log records a self-catch by writing `author: "self"` — the author
    field says the catcher caught itself, and `caught_by` says which one. So a
    self-catch is read from the log's own convention, NOT by matching the author
    string against the catcher string. That matters: the fleet uses several names
    for the same seat (`T1`, `GM`, `T1-coordinator`), and a substring match across
    those names would invent self-catches that the log never recorded. Where the
    seat identity is genuinely ambiguous this reports the ambiguity instead of
    resolving it.

    The ruling it forces: an author with a self-catch rate of zero is not
    reviewing itself, whatever its process document says. Its work needs an
    independent checker, because its own review is not a control."""
    rows = _read_jsonl(catches_path)
    if not rows:
        return {"population": 0, "path": catches_path, "authors": [],
                "unattributed": 0, "self_caught": 0, "ambiguous_seats": []}

    authored = collections.Counter()
    self_caught_by = collections.Counter()
    for r in rows:
        author = (r.get("author") or "").strip() or "unknown"
        if author == "self":
            # The log's own convention: the catcher caught its own error.
            self_caught_by[(r.get("caught_by") or "unknown").strip()] += 1
        else:
            authored[author] += 1

    # A seat that appears as a catcher and never as an author, next to an author
    # that never catches, is where an alias would hide. Report the pair; do not
    # merge them on a guess.
    catchers = {(r.get("caught_by") or "").strip() for r in rows}
    ambiguous = sorted(c for c in catchers if c and c not in authored
                       and any(c.lower() in a.lower() or a.lower() in c.lower()
                               for a in authored if a not in ("unknown", "self")))

    out = []
    for author, n in authored.most_common():
        if author == "unknown":
            continue
        own = self_caught_by.get(author, 0)
        out.append({"author": author, "authored": n, "self_caught": own,
                    "rate": round(own / (n + own), 3) if (n + own) else 0.0})
    return {"population": len(rows), "path": catches_path, "authors": out,
            "unattributed": authored.get("unknown", 0),
            "self_caught": sum(self_caught_by.values()),
            "self_caught_by": dict(self_caught_by),
            "ambiguous_seats": ambiguous}


# --- D2: lane identity churn ----------------------------------------------

def lane_churn(runs_dir: str) -> dict:
    """One seat under several names, and one seat over several objects.

    Reads every `*-lanes.jsonl` in the runs directory as a time series. Two
    aggregate defects fall out that no single row shows:

    - NAME DRIFT: one seat runs under two or more lane names (`zup` and `T3-zup`
      on the same day; `design-daily` becoming `design`). Every rename was fine.
      In aggregate the lane has no stable address, so work filed under one name
      is invisible to anyone looking under the other.
    - OBJECT DRIFT: one seat's object changes across the window (`T4-mountain-of-
      helicon` becoming `T4-weirder-md`). Each move was a decision someone made
      for a reason. Across the window it means no seat kept an object long enough
      to finish one.

    The ruling it forces: freeze the seat-to-object binding for the coming week,
    or accept that the object moved and say which one is current."""
    files = sorted(f for f in os.listdir(runs_dir)
                   if f.endswith("-lanes.jsonl")) if os.path.isdir(runs_dir) else []
    days, rows = [], []
    for fn in files:
        for r in _read_jsonl(os.path.join(runs_dir, fn)):
            r["_day"] = fn[:10]
            rows.append(r)
        days.append(fn[:10])
    if not rows:
        return {"population": 0, "days": [], "name_drift": [], "object_drift": []}

    # A seat is the terminal prefix when the lane name carries one (T4-foo -> T4),
    # otherwise the lane name itself. Naming a seat by its prefix is what makes
    # "T4 moved object" visible; grouping on the full lane name hides it, because
    # the name moved WITH the object.
    by_seat: dict = collections.defaultdict(lambda: {"names": set(), "objects": {}})
    for r in rows:
        lane = (r.get("lane") or "").strip()
        if not lane:
            continue
        seat = lane.split("-", 1)[0] if _is_terminal_prefix(lane) else lane
        by_seat[seat]["names"].add(lane)
        obj = _object_of(r)
        if obj:
            by_seat[seat]["objects"].setdefault(obj, set()).add(r["_day"])

    name_drift, object_drift = [], []
    for seat, d in sorted(by_seat.items()):
        if len(d["names"]) > 1:
            name_drift.append({"seat": seat, "names": sorted(d["names"]),
                               "count": len(d["names"])})
        if len(d["objects"]) > 1:
            object_drift.append({
                "seat": seat, "count": len(d["objects"]),
                "objects": [{"object": o, "days": sorted(ds)}
                            for o, ds in sorted(d["objects"].items())]})
    return {"population": len(rows), "days": sorted(set(days)),
            "files": files, "name_drift": name_drift, "object_drift": object_drift}


def _is_terminal_prefix(lane: str) -> bool:
    head = lane.split("-", 1)[0]
    return len(head) <= 3 and head[:1].upper() == "T" and head[1:].isdigit()


def _object_of(row: dict) -> str:
    """The thing a lane was pointed at: the repo for a path, the host+path for a
    URL, else the ship line. A commit sha is not an object — it is a moment in
    one — so a sha-shaped artifact falls back to the ship."""
    art = (row.get("artifact") or "").strip()
    if art.startswith("http"):
        return art.split("://", 1)[-1].split("?", 1)[0].rstrip("/")
    if "/" in art:
        parts = [p for p in art.split("/") if p]
        for i, p in enumerate(parts):
            if p == "CODE" and i + 1 < len(parts):
                return f"~/CODE/{parts[i + 1]}"
        return "/".join(parts[:3])
    return (row.get("ship") or art or "").strip()[:70]


# --- D3: drifted duplicates -----------------------------------------------

def _lines(path: str) -> set:
    """The comparable body of a document: non-empty, whitespace-normalized lines.
    Blank lines and indentation carry no claim, so two copies that differ only in
    formatting are the same document."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return {" ".join(ln.split()) for ln in f if ln.strip()}
    except OSError:
        return set()


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def artifact_scatter(code_root: str, min_locations: int = 3, max_depth: int = 4,
                     similarity: float = 0.5) -> dict:
    """One document, several homes, and the copies no longer agree.

    A shared basename is NOT the signal, and the first version of this detector
    proved it by reporting `SUBMISSION.md` in seven hackathon repos as scatter.
    Seven projects each writing their own submission doc is how projects work.
    That finding was true and worthless — precisely the 449-finding pile the
    weekly review's gate exists to prevent, rebuilt inside the detector meant to
    replace it.

    A stoplist of conventional names does not fix it either; it only lags the
    next name. What separates the two cases is CONTENT: per-project docs that
    share a name share almost no text, while real scatter is one document copied
    and then edited in place, so the copies still share most of their lines.

    So the signal is: >= min_locations copies of one basename that OVERLAP above
    `similarity` on their normalized lines and are not byte-identical. Identical
    copies are duplication; drifted copies are the defect, because an agent that
    opens one reads a different truth from an agent that opens another and
    neither knows the other exists.

    Basename grouping is the candidate generator, so a copy that was also renamed
    is out of scope and this says so rather than implying full coverage.

    The ruling it forces: name the canonical copy and retire the rest, or accept
    the fork and give the copies different names."""
    if not os.path.isdir(code_root):
        return {"population": 0, "root": code_root, "scattered": []}
    by_name: dict = collections.defaultdict(list)
    scanned = 0
    base_depth = code_root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(code_root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        # A directory carrying its own .git inside another repo is a vendored
        # dependency or a submodule, not the user's stack. Without this, two
        # copies of OpenZeppelin's CODE_OF_CONDUCT.md read as scatter the user
        # could act on; they are someone else's file and there is no ruling to
        # make. Depth-first, so pruning here prunes the whole tree.
        if dirpath != code_root:
            dirnames[:] = [d for d in dirnames
                           if not os.path.exists(os.path.join(dirpath, d, ".git"))]
        if dirpath.count(os.sep) - base_depth >= max_depth:
            dirnames[:] = []
        for fn in filenames:
            if not fn.endswith(".md") or fn.lower() in CONVENTIONAL:
                continue
            path = os.path.join(dirpath, fn)
            try:
                digest = hashlib.sha256(open(path, "rb").read()).hexdigest()[:12]
            except OSError:
                continue
            scanned += 1
            by_name[fn.lower()].append((path, digest))

    scattered = []
    for name, copies in by_name.items():
        if len(copies) < min_locations:
            continue
        bodies = {p: _lines(p) for p, _ in copies}
        # Cluster by content: a copy joins the cluster only if it overlaps an
        # existing member above the threshold. Two unrelated docs sharing a name
        # form two clusters of one and neither is reported.
        clusters: list = []
        for path, digest in sorted(copies):
            for cluster in clusters:
                if any(_overlap(bodies[path], bodies[q]) >= similarity
                       for q, _ in cluster):
                    cluster.append((path, digest))
                    break
            else:
                clusters.append([(path, digest)])
        for cluster in clusters:
            digests = {d for _, d in cluster}
            homes = {_repo_of(p, code_root) for p, _ in cluster}
            # Count HOMES, not copies. Six byte-identical RULES.md files across
            # six arms of one experiment is that experiment's design, and reading
            # it as scatter is a finding with no ruling behind it. Scatter is one
            # document loose in several projects, so the threshold is on projects.
            if len(homes) < min_locations or len(digests) < 2:
                continue
            pairs = [(a, b) for i, (a, _) in enumerate(cluster)
                     for b, _ in cluster[i + 1:]]
            worst = min((_overlap(bodies[a], bodies[b]) for a, b in pairs),
                        default=1.0)
            scattered.append({
                "name": name, "locations": len(cluster), "repos": sorted(homes),
                "versions": len(digests), "min_overlap": round(worst, 2),
                "copies": sorted((os.path.relpath(p, code_root), d)
                                 for p, d in cluster)})
    scattered.sort(key=lambda s: (-s["locations"], -s["versions"], s["name"]))
    return {"population": scanned, "root": code_root, "scattered": scattered,
            "min_locations": min_locations, "max_depth": max_depth,
            "similarity": similarity}


def _repo_of(path: str, root: str) -> str:
    rel = os.path.relpath(path, root)
    return rel.split(os.sep)[0]


# --- D4: scattered homes ---------------------------------------------------

# Tokens that name a kind of thing rather than a thing. Two repos both containing
# "agent" are not the same project; two both containing "slask" are.
GENERIC_TOKENS = {
    "agent", "agents", "app", "apps", "archive", "backup", "bot", "claude",
    "cli", "code", "core", "data", "demo", "dev", "docs", "eval", "evals",
    "experiment", "fork", "forge", "hack", "harness", "lab", "labs", "main",
    "master", "mirror", "local", "new", "next", "node", "old", "project",
    "projects", "prototype", "repo", "sdk", "server", "site", "site2", "src",
    "stack", "temp", "test", "tests", "tool", "tools", "ui", "web", "www",
}


def scattered_homes(code_root: str, min_homes: int = 2) -> dict:
    """One object living in several directories, each of which was reasonable.

    A project gets a second home the day someone clones it to try something, or
    downloads a zip that unpacks as `<name>-main`, or starts the rewrite in a
    fresh directory. Each of those is a good decision in the moment. The defect
    is that after a week the question "where does X live" has no answer, so a
    brief points a lane at one home while the work happens in another. That is
    the shape the fleet hit: one object, four homes, and nobody holding the count.

    Deliberately shallow: top-level directory names under the code root, split on
    separators, generic tokens dropped. It reports CANDIDATES and does not know
    which pairs a human has already ruled to be genuinely different projects that
    share a word — so a settled pair will keep appearing until the ruling lives
    somewhere this can read.

    The ruling it forces: name the canonical home, and retire or rename the
    others."""
    if not os.path.isdir(code_root):
        return {"population": 0, "root": code_root, "scattered": []}
    homes = sorted(d for d in os.listdir(code_root)
                   if os.path.isdir(os.path.join(code_root, d))
                   and not d.startswith("."))
    by_token: dict = collections.defaultdict(set)
    for home in homes:
        for raw in _split_name(home):
            if len(raw) >= 4 and raw not in GENERIC_TOKENS:
                by_token[raw].add(home)

    # Two strengths of evidence, reported apart, because rendering the weak one
    # as confidently as the strong one is how a review surface produces a wrong
    # ruling that looks sourced.
    #
    #   NESTED   one home's normalized name contains another's whole name, so
    #            `loop-labs` / `loop-labs-main` and `Paris Portfolio` /
    #            `paris-portfolio` are the same object twice. Near-certain.
    #   SHARED   the homes share one distinctive word and nothing more. That is
    #            a candidate: `fleet-experiment-2..5` share "fleet" and are four
    #            deliberately separate experiments, not one object in four homes.
    nested, shared = [], []
    for tok, hs in by_token.items():
        if len(hs) < min_homes:
            continue
        group = sorted(hs)
        norm = {h: "".join(_split_name(h)) for h in group}
        # `norm[a] in norm[b]` covers both cases, and equality is the strongest
        # of them: `Paris Portfolio` and `paris-portfolio` normalize to the same
        # string, so they are one object in two homes that differ only in case
        # and separator. An earlier version required norm[a] != norm[b] and threw
        # that pair away — it dropped the clearest finding in the whole section.
        pairs = sorted({tuple(sorted((a, b))) for a in group for b in group
                        if a != b and (norm[a] in norm[b] or norm[b] in norm[a])})
        pairs = [(a, b) if len(norm[a]) <= len(norm[b]) else (b, a)
                 for a, b in pairs]
        entry = {"object": tok, "homes": group, "count": len(group)}
        if pairs:
            entry["nested_pairs"] = [{"inner": a, "outer": b} for a, b in pairs]
            nested.append(entry)
        else:
            shared.append(entry)
    nested.sort(key=lambda s: (-len(s["nested_pairs"]), -s["count"], s["object"]))
    shared.sort(key=lambda s: (-s["count"], s["object"]))
    return {"population": len(homes), "root": code_root, "nested": nested,
            "shared": shared, "min_homes": min_homes}


def _split_name(name: str) -> list:
    out, cur = [], []
    for ch in name.lower():
        if ch.isalnum():
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


# --- D5: git churn — the same class, from a source every stranger has -------

def _git(repo: str, args: list) -> str:
    import subprocess
    try:
        r = subprocess.run(["git", "-C", repo] + args, capture_output=True,
                           text=True, timeout=20)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _default_branch(repo: str) -> str:
    """The branch to measure against. Reads the remote's HEAD rather than
    assuming `main`: a repo whose default is `master` or `develop` would
    otherwise report every branch as unmerged."""
    head = _git(repo, ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"]).strip()
    if head:
        return head.rsplit("/", 1)[-1]
    for guess in ("main", "master", "develop", "trunk"):
        if _git(repo, ["rev-parse", "--verify", "--quiet", guess]).strip():
            return guess
    return ""


def git_churn(repos: list, days: int = 7, stale_days: int = 14) -> dict:
    """The overboard class, read from git — which every stranger already has.

    D1 and D2 read files that exist in one person's ops repo. These read the same
    class of defect out of history that every git user carries:

    - MERGED, NOT DELETED: a branch whose work is already in the default branch
      and which is still sitting there. Leaving it was free every single time.
      In aggregate the repo has a set of addresses that all look live and mostly
      are not, so "which branch is this work on" stops having an answer.
    - ABANDONED: unmerged and untouched for stale_days. Each was a real
      exploration someone meant to come back to.
    - SPREAD: how many repos were touched in the window, and how many of those
      were touched on exactly ONE day. A one-day repo is the git-visible form of
      a seat moving object: work started, and nothing came back to it.

    Every count names the population it was taken over, because the first probe
    that produced these numbers by hand reported 15 branches when the repo has 8
    — it had counted remote refs. A branch count without "local, including the
    default branch" attached is not a measurement."""
    out = []
    spread: dict = collections.defaultdict(set)
    for repo in repos:
        repo = os.path.expanduser(repo or "")
        if not os.path.isdir(os.path.join(repo, ".git")):
            continue
        name = os.path.basename(repo.rstrip(os.sep))
        base = _default_branch(repo)
        locals_ = [b for b in _git(repo, ["branch", "--format=%(refname:short)"]
                                   ).split() if b]
        merged, abandoned = [], []
        if base:
            unmerged = {b for b in _git(
                repo, ["branch", "--no-merged", base,
                       "--format=%(refname:short)"]).split() if b}
            for line in _git(repo, ["for-each-ref", "refs/heads",
                                    "--format=%(committerdate:short) %(refname:short)"
                                    ]).splitlines():
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                when, branch = parts[0], parts[1].strip()
                if branch == base:
                    continue
                if branch in unmerged:
                    if _age_days(when) >= stale_days:
                        abandoned.append({"branch": branch, "last": when})
                else:
                    merged.append({"branch": branch, "last": when})
        for line in _git(repo, ["log", f"--since={days}.days",
                                "--format=%ad", "--date=short"]).splitlines():
            if line.strip():
                spread[name].add(line.strip())
        out.append({"repo": name, "default_branch": base,
                    "local_branches": len(locals_),
                    "merged_not_deleted": sorted(merged, key=lambda m: m["last"]),
                    "abandoned": sorted(abandoned, key=lambda a: a["last"])})

    touched = {r: sorted(d) for r, d in spread.items() if d}
    one_day = sorted(r for r, d in touched.items() if len(d) == 1)
    return {"repos_scanned": len(out), "window_days": days,
            "stale_days": stale_days, "repos": out,
            "touched": touched, "one_day_repos": one_day,
            "days_active": sorted({d for ds in touched.values() for d in ds})}


def _age_days(yyyy_mm_dd: str) -> int:
    from datetime import date
    try:
        y, m, d = (int(x) for x in yyyy_mm_dd.split("-"))
    except ValueError:
        return 0
    return (datetime.now(timezone.utc).date() - date(y, m, d)).days


# --- the report ------------------------------------------------------------

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
                continue        # a malformed row is skipped, never guessed at
    return out


def repos_under(code_root: str, limit: int = 200) -> list:
    """Every git repo directly under the code root. The stranger's default
    population: no configuration, no file format, just the directories they
    already have."""
    if not code_root or not os.path.isdir(code_root):
        return []
    out = []
    for d in sorted(os.listdir(code_root)):
        path = os.path.join(code_root, d)
        if os.path.isdir(os.path.join(path, ".git")):
            out.append(path)
    return out[:limit]


def overboard_report(catches_path: str = "", runs_dir: str = "",
                     code_root: str = "", min_locations: int = 3,
                     repos: list = None, days: int = 7) -> dict:
    # The git half needs no configuration at all: given a code root, the repos
    # under it ARE the population. That is the difference between a detector a
    # stranger can run on day one and one that reads a file only its author has.
    git_repos = list(repos) if repos else repos_under(code_root)
    return {
        "read_at": _now(),
        "blindness": self_catch_blindness(catches_path) if catches_path else None,
        "churn": lane_churn(runs_dir) if runs_dir else None,
        "scatter": artifact_scatter(code_root, min_locations) if code_root else None,
        "homes": scattered_homes(code_root) if code_root else None,
        "git": git_churn(git_repos, days=days) if git_repos else None,
    }


def render_overboard(report: dict, top: int = 6) -> str:
    """The card. Every section states the population it graded and the command
    that reproduces it, because a number without both is a claim with an author."""
    read_at = report.get("read_at", "")
    out = ["OVERBOARD — defects that only exist in aggregate", ""]

    b = report.get("blindness")
    if b is None:
        out += ["1. SELF-CATCH BLINDNESS — no catch log configured", ""]
    elif not b["population"]:
        out += [f"1. SELF-CATCH BLINDNESS — no rows at {b['path']}", ""]
    else:
        share = round(100 * b["unattributed"] / b["population"])
        out.append(f"1. SELF-CATCH BLINDNESS   {b['population']} logged errors, "
                   f"{b['unattributed']} unattributed ({share}%)")
        out.append(f"   rates below are computed over the "
                   f"{b['population'] - b['unattributed']} attributed rows only")
        for a in b["authors"][:top]:
            verdict = ("catches none of its own" if a["self_caught"] == 0
                       else f"{a['self_caught']} self-caught")
            out.append(f"     {a['author']:<14} authored {a['authored']:>3}   {verdict}")
        if b["ambiguous_seats"]:
            out.append(f"     ambiguous seat names, NOT merged: "
                       f"{', '.join(b['ambiguous_seats'])}")
        out += ["   rule: an author with no self-catches is not a control on itself; "
                "route its work to an independent checker", ""]

    c = report.get("churn")
    if c is None:
        out += ["2. LANE CHURN — no runs directory configured", ""]
    elif not c["population"]:
        out += ["2. LANE CHURN — no lane rows found", ""]
    else:
        out.append(f"2. LANE CHURN   {c['population']} lane rows over "
                   f"{len(c['days'])} day(s) observed: {', '.join(c['days'])}")
        for d in c["object_drift"][:top]:
            out.append(f"     {d['seat']} held {d['count']} objects:")
            for o in d["objects"]:
                out.append(f"        {o['object']:<44} {', '.join(o['days'])}")
        for d in c["name_drift"][:top]:
            out.append(f"     {d['seat']} ran under {d['count']} names: "
                       f"{', '.join(d['names'])}")
        if not c["object_drift"] and not c["name_drift"]:
            out.append("     no seat changed name or object in the window")
        out += ["   rule: freeze the seat-to-object binding, or name which object "
                "is current", ""]

    s = report.get("scatter")
    if s is None:
        out += ["3. DRIFTED DUPLICATES — no code root configured", ""]
    else:
        out.append(f"3. DRIFTED DUPLICATES   {s['population']} distinctive .md files "
                   f"scanned under {s['root']}")
        out.append(f"   grouped by basename, kept only clusters overlapping "
                   f">={s.get('similarity', 0.5)} on content; a renamed copy is out of scope")
        for item in s["scattered"][:top]:
            out.append(f"     {item['name']:<38} {item['locations']} copies, "
                       f"{item['versions']} versions, {len(item['repos'])} repos, "
                       f"overlap >={item['min_overlap']}")
            for rel, digest in item["copies"][:6]:
                out.append(f"        {digest}  {rel}")
        if not s["scattered"]:
            out.append("     no distinctive document is duplicated and drifted")
        out += ["   rule: name the canonical copy and retire the rest, or give the "
                "forks different names", ""]

    h = report.get("homes")
    if h is None:
        out += ["4. SCATTERED HOMES — no code root configured", ""]
    else:
        out.append(f"4. SCATTERED HOMES   {h['population']} top-level directories "
                   f"under {h['root']}; prior rulings are not known here")
        if h["nested"]:
            out.append("   one name contains another — the same object twice:")
        # One pair can be reached through several shared tokens (`Paris Portfolio`
        # / `paris-portfolio` arrives under both "paris" and "portfolio"). Printing
        # it once per token would make one defect look like two, and a card that
        # inflates its own count is the persuasive-and-wrong failure again.
        seen_pairs = set()
        shown = 0
        for item in h["nested"]:
            if shown >= top:
                break
            for pair in item["nested_pairs"]:
                key = (pair["inner"], pair["outer"])
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                out.append(f"     {item['object']:<16} {pair['inner']}  ->  "
                           f"{pair['outer']}")
                shown += 1
        if h["shared"]:
            out.append("   share one word only — candidates, may be separate projects:")
        for item in h["shared"][:top]:
            out.append(f"     {item['object']:<16} {item['count']} homes: "
                       f"{', '.join(item['homes'])}")
        if not h["nested"] and not h["shared"]:
            out.append("     every object has exactly one home")
        out += ["   rule: name the canonical home, then retire or rename the "
                "others", ""]

    g = report.get("git")
    if g is None:
        out += ["5. GIT CHURN — no git repos found", ""]
    else:
        stale, dead = [], []
        for r in g["repos"]:
            for a in r["abandoned"]:
                stale.append((r["repo"], a["branch"], a["last"]))
            if r["merged_not_deleted"]:
                dead.append((r["repo"], len(r["merged_not_deleted"]),
                             r["local_branches"], r["default_branch"]))
        out.append(f"5. GIT CHURN   {g['repos_scanned']} repos, "
                   f"{len(g['touched'])} touched in the last {g['window_days']} days "
                   f"over {len(g['days_active'])} active day(s)")
        if dead:
            out.append("   merged into the default branch and never deleted "
                       "(counts are LOCAL branches, default branch included):")
        for repo, n, total, base in sorted(dead, key=lambda d: -d[1])[:top]:
            out.append(f"     {repo:<28} {n} of {total} local branches, "
                       f"vs {base}")
        if stale:
            out.append(f"   unmerged and untouched for {g['stale_days']}+ days:")
        for repo, branch, last in sorted(stale, key=lambda s: s[2])[:top]:
            out.append(f"     {repo:<28} {branch:<34} last {last}")
        if g["one_day_repos"]:
            out.append(f"   touched on exactly ONE day in the window "
                       f"({len(g['one_day_repos'])} of {len(g['touched'])}): "
                       f"{', '.join(g['one_day_repos'][:10])}")
        if not dead and not stale and not g["one_day_repos"]:
            out.append("     no dead branches, no abandoned work, no one-day repos")
        out += ["   rule: delete the merged branches; merge or delete the "
                "abandoned ones; for a one-day repo, finish it or archive it", ""]

    out.append(f"read {read_at}  ·  helicon overboard")
    return "\n".join(out)
