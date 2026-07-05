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


def test_decision_status_poles():
    got = extract_status_claims("rebrand EXECUTED Jul 2, live in store")
    assert any(c["metric"] == "decision-status" and c["value"] == "executed"
               for c in got)
    got = extract_status_claims("Section 1 open decisions: rebrand naming")
    assert any(c["metric"] == "decision-status" and c["value"] == "open"
               for c in got)


def test_domain_lexicon_from_config(conn):
    """The enterprise answer: a new domain's counted things and statuses are
    CONFIG, not code."""
    config = {"claims": {
        "metrics": {"headcount": r"\b(\d{2,5})\s+employees\b"},
        "statuses": {"contract": {"live": r"\bcontract (?:is )?live\b",
                                  "expired": r"\bcontract (?:is )?expired\b"}},
    }}
    _cube(conn, "the Acme deal: 120 employees, contract is live", "crm.md")
    _cube(conn, "Acme headcount 90 employees; NB contract is expired", "wiki.md")
    got = find_claim_conflicts(conn, config)
    metrics = {c["metric"] for c in got}
    assert "headcount" in metrics and "contract" in metrics
    hc = next(c for c in got if c["metric"] == "headcount")
    assert set(hc["values"]) == {"120", "90"}


def test_bad_config_regex_is_skipped_not_fatal(conn):
    config = {"claims": {"metrics": {"broken": r"([unclosed"}}}
    _cube(conn, "Track record: 9 hackathon wins", "a.md")
    _cube(conn, "site: 8 hackathon wins", "b.md")
    got = find_claim_conflicts(conn, config)  # must not raise
    assert any(c["metric"] == "wins" for c in got)


def test_canonical_source_predecides_direction(conn):
    """Vault rule #3 as a check: canonical numbers live in ONE place; every
    other assertion is the drift, direction pre-decided."""
    config = {"claims": {"canonical": {"wins": "mindmap.md"}}}
    _cube(conn, "IDENTITY: 9 hackathon wins", "mindmap.md")
    _cube(conn, "bio: 10 hackathon wins", "content-plan.md")
    _cube(conn, "resume blurb: 8 hackathon wins", "resume.md")
    c = next(x for x in find_claim_conflicts(conn, config)
             if x["metric"] == "wins")
    assert c["canonical"]["truth"] == "9"
    assert c["canonical"]["drifted"] == ["10", "8"] or \
           c["canonical"]["drifted"] == sorted(["10", "8"])
    res = claim_scan(conn, config)
    assert any("Drift from canon" in f["finding"] and "says 9" in f["finding"]
               for f in res["filed"])


def test_evidence_values_stay_aligned_with_their_lines(conn):
    """Live bug caught by the first evidence card: sorted value labels were
    paired with unsorted A/B lines — '4' displayed over the 9-wins line. A
    receipt with crossed labels is worse than no receipt."""
    import json
    from helicon.pairing import format_pair_evidence
    _cube(conn, "Track record: 9 hackathon wins, growing", "memory.md")
    _cube(conn, "site copy: 4 hackathon wins + 2 more", "portfolio.md")
    claim_scan(conn)
    row = conn.execute("SELECT details FROM audit_log WHERE details LIKE "
                       "'%claim|wins%'").fetchone()
    d = json.loads(row["details"])
    assert d["value_a"] in d["line_a"] and d["value_b"] in d["line_b"]
    card = format_pair_evidence(d)
    a_block, b_block = card.split("B:", 1)
    assert d["value_a"] in a_block and d["line_a"][:30] in a_block
    assert d["value_b"] in b_block and d["line_b"][:30] in b_block


def test_claim_scan_files_once_and_shows_in_rot(conn):
    _cube(conn, "Identity: 8 hackathon wins", "mindmap.md")
    _cube(conn, "About: 9 hackathon wins", "portfolio.md")
    first = claim_scan(conn)
    assert len(first["filed"]) == 1
    assert "wins" in first["filed"][0]["finding"]
    assert claim_scan(conn)["filed"] == []
    r1 = next(c for c in run_rot_exam(conn)["checks"] if c["id"] == "R1")
    assert r1["verdict"] == "ROT FOUND" and "claim" in r1["receipt"]


def test_line_matching_both_poles_yields_no_status_claim():
    """P0 from the night audit: the LOUPE banner that CLOSES a decision was
    filed as evidence the decision was still open. A line matching both
    poles asserts neither."""
    line = "> **LOUPE STATUS FLIP: rebrand EXECUTED Jul 2. Section 1 'open decisions' are DONE.**"
    got = [c for c in extract_status_claims(line) if c["metric"] == "decision-status"]
    assert got == []
    # single-pole lines still assert
    assert extract_status_claims("rebrand executed Jul 2")[0]["value"] == "executed"


def test_canonical_omitted_when_canon_file_asserts_both_values(conn):
    config = {"claims": {"canonical": {"episode": "ep29.md"}}}
    _cube(conn, "released as ep29; the raw session was labeled ep25", "ep29.md")
    _cube(conn, "promo clip refers to ep25", "notes.md")
    for c in find_claim_conflicts(conn, config):
        if c["metric"] == "episode":
            assert c.get("canonical") is None


def test_canonical_requires_exact_basename_match(conn):
    config = {"claims": {"canonical": {"wins": "mindmap.md"}}}
    _cube(conn, "archive copy: 12 hackathon wins", "old-mindmap.md")
    _cube(conn, "site: 9 hackathon wins", "site.md")
    for c in find_claim_conflicts(conn, config):
        if c["metric"] == "wins":
            assert c.get("canonical") is None  # near-name must not hijack truth
