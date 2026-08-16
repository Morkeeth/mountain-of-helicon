"""A — the overboard detector.

Every test here builds a fixture where each individual row is DEFENSIBLE and only
the aggregate is wrong. That is the class: if a test can be written where one row
is obviously bad, it belongs to a different detector.

The precision tests matter more than the recall tests. The first version of the
scatter detector reported SUBMISSION.md across seven hackathon repos as a defect
— true, and worthless, and exactly the finding pile the weekly review's gate
exists to prevent. So the noise fixtures are kept next to the signal fixtures and
both are asserted.
"""
import json
import os

import pytest

from helicon.overboard import (artifact_scatter, lane_churn, overboard_report,
                               render_overboard, scattered_homes,
                               self_catch_blindness)


def _jsonl(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return str(path)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


# --- D1: self-catch blindness ---------------------------------------------

def test_a_self_catch_is_read_from_the_logs_convention(tmp_path):
    """The log writes `author: "self"` for a self-catch and names the catcher in
    caught_by. Reading it any other way invents or loses catches."""
    p = _jsonl(tmp_path / "c.jsonl", [
        {"author": "coordinator", "caught_by": "T3"},
        {"author": "coordinator", "caught_by": "T4"},
        {"author": "self", "caught_by": "T3"},
    ])
    r = self_catch_blindness(p)
    coord = next(a for a in r["authors"] if a["author"] == "coordinator")
    assert coord["authored"] == 2 and coord["self_caught"] == 0
    assert r["self_caught_by"]["T3"] == 1


def test_seat_aliases_are_reported_not_merged(tmp_path):
    """`T1` and `T1-coordinator` may be one seat. Merging them on a substring
    match would invent self-catches the log never recorded, and a number invented
    by a join is the persuasive-and-wrong failure this product exists to catch."""
    p = _jsonl(tmp_path / "c.jsonl", [
        {"author": "coordinator", "caught_by": "T1"},
        {"author": "coordinator", "caught_by": "T3"},
    ])
    r = self_catch_blindness(p)
    coord = next(a for a in r["authors"] if a["author"] == "coordinator")
    assert coord["self_caught"] == 0, "a substring join would have invented one"
    assert r["ambiguous_seats"] == [], "T1 does not contain 'coordinator'"

    p2 = _jsonl(tmp_path / "c2.jsonl", [
        {"author": "coordinator", "caught_by": "T1-coordinator"},
    ])
    r2 = self_catch_blindness(p2)
    assert r2["ambiguous_seats"] == ["T1-coordinator"]
    assert next(a for a in r2["authors"]
                if a["author"] == "coordinator")["self_caught"] == 0


def test_unattributed_rows_are_named_not_absorbed(tmp_path):
    """A per-author rate over 70% of the log is a different number from a
    per-author rate. The population and the unattributed share are both reported."""
    p = _jsonl(tmp_path / "c.jsonl", [
        {"author": "unknown", "caught_by": "T3"},
        {"author": "unknown", "caught_by": "T4"},
        {"author": "coordinator", "caught_by": "T3"},
    ])
    r = self_catch_blindness(p)
    assert r["population"] == 3 and r["unattributed"] == 2
    assert [a["author"] for a in r["authors"]] == ["coordinator"]


# --- D2: lane churn --------------------------------------------------------

def test_one_seat_over_two_objects_is_only_visible_across_days(tmp_path):
    """Each row is a lane doing sensible work on a real repo. The defect is that
    it is not the SAME repo, and no single row can show that."""
    runs = tmp_path / "runs"
    runs.mkdir()
    _jsonl(runs / "2026-08-15-lanes.jsonl",
           [{"lane": "T4-alpha", "artifact": "/Users/x/CODE/alpha", "ship": "a"}])
    _jsonl(runs / "2026-08-16-lanes.jsonl",
           [{"lane": "T4-beta", "artifact": "/Users/x/CODE/beta", "ship": "b"}])
    r = lane_churn(str(runs))
    assert r["days"] == ["2026-08-15", "2026-08-16"]
    drift = next(d for d in r["object_drift"] if d["seat"] == "T4")
    assert drift["count"] == 2
    assert next(d for d in r["name_drift"] if d["seat"] == "T4")["count"] == 2


def test_a_seat_holding_one_object_all_week_is_not_a_finding(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    for day in ("2026-08-15", "2026-08-16"):
        _jsonl(runs / f"{day}-lanes.jsonl",
               [{"lane": "T4-alpha", "artifact": "/Users/x/CODE/alpha", "ship": "a"}])
    r = lane_churn(str(runs))
    assert r["object_drift"] == [] and r["name_drift"] == []


def test_a_commit_sha_is_not_an_object(tmp_path):
    """A lane shipping two commits to one repo did not move. Reading the sha as
    the object would report every productive lane as churning."""
    runs = tmp_path / "runs"
    runs.mkdir()
    _jsonl(runs / "2026-08-15-lanes.jsonl",
           [{"lane": "zup", "artifact": "7ad39d5", "ship": "the capture window"}])
    _jsonl(runs / "2026-08-16-lanes.jsonl",
           [{"lane": "zup", "artifact": "131d551", "ship": "the capture window"}])
    assert lane_churn(str(runs))["object_drift"] == []


# --- D3: drifted duplicates ------------------------------------------------

def test_per_project_docs_that_share_a_name_are_not_scatter(tmp_path):
    """The noise fixture. Seven projects each writing their own SUBMISSION.md
    share a basename and nothing else. Reporting it is true and worthless."""
    root = tmp_path / "code"
    for i, body in enumerate(["chain wallet demo", "an eval harness",
                              "a design tool", "a memory audit"]):
        _write(str(root / f"proj{i}" / "SUBMISSION.md"),
               f"# Submission\n{body}\nbuilt at hackathon {i}\n")
    assert artifact_scatter(str(root))["scattered"] == []


def test_one_document_copied_and_then_edited_is_scatter(tmp_path):
    """The signal fixture. Same document, three homes, and the copies no longer
    agree — so an agent that opens one reads a different truth from an agent that
    opens another, and neither knows the other exists."""
    root = tmp_path / "code"
    shared = "\n".join(f"prize {i}: unclaimed" for i in range(20))
    _write(str(root / "a" / "LEDGER.md"), shared + "\ntotal: 20\n")
    _write(str(root / "b" / "LEDGER.md"), shared + "\ntotal: 21\n")
    _write(str(root / "c" / "LEDGER.md"), shared + "\ntotal: 19\n")
    found = artifact_scatter(str(root))["scattered"]
    assert len(found) == 1
    assert found[0]["name"] == "ledger.md"
    assert found[0]["locations"] == 3 and found[0]["versions"] == 3


def test_identical_copies_inside_one_project_are_that_projects_design(tmp_path):
    """Six byte-identical RULES.md across six arms of one experiment is how that
    experiment works. The threshold counts HOMES, not copies."""
    root = tmp_path / "code"
    for arm in "abcdef":
        _write(str(root / "experiment" / arm / "RULES.md"), "one rule\ntwo rule\n")
    assert artifact_scatter(str(root))["scattered"] == []


def test_a_vendored_dependency_is_not_the_users_stack(tmp_path):
    """Two copies of a dependency's doc are someone else's file, and there is no
    ruling for the user to make on them."""
    root = tmp_path / "code"
    body = "\n".join(f"clause {i}" for i in range(20))
    for dep in ("dep-a", "dep-b"):
        _write(str(root / "app" / "lib" / dep / "CONDUCT.md"), body)
        _write(str(root / "app" / "lib" / dep / ".git"), "gitdir: elsewhere")
    _write(str(root / "own" / "CONDUCT.md"), body + "\nextra\n")
    assert artifact_scatter(str(root))["scattered"] == []


# --- D4: scattered homes ---------------------------------------------------

def test_one_name_containing_another_is_one_object_in_two_homes(tmp_path):
    root = tmp_path / "code"
    for d in ("parisinnovhack", "parisinnovhack-master", "unrelated-thing"):
        (root / d).mkdir(parents=True)
    r = scattered_homes(str(root))
    nested = next(n for n in r["nested"] if n["object"] == "parisinnovhack")
    assert nested["nested_pairs"] == [
        {"inner": "parisinnovhack", "outer": "parisinnovhack-master"}]


def test_two_homes_differing_only_in_case_and_separator_are_the_strongest_case(tmp_path):
    """`Paris Portfolio` and `paris-portfolio` normalize to the same string. An
    earlier version required the normalized names to DIFFER and threw this pair
    away — it dropped the clearest finding in the section."""
    root = tmp_path / "code"
    for d in ("Paris Portfolio", "paris-portfolio"):
        (root / d).mkdir(parents=True)
    pairs = [p for n in scattered_homes(str(root))["nested"]
             for p in n["nested_pairs"]]
    assert {"inner": "Paris Portfolio", "outer": "paris-portfolio"} in pairs


def test_a_shared_word_is_a_candidate_not_a_finding(tmp_path):
    """Four deliberately separate experiments share the word `fleet`. Rendering
    that as confidently as a nested-name match is how a review surface produces a
    wrong ruling that looks sourced."""
    root = tmp_path / "code"
    for d in ("fleet-experiment-2", "fleet-experiment-3", "fleet-experiment-4"):
        (root / d).mkdir(parents=True)
    r = scattered_homes(str(root))
    assert r["nested"] == []
    assert next(s for s in r["shared"] if s["object"] == "fleet")["count"] == 3


def test_generic_words_do_not_bind_two_projects(tmp_path):
    root = tmp_path / "code"
    for d in ("alpha-agent", "beta-agent"):
        (root / d).mkdir(parents=True)
    r = scattered_homes(str(root))
    assert r["nested"] == [] and r["shared"] == []


# --- the card --------------------------------------------------------------

def test_every_section_names_its_population_and_the_command(tmp_path):
    """A number without the command that reproduces it and the moment it was read
    is a claim with an author."""
    runs = tmp_path / "runs"
    runs.mkdir()
    _jsonl(runs / "2026-08-16-lanes.jsonl",
           [{"lane": "T4-alpha", "artifact": "/Users/x/CODE/alpha", "ship": "a"}])
    catches = _jsonl(tmp_path / "c.jsonl", [{"author": "coordinator",
                                             "caught_by": "T3"}])
    root = tmp_path / "code"
    root.mkdir()
    card = render_overboard(overboard_report(catches, str(runs), str(root)))
    assert "helicon overboard" in card
    assert "1 logged errors" in card and "1 day(s) observed" in card
    assert "top-level directories" in card


def test_an_unconfigured_section_says_so_instead_of_reporting_clean():
    """An unmeasured population is not a pass. A detector that silently grades
    nothing and prints no findings is the false-green it was built to catch."""
    card = render_overboard(overboard_report("", "", ""))
    assert "no catch log configured" in card
    assert "no runs directory configured" in card
    assert "no code root configured" in card


def test_a_measured_but_empty_population_is_different_from_an_unread_one(tmp_path):
    root = tmp_path / "code"
    root.mkdir()
    card = render_overboard(overboard_report("", "", str(root)))
    assert "no distinctive document is duplicated and drifted" in card
    assert "every object has exactly one home" in card


def test_a_malformed_row_is_skipped_never_guessed_at(tmp_path):
    p = tmp_path / "c.jsonl"
    with open(p, "w") as f:
        f.write('{"author": "coordinator", "caught_by": "T3"}\n')
        f.write("not json at all\n")
    assert self_catch_blindness(str(p))["population"] == 1
