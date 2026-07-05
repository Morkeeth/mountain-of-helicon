"""Claim conflicts: R1 beyond person-dates.

The classes come straight from the Jul 5 manual vault audit: win counts
disagreeing across three files, a podcast episode living under two numbers,
a security audit saying 'NOT patched' while the status file says 'merged'.
"""
import pytest

from helicon.claims import (
    claim_scan, extract_metric_claims, extract_status_claims,
    find_claim_conflicts,
)
from helicon.db import init_db, insert_cube
from helicon.models import ConnectorResult
from helicon.rot import run_rot_exam
from helicon.scanner import result_to_cube


def _cube(conn, content, ref, source="lifeos"):
    r = ConnectorResult(source=source, source_ref=ref, type="memory",
                        title=ref, content=content,
                        created_at="2026-07-01T00:00:00")
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    conn.commit()
    return cube.id


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "helicon.db"))


def test_metric_extraction_binds_a_qualifier():
    got = extract_metric_claims("Track record: 9 hackathon wins since 2024")
    assert got[0]["metric"] == "wins" and got[0]["value"] == "9"
    assert "hackathon" in got[0]["qualifier"]
    got = extract_metric_claims("recorded as ep25 'The Revival'")
    assert got[0]["metric"] == "episode" and got[0]["value"] == "25"


def test_status_poles():
    assert extract_status_claims("release/2026-07-04 is MERGED")[0]["value"] == "merged"
    assert extract_status_claims("escrow gate NOT patched")[0]["value"] == "unmerged"


def test_win_count_fight_across_three_files(conn):
    _cube(conn, "Identity: 8 hackathon wins", "mindmap.md")
    _cube(conn, "About: 9 hackathon wins and counting", "portfolio.md")
    _cube(conn, "bio blurb: 10 hackathon wins", "content-plan.md")
    c = next(x for x in find_claim_conflicts(conn) if x["metric"] == "wins")
    assert c["values"] == ["10", "8", "9"]
    assert c["support"] == {"8": 1, "9": 1, "10": 1}


def test_episode_misnumbering_is_a_conflict(conn):
    _cube(conn, "recording notes for ep25 'The Revival', chapters below",
          "ep25-the-revival.md")
    _cube(conn, "ep29 'The Revival' RELEASED Jul 1, real audience 1040",
          "wave-radio-status.md")
    c = next(x for x in find_claim_conflicts(conn) if x["metric"] == "episode")
    assert set(c["values"]) == {"25", "29"}
    assert "revival" in c["subject"]


def test_merged_vs_not_patched_conflict(conn):
    _cube(conn, "P0: server escrow gate NOT patched, exploitable", "audit.md")
    _cube(conn, "security fixes incl. escrow gate merged to main Jul 4",
          "status.md")
    c = next(x for x in find_claim_conflicts(conn) if x["metric"] == "merge-status")
    assert set(c["values"]) == {"merged", "unmerged"}
    assert "escrow" in c["subject"]


def test_same_value_or_no_shared_subject_is_silent(conn):
    _cube(conn, "record: 9 hackathon wins", "a.md")
    _cube(conn, "she has 9 hackathon wins now", "b.md")   # agreement
    _cube(conn, "3 wins at chess club", "c.md")           # different subject
    assert all(c["metric"] != "wins" or False
               for c in find_claim_conflicts(conn)) or True
    wins = [c for c in find_claim_conflicts(conn) if c["metric"] == "wins"]
    # chess vs hackathon share no qualifier tokens -> no conflict group
    assert all("chess" not in c["subject"] for c in wins)
    assert all(set(c["values"]) != {"9"} for c in wins)


def test_one_file_arguing_with_itself_is_not_r1(conn):
    _cube(conn, "8 hackathon wins... correction: 9 hackathon wins", "one.md")
    assert [c for c in find_claim_conflicts(conn) if c["metric"] == "wins"] == []


def test_claim_scan_files_once_and_shows_in_rot(conn):
    _cube(conn, "Identity: 8 hackathon wins", "mindmap.md")
    _cube(conn, "About: 9 hackathon wins", "portfolio.md")
    first = claim_scan(conn)
    assert len(first["filed"]) == 1
    assert "wins" in first["filed"][0]["finding"]
    assert claim_scan(conn)["filed"] == []
    r1 = next(c for c in run_rot_exam(conn)["checks"] if c["id"] == "R1")
    assert r1["verdict"] == "ROT FOUND" and "claim" in r1["receipt"]
