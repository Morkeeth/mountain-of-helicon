"""The complaint log: Oscar's pushbacks, kept instead of thrown away.

A correction is the only honest eval an agent gets. Every other signal in this
repo is the machine grading itself — battery verdicts, judge runs, self-scored
retrieval. A pushback is a human saying "no, that is wrong" with nothing to gain
by lying, and it is destroyed the moment the terminal closes.

So this reads it back out of the transcripts, where it already exists and is
already being deleted by attrition.

TWO AUTHORSHIP GATES, both load-bearing, both measured before this was written.

Gate 1 — a `type: user` entry is NOT necessarily the human. Across ~600 local
transcripts, 2,833 non-tool user turns broke down as: 2,285 `typed` + 191
`queued` (his), against 392 `sdk` (programmatic judge runs), 414 `system` (task
notifications and messages from OTHER Claude sessions), 483 `isMeta` (injected
skill bodies, image references) and 68 other. Treat the raw stream as human
feedback and 46% of the corpus is text he never wrote — including other agents'
prose and this repo's own skill files. An agent would be grading itself on its
own output and calling it human signal.

Gate 2 — even a `typed` turn is not always his WRITING. He pastes agent-drafted
lane prompts and long content and presses enter; `promptSource` says typed
because it was. Those pastes are long and any correction-shaped phrase inside
them sits deep in the body, so length + position separates them.

MEASURED, self-graded, n=20 read by hand: raw user turns 28% precision, gate 1
alone ~43%, both gates ~90%. Yield 43 complaints in 2,476 authored turns (1.7%).
The numbers live in the docstring rather than a doc because they are the reason
the gates exist and they should be read by whoever next widens the pattern.

No new table: a complaint is a cube of `type='complaint'`, so it inherits FTS,
embeddings, decay and the human review loop that already exist. 38 tables was
already too many.
"""
import glob
import hashlib
import json
import os
import re
from datetime import datetime, timezone

from helicon.db import insert_cube
from helicon.models import HeliconCube

PROJECTS = os.path.expanduser("~/.claude/projects")

# Turns the human actually authored. 'queued' is typed-while-busy, still his.
HUMAN_SOURCES = ("typed", "queued")

# A pasted brief is not a complaint, however cross it reads. What separates one
# is WHERE the correction sits: he opens with it, an agent-drafted lane prompt
# happens to contain it somewhere in the body.
#
# The first version also capped total length at 400 chars. Measured against the
# real corpus that cap rejected exactly 3 turns, and 2 of the 3 were genuine
# pushbacks that simply ran long ("no, mac OS we pilot it...", "you didnt use
# any of the design skills no?..."). It bought one true rejection and cost two,
# so it is gone. Position does the work; length was taste dressed up as a rule.
HEAD_CHARS = 120

# Correction shapes, each anchored to a sentence start. The loose words that a
# first pass used — don't, stop, focus, again — fired on ordinary instructions
# ("don't scope it", "focus on the table") and on skill-file prose, and cost
# more precision than they bought recall. They are deliberately absent.
PUSHBACK = re.compile(
    r"(^|[.!?]\s+|\n)\s*("
    r"no\b|nope\b|wrong\b|that'?s not\b|not what i\b|"
    r"i (told|said|asked|meant) you\b|i (told|said|asked|meant)\b|"
    r"you (didn'?t|did not|never|missed|forgot|broke)\b|"
    r"why (did|are|is) you\b|\brevert\b|\bundo (that|it)\b|incorrect\b|"
    r"misunderstan|that is wrong|thats wrong|still (broken|wrong|failing)\b|"
    r"doesn'?t work\b)", re.I)

# What the correction is ABOUT. A complaint you cannot group is a complaint you
# cannot act on: 43 rows of prose is a diary, and the point is to see the same
# objection arrive for a fourth time.
#
# These five came from READING all 43 stored complaints, not from imagining what
# a person might object to. The first guess was a plausible-sounding six —
# staleness, fabrication, scope, wrong-target, ignored-instruction, identity —
# and it left 35 of 43 unlabelled, because it was a taxonomy of what an agent
# fears rather than of what this human actually says. First match wins, so the
# order is the precedence.
LABELS = (
    # Kept, not filtered. "no this is great" is a false positive of the detector
    # and hiding it would flatter the yield; labelling it lets the rate be SEEN.
    ("agreement",
     r"^\s*no[,.!\s]+(this|that|it|you)?\s*(is|looks|sounds|can|are)?\s*"
     r"(great|good|fine|perfect|nice|correct|right|ok)\b"),
    # The agent asserted something untrue about the world.
    ("stale-or-false",
     r"you (didn'?t|did not|never) (fetch|check|read|see|look)|i (already|didn'?t|did not|never) "
     r"(post|do|use|have|auth)|that was (a year|months|yesterday)|\bstale\b|not up to date|"
     r"out of date|old context|in great shape|already (done|posted|shipped|searched)"),
    # The agent misunderstands what a thing IS, or is missing the context to know.
    ("wrong-model",
     r"misunderstan|you don'?t have the (right|full) context|no clue what|"
     r"keep them (differnet|different)|is a (agent|product|suite|app)\b|that'?s not (the|what)"),
    # The agent did more, or other, than was asked.
    ("over-scope",
     r"i (just|only) want|i don'?t want|no need (to|for)|don'?t need|too much|no tables|"
     r"simpler|easier than this|not the point|stupid details|full (article )?review"),
    # The agent proposed or took the wrong next action.
    ("wrong-plan",
     r"you'?re the orchestrator|the main goal|we (do|build|need|want)\b|lets fix|don'?t kill|"
     r"instead\b|we wont fork|no new "),
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def label(text: str) -> str:
    """First matching label wins; order above is the precedence."""
    for name, pattern in LABELS:
        if re.search(pattern, text, re.I):
            return name
    return "unlabelled"


def is_pushback(text: str) -> bool:
    """Gate 2. Applied to text that has ALREADY passed gate 1."""
    if not text:
        return False
    match = PUSHBACK.search(text)
    return bool(match) and match.start() < HEAD_CHARS


def authored_turns(path: str) -> list[dict]:
    """Gate 1: only the turns the human wrote, with the transcript's own facts.

    Never infers authorship from content. `promptSource` is what the harness
    recorded at the time and is the only thing here that cannot be faked by a
    convincing-sounding message from another agent.
    """
    out = []
    try:
        fh = open(path, errors="ignore")
    except OSError:
        return out
    with fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") != "user":
                continue
            if entry.get("toolUseResult") or entry.get("isMeta"):
                continue
            if entry.get("promptSource") not in HUMAN_SOURCES:
                continue
            content = (entry.get("message") or {}).get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(p.get("text", "") for p in content
                                if isinstance(p, dict) and p.get("type") == "text")
            else:
                continue
            text = text.strip()
            if not text or text.startswith("<"):
                continue
            out.append({
                "text": text,
                "session_id": entry.get("sessionId") or "",
                "cwd": entry.get("cwd") or "",
                "timestamp": entry.get("timestamp") or "",
                "source_ref": f"{os.path.basename(path)}#{entry.get('uuid') or ''}",
            })
    return out


def scan(conn, *, projects_dir: str | None = None, limit: int | None = None) -> dict:
    """Read every transcript, keep the complaints, skip what is already stored.

    Idempotent by content hash, so it is safe on a timer: the UNIQUE constraint
    on helicon_cubes.content_hash makes a re-scan a no-op rather than a
    duplicate, which is what lets this be re-run without anyone deciding to.
    """
    root = projects_dir or PROJECTS
    found = stored = 0
    labels: dict[str, int] = {}
    scanned_turns = 0
    for path in sorted(glob.glob(os.path.join(root, "*", "*.jsonl"))):
        for turn in authored_turns(path):
            scanned_turns += 1
            if not is_pushback(turn["text"]):
                continue
            found += 1
            kind = label(turn["text"])
            labels[kind] = labels.get(kind, 0) + 1
            digest = hashlib.sha256(turn["text"].encode()).hexdigest()
            project = os.path.basename(turn["cwd"]) or "unknown"
            cube = HeliconCube(
                id="cx_" + digest[:12],
                source="claude-code",
                source_ref=turn["source_ref"],
                type="complaint",
                # The complaint IS the title. Summarising a correction is how you
                # lose the thing that made it worth keeping.
                title=turn["text"][:80],
                content=turn["text"],
                summary=f"{kind} · {project}",
                content_hash=digest,
                created_at=turn["timestamp"] or _now(),
                valid_from=turn["timestamp"] or _now(),
                tags=[kind, project],
                metadata={"label": kind, "project": project,
                          "session_id": turn["session_id"], "cwd": turn["cwd"]},
            )
            if insert_cube(conn, cube):
                stored += 1
            if limit and stored >= limit:
                break
    conn.commit()
    return {"turns_scanned": scanned_turns, "complaints_found": found,
            "newly_stored": stored, "by_label": labels}


def recent(conn, limit: int = 20, label_filter: str | None = None) -> list[dict]:
    sql = ("SELECT id, title, content, summary, created_at, metadata FROM helicon_cubes "
           "WHERE type='complaint'")
    params: list = []
    if label_filter:
        sql += " AND summary LIKE ?"
        params.append(f"{label_filter}%")
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def by_project(conn, project: str) -> list[tuple[str, int]]:
    """What he pushed back on in ONE project, by kind. Feeds the fleet screen's
    friction line — the only field on it sourced from a human rather than a
    machine."""
    rows = conn.execute(
        "SELECT json_extract(metadata,'$.label') AS label, COUNT(*) c "
        "FROM helicon_cubes WHERE type='complaint' "
        "AND json_extract(metadata,'$.project')=? "
        "GROUP BY label ORDER BY c DESC", (project,)).fetchall()
    return [(r["label"] or "unlabelled", r["c"]) for r in rows]


def by_label(conn) -> list[tuple[str, int]]:
    """The count is the point. One complaint is noise; the same objection four
    times is a defect in how the agent works."""
    rows = conn.execute(
        "SELECT json_extract(metadata,'$.label') AS label, COUNT(*) c "
        "FROM helicon_cubes WHERE type='complaint' GROUP BY label ORDER BY c DESC"
    ).fetchall()
    return [(r["label"] or "unlabelled", r["c"]) for r in rows]


def format_log(counts: list[tuple[str, int]], rows: list[dict], scanned=None) -> str:
    # "what YOU pushed back on", not a name. On a cold clone the first thing this
    # command said to a new user was "what Oscar pushed back on", which is both
    # meaningless to them and a personalisation leak in a repo about to be public.
    out = ["", "COMPLAINT LOG — what you pushed back on", ""]
    if not counts:
        if scanned is not None and not scanned.get("turns_scanned"):
            # Telling someone to run the command they just ran is how a tool
            # teaches you it is not listening.
            out.append("  no transcripts found under ~/.claude/projects — nothing to read yet.")
        elif scanned is not None:
            out.append(f"  read {scanned['turns_scanned']} of your turns and found no "
                       f"corrections in them.")
        else:
            out.append("  no complaints stored yet. run: helicon brief complaints --scan")
        return "\n".join(out)
    total = sum(c for _, c in counts)
    out.append(f"  {total} correction(s), by kind:")
    for name, count in counts:
        out.append(f"    {name:22s} {count:3d}  {'=' * min(count, 40)}")
    out.append("")
    out.append("  most recent:")
    for row in rows:
        meta = json.loads(row["metadata"] or "{}")
        when = (row["created_at"] or "")[:10]
        out.append(f"    [{when}] ({meta.get('label', '?')}/{meta.get('project', '?')}) "
                   f"{row['title'][:88]}")
    out.append("")
    return "\n".join(out)
