"""The one number `helicon witness` emits: verified-claims share.

Definition under test (helicon/witness.py::share_of): CONFIRMED ÷ checkable
claims. NO-EVIDENCE and CONTRADICTED are both UNVERIFIED and both appear in
the unverified list with their verdict. Zero claims → share is None.
"""
import argparse
import json
import os

from helicon import witness
from helicon.cli import cmd_truth, cmd_witness

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SHARE_FIX = os.path.join(FIX, "witness_share_fixture.jsonl")
LEDGER_FIX = os.path.join(FIX, "witness_fixture.jsonl")
ROTTEN = os.path.join(FIX, "rotten-repo")


def test_share_fixture_two_of_three():
    rep = witness.witness_report(SHARE_FIX)
    assert rep["session_id"] == "witness_share_fixture"
    assert rep["claims"] == 3
    assert rep["verified"] == 2
    assert rep["contradicted"] == 0
    assert abs(rep["share"] - 2 / 3) < 1e-3
    assert [u["line"] for u in rep["unverified"]] == [6]
    u = rep["unverified"][0]
    assert u["verdict"] == "NO-EVIDENCE"
    assert "README.md" in u["text"]


def test_contradicted_is_unverified_not_verified():
    rep = witness.witness_report(LEDGER_FIX)
    assert rep["claims"] == 4
    assert rep["verified"] == 2
    assert rep["contradicted"] == 1
    assert rep["share"] == 0.5
    verdicts = sorted(u["verdict"] for u in rep["unverified"])
    assert verdicts == ["CONTRADICTED", "NO-EVIDENCE"]
    assert rep["verdicts"] == {"CONFIRMED": 2, "NO-EVIDENCE": 1, "CONTRADICTED": 1}


def test_zero_claims_is_none_not_zero(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text('{"type": "assistant", "message": {"role": "assistant", '
                 '"content": [{"type": "text", "text": "Hello."}]}}\n')
    rep = witness.witness_report(str(p))
    assert rep["claims"] == 0
    assert rep["share"] is None
    assert rep["unverified"] == []
    assert witness.render_summary(rep).endswith("share=n/a")


def test_ledger_prints_the_share_line():
    out = witness.run_ledger(SHARE_FIX)
    assert "VERIFIED-CLAIMS SHARE: 0.67 (2/3)" in out


def test_cli_json_contract(capsys):
    cmd_witness(argparse.Namespace(transcript=SHARE_FIX, json=True,
                                   summary=False, judge=False))
    rep = json.loads(capsys.readouterr().out)
    for key in ("session_id", "claims", "verified", "share", "unverified"):
        assert key in rep
    assert rep["claims"] == 3 and rep["verified"] == 2
    assert rep["unverified"] == [{"text": rep["unverified"][0]["text"],
                                 "line": 6, "verdict": "NO-EVIDENCE"}]


def test_cli_summary_is_one_line(capsys):
    cmd_witness(argparse.Namespace(transcript=SHARE_FIX, json=False,
                                   summary=True, judge=False))
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert out.strip() == ("witness_share_fixture claims=3 verified=2 "
                           "contradicted=0 share=0.67")


def test_truth_count_matches_scan_store(capsys):
    from helicon.truth import scan_store
    expected = scan_store(ROTTEN)["flagged"]
    cmd_truth(argparse.Namespace(path=ROTTEN, count=True, json=False,
                                 archive=False, recursive=False))
    out = capsys.readouterr().out.strip()
    assert out == str(expected)
    assert out.isdigit()


def test_truth_count_is_nonzero_on_a_stale_stamp(tmp_path, capsys):
    # A freshness stamp older than the file's own mtime is signal #1
    # (stamp-stale); the probe must count it, and count nothing else.
    (tmp_path / "rules.md").write_text("---\nupdated: 2020-01-01\n---\n# Rules\nAlways run tests.\n")
    (tmp_path / "clean.md").write_text("# Clean\nNo stamp, no dated claim.\n")
    cmd_truth(argparse.Namespace(path=str(tmp_path), count=True, json=False,
                                 archive=False, recursive=False))
    assert capsys.readouterr().out.strip() == "1"


def test_truth_count_error_never_reads_as_zero(tmp_path, capsys):
    import pytest
    with pytest.raises(SystemExit) as ex:
        cmd_truth(argparse.Namespace(path=str(tmp_path / "missing"), count=True,
                                     json=False, archive=False, recursive=False))
    assert ex.value.code != 0
    assert capsys.readouterr().out.strip() == ""
