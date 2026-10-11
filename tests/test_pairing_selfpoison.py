"""#361: the ruling loop poisoned itself.

Recording a ruling manufactured the evidence that the ruling had been violated.
`resolve --list` showed "Casey wedding: 03-14..03-22 vs 04-11..04-13" as a LIVE
critical contradiction — a fact ruled on May 11 (#322) and already compiled into
GOLDEN_RULES. The source of the "wrong" side was the correction itself:

    #322 Casey wedding = **04-11..04-13** (the "Mar 14-22" cube was mislabeled)

Two independent faults, both proven live before these tests were written:

1. The parser could not read `04-11..04-13`, which is HELICON'S OWN canonical
   interval label (_iv_label) — the format every ruling, resolution and
   GOLDEN_RULE is written in. Resolutions are parsed by _parse_label, which
   understands `..`; cube content was parsed only by the prose patterns. Two
   parsers, two grammars, one format. So the line asserted ONLY the dead value
   it quoted, and never the truth it stated.

2. The never-twice guard re-alarms on any post-resolution cube asserting the
   dead value. The memory that RECORDS a ruling is written moments after it and
   must name the dead value to say what was wrong. So every ruling planted a
   future false alarm, inflating R1 forever and discrediting the one exam that
   has to stay trustworthy.

The guard itself must survive: real rot coming back MUST still re-alarm. That is
what test_the_never_twice_guard_still_fires_on_real_rot exists to prove.
"""
import pytest

from helicon.db import init_db, insert_audit, insert_cube
from helicon.models import AuditResult, HeliconCube
from helicon.pairing import _intervals_in, extract_assertions, find_conflicts

RESOLVED_AT = "2026-07-11T12:00:00"
AFTER = "2026-07-11T16:49:16"      # the correction, written just after the ruling
BEFORE = "2026-07-01T09:00:00"


def _cube(conn, cid, title, content, created_at):
    insert_cube(conn, HeliconCube(
        id=cid, source="claude-code", source_ref=f"memory_{cid}.md", type="memory",
        title=title, content=content, content_hash=cid,
        created_at=created_at, valid_from=created_at, review_status="approved"))
    conn.commit()


@pytest.fixture
def ruled(tmp_path):
    """A store where Casey's wedding was ruled 04-11..04-13 on May 11."""
    conn = init_db(str(tmp_path / "helicon.db"))
    insert_audit(conn, AuditResult(
        audit_type="factual", target_type="cube", target_id="gc_x",
        finding="Cross-source contradiction: Casey wedding",
        severity="critical", human_decision="resolved:04-11..04-13",
        details={"pair_key": "casey|wedding", "person": "casey", "topic": "wedding",
                 "dates": ["03-14..03-22", "04-11..04-13"]},
        audited_at="2026-07-11", resolved_at=RESOLVED_AT))
    insert_cube(conn, HeliconCube(
        id="gc_resolution", source="human-resolution", source_ref="audit:1",
        type="memory", title="Resolved: Casey wedding = 04-11..04-13",
        content="Resolved: Casey wedding = 04-11..04-13", content_hash="res",
        created_at=RESOLVED_AT, valid_from=RESOLVED_AT, review_status="approved"))
    conn.commit()
    return conn


def test_the_canonical_interval_label_is_readable_by_its_own_parser():
    """_iv_label emits `04-11..04-13`. The parser returned [] for it, so a
    correction stating the truth in canonical form asserted nothing at all."""
    assert _intervals_in("04-11..04-13") == [("04-11", "04-13")]
    assert _intervals_in("**04-11..04-13**") == [("04-11", "04-13")]


@pytest.mark.parametrize("text", [
    "status_2026-07-11.md",   # a filename, not a date range
    "v12-34..56-78",          # impossible months/days
    "scored 3-1",
])
def test_reading_the_canonical_form_did_not_invent_dates(text):
    """A bare MM-DD pattern would match filenames and version numbers all over
    the vault. Only the distinctive `..` form is read."""
    assert _intervals_in(text) == []


def test_a_correction_line_asserts_the_truth_not_only_the_corpse():
    line = '- #322 Casey wedding = **04-11..04-13** (the "Mar 14-22" cube was mislabeled)'
    ivs = {a["interval"] for a in extract_assertions(line)}
    assert ("04-11", "04-13") in ivs, "the truth the line states was never read"
    assert ("03-14", "03-22") in ivs, "the corpse it quotes should still be seen"


def test_recording_a_ruling_does_not_manufacture_a_finding(ruled):
    """THE bug: the correction cube is dated after the resolution and names the
    dead value, so the never-twice guard read the ruling as its own violation."""
    _cube(ruled, "gc_correction", "status_2026-07-11: orchestrator run",
          '- #322 Casey wedding = **04-11..04-13** (the "Mar 14-22" cube was '
          'the Italy trip mislabeled)', AFTER)
    conflicts = find_conflicts(ruled)
    assert conflicts == [], f"ruling planted a false finding: {conflicts}"


def test_one_line_about_two_trips_is_not_a_contradiction(ruled):
    """Keyword proximity, not grammar: 'Italy (Mar 14-22) and Casey's wedding,
    Sweden (Apr 11-13)' is one line about two trips, and the date window grabs
    both. It asserts the truth too, so it is not a resurfacing."""
    _cube(ruled, "gc_flights", "Flights",
          "- **Flights to book:** Italy (Mar 14-22) and Casey's wedding, "
          "Sweden (Apr 11-13)", AFTER)
    assert find_conflicts(ruled) == []


def test_the_never_twice_guard_still_fires_on_real_rot(ruled):
    """The guard must survive the fix. A cube written AFTER the ruling that
    asserts the dead value and does NOT state the truth is the rot genuinely
    coming back, and it has to re-alarm. If this test ever passes empty, the fix
    above has quietly disabled the never-twice guarantee."""
    _cube(ruled, "gc_relapse", "Casey wedding plan",
          "Casey wedding is Mar 14-22, booking flights now.", AFTER)
    conflicts = find_conflicts(ruled)
    assert conflicts, "real rot resurfaced and the guard stayed silent"
    d = conflicts[0].get("details", conflicts[0])
    assert d["topic"] == "wedding"
    assert "03-14..03-22" in d["dates"]


def test_rot_that_predates_the_ruling_stays_closed(ruled):
    """A ruling closes what came before it. Only NEW contradicting memory
    re-opens the question."""
    _cube(ruled, "gc_old", "old note",
          "Casey wedding Mar 14-22 in Italy.", BEFORE)
    assert find_conflicts(ruled) == []


def test_real_rot_cannot_hide_in_a_doc_that_names_the_truth_elsewhere(ruled):
    """The hole the first version of this fix opened. Excluding a whole CUBE
    that mentions the truth let real rot hide on any other line of the same
    document — trading a false alarm for a missed one, which is strictly worse.
    A correction is a property of a LINE, not of a file."""
    body = ("Casey wedding is 04-11..04-13 per the ruling.\n"
            + "filler\n" * 88
            + "Booking flights: Casey wedding Mar 14-22, confirm with the venue.\n")
    _cube(ruled, "gc_long", "status", body, AFTER)
    conflicts = find_conflicts(ruled)
    assert conflicts, "rot re-asserted on line 90 hid behind the truth on line 1"
    d = conflicts[0].get("details", conflicts[0])
    assert "03-14..03-22" in d["dates"]


@pytest.mark.parametrize("order", ["ruling-first", "rot-first"])
def test_real_rot_is_caught_whichever_order_the_doc_is_written_in(ruled, order):
    """D1, found by adversarial review. The (cube, line) fix was defeated by a
    dedupe two functions away: extract_assertions kept the FIRST occurrence of
    (person, topic, interval), so when the ruling line came first, the real
    re-assertion further down inherited the CORRECTION's line and was excluded
    with it. Order-dependent, and the natural order was the broken one — a status
    doc records the ruling near the top and plans further down.

    The earlier test passed only because its truth line did not quote the corpse,
    which is the one shape with no dedupe collision. The canonical correction
    format — the entire subject of this fix — always quotes both poles.
    """
    ruling = ('- #322 Casey wedding = **04-11..04-13** (the "Mar 14-22" cube was '
              'the Italy trip mislabeled)')
    rot = "- Casey wedding is Mar 14-22, booking flights now."
    body = (f"{ruling}\nfiller\n{rot}\n" if order == "ruling-first"
            else f"{rot}\nfiller\n{ruling}\n")
    _cube(ruled, "gc_doc", "status", body, AFTER)
    conflicts = find_conflicts(ruled)
    assert conflicts, f"real rot went unreported ({order})"
    assert "03-14..03-22" in conflicts[0].get("details", conflicts[0])["dates"]


def test_the_correction_alone_still_manufactures_nothing(ruled):
    """The other side of the same coin: fixing the order dependence must not
    bring #361 back."""
    _cube(ruled, "gc_corr", "status",
          '- #322 Casey wedding = **04-11..04-13** (the "Mar 14-22" cube was '
          'the Italy trip mislabeled)\n', AFTER)
    assert find_conflicts(ruled) == []
