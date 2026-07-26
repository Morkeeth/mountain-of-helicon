"""R1 pair selector: deterministic cross-source contradiction pairing.

The class under test (ROT.md R1): two source files assert different dates for
the same person's event; the store serves both as truth. The selector must
find that pair unprompted, treat overlapping ranges as agreement, ignore
questions, never pair a file with itself, and file each finding exactly once.
"""
import pytest

from helicon.db import init_db, insert_audit, insert_cube
from helicon.models import ConnectorResult
from helicon.pairing import (
    _disjoint, _intervals_in, extract_assertions, find_conflicts, pair_scan,
)
from helicon.rot import run_rot_exam
from helicon.scanner import result_to_cube


def _cube(conn, content, ref, source="obsidian", status="pending",
          created_at="2026-07-01T00:00:00"):
    r = ConnectorResult(source=source, source_ref=ref, type="memory",
                        title=ref, content=content, created_at=created_at)
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    if status != "pending":
        conn.execute("UPDATE helicon_cubes SET review_status=? WHERE id=?",
                     (status, cube.id))
    conn.commit()
    return cube.id


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "helicon.db"))


# --- extraction ---------------------------------------------------------

def test_interval_formats_normalize():
    assert _intervals_in("Jul 13") == [("07-13", "07-13")]
    assert _intervals_in("July 13") == [("07-13", "07-13")]
    assert _intervals_in("13 Jul") == [("07-13", "07-13")]
    assert _intervals_in("2026-07-13") == [("07-13", "07-13")]
    assert _intervals_in("Sep 11-13") == [("09-11", "09-13")]


def test_disjoint_vs_overlap():
    assert _disjoint(("07-13", "07-13"), ("07-18", "07-18"))
    assert not _disjoint(("09-11", "09-13"), ("09-13", "09-13"))  # range agrees


def test_assertion_needs_person_topic_and_date_on_one_line():
    got = extract_assertions("Lea birthday: Jul 13 (order gift)")
    assert [(a["person"], a["topic"], a["interval"]) for a in got] == [
        ("Lea", "birthday", ("07-13", "07-13"))]
    assert extract_assertions("standup moved to Jul 13") == []       # no topic
    assert extract_assertions("her birthday is coming up soon") == []  # no date


def test_question_is_not_an_assertion():
    assert extract_assertions("| Nov 13-15 | Trip back for Lea's birthday? |") == []


def test_places_are_not_people():
    # live false positive Jul 5: 'Lea's birthday (Paris)' filed 'Paris birthday'
    got = extract_assertions("| Jul 18 | Lea's birthday (Paris) | plan dinner |")
    assert {a["person"] for a in got} == {"Lea"}
    got = extract_assertions("Itai's wedding in Lisbon, Sep 13")
    assert {a["person"] for a in got} == {"Itai"}
    got = extract_assertions("Trip to Sweden for Lea's birthday, Nov 13")
    assert "Sweden" not in {a["person"] for a in got}


def test_person_window_drops_far_capitalized_words():
    # 'Lisbon' sits outside PERSON_WINDOW of 'Wedding' — a place name in the
    # same sentence must not become the subject of the event.
    got = extract_assertions("~~ETHGlobal Lisbon~~ -- DROPPED early. Wedding conflict Jul 24-26.")
    assert all(a["person"] != "Lisbon" for a in got)


def test_gift_and_deadline_dates_are_not_the_event_date():
    # Regression for false positive #279: the selector must not read a
    # gift/order/deadline date as the event's own date.
    # (1) keyword heads a shopping item -> asserts no event date at all
    assert extract_assertions("| Birthday gift | Lea (Jul 13) | order this week |") == []
    assert extract_assertions("Wedding present for Itai -- arrives Sep 13") == []
    # (2) a date behind a deadline/logistics cue is dropped; event date stays
    got = extract_assertions("| Jul 18 | Lea's birthday (Paris) | plan gift before Jul 13 |")
    assert [a["interval"][0] for a in got] == ["07-18"]      # not 07-13
    got = extract_assertions("| Lea birthday (Paris) | Jul 18 | gift by Jul 13 |")
    assert [a["interval"][0] for a in got] == ["07-18"]
    # (3) a flat claim ("birthday: Jul 13") is still a real assertion, not logistics
    got = extract_assertions("Lea birthday: Jul 13")
    assert [(a["person"], a["interval"][0]) for a in got] == [("Lea", "07-13")]


def test_gift_date_and_real_birthday_do_not_conflict(conn):
    # The live #279 shape: one file has the gift errand, another the birthday.
    # A gift date is not a competing birthday, so this is NOT a contradiction.
    _cube(conn, "| Birthday gift | Lea (Jul 13) | order this week |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    assert find_conflicts(conn) == []


# --- pairing ------------------------------------------------------------

def test_cross_file_disjoint_dates_conflict(conn):
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    conflicts = find_conflicts(conn)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert (c["person"], c["topic"]) == ("lea", "birthday")
    assert c["dates"] == ["07-13", "07-18"]
    reps = c["representatives"]
    assert reps["07-13"]["scope"] != reps["07-18"]["scope"]


def test_same_file_disagreeing_with_itself_is_not_cross_source(conn):
    _cube(conn, "Lea birthday: Jul 13. Correction: Lea birthday: Jul 18.", "one-file.md")
    assert find_conflicts(conn) == []


def test_overlapping_range_is_agreement_not_conflict(conn):
    _cube(conn, "| Sweden Sep 11-13 | Itai's wedding | book flights |", "mindmap.md")
    _cube(conn, "Itai's wedding (Sep 13), fly out Friday", "trips.md")
    assert find_conflicts(conn) == []


def test_retired_memory_cannot_raise_a_conflict(conn):
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md",
          status="superseded")
    assert find_conflicts(conn) == []  # battery Freshness owns retired cubes


def test_pair_scan_files_once_and_is_idempotent(conn):
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")

    first = pair_scan(conn)  # no client: date mismatch is the verdict
    assert len(first["filed"]) == 1
    assert first["filed"][0]["severity"] == "critical"
    assert "Lea birthday" in first["filed"][0]["finding"]

    second = pair_scan(conn)
    assert second["filed"] == []
    assert second["already_filed"] == [first["filed"][0]["pair_key"]]

    open_rows = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE audit_type='factual' "
        "AND details LIKE '%pair_key%'").fetchone()[0]
    assert open_rows == 1


# --- resolve: the fix loop ----------------------------------------------

def _filed_finding_id(conn):
    return conn.execute(
        "SELECT id FROM audit_log WHERE audit_type='factual' "
        "AND details LIKE '%pair_key%' ORDER BY id DESC LIMIT 1").fetchone()["id"]


def test_resolve_closes_finding_and_files_correction(conn):
    from helicon.pairing import resolve_pair
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    pair_scan(conn)
    fid = _filed_finding_id(conn)

    res = resolve_pair(conn, fid, "07-18", note="Oscar confirmed")
    assert res["ok"] and res["wrong_dates"] == ["07-13"]

    row = conn.execute("SELECT human_decision, resolved_at FROM audit_log "
                       "WHERE id=?", (fid,)).fetchone()
    assert row["human_decision"] == "resolved:07-18" and row["resolved_at"]

    cube = conn.execute("SELECT * FROM helicon_cubes WHERE id=?",
                        (res["correction_cube"],)).fetchone()
    assert cube["review_status"] == "approved"
    assert cube["source"] == "human-resolution"
    assert "07-18" in cube["content"] and "07-13" in cube["content"]

    # the conflict is closed: selector stays quiet, scan refiles nothing
    assert find_conflicts(conn) == []
    assert pair_scan(conn)["filed"] == []


def test_ruled_out_value_can_neither_be_retrieved_nor_refiled(conn):
    """The atom of the 'verifier with a memory' thesis: a claim you have RULED
    ON cannot come back. After resolving Lea's birthday to 07-18, the wrong
    value 07-13 must be (a) not retrievable and (b) not re-filed on the next
    scan. (a) is the inch resolve_pair was missing — it filed the correction
    cube but left the losing cube live and retrievable, so retrieval could
    still serve the value the human already ruled out."""
    from helicon.pairing import resolve_pair
    from helicon.db import rebuild_fts, search_cubes
    wrong_id = _cube(conn, "Lea birthday Jul 13, from her list", "mindmap.md")
    _cube(conn, "Jul 18 Lea birthday (Paris), plan dinner", "summer-trips.md")
    pair_scan(conn)
    res = resolve_pair(conn, _filed_finding_id(conn), "07-18")
    assert res["ok"]

    rebuild_fts(conn)
    ids = {h["id"] for h in search_cubes(conn, "Lea birthday")}
    assert wrong_id not in ids, "ruled-out value must not be retrievable"
    assert res["correction_cube"] in ids, "the truth must be served"
    assert wrong_id in res.get("retired", []), "resolve must retire the losing cube"
    assert pair_scan(conn)["filed"] == [], "a ruled-on claim must not re-file"


def test_resolve_rejects_bad_input(conn):
    from helicon.pairing import resolve_pair
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    pair_scan(conn)
    fid = _filed_finding_id(conn)
    assert not resolve_pair(conn, 99999, "07-18")["ok"]        # no such finding
    assert not resolve_pair(conn, fid, "12-25")["ok"]          # not an asserted date
    assert resolve_pair(conn, fid, "07-18")["ok"]
    assert not resolve_pair(conn, fid, "07-18")["ok"]          # already decided


def test_never_twice_ruled_out_date_resurfacing_realarm(conn):
    from helicon.pairing import resolve_pair
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    pair_scan(conn)
    resolve_pair(conn, _filed_finding_id(conn), "07-18")
    assert find_conflicts(conn) == []

    # NEW memory (written after the resolution) asserts the ruled-out date
    _cube(conn, "reminder: Lea birthday Jul 13, buy the gift", "fresh-note.md",
          created_at="2027-01-01T00:00:00")
    conflicts = find_conflicts(conn)
    assert len(conflicts) == 1
    assert conflicts[0]["resurfaced"] is True
    assert "07-13" in conflicts[0]["dates"]
    # and it files as a NEW finding (different pair_key), not grandfathered
    assert len(pair_scan(conn)["filed"]) == 1


def test_pre_resolution_stale_cubes_stay_closed(conn):
    from helicon.pairing import resolve_pair
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    _cube(conn, "note from May: Lea birthday Jul 13", "old-note.md",
          created_at="2026-05-01T00:00:00")
    pair_scan(conn)
    resolve_pair(conn, _filed_finding_id(conn), "07-18")
    # the OLD wrong cubes predate the resolution: closed means closed
    assert find_conflicts(conn) == []


# --- audit regressions (Jul 5 adversarial review) ------------------------

def test_resurfaced_pair_scan_with_judge_does_not_crash(conn, monkeypatch):
    """P0 from the audit: with a Qwen client, the resurfaced conflict's truth
    side used a synthetic representative with no DB row -> TypeError inside
    pair_scan, killing helicon report and every watch cron tick the moment
    the never-twice guard fired. The truth side now speaks through the real
    correction cube; a missing row skips the judge, never crashes."""
    from helicon import qwen
    from helicon.pairing import resolve_pair
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    pair_scan(conn)
    resolve_pair(conn, _filed_finding_id(conn), "07-18")
    _cube(conn, "reminder: Lea birthday Jul 13", "fresh.md",
          created_at="2027-01-01T00:00:00")

    seen = {}
    def fake_judge(client, a, b, model="m", audit_context=""):
        seen["contents"] = (a, b)
        return {"contradicts": True, "severity": "critical", "explanation": "x"}
    monkeypatch.setattr(qwen, "detect_contradictions", fake_judge)

    res = pair_scan(conn, client=object())  # crashed before the fix
    assert len(res["filed"]) == 1
    # the judge read the real correction cube, not a synthetic marker
    assert any("human resolution" in c or "07-18" in c for c in seen["contents"])


def test_realarm_fires_again_after_second_resolution(conn):
    """P1: the resurfaced pair_key was constant, so never-twice decayed into
    never-only-once-more — a third wave of the wrong date went unfiled and
    unresolvable. The key now carries the resolution it violates."""
    from helicon.pairing import resolve_pair
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    pair_scan(conn)
    resolve_pair(conn, _filed_finding_id(conn), "07-18")

    _cube(conn, "reminder: Lea birthday Jul 13", "wave2.md",
          created_at="2027-01-01T00:00:00")
    assert len(pair_scan(conn)["filed"]) == 1          # first re-alarm
    resolve_pair(conn, _filed_finding_id(conn), "07-18")

    _cube(conn, "note: Lea birthday is Jul 13, order cake", "wave3.md",
          created_at="2027-02-01T00:00:00")
    assert len(pair_scan(conn)["filed"]) == 1          # second re-alarm, was 0


def test_best_pair_shift_does_not_file_orphan_sibling(conn):
    """P1: when the best-supported pair's dates shift while the first finding
    is open, a sibling finding for the same fact must not pile up — one open
    finding per (person, topic)."""
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    assert len(pair_scan(conn)["filed"]) == 1
    # a third date gains majority support -> best pair changes
    for i, ref in enumerate(["a.md", "b.md", "c.md"]):
        _cube(conn, f"Lea birthday: Jul 20 (v{i})", ref)
    res = pair_scan(conn)
    assert res["filed"] == []  # skipped: fact already has an open finding
    open_rows = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE audit_type='factual' "
        "AND details LIKE '%pair_key%' AND human_decision IS NULL").fetchone()[0]
    assert open_rows == 1


def test_never_twice_respects_timezone_offsets(conn):
    """P1: created_at vs resolved_at compared as raw strings; a +02:00 stamp
    from before the resolution compared as after -> false re-alarm."""
    from helicon.pairing import resolve_pair
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    pair_scan(conn)
    resolve_pair(conn, _filed_finding_id(conn), "07-18")
    row = conn.execute("SELECT resolved_at FROM audit_log WHERE "
                       "human_decision='resolved:07-18'").fetchone()
    # stamp is +02:00 local, 90 min BEFORE the resolution in UTC
    from datetime import datetime, timedelta, timezone
    res_utc = datetime.fromisoformat(row["resolved_at"])
    local = (res_utc - timedelta(minutes=90)).replace(
        tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=2)))
    _cube(conn, "old draft: Lea birthday Jul 13", "predates.md",
          created_at=local.isoformat())
    assert find_conflicts(conn) == []  # pre-resolution memory stays closed


def test_meta_cube_quoting_both_dates_is_not_support(conn):
    """Receipt-verification finding: 5 live cubes sat on BOTH sides of the
    Lea pair, inflating support. A cube quoting both dates documents the
    conflict; it doesn't take a side."""
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "trips.md")
    _cube(conn, "CONFLICT NOTE: Lea birthday Jul 13 vs Jul 18, confirm",
          "meta.md")
    c = find_conflicts(conn)[0]
    assert c["support"] == {"07-13": 1, "07-18": 1}  # meta cube counts neither
    # and a "conflict" made ONLY of meta cubes is no conflict at all
    conn.execute("UPDATE helicon_cubes SET review_status='killed' "
                 "WHERE source_ref IN ('mindmap.md', 'trips.md')")
    conn.commit()
    assert find_conflicts(conn) == []


def test_machine_retired_pair_does_not_suppress_live_realarm(conn):
    """A valuation auto-retire must not permanently suppress the same fact.
    Human dismissals still dedup forever; machine-only closure does not."""
    from helicon.pairing import _existing_pair_keys
    import json

    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "trips.md")
    details = json.dumps({
        "pair_key": "lea|birthday|07-13|07-18",
        "person": "lea", "topic": "birthday",
        "dates": ["07-13", "07-18"],
    })
    conn.execute(
        "INSERT INTO audit_log (audit_type, target_type, target_id, finding, "
        "severity, details, audited_at, machine_decision) "
        "VALUES ('factual','cube','x','conflict','critical',?, '2026-07-01', "
        "'auto-retired')",
        (details,))
    conn.commit()
    exact, open_facts = _existing_pair_keys(conn)
    assert "lea|birthday|07-13|07-18" not in exact
    assert "lea|birthday" not in open_facts
    # And the unique index must allow a new pending row with the same pair_key
    conn.execute(
        "INSERT INTO audit_log (audit_type, target_type, target_id, finding, "
        "severity, details, audited_at) "
        "VALUES ('factual','cube','y','conflict again','critical',?, '2026-07-02')",
        (details,))
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE human_decision IS NULL "
        "AND machine_decision IS NULL AND details LIKE '%pair_key%'"
    ).fetchone()[0] == 1


# --- rot exam -----------------------------------------------------------

def test_rot_r1_is_tested_and_finds_the_pair(conn):
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | plan dinner |", "summer-trips.md")
    r1 = next(c for c in run_rot_exam(conn)["checks"] if c["id"] == "R1")
    assert r1["coverage"] == "TESTED"
    assert r1["verdict"] == "ROT FOUND"
    assert "Lea birthday: 07-13 vs 07-18" in r1["receipt"]
