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
    assert _intervals_in("May 13") == [("05-13", "05-13")]
    assert _intervals_in("May 13") == [("05-13", "05-13")]
    assert _intervals_in("13 May") == [("05-13", "05-13")]
    assert _intervals_in("2026-05-13") == [("05-13", "05-13")]
    assert _intervals_in("Apr 11-13") == [("04-11", "04-13")]


def test_disjoint_vs_overlap():
    assert _disjoint(("05-13", "05-13"), ("05-18", "05-18"))
    assert not _disjoint(("04-11", "04-13"), ("04-13", "04-13"))  # range agrees


def test_assertion_needs_person_topic_and_date_on_one_line():
    got = extract_assertions("Avery birthday: May 13 (order gift)")
    assert [(a["person"], a["topic"], a["interval"]) for a in got] == [
        ("Avery", "birthday", ("05-13", "05-13"))]
    assert extract_assertions("standup moved to May 13") == []       # no topic
    assert extract_assertions("her birthday is coming up soon") == []  # no date


def test_question_is_not_an_assertion():
    assert extract_assertions("| Nov 13-15 | Trip back for Avery's birthday? |") == []


def test_places_are_not_people():
    # live false positive Jul 5: 'Avery's birthday (Paris)' filed 'Paris birthday'
    got = extract_assertions("| May 18 | Avery's birthday (Paris) | plan dinner |")
    assert {a["person"] for a in got} == {"Avery"}
    got = extract_assertions("Casey's wedding in Lisbon, Apr 13")
    assert {a["person"] for a in got} == {"Casey"}
    got = extract_assertions("Trip to Sweden for Avery's birthday, Nov 13")
    assert "Sweden" not in {a["person"] for a in got}


def test_person_window_drops_far_capitalized_words():
    # 'Lisbon' sits outside PERSON_WINDOW of 'Wedding' — a place name in the
    # same sentence must not become the subject of the event.
    got = extract_assertions("~~ETHGlobal Lisbon~~ -- DROPPED early. Wedding conflict Jul 24-26.")
    assert all(a["person"] != "Lisbon" for a in got)


# --- pairing ------------------------------------------------------------

def test_cross_file_disjoint_dates_conflict(conn):
    _cube(conn, "| Birthday gift | Avery (May 13) | Order this week |", "mindmap.md")
    _cube(conn, "| May 18 | Avery birthday (Paris) | plan dinner |", "summer-trips.md")
    conflicts = find_conflicts(conn)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert (c["person"], c["topic"]) == ("avery", "birthday")
    assert c["dates"] == ["05-13", "05-18"]
    reps = c["representatives"]
    assert reps["05-13"]["scope"] != reps["05-18"]["scope"]


def test_same_file_disagreeing_with_itself_is_not_cross_source(conn):
    _cube(conn, "Avery birthday: May 13. Correction: Avery birthday: May 18.", "one-file.md")
    assert find_conflicts(conn) == []


def test_overlapping_range_is_agreement_not_conflict(conn):
    _cube(conn, "| Sweden Apr 11-13 | Casey's wedding | book flights |", "mindmap.md")
    _cube(conn, "Casey's wedding (Apr 13), fly out Friday", "trips.md")
    assert find_conflicts(conn) == []


def test_retired_memory_cannot_raise_a_conflict(conn):
    _cube(conn, "| Birthday gift | Avery (May 13) | Order this week |", "mindmap.md")
    _cube(conn, "| May 18 | Avery birthday (Paris) | plan dinner |", "summer-trips.md",
          status="superseded")
    assert find_conflicts(conn) == []  # battery Freshness owns retired cubes


def test_pair_scan_files_once_and_is_idempotent(conn):
    _cube(conn, "| Birthday gift | Avery (May 13) | Order this week |", "mindmap.md")
    _cube(conn, "| May 18 | Avery birthday (Paris) | plan dinner |", "summer-trips.md")

    first = pair_scan(conn)  # no client: date mismatch is the verdict
    assert len(first["filed"]) == 1
    assert first["filed"][0]["severity"] == "critical"
    assert "Avery birthday" in first["filed"][0]["finding"]

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
    _cube(conn, "| Birthday gift | Avery (May 13) | Order this week |", "mindmap.md")
    _cube(conn, "| May 18 | Avery birthday (Paris) | plan dinner |", "summer-trips.md")
    pair_scan(conn)
    fid = _filed_finding_id(conn)

    res = resolve_pair(conn, fid, "05-18", note="Oscar confirmed")
    assert res["ok"] and res["wrong_dates"] == ["05-13"]

    row = conn.execute("SELECT human_decision, resolved_at FROM audit_log "
                       "WHERE id=?", (fid,)).fetchone()
    assert row["human_decision"] == "resolved:05-18" and row["resolved_at"]

    cube = conn.execute("SELECT * FROM helicon_cubes WHERE id=?",
                        (res["correction_cube"],)).fetchone()
    assert cube["review_status"] == "approved"
    assert cube["source"] == "human-resolution"
    assert "05-18" in cube["content"] and "05-13" in cube["content"]

    # the conflict is closed: selector stays quiet, scan refiles nothing
    assert find_conflicts(conn) == []
    assert pair_scan(conn)["filed"] == []


def test_resolve_rejects_bad_input(conn):
    from helicon.pairing import resolve_pair
    _cube(conn, "| Birthday gift | Avery (May 13) | Order this week |", "mindmap.md")
    _cube(conn, "| May 18 | Avery birthday (Paris) | plan dinner |", "summer-trips.md")
    pair_scan(conn)
    fid = _filed_finding_id(conn)
    assert not resolve_pair(conn, 99999, "05-18")["ok"]        # no such finding
    assert not resolve_pair(conn, fid, "12-25")["ok"]          # not an asserted date
    assert resolve_pair(conn, fid, "05-18")["ok"]
    assert not resolve_pair(conn, fid, "05-18")["ok"]          # already decided


def test_never_twice_ruled_out_date_resurfacing_realarm(conn):
    from helicon.pairing import resolve_pair
    _cube(conn, "| Birthday gift | Avery (May 13) | Order this week |", "mindmap.md")
    _cube(conn, "| May 18 | Avery birthday (Paris) | plan dinner |", "summer-trips.md")
    pair_scan(conn)
    resolve_pair(conn, _filed_finding_id(conn), "05-18")
    assert find_conflicts(conn) == []

    # NEW memory (written after the resolution) asserts the ruled-out date
    _cube(conn, "reminder: Avery birthday May 13, buy the gift", "fresh-note.md",
          created_at="2027-01-01T00:00:00")
    conflicts = find_conflicts(conn)
    assert len(conflicts) == 1
    assert conflicts[0]["resurfaced"] is True
    assert "05-13" in conflicts[0]["dates"]
    # and it files as a NEW finding (different pair_key), not grandfathered
    assert len(pair_scan(conn)["filed"]) == 1


def test_pre_resolution_stale_cubes_stay_closed(conn):
    from helicon.pairing import resolve_pair
    _cube(conn, "| Birthday gift | Avery (May 13) | Order this week |", "mindmap.md")
    _cube(conn, "| May 18 | Avery birthday (Paris) | plan dinner |", "summer-trips.md")
    _cube(conn, "note from May: Avery birthday May 13", "old-note.md",
          created_at="2026-05-01T00:00:00")
    pair_scan(conn)
    resolve_pair(conn, _filed_finding_id(conn), "05-18")
    # the OLD wrong cubes predate the resolution: closed means closed
    assert find_conflicts(conn) == []


# --- rot exam -----------------------------------------------------------

def test_rot_r1_is_tested_and_finds_the_pair(conn):
    _cube(conn, "| Birthday gift | Avery (May 13) | Order this week |", "mindmap.md")
    _cube(conn, "| May 18 | Avery birthday (Paris) | plan dinner |", "summer-trips.md")
    r1 = next(c for c in run_rot_exam(conn)["checks"] if c["id"] == "R1")
    assert r1["coverage"] == "TESTED"
    assert r1["verdict"] == "ROT FOUND"
    assert "Avery birthday: 05-13 vs 05-18" in r1["receipt"]
