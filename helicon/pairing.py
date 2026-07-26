"""Cross-source contradiction pairing — the R1 selector.

ROT.md R1 said it out loud: the Qwen detector was proven on the real birthday
pair, but *production pairing across sources* was the gap — nothing selected
which two cubes to hand the detector, so the conflict only surfaced when a
human already knew where to look.

This closes the gap deterministically. From every live cube it extracts
(person, topic, interval) assertions — a person name and a calendar date (or
range) inside a small window around an event keyword ("birthday", "wedding",
...). Assertions group by (person, topic); a group where two different source
files assert two *disjoint* intervals is a candidate contradiction ("Sep
11-13" vs "Sep 13" overlap, so they agree; "Jul 13" vs "Jul 18" cannot both
be true). The selector finds, the Qwen judge (detect_contradictions) rules;
with no key the disjoint-interval mismatch itself is the verdict. Zero LLM
calls in the selector.

Findings land in audit_log as audit_type='factual' (same shape audit_factual
writes), so the dashboard FINDINGS feed, the graph's 'contradicts' edges and
the rot exam all pick them up with no new plumbing.
"""
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone

from helicon.models import AuditResult
from helicon.db import insert_audit
from helicon.reconcile import source_ref_scope

# Person-anchored, date-bearing event facts. Deliberately few: precision over
# recall — a missed pair is a gap, a false pair teaches the human to ignore
# the feed.
TOPIC_KEYWORDS = ("birthday", "wedding", "anniversary")

# Windows (chars around the keyword) within which a person / date must sit to
# count as the same fact. The person window is tighter: names bind to their
# event ("Lea birthday", "Itai's wedding"), while dates ride further out
# ("Birthday gift | Lea (Jul 13)").
PERSON_WINDOW = 25
DATE_WINDOW = 40

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}

_MON = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_DATE_RES = [
    # Jul 13 / July 13 / Sep 11-13 (optional range end)
    re.compile(rf"\b{_MON}\s+(\d{{1,2}})(?:\s*[-–]\s*(\d{{1,2}}))?\b"),
    # 13 Jul / 13 July
    re.compile(rf"\b(\d{{1,2}})\s+{_MON}\b"),
    # 2026-07-13
    re.compile(r"\b\d{4}-(\d{2})-(\d{2})\b"),
    # 09-11..09-13 — HELICON'S OWN canonical interval label (_iv_label). This is
    # the format every ruling, every resolution and every GOLDEN_RULE is written
    # in, and the parser could not read it. Resolutions are parsed by
    # _parse_label, which understands `..`; cube CONTENT was parsed only by the
    # prose patterns above. Two parsers, two grammars, one format.
    #
    # The cost was the ruling loop poisoning itself. Recording a ruling writes a
    # line like:
    #   #322 Itai wedding = **09-11..09-13** (the "Aug 14-22" cube was mislabeled)
    # The truth is stated in canonical form and the DEAD value is quoted in prose
    # to name what was wrong. The parser skipped the canonical truth it could not
    # read, lifted "Aug 14-22" out of the sentence written to kill it, and filed
    # the correction as if it ASSERTED the dead value — a fresh critical finding,
    # manufactured by the act of ruling. Every ruling planted a future false
    # alarm, which inflates R1 forever and discredits the exam that has to stay
    # trustworthy. Reading both poles lets the existing one-cube-quotes-both
    # guard do its job.
    re.compile(r"\b(\d{2})-(\d{2})\.\.(\d{2})-(\d{2})\b"),
]

_PERSON_RE = re.compile(r"\b([A-ZÀ-Þ][a-zà-öø-ÿ]{2,})\b")

# Capitalized words that are not people. Months/weekdays plus the sentence
# furniture and vault vocabulary that shows up capitalized around event lines.
_PERSON_BLOCKLIST = {
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
    "nov", "dec", "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun", "if", "poster",
    "the", "this", "that", "these", "then", "when", "after", "before",
    "with", "from", "and", "but", "his", "her", "our", "their", "your",
    "birthday", "wedding", "anniversary", "gift", "party", "list", "week",
    "weekend", "today", "tomorrow", "date", "conflict", "says", "order",
    "book", "buy", "send", "plan", "confirm", "confirmed", "pending", "status",
    "done", "next", "what", "who", "why", "how", "note", "draft", "file",
    "edited", "created", "updated", "timeline", "trip", "trips", "hotel",
    "summer", "romantic", "dropped",
}


def _fmt(month: int, day: int) -> str:
    return f"{month:02d}-{day:02d}"


# Date-role filter. The event keyword tells us WHICH fact a line is about, but a
# date near it is only the event date if it is not playing a *logistics* role.
# Learned from live false positive #279: "Birthday gift | Lea (Jul 13)" and
# "plan gift before Jul 13" both rode a gift/deadline date into 'Lea birthday'.
# Two guards, mirroring the person-role heuristics in _persons_in:
#   (1) keyword immediately followed by a logistics noun ("birthday gift") is a
#       shopping item, not a dated event — the occurrence asserts no event date.
#   (2) a date immediately preceded by a logistics/deadline cue ("before Jul 13",
#       "order ... Jul 13", "gift by Jul 13") is that errand's date, not the event.
_EVENT_LOGISTICS_NOUNS = (
    "gift", "gifts", "present", "presents", "party", "card", "cards",
    "cake", "dinner", "shopping", "list", "reminder",
)
_DATE_ROLE_CUE_RE = re.compile(
    r"\b(?:before|after|by|until|till|due|deadline|order|ordered|ordering|"
    r"arriv\w+|deliver\w+|ship\w*|sent|send|sending|buy|bought|buying|"
    r"plan|planning|book|booked|rsvp|gift|present|reminder|from)\b[\s:>|\-–]*$",
    re.IGNORECASE)


def _keyword_is_logistics_item(line_low: str, kw_end: int) -> bool:
    """True when the event keyword is the head of a shopping item rather than a
    dated event: 'birthday gift', 'wedding present'. Possessive/punctuation
    between the keyword and the noun is skipped ("birthday's card")."""
    after = line_low[kw_end: kw_end + 16].lstrip(" '’s:|-–\t")
    return any(after.startswith(n) for n in _EVENT_LOGISTICS_NOUNS)


def _intervals_with_pos(text: str) -> list[tuple[tuple[str, str], int]]:
    """Like _intervals_in, but each interval carries the char offset where its
    date match starts — so callers can inspect the words just before it and
    decide whether the date is playing an event or a logistics role."""
    out = []
    for i, rx in enumerate(_DATE_RES):
        for m in rx.finditer(text):
            if i == 3:
                # MM-DD..MM-DD spans two months in the general case, so it is
                # built directly rather than through the same-month _fmt pair.
                m1, d1, m2, d2 = (int(m.group(1)), int(m.group(2)),
                                  int(m.group(3)), int(m.group(4)))
                if (1 <= m1 <= 12 and 1 <= m2 <= 12
                        and 1 <= d1 <= 31 and 1 <= d2 <= 31
                        and (m1, d1) <= (m2, d2)):
                    out.append(((_fmt(m1, d1), _fmt(m2, d2)), m.start()))
                continue
            if i == 0:
                month, day = _MONTHS[m.group(1).lower()[:3]], int(m.group(2))
                end_day = int(m.group(3)) if m.group(3) else day
            elif i == 1:
                month, day = _MONTHS[m.group(2).lower()[:3]], int(m.group(1))
                end_day = day
            else:
                month, day = int(m.group(1)), int(m.group(2))
                end_day = day
            if 1 <= month <= 12 and 1 <= day <= 31 and day <= end_day <= 31:
                out.append(((_fmt(month, day), _fmt(month, end_day)), m.start()))
    return out


def _intervals_in(text: str) -> list[tuple[str, str]]:
    """Every calendar date in `text`, normalized to ('MM-DD', 'MM-DD')
    (start, end) intervals — a single day is a zero-length interval, a range
    like 'Sep 11-13' keeps both endpoints so overlap can mean agreement."""
    return [iv for iv, _ in _intervals_with_pos(text)]


def _event_intervals_in(text: str) -> list[tuple[str, str]]:
    """Dates in `text` that are playing the EVENT role — a date immediately
    preceded by a logistics/deadline cue ("before Jul 13", "gift by Jul 13")
    is dropped, so an errand's date never masquerades as the event's."""
    out = []
    for iv, pos in _intervals_with_pos(text):
        if _DATE_ROLE_CUE_RE.search(text[:pos]):
            continue
        out.append(iv)
    return out


def _disjoint(a: tuple[str, str], b: tuple[str, str]) -> bool:
    """MM-DD strings compare lexicographically, so interval logic is direct."""
    return a[1] < b[0] or b[1] < a[0]


_PAREN_RE = re.compile(r"\([^)]*\)?|\)[^(]*$")
_PLACE_PREP_RE = re.compile(r"\b(?:in|at|near|to|via)\s+$", re.IGNORECASE)


def _persons_in(text: str) -> list[str]:
    """Person candidates. Two location heuristics learned from live false
    positives ('Paris birthday', 'Lisbon wedding'): a capitalized word inside
    parentheses is an annotation ('birthday (Paris)'), and one preceded by a
    place preposition ('wedding in Lisbon') is a venue. Neither is a subject."""
    # strip parenthesized chunks for PERSON extraction only — dates often
    # live in parens ('Lea (Jul 13)') and must stay visible to _intervals_in
    clean = _PAREN_RE.sub(" ", text)
    out = []
    for m in _PERSON_RE.finditer(clean):
        if m.group(1).lower() in _PERSON_BLOCKLIST:
            continue
        if _PLACE_PREP_RE.search(clean[: m.start()]):
            continue
        out.append(m.group(1))
    return out


def extract_assertions(content: str, title: str = "") -> list[dict]:
    """(person, topic, interval) assertions from one cube's text. An assertion
    needs a person within PERSON_WINDOW and a date within DATE_WINDOW of an
    event keyword, all on one line — the deterministic definition of 'this
    line asserts a dated fact about a person'. A keyword immediately followed
    by '?' is a question, not an assertion."""
    assertions = []
    for line in f"{title}\n{content or ''}".splitlines():
        low = line.lower()
        for topic in TOPIC_KEYWORDS:
            for kw in re.finditer(re.escape(topic), low):
                if "?" in line[kw.end(): kw.end() + 4]:
                    continue  # "Trip back for Lea's birthday?" is a question
                if _keyword_is_logistics_item(low, kw.end()):
                    continue  # "Birthday gift | Lea (Jul 13)" is a shopping item
                p_win = line[max(0, kw.start() - PERSON_WINDOW): kw.end() + PERSON_WINDOW]
                d_win = line[max(0, kw.start() - DATE_WINDOW): kw.end() + DATE_WINDOW]
                for p in _persons_in(p_win):
                    for iv in _event_intervals_in(d_win):
                        assertions.append({"person": p, "topic": topic,
                                           "interval": iv, "line": line.strip()})
    # Dedupe within the cube — but when several lines assert the same interval,
    # keep the one that asserts it ALONE.
    #
    # This is load-bearing for the never-twice guard. A correction line always
    # quotes both poles ("X = **TRUTH** (the 'DEAD' cube was mislabeled)"), and
    # the guard excludes an assertion whose LINE also states the truth. Keeping
    # the first occurrence meant a genuine re-assertion further down the same
    # document inherited the CORRECTION's line and got excluded with it — so the
    # rot went unreported. Order-dependent, and the natural order was the broken
    # one: a status doc records the ruling near the top and plans further down.
    #
    #   ruling line 1, rot line 5  ->  SILENT   (rot deduped into the ruling)
    #   rot line 1, ruling line 5  ->  fires
    #
    # A line asserting the interval alone is the incriminating one, and it is
    # never a correction, because a correction names what it replaces.
    solo = {}
    for a in assertions:
        k = (a["person"].lower(), a["topic"], a["line"])
        solo.setdefault(k, set()).add(a["interval"])
    seen, out = set(), []
    for a in sorted(assertions,
                    key=lambda x: len(solo[(x["person"].lower(), x["topic"], x["line"])])):
        key = (a["person"].lower(), a["topic"], a["interval"])
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def _cube_scope(row) -> str:
    """The 'source file' a cube speaks for: connector + file-level source_ref."""
    return f"{row['source']}:{source_ref_scope(row['source_ref'] or '')}"


def _parse_label(label: str) -> tuple[str, str]:
    """'07-18' or '07-11..07-13' back to an interval."""
    if ".." in label:
        a, b = label.split("..", 1)
        return (a, b)
    return (label, label)


def load_resolutions(conn: sqlite3.Connection) -> dict:
    """(person, topic) -> {'truth', 'resolved_at', 'audit_id'} from resolved
    pairing findings. The truth is what the human said when they closed the
    finding; with several resolutions for one fact, the LATEST wins (ordered
    explicitly — table scan order is not a contract)."""
    from helicon.timeutil import ts_norm
    out = {}
    for row in conn.execute(
        "SELECT id, details, human_decision, resolved_at FROM audit_log "
        "WHERE audit_type = 'factual' AND human_decision LIKE 'resolved:%' "
        "AND details LIKE '%pair_key%' ORDER BY resolved_at, id"
    ):
        try:
            d = json.loads(row["details"])
        except (json.JSONDecodeError, TypeError):
            continue
        truth = row["human_decision"].split(":", 1)[1]
        out[(d.get("person"), d.get("topic"))] = {
            "truth": truth,
            "resolved_at": ts_norm(row["resolved_at"]) or (row["resolved_at"] or ""),
            "audit_id": row["id"]}
    return out


def _iv_label(iv: tuple[str, str]) -> str:
    return iv[0] if iv[0] == iv[1] else f"{iv[0]}..{iv[1]}"


def find_conflicts(conn: sqlite3.Connection) -> list[dict]:
    """The pair selector. Scans live cubes, groups assertions by (person,
    topic), and for each group picks the best-supported pair of DISJOINT
    intervals asserted by at least two different source files. Deterministic,
    no LLM, cheap enough to run on every report / rot exam."""
    like = " OR ".join("lower(content) LIKE ?" for _ in TOPIC_KEYWORDS)
    rows = conn.execute(
        f"SELECT id, title, content, source, source_ref, created_at, review_status "
        f"FROM helicon_cubes "
        f"WHERE review_status IN ('pending', 'revised', 'approved') "
        f"AND merged_into IS NULL AND ({like})",
        [f"%{t}%" for t in TOPIC_KEYWORDS],
    ).fetchall()

    groups: dict = {}
    for row in rows:
        for a in extract_assertions(row["content"], row["title"]):
            g = groups.setdefault((a["person"].lower(), a["topic"]), {})
            d = g.setdefault(a["interval"], {"scopes": set(), "cubes": []})
            d["scopes"].add(_cube_scope(row))
            d["cubes"].append({"id": row["id"], "title": row["title"],
                               "scope": _cube_scope(row),
                               "created_at": row["created_at"],
                               "line": a["line"]})

    resolutions = load_resolutions(conn)
    conflicts = []
    for (person, topic), by_iv in groups.items():
        # A resolved fact stays closed — unless memory written AFTER the
        # resolution asserts a date the human already ruled out. That is the
        # never-twice guard: the same rot resurfacing re-alarms, it does not
        # get grandfathered in under the old resolution.
        res = resolutions.get((person, topic))
        resurfaced = False
        if res:
            from helicon.timeutil import ts_norm
            truth_iv = _parse_label(res["truth"])
            # A cube that ALSO asserts the truth is a CORRECTION, not the rot
            # coming back. This is the loop poisoning itself: the never-twice
            # guard re-alarms on any post-resolution cube asserting the dead
            # value, but the memory that RECORDS a ruling is written moments
            # after it and has to name the dead value to say what was wrong:
            #   #322 Itai wedding = **09-11..09-13** ("Aug 14-22" was mislabeled)
            # That line asserts the truth and quotes the corpse. Counting it as
            # resurfacing means the act of ruling manufactures the evidence that
            # the ruling was violated — every ruling Oscar makes plants a future
            # false alarm, R1 inflates forever, and the one exam that has to stay
            # trustworthy slowly discredits itself.
            #
            # Same shape catches enumeration: "Italy (Aug 14-22) and Itai's
            # wedding, Sweden (Sep 11-13)" is one line about two trips, and the
            # keyword-proximity window grabs both dates. It asserts the truth
            # too, so it is not a resurfacing either.
            # Keyed by (cube, LINE), not by cube. A correction is a property of
            # a sentence: "wedding = **09-11..09-13** (the 'Aug 14-22' cube was
            # mislabeled)" states the truth and names the corpse on ONE line.
            # Excluding the whole CUBE instead would let real rot hide anywhere
            # else in the same document — a status doc naming the truth on line 1
            # and genuinely re-asserting the dead value on line 90 would go
            # unreported, which trades a false alarm for a missed one and quietly
            # guts the never-twice guarantee. That hole was real and is what this
            # tuple closes.
            truth_lines = {(c["id"], c["line"]) for iv, d in by_iv.items()
                           if not _disjoint(iv, truth_iv) for c in d["cubes"]}
            by_iv = {
                iv: {"scopes": {c["scope"] for c in cubes},
                     "cubes": cubes}
                for iv, d in by_iv.items()
                if _disjoint(iv, truth_iv)
                and (cubes := [c for c in d["cubes"]
                               if ts_norm(c["created_at"]) > res["resolved_at"]
                               and (c["id"], c["line"]) not in truth_lines])
            }
            if not by_iv:
                continue  # resolved, and nothing new contradicts the truth
            # The truth's representative is the CORRECTION CUBE resolve_pair
            # wrote — a real DB row, so the Qwen judge downstream always has
            # real content to rule on (a synthetic marker here crashed
            # pair_scan the moment the guard fired with a client configured).
            crow = conn.execute(
                "SELECT id, title, created_at FROM helicon_cubes "
                "WHERE source = 'human-resolution' AND source_ref = ?",
                (f"audit:{res['audit_id']}",)).fetchone()
            truth_cube = ({"id": crow["id"], "title": crow["title"],
                           "scope": "human-resolution",
                           "created_at": crow["created_at"],
                           "line": f"resolved {res['truth']}"} if crow else
                          {"id": f"resolution:{person}|{topic}",
                           "title": f"human resolution: {res['truth']}",
                           "scope": "human-resolution",
                           "created_at": res["resolved_at"],
                           "line": f"resolved {res['truth']}"})
            by_iv[truth_iv] = {"scopes": {"human-resolution"},
                               "cubes": [truth_cube]}
            resurfaced = True
        if len(by_iv) < 2:
            continue
        # Best-supported disjoint pair: two intervals that cannot both be
        # true, asserted by >=2 distinct files, ranked by how much memory
        # stands behind each side (a date asserted once is probably noise;
        # the fight is between the two well-attested versions).
        best = None
        ivs = list(by_iv.keys())
        for x in range(len(ivs)):
            for y in range(x + 1, len(ivs)):
                a, b = ivs[x], ivs[y]
                if not _disjoint(a, b):
                    continue
                sa, sb = by_iv[a], by_iv[b]
                if len(sa["scopes"] | sb["scopes"]) < 2:
                    continue  # one file arguing with itself is not cross-source
                # Support counts only single-side cubes: a cube quoting BOTH
                # dates documents the conflict, it doesn't take a side — and
                # each side needs at least one genuine asserter, or the
                # "conflict" is just meta-memory talking about itself.
                ids_a = {c["id"] for c in sa["cubes"]}
                ids_b = {c["id"] for c in sb["cubes"]}
                only_a, only_b = ids_a - ids_b, ids_b - ids_a
                if not only_a or not only_b:
                    continue
                support = (min(len(only_a), len(only_b)),
                           len(only_a) + len(only_b))
                if best is None or support > best[0]:
                    best = (support, a, b, only_a, only_b)
        if best is None:
            continue
        _, iv_a, iv_b, only_a, only_b = best
        # Representatives: each side speaks from its most-attested file (the
        # scope repeating that date hardest), newest single-side cube within
        # it — and the two sides must come from different files where the
        # store allows it. The pair handed to the judge should BE the
        # cross-source disagreement, not one diff cube quoting both versions.
        from helicon.timeutil import ts_norm as _tsn

        def _rep(cubes, only_ids, avoid_scope=None):
            pool = ([c for c in cubes if c["id"] in only_ids] or cubes)
            pool = ([c for c in pool if c["scope"] != avoid_scope] or pool)
            per_scope = Counter(c["scope"] for c in pool)
            top = max(per_scope, key=lambda s: per_scope[s])
            return max((c for c in pool if c["scope"] == top),
                       key=lambda c: _tsn(c["created_at"]))
        rep_a = _rep(by_iv[iv_a]["cubes"], only_a)
        reps = {_iv_label(iv_a): rep_a,
                _iv_label(iv_b): _rep(by_iv[iv_b]["cubes"], only_b,
                                      avoid_scope=rep_a["scope"])}
        labels = sorted(reps.keys())
        # A resurfaced key carries the resolution it violates, so a SECOND
        # resurface after a second resolution files again — never-twice must
        # not decay into never-only-once-more.
        key = f"{person}|{topic}|{'/'.join(labels)}"
        if resurfaced:
            key += f"|resurfaced:{res['resolved_at']}"
        conflicts.append({
            "person": person, "topic": topic,
            "dates": labels,
            "all_dates": sorted(_iv_label(iv) for iv in by_iv),
            "pair_key": key,
            "representatives": reps,
            "support": {_iv_label(iv_a): len(only_a), _iv_label(iv_b): len(only_b)},
            "cube_count": sum(len(d["cubes"]) for d in by_iv.values()),
            "scopes": sorted(by_iv[iv_a]["scopes"] | by_iv[iv_b]["scopes"]),
            "resurfaced": resurfaced,
        })
    return conflicts


def _memories(n) -> str:
    """'1 memory' / '3 memories'. The old text said "cube(s)" to dodge
    pluralising; the name is a real word now, so it agrees with its count."""
    return f"{n} memor{'y' if n == 1 else 'ies'}"


def format_pair_evidence(details: dict) -> str:
    """The human-verifiable receipt for a contradiction finding: the two
    exact lines, where each lives, and how much memory stands behind each
    side. The finding ASSERTS; this is what lets a human VERIFY it in five
    seconds instead of trusting it."""
    d = details
    support = d.get("support", {})
    vals = list(d.get("dates") or [])
    # explicit value<->line alignment when present — sorted date labels and
    # A/B line order are independent, and a receipt with crossed labels is
    # worse than no receipt
    va = d.get("value_a") or (vals[0] if vals else "?")
    vb = d.get("value_b") or (vals[-1] if len(vals) > 1 else "?")
    scopes = d.get("scopes", [])
    sa = d.get("scope_a") or (scopes[0] if scopes else "?")
    sb = d.get("scope_b") or (scopes[-1] if len(scopes) > 1 else "?")
    out = [
        f"A: {va}   ({_memories(support.get(va, '?'))})   {sa}",
        f"   | {(d.get('line_a') or '')[:160]}",
        f"B: {vb}   ({_memories(support.get(vb, '?'))})   {sb}",
        f"   | {(d.get('line_b') or '')[:160]}",
    ]
    extra = [v for v in d.get("all_dates", []) if v not in (va, vb)]
    if extra:
        out.append(f"   also asserted: {', '.join(str(x) for x in extra)}")
    if d.get("explanation"):
        out.append(f"   judge: {str(d['explanation'])[:200]}")
    return "\n".join(out)


def dismiss_finding(conn: sqlite3.Connection, audit_id: int, reason: str) -> dict:
    """The other verdict: this finding is not real rot. Reason is recorded
    (a dismissal without a why is future confusion); the pair_key stays in
    the dedup set so the same finding never refiles."""
    row = conn.execute(
        "SELECT id, human_decision, machine_decision FROM audit_log WHERE id = ?",
        (audit_id,)).fetchone()
    if row is None:
        return {"ok": False, "error": f"no audit finding #{audit_id}"}
    if row["human_decision"]:
        return {"ok": False, "error": f"finding #{audit_id} already decided: "
                                      f"{row['human_decision']}"}
    if row["machine_decision"]:
        return {"ok": False, "error": f"finding #{audit_id} already machine-"
                                      f"closed: {row['machine_decision']}"}
    conn.execute(
        "UPDATE audit_log SET human_decision = 'dismissed', resolved_at = ?, "
        "details = json_set(details, '$.dismiss_reason', ?) WHERE id = ?",
        (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), reason, audit_id))
    conn.commit()
    return {"ok": True, "audit_id": audit_id}


def resolve_pair(conn: sqlite3.Connection, audit_id: int, truth: str,
                 note: str = "") -> dict:
    """Close a pairing finding with the human's answer. Three writes, all
    with provenance: the finding is marked resolved:<truth>, a correction
    cube (source 'human-resolution', approved, confidence 1.0) enters the
    store so retrieval serves the answer instead of the argument, and the
    resolution feeds the never-twice guard in find_conflicts."""
    row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (audit_id,)).fetchone()
    if row is None:
        return {"ok": False, "error": f"no audit finding #{audit_id}"}
    try:
        d = json.loads(row["details"])
    except (json.JSONDecodeError, TypeError):
        d = {}
    if row["audit_type"] != "factual" or "pair_key" not in d:
        return {"ok": False, "error": f"finding #{audit_id} is not a pairing finding"}
    if row["human_decision"]:
        return {"ok": False, "error": f"finding #{audit_id} already decided: "
                                      f"{row['human_decision']}"}
    if row["machine_decision"]:
        return {"ok": False, "error": f"finding #{audit_id} already machine-"
                                      f"closed: {row['machine_decision']}"}
    if truth not in d.get("all_dates", d.get("dates", [])):
        return {"ok": False,
                "error": f"truth {truth!r} is not one of the asserted dates "
                         f"{d.get('all_dates', d.get('dates'))} — if none of them "
                         f"is true, dismiss the finding and fix the sources"}

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    conn.execute(
        "UPDATE audit_log SET human_decision = ?, resolved_at = ? WHERE id = ?",
        (f"resolved:{truth}", now, audit_id))

    wrong = [x for x in d.get("dates", []) if x != truth]
    from helicon.models import HeliconCube
    from helicon.scanner import make_id, content_hash as _hash
    content = (f"{d['person'].title()}'s {d['topic']} is {truth} "
               f"(human resolution of finding #{audit_id}, {now[:10]}). "
               f"The competing value(s) {', '.join(wrong)} are wrong; any memory "
               f"asserting them predates this resolution."
               + (f" Note: {note}" if note else ""))
    cube = HeliconCube(
        id=make_id(), source="human-resolution", source_ref=f"audit:{audit_id}",
        type="decision", title=f"Resolved: {d['person'].title()} {d['topic']} = {truth}",
        content=content, summary="", content_hash=_hash(content),
        created_at=now, valid_from=now, last_reinforced=now,
        confidence=1.0, review_status="approved",
    )
    from helicon.db import insert_cube
    insert_cube(conn, cube)

    # Retire the losing cubes: any live cube asserting a ruled-out value for
    # this (person, topic) is now known-wrong, so mark it 'superseded' — that
    # drops it from both retrieval branches (search_cubes + semantic) and from
    # find_conflicts' live set. This is the "can't be retrieved" half of
    # never-twice; the "can't re-file" half is the guard in find_conflicts, and
    # NEW memory re-asserting a wrong value AFTER now still re-alarms there.
    truth_iv = _parse_label(truth)
    person_l, topic_l = d["person"].lower(), d["topic"]
    like = " OR ".join("lower(content) LIKE ?" for _ in TOPIC_KEYWORDS)
    rows = conn.execute(
        f"SELECT id, title, content FROM helicon_cubes "
        f"WHERE review_status IN ('pending', 'revised', 'approved') "
        f"AND merged_into IS NULL AND id != ? AND ({like})",
        [cube.id] + [f"%{t}%" for t in TOPIC_KEYWORDS]).fetchall()
    retired = []
    for r in rows:
        ivs = {a["interval"] for a in extract_assertions(r["content"], r["title"])
               if a["person"].lower() == person_l and a["topic"] == topic_l}
        # retire a cube that takes the WRONG side and not the truth; a cube
        # quoting BOTH values documents the conflict — leave it retrievable
        if ivs and truth_iv not in ivs and any(_disjoint(iv, truth_iv) for iv in ivs):
            conn.execute("UPDATE helicon_cubes SET review_status = 'superseded', "
                         "last_reinforced = ? WHERE id = ?", (now, r["id"]))
            retired.append(r["id"])
    conn.commit()
    return {"ok": True, "audit_id": audit_id, "truth": truth,
            "correction_cube": cube.id, "wrong_dates": wrong, "retired": retired,
            "person": d["person"], "topic": d["topic"]}


def _existing_pair_keys(conn: sqlite3.Connection) -> tuple[set[str], set[str]]:
    """(exact pair_keys ever filed, 'person|topic' of still-OPEN findings).
    Exact keys stop the same finding refiling forever (incl. dismissed FPs);
    the open set stops a sibling finding for the same fact when the best
    pair's dates shift while the first finding is still undecided — one open
    finding per fact, not one per date combination.

    'Open' means neither a human nor the valuation gate has closed it.
    Machine-retired findings must not suppress a live re-alarm forever.
    """
    exact, open_facts = set(), set()
    for row in conn.execute(
        "SELECT details, human_decision, machine_decision FROM audit_log "
        "WHERE audit_type = 'factual' AND details LIKE '%pair_key%'"
    ):
        try:
            d = json.loads(row["details"])
        except (json.JSONDecodeError, TypeError):
            continue
        if d.get("pair_key"):
            # Human rulings (incl. dismiss) permanently dedup this exact key.
            # Machine-only retirement must not — the conflict can return.
            if (row["machine_decision"] is None
                    or row["human_decision"] is not None):
                exact.add(d["pair_key"])
        if (row["human_decision"] is None
                and row["machine_decision"] is None
                and d.get("person") and d.get("topic")):
            open_facts.add(f"{d['person']}|{d['topic']}")
    return exact, open_facts


def _cohen_kappa(p: dict) -> float | None:
    """Cohen's κ for the two-judge binary panel (agreement beyond chance)."""
    n = sum(p.values())
    if n == 0:
        return None
    po = (p["both_yes"] + p["both_no"]) / n
    p1_yes = (p["both_yes"] + p["qwen_only"]) / n
    p2_yes = (p["both_yes"] + p["judge2_only"]) / n
    pe = p1_yes * p2_yes + (1 - p1_yes) * (1 - p2_yes)
    return 1.0 if pe >= 1 else round((po - pe) / (1 - pe), 3)


def pair_scan(conn: sqlite3.Connection, client=None, model: str = "qwen3.6-plus",
              judge2_model: str = "deepseek-v4-flash") -> dict:
    """Find cross-source conflicts and file each new one as a factual audit
    finding. With a Qwen client, every candidate pair is confirmed by
    detect_contradictions before filing (the judge can veto the selector);
    without one, the disjoint-interval mismatch is the verdict. Idempotent:
    a pair_key already in audit_log is never filed twice."""
    conflicts = find_conflicts(conn)
    existing, open_facts = _existing_pair_keys(conn)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    filed, rejected, skipped = [], [], []
    # Two-judge panel confusion counts, for Cohen's κ across the scan.
    panel = {"both_yes": 0, "both_no": 0, "qwen_only": 0, "judge2_only": 0}

    for c in conflicts:
        if (c["pair_key"] in existing
                or f"{c['person']}|{c['topic']}" in open_facts):
            skipped.append(c["pair_key"])
            continue
        (date_a, rep_a), (date_b, rep_b) = sorted(c["representatives"].items())
        severity = "critical"
        explanation = (f"'{rep_a['line'][:80]}' vs '{rep_b['line'][:80]}' — "
                       f"same {c['topic']} for {c['person'].title()}, "
                       f"dates cannot both be true")
        judged_by = "deterministic"
        if client is not None:
            from helicon.qwen import detect_contradictions
            row_a = conn.execute("SELECT content FROM helicon_cubes WHERE id = ?",
                                 (rep_a["id"],)).fetchone()
            row_b = conn.execute("SELECT content FROM helicon_cubes WHERE id = ?",
                                 (rep_b["id"],)).fetchone()
            # A representative without a DB row (synthetic resolution marker
            # fallback) has nothing for the judges to read — keep the
            # deterministic verdict instead of crashing the watch tick.
            if row_a is not None and row_b is not None:
                v1 = detect_contradictions(client, row_a["content"], row_b["content"], model=model)
                # Second judge from a DIFFERENT model family (two Qwens share
                # failure modes and inflate agreement). The court sits with two
                # independent judges; a split verdict is escalated to the human.
                v2 = (detect_contradictions(client, row_a["content"], row_b["content"], model=judge2_model)
                      if judge2_model else None)
                c1 = bool(v1.get("contradicts")) if v1 else None
                c2 = bool(v2.get("contradicts")) if v2 else None
                if c1 is not None and c2 is not None:
                    if c1 and c2:
                        panel["both_yes"] += 1
                    elif not c1 and not c2:
                        panel["both_no"] += 1
                    elif c1 and not c2:
                        panel["qwen_only"] += 1
                    else:
                        panel["judge2_only"] += 1
                    if c1 == c2:
                        if not c1:
                            rejected.append(c["pair_key"])
                            continue
                        judged_by = f"consensus ({model} + {judge2_model})"
                        severity = v1.get("severity", severity)
                        explanation = v1.get("explanation", explanation)
                    else:
                        judged_by = f"split_decision ({model} vs {judge2_model})"
                        severity = "warning"
                        explanation = ("Judges disagree — "
                                       f"{model}: {(v1 or {}).get('explanation', '')[:70]} | "
                                       f"{judge2_model}: {(v2 or {}).get('explanation', '')[:70]}")
                elif c1 is not None:
                    if not c1:
                        rejected.append(c["pair_key"])
                        continue
                    judged_by = model
                    severity = v1.get("severity", severity)
                    explanation = v1.get("explanation", explanation)
                # both judges failed -> keep the deterministic verdict

        finding = AuditResult(
            audit_type="factual",
            target_type="cube",
            target_id=rep_a["id"],
            finding=(f"Cross-source contradiction: {c['person'].title()} {c['topic']} — "
                     f"{date_a} ({rep_a['scope']}, {_memories(c['support'][date_a])}) vs "
                     f"{date_b} ({rep_b['scope']}, {_memories(c['support'][date_b])})"),
            severity=severity,
            proposed_action="flag",
            details={
                "pair_key": c["pair_key"],
                "person": c["person"], "topic": c["topic"],
                "dates": c["dates"], "all_dates": c["all_dates"],
                "support": c["support"],
                "cube_a": rep_a["id"], "cube_b": rep_b["id"],
                "title_a": rep_a["title"], "title_b": rep_b["title"],
                "line_a": rep_a["line"], "line_b": rep_b["line"],
                "scope_a": rep_a["scope"], "scope_b": rep_b["scope"],
                "scopes": c["scopes"], "cube_count": c["cube_count"],
                "explanation": explanation,
                "judged_by": judged_by,
            },
            audited_at=now,
        )
        insert_audit(conn, finding)
        filed.append({"pair_key": c["pair_key"], "finding": finding.finding,
                      "severity": severity, "judged_by": judged_by})
    conn.commit()

    return {
        "conflicts_found": len(conflicts),
        "filed": filed,
        "already_filed": skipped,
        "judge_rejected": rejected,
        "panel": panel,
        "kappa": _cohen_kappa(panel),
        "judge2_model": judge2_model,
        "split_decisions": [f for f in filed if str(f.get("judged_by", "")).startswith("split")],
    }
