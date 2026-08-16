"""B — the learning ledger.

The classifier's fixture is HAND-LABELLED. Thirty real checks were read and
sorted by a person before the classifier existed, and the classifier's job is to
reproduce that sort. Written the other way round — classifier first, labels
inferred from its output — the test would only prove the code agrees with itself.

The rest of the tests are precision tests, because both of this module's real
defects were over-reporting: an artifact that merely RECORDS a learning counted
as enacting it, and a data dump counted as a runnable file.
"""
import json
import os

from helicon.ledger import (gate_inventory, is_command, learning_ledger,
                            render_ledger, runnable_index)

# --- the hand-labelled fixture --------------------------------------------
# Read from the real catch log on 2026-08-16 and sorted by hand. COMMAND means a
# machine could run it; PROSE means it needs a person to remember it.
HAND_LABELLED = [
    ("open the post URL, not the repo that describes it", False),
    ("grep -rn 'Gate 1' ROADMAP.md", True),
    ("jq '[.[] | select(.author==\"Morkeeth\")] | length' .corpus-jul23.json", True),
    ("gh api repos/OWNER/human-review --jq '.stargazers_count,.description'", True),
    ("open the JD at its own URL before scoring location fit", False),
    ("git log --all --oneline | wc -l", True),
    ("gh pr diff 2", True),
    ("read the aggregation, not its label", False),
    ("resolve the path the invite points at before auditing a repo by name", False),
    ("gh repo view Morkeeth/fleet --json name,isPrivate,createdAt", True),
    ("grep -n startZenBridge electron/main.ts", True),
    ("grep -n installHelper electron/lib/zen-bridge.ts", True),
    ("grep -o '\"caught\": *[0-9]*' runs/$(date -u +%F)-lanes.jsonl", True),
    ("python3 -c \"import json;[print(json.loads(l)['artifact']) for l in "
     "open('runs/2026-08-16-lanes.jsonl') if l.strip()]\"", True),
    ("python3 fleet-capture.py summary | grep -c '\\[missing\\]'", True),
    ("python3 fleet-capture.py generate --stdout | grep 'position that made them'", True),
    ("for every self-declared marker the gate trusts, replace its payload with a "
     "value that cannot resolve and confirm the gate still fails", False),
    ("grep -c '<the claim>' runs/catches.jsonl before reporting a catch as filed", True),
    ("date -r $(( $(grep -o 'lastProgressAt\": *[0-9]*' journal | grep -o '[0-9]*') / 1000 ))", True),
    ("grep -rn '<the figure>' ~/CODE/fleet-ops before rendering a count as a hero number", True),
    ("python3 -c \"import json,collections;rows=[json.loads(l) for l in "
     "open('runs/catches.jsonl') if l.strip()]\"", True),
    ("point the gate at a brief that names a real file and asserts a false number "
     "about it; if it passes, the gate checks citation, not truth", False),
    ("for any gate, name the claim it does NOT check and put that in its output", False),
    ("quote a live append-only file's count with the timestamp you took it, or "
     "quote the command instead of the number", False),
    ("when a relay states an outcome, quote the exit code, never the adjective", False),
    ("derive every count in a document from a command before writing it", False),
    ("resolve every cited id against the log before the document is committed: "
     "grep -o 'C-[0-9a-f]\\{6\\}' <doc> | sort -u | while read i; do echo $i; done", True),
    ("grep -c 'git(repoPath' electron/lib/project-state.ts", True),
    ("read the brief's own limits section before repeating its verdict", False),
    ("re-measure the cost a fix was justified by, after the previous fix lands, "
     "before building the next one", False),
]


def test_the_classifier_reproduces_every_hand_label():
    wrong = [(c, want) for c, want in HAND_LABELLED if is_command(c) is not want]
    assert not wrong, f"{len(wrong)} of {len(HAND_LABELLED)} disagree: {wrong[:3]}"


def test_the_fixture_is_not_all_one_label():
    """A fixture that is 30 of one class would pass against a constant function."""
    commands = sum(1 for _, want in HAND_LABELLED if want)
    assert commands == 18 and len(HAND_LABELLED) - commands == 12


def test_an_english_verb_that_is_also_a_command_needs_an_argument():
    """`open the post URL` is an instruction. `open -a Safari` is a command. The
    word alone cannot separate them."""
    assert not is_command("open the post URL, not the repo")
    assert is_command("open -a Safari https://example.com")
    assert not is_command("find the real object first")
    assert is_command("find . -name '*.py'")


def test_a_shell_keyword_at_the_head_is_not_a_command():
    """`for every self-declared marker ...` opens with a real shell keyword and is
    a paragraph."""
    assert not is_command("for every marker the gate trusts, replace its payload")


def test_the_command_after_a_colon_is_found():
    """The log's convention is `<the rule>: <the command>`."""
    assert is_command("resolve every cited id before commit: grep -o 'C-[0-9a-f]' doc")


# --- the wiring probe ------------------------------------------------------

def _log(tmp_path, rows):
    p = tmp_path / "catches.jsonl"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return str(p)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def test_an_artifact_that_only_records_the_learning_is_not_enacting_it(tmp_path):
    """The first version graded 14 learnings STAGED and nearly every hit was the
    script that BACKFILLED the catch log — it contained the checks because it
    wrote them down. That is the log vouching for itself (R9), reproduced inside
    the detector built to catch unenacted rules."""
    repo = tmp_path / "repo"
    check = "grep -n installHelper electron/lib/zen-bridge.ts"
    _write(str(repo / "backfill.py"),
           f'rows = [{{"check": "{check}", "claimed": "the helper installs"}}]\n')
    log = _log(tmp_path, [{"day": "2026-08-16", "check": check,
                           "claimed": "the helper installs"}])
    r = learning_ledger(log, [str(repo)], [])
    assert r["counts"].get("STAGED", 0) == 0
    assert r["counts"]["STATED"] == 1


def test_a_real_artifact_does_count_as_staged(tmp_path):
    repo = tmp_path / "repo"
    _write(str(repo / "gate.sh"), "#!/bin/sh\ngrep -n installHelper "
                                  "electron/lib/zen-bridge.ts || exit 1\n")
    log = _log(tmp_path, [{"day": "2026-08-16", "claimed": "x",
                           "check": "grep -n installHelper electron/lib/zen-bridge.ts"}])
    r = learning_ledger(log, [str(repo)], [])
    assert r["counts"]["STAGED"] == 1


def test_a_live_config_naming_the_artifact_is_what_makes_it_wired(tmp_path):
    """The whole distinction: a repo full of hooks proves nothing until the
    running system points at one."""
    repo = tmp_path / "repo"
    _write(str(repo / "gate.sh"), "grep -n installHelper electron/lib/zen-bridge.ts\n")
    log = _log(tmp_path, [{"day": "2026-08-16", "claimed": "x",
                           "check": "grep -n installHelper electron/lib/zen-bridge.ts"}])
    assert learning_ledger(log, [str(repo)], [])["counts"]["STAGED"] == 1

    cfg = tmp_path / "settings.json"
    _write(str(cfg), json.dumps({"hooks": [{"command": "gate.sh"}]}))
    r = learning_ledger(log, [str(repo)], [str(cfg)])
    assert r["counts"]["WIRED"] == 1 and r["counts"].get("STAGED", 0) == 0


def test_a_data_dump_is_not_a_runnable_file(tmp_path):
    """Including every .json graded a 389KB prompt corpus as the artifact
    enacting a learning, because it happened to contain the words the check
    greps for."""
    repo = tmp_path / "repo"
    _write(str(repo / "runs" / "corpus.json"), json.dumps({"text": "Gate 1 unmet"}))
    assert not runnable_index([str(repo)])
    _write(str(repo / "settings.json"), "{}")
    assert len(runnable_index([str(repo)])) == 1


def test_a_prepared_diff_is_not_an_installation(tmp_path):
    """The instance this was written for: the week's best learning had a real
    script AND a settings diff prepared, and the live config referenced neither."""
    repo = tmp_path / "repo"
    _write(str(repo / "hooks" / "cite-check.py"), "print('gate')\n")
    _write(str(repo / "hooks" / "settings.json.diff"),
           "+  \"command\": \"cite-check.py\"\n")
    cfg = tmp_path / "settings.json"
    _write(str(cfg), json.dumps({"hooks": []}))
    inv = gate_inventory([str(repo)], [str(cfg)])
    assert any("cite-check.py" in p for p in inv["orphaned"])
    assert inv["installed"] == []


def test_the_card_never_claims_a_check_ran(tmp_path):
    """WIRED means a config names the artifact. Artifacts cannot show execution,
    and a card that implies they can is the persuasive-wrong failure."""
    repo = tmp_path / "repo"
    _write(str(repo / "gate.sh"), "grep -n installHelper electron/lib/zen-bridge.ts\n")
    cfg = tmp_path / "settings.json"
    _write(str(cfg), json.dumps({"hooks": [{"command": "gate.sh"}]}))
    log = _log(tmp_path, [{"day": "2026-08-16", "claimed": "x",
                           "check": "grep -n installHelper electron/lib/zen-bridge.ts"}])
    card = render_ledger(learning_ledger(log, [str(repo)], [str(cfg)]),
                         read_at="2026-08-16T13:04")
    assert "execution unverified" in card
    assert "helicon ledger" in card and "2026-08-16T13:04" in card


def test_an_unread_log_is_not_a_clean_one():
    card = render_ledger(learning_ledger("", [], []))
    assert "no catch log configured" in card


def test_rows_with_no_check_are_counted_separately(tmp_path):
    log = _log(tmp_path, [{"day": "d", "check": ""}, {"day": "d"},
                          {"day": "d", "check": "grep -n foo bar.ts"}])
    r = learning_ledger(log, [], [])
    assert r["population"] == 3 and r["no_check"] == 2 and r["with_check"] == 1
