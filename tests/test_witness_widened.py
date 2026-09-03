"""Three claim classes added 2026-09-03 to helicon/witness.py.

Before them, 10 of the 20 newest sessions scored ZERO checkable claims —
tool-heavy, prose-light sessions said "Deployed." / "72 passed" / "Saved:
`x.md`" and none of the five original types saw it. Each class here has a
fixture with >=2 true claims AND >=2 decoys lifted from real false positives
on the 09-03 corpus; every decoy must NOT extract.
"""
import os

from helicon import witness

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
DEPLOY = os.path.join(FIX, "witness_deploy_fixture.jsonl")
TESTCOUNT = os.path.join(FIX, "witness_testcount_fixture.jsonl")
FILEWRITTEN = os.path.join(FIX, "witness_filewritten_fixture.jsonl")


def _rows(path, typ):
    events, _ = witness.parse_transcript(path)
    rows = witness.judge(witness.extract_claims(events), events)
    return rows, [r for r in rows if r["type"] == typ]


# ------------------------------------------------------------ (a) deployed

def test_deploy_true_claims_get_verdicts():
    rows, dep = _rows(DEPLOY, "deployed")
    by_line = {r["line"]: r for r in dep}
    assert sorted(by_line) == [1, 5, 8, 11]
    # "Deployed." bound to the vercel deploy whose output says READY/Production
    assert by_line[5]["verdict"] == "CONFIRMED"
    assert by_line[5]["witness"]["line"] == 3
    # "return 200 at <host>" prefers the curl that names the host and printed 200
    assert by_line[8]["verdict"] == "CONFIRMED"
    assert by_line[8]["witness"]["line"] == 6
    # the docs curl printed HTTP/2 404 — the witness contradicts "is live"
    assert by_line[11]["verdict"] == "CONTRADICTED"
    assert by_line[11]["witness"]["line"] == 9
    assert "404" in by_line[11]["why"]


def test_deploy_evidence_in_a_later_turn_is_not_evidence():
    _, dep = _rows(DEPLOY, "deployed")
    first = [r for r in dep if r["line"] == 1][0]
    assert first["verdict"] == "NO-EVIDENCE"
    assert first["witness"] is None
    assert "later turn" in first["why"]


def test_deploy_decoys_do_not_extract():
    rows, _ = _rows(DEPLOY, "deployed")
    assert not [r for r in rows if r["line"] == 12], \
        [r["text"] for r in rows if r["line"] == 12]


def test_page_body_500_is_not_an_http_500(tmp_path):
    # a WebFetch body saying "$500 prize" was read as a 5xx on the real corpus
    p = tmp_path / "s.jsonl"
    p.write_text(
        '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"f1","name":"WebFetch","input":{"url":"https://ethglobal.com/prizes"}}]}}\n'
        '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"f1","is_error":false,"content":"Prizes: $500 for first, 491 entrants"}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":"The prizes page is live now."}]}}\n')
    rows, dep = _rows(str(p), "deployed")
    assert len(dep) == 1 and dep[0]["verdict"] == "CONFIRMED"


def test_heredoc_body_is_not_a_command():
    cmd = "python3 - <<'PY'\nnote = 'run curl https://x.app'\nPY\necho done"
    assert "curl" not in witness._cmd_sans_heredoc(cmd)
    assert "echo done" in witness._cmd_sans_heredoc(cmd)


# --------------------------------------------------------- (b) test-count

def test_testcount_true_claims_get_verdicts():
    rows, tc = _rows(TESTCOUNT, "test-count")
    by_line = {r["line"]: r for r in tc}
    assert sorted(by_line) == [4, 7, 11, 13]
    assert by_line[4]["verdict"] == "CONFIRMED" and by_line[4]["witness"]["line"] == 2
    assert by_line[4]["expected_passed"] == 72
    # green 7/7 binds to the shell suite in the same turn, not the pytest run
    assert by_line[7]["verdict"] == "CONFIRMED" and by_line[7]["witness"]["line"] == 5
    assert "7/7" in by_line[7]["why"]


def test_testcount_number_mismatch_is_contradicted():
    _, tc = _rows(TESTCOUNT, "test-count")
    r = [x for x in tc if x["line"] == 11][0]
    assert r["verdict"] == "CONTRADICTED"
    assert r["witness"]["line"] == 9
    assert "claimed 72 passed" in r["why"] and "70 passed" in r["why"]


def test_testcount_needs_a_runner_in_the_same_turn():
    _, tc = _rows(TESTCOUNT, "test-count")
    r = [x for x in tc if x["line"] == 13][0]
    assert r["verdict"] == "NO-EVIDENCE"
    assert r["witness"] is None
    assert "same turn" in r["why"]


def test_testcount_decoys_do_not_extract():
    rows, _ = _rows(TESTCOUNT, "test-count")
    assert not [r for r in rows if r["line"] == 14], \
        [r["text"] for r in rows if r["line"] == 14]


def test_turns_are_counted_from_human_messages():
    events, meta = witness.parse_transcript(TESTCOUNT)
    assert meta["turns"] == 3
    turns = {e["line"]: e["turn"] for e in events}
    assert turns[2] == 1 and turns[9] == 2 and turns[13] == 3


# ------------------------------------------------------- (c) file-written

def test_filewritten_true_claims_get_verdicts():
    rows, fw = _rows(FILEWRITTEN, "file-written")
    by_line = {r["line"]: r for r in fw}
    assert sorted(by_line) == [3, 6, 7, 10]
    assert by_line[3]["verdict"] == "CONFIRMED" and by_line[3]["witness"]["tool"] == "Write"
    assert by_line[3]["path"] == "docs/PLAN-2026-09-03.md"
    # a heredoc `cat > path` is a write witness
    assert by_line[6]["verdict"] == "CONFIRMED" and by_line[6]["witness"]["line"] == 4


def test_filewritten_later_ls_can_contradict():
    _, fw = _rows(FILEWRITTEN, "file-written")
    r = [x for x in fw if x["line"] == 7][0]
    assert r["verdict"] == "CONTRADICTED"
    assert r["witness"]["line"] == 8
    assert "No such file" in r["why"]


def test_filewritten_without_a_witness_is_no_evidence():
    _, fw = _rows(FILEWRITTEN, "file-written")
    r = [x for x in fw if x["line"] == 10][0]
    assert r["verdict"] == "NO-EVIDENCE" and r["witness"] is None


def test_filewritten_decoys_do_not_extract():
    rows, _ = _rows(FILEWRITTEN, "file-written")
    assert not [r for r in rows if r["line"] == 11], \
        [r["text"] for r in rows if r["line"] == 11]


# ------------------------------------------------------------ the surface

def test_share_counts_the_new_classes():
    rep = witness.witness_report(DEPLOY)
    assert rep["claims"] == 4 and rep["verified"] == 2 and rep["contradicted"] == 1
    assert rep["share"] == 0.5


def test_ledger_names_the_new_types(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text('{"type":"assistant","message":{"content":[{"type":"text","text":"Hello."}]}}\n')
    out = witness.run_ledger(str(p))
    assert "deployed, test-count, file-written" in out


def test_original_five_types_are_untouched():
    # every row on the two pre-existing fixtures keeps its type and verdict
    for fx, expected in (("witness_fixture.jsonl",
                          {"CONFIRMED": 2, "NO-EVIDENCE": 1, "CONTRADICTED": 1}),
                         ("witness_share_fixture.jsonl",
                          {"CONFIRMED": 2, "NO-EVIDENCE": 1})):
        rep = witness.witness_report(os.path.join(FIX, fx))
        assert rep["verdicts"] == expected, fx


def test_new_fail_signal_ignores_kv_zero_and_module_not_found():
    assert not witness._NEW_FAIL.search("PASS the source run is not mutated\nok=8 fail=0")
    assert witness._NEW_FAIL.search("8 failed, 2 passed")
    assert not witness._DEPLOY_FAIL.search("ModuleNotFoundError: No module named 'x'")
    assert witness._DEPLOY_FAIL.search("getaddrinfo ENOTFOUND docs.example.app")
