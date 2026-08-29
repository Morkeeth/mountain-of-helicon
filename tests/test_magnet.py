"""MAGNET — ranking a flood against the gaps in one stack.

The tests that matter here are the NEGATIVE ones. A ranker that surfaces good
skills is easy; the flood's actual cost is the popular thing you already own and
the invented gap that sends you shopping for a hole you do not have.
"""
import json
import os

import pytest

from helicon.magnet import (CAPABILITIES, gaps, inventory, load_candidates,
                            magnet_report, rank, render_magnet)


def _stack(tmp_path, skills=None, commands=None, agents=None, settings=None):
    root = tmp_path / ".claude"
    for name, desc in (skills or {}).items():
        d = root / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n")
    for name, desc in (commands or {}).items():
        d = root / "commands"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.md").write_text(f'---\ndescription: "{desc}"\n---\n')
    for name, desc in (agents or {}).items():
        d = root / "agents"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.md").write_text(f"---\ndescription: {desc}\n---\n")
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(json.dumps(settings if settings is not None else {}))
    return str(root)


# --- inventory -------------------------------------------------------------

def test_a_backup_file_is_not_a_live_command(tmp_path):
    """Counting a .bak inflates coverage, and an inventory must never err in the
    direction of claiming you have more than you do."""
    root = _stack(tmp_path, commands={"bagel": "operator"})
    (tmp_path / ".claude" / "commands" / "bagel.md.bak-keyswap").write_text("x")
    inv = inventory(root)
    assert [c["name"] for c in inv["commands"]] == ["bagel"]


def test_the_inventory_carries_no_values(tmp_path):
    """An inventory is something you might paste into a report."""
    root = _stack(tmp_path, settings={"env": {"MY_API_KEY": "sk-secret-value"},
                                      "hooks": {}})
    blob = json.dumps(inventory(root))
    assert "sk-secret-value" not in blob


# --- the false-gap guard ---------------------------------------------------

def test_a_surface_that_cannot_be_enumerated_is_never_called_empty(tmp_path):
    """MCP servers arrive from project .mcp.json, `claude mcp add` and cloud
    connectors — none of which are in settings.json. Reporting the surface as
    empty invents a gap, and a fabricated gap is worse than a missed one: it
    sends the ranker hunting for a hole that is already filled. This fired on the
    real stack on the first run."""
    root = _stack(tmp_path, settings={"hooks": {}})       # no mcpServers key
    g = gaps(inventory(root))
    assert "mcp" not in g["empty_surfaces"]
    assert "mcp" in g["not_enumerable"]


def test_an_mcp_key_that_is_present_and_empty_IS_a_gap(tmp_path):
    """Absent is not zero — but zero is zero."""
    root = _stack(tmp_path, settings={"mcpServers": {}, "hooks": {}})
    g = gaps(inventory(root))
    assert "mcp" in g["empty_surfaces"] and "mcp" not in g["not_enumerable"]


def test_an_empty_surface_needs_no_judgement(tmp_path):
    root = _stack(tmp_path, skills={"zup": "task capture"})
    assert "agents" in gaps(inventory(root))["empty_surfaces"]


def test_a_capability_you_cover_is_not_reported_uncovered(tmp_path):
    root = _stack(tmp_path, skills={"eval": "define the verifiable check that "
                                            "proves a task is right, a probe "
                                            "with real evidence"})
    assert "verification" not in gaps(inventory(root))["uncovered"]


# --- ranking ---------------------------------------------------------------

def _rank(root, rows, top=10):
    """The scored shortlist only. rank() returns a dict now: items with no
    positive signal are UNRANKED rather than ordered, which is the whole point of
    the EXP-MAGNET-01 fix."""
    inv = inventory(root)
    return rank(rows, inv, gaps(inv), top=top)


def _all(root, rows, top=10):
    inv = inventory(root)
    return rank(rows, inv, gaps(inv), top=top)


def test_a_candidate_you_already_own_is_demoted_below_everything(tmp_path):
    """The flood's real cost. A directory sorted by stars puts the popular
    duplicate first; this is the one thing the stack knows that stars cannot."""
    root = _stack(tmp_path, skills={
        "writing": "Oscar's writing rules for anything with a reader: draft an "
                   "email, reply, DM, LinkedIn note, cover letter, bio or post"})
    res = _all(root, [
        {"name": "writing-coach", "description":
            "Oscar's writing rules for anything with a reader. Draft an email, "
            "reply, DM, LinkedIn note, cover letter, bio or post"},
        {"name": "pdb-navigator", "description":
            "Debug a failing test with pdb, breakpoints and a bisect of the trace"},
    ])
    assert [r["name"] for r in res["ranked"]] == ["pdb-navigator"]
    assert [r["name"] for r in res["demoted"]] == ["writing-coach"]
    assert res["demoted"][0]["duplicates"][0]["name"] == "writing"


def test_marketing_copy_with_no_signal_scores_zero(tmp_path):
    """It must not be possible to rank by enthusiasm."""
    root = _stack(tmp_path, skills={"zup": "task capture"})
    res = _all(root, [{"name": "star-magnet-9000", "description":
                       "An awesome productivity booster that supercharges your "
                       "workflow effortlessly"}])
    assert res["ranked"] == [] and res["demoted"] == []
    assert res["no_signal"] == 1


def test_a_candidate_filling_a_real_gap_outranks_one_that_does_not(tmp_path):
    root = _stack(tmp_path, skills={"zup": "task capture and eviction"})
    res = _all(root, [
        {"name": "unrelated", "description": "task capture and eviction helper"},
        {"name": "pdb-navigator", "description":
            "Debug a failing test, set breakpoints, bisect the stack trace"},
    ])
    assert res["ranked"][0]["name"] == "pdb-navigator"
    assert "debug" in res["ranked"][0]["fills"]


def test_targeting_an_empty_surface_scores_but_scores_less_than_a_gap(tmp_path):
    """An empty surface is a weaker signal than a named missing capability, and
    the scores have to say so rather than being tuned until the demo looks good."""
    root = _stack(tmp_path, skills={"zup": "task capture"})
    res = _all(root, [
        {"name": "fanout", "surface": "agents", "description":
            "define reusable subagents that report structured findings"},
        {"name": "pdb", "description":
            "Debug a failing test, set breakpoints, bisect the stack trace"},
    ])
    scores = {r["name"]: r["score"] for r in res["ranked"]}
    assert scores["pdb"] > scores["fanout"] > 0


# --- the feed --------------------------------------------------------------

def test_the_feed_is_read_never_crawled(tmp_path):
    """Rebuilding a directory is a coverage race that several projects have
    already won. The feed is an input."""
    p = tmp_path / "feed.jsonl"
    p.write_text('{"name":"a","description":"debug a trace"}\n'
                 'not json\n'
                 '{"name":"b","description":"refactor and rename"}\n')
    rows = load_candidates(str(p))
    assert [r["name"] for r in rows] == ["a", "b"], "a bad row is skipped, not guessed"


def test_no_feed_says_so_instead_of_showing_an_empty_ranking(tmp_path):
    root = _stack(tmp_path, skills={"zup": "task capture"})
    card = render_magnet(magnet_report(root, ""), read_at="t")
    assert "NO FEED CONFIGURED" in card
    assert "does not crawl" in card


def test_an_empty_feed_is_different_from_no_feed(tmp_path):
    root = _stack(tmp_path, skills={"zup": "task capture"})
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    card = render_magnet(magnet_report(root, str(p)), read_at="t")
    assert "FEED READ 0 ROWS" in card
    assert "an empty feed is not an empty result" in card


def test_the_card_says_these_are_candidates_not_verdicts(tmp_path):
    root = _stack(tmp_path, skills={"zup": "task capture"})
    p = tmp_path / "feed.jsonl"
    p.write_text('{"name":"pdb","description":"debug a failing trace"}\n')
    card = render_magnet(magnet_report(root, str(p)), read_at="t")
    assert "CANDIDATES" in card and "The ruling is yours" in card


def test_a_missing_stack_is_reported_not_invented(tmp_path):
    card = render_magnet(magnet_report(str(tmp_path / "nope"), ""), read_at="t")
    assert "no stack found" in card


# --- the EXP-MAGNET-01 finding, locked in ----------------------------------

def test_no_signal_is_unranked_never_ordered_by_name(tmp_path):
    """EXP-MAGNET-01's real finding. Three synonym candidates scored 0 —
    identical to 990 noise items — and two still landed at rank 5 and 6 because
    'code-surgeon' and 'fault-localiser' sort before 'noise-000'. That read as
    87.5% recall; the true signal-based recall was 62.5%. A tie-break is not a
    finding, and a ranker that cannot say 'no evidence' will always invent one."""
    root = _stack(tmp_path, skills={"zup": "task capture"})
    rows = [{"name": "aaa-first-alphabetically", "description": "wine pairing"},
            {"name": "zzz-last-alphabetically", "description": "guitar tuning"},
            {"name": "noise-000", "description": "flashcards"}]
    res = _all(root, rows)
    assert res["ranked"] == [], "nothing here names a gap; nothing may be ranked"
    assert res["no_signal"] == 3
    assert res["considered"] == 3


def test_a_zero_score_never_outranks_another_zero_score(tmp_path):
    root = _stack(tmp_path, skills={"zup": "task capture"})
    res = _all(root, [{"name": f"cand-{i}", "description": "wine pairing"}
                      for i in range(50)])
    assert res["no_signal"] == 50 and not res["ranked"]


# --- S1: declared-and-verified tags, and the gaming hole they opened --------

from helicon.magnet import verify_declaration


def test_a_declared_tag_the_text_supports_is_verified():
    v = verify_declaration(["debug"], "debug a failing test and bisect the trace")
    assert v["debug"] == "verified"


def test_a_declared_tag_the_text_does_not_support_is_claimed_not_rejected():
    """The synonym case the whole fix exists for: the capability is real, the
    words are different. Carried and flagged, never silently dropped."""
    v = verify_declaration(["debug"], "narrow a misbehaving program to its cause")
    assert v["debug"] == "claimed"


def test_a_declared_tag_not_in_the_vocabulary_is_unknown():
    v = verify_declaration(["telepathy"], "reads your mind")
    assert v["telepathy"] == "unknown"


def test_a_declared_verified_tag_recovers_a_synonym_into_the_PRIMARY_list(tmp_path):
    """The recall fix, in the trustable tier: when the text ALSO supports the
    declared tag, it is a full-confidence fill."""
    root = _stack(tmp_path, skills={"zup": "task capture"})
    res = _all(root, [{"name": "dbg", "capabilities": ["debug"],
                       "description": "debug a failing test, bisect the trace"}])
    assert res["ranked"] and "debug" in res["ranked"][0]["fills"]


def test_an_unverified_claim_NEVER_enters_the_trustable_primary_list(tmp_path):
    """The correction. The first S1 build let a claim buy score, and a
    wine-pairing skill declaring [debug, refactor] scored 4 and OUTRANKED an
    honest synonym. A deterministic filter cannot confirm a claim, so a claim may
    never contaminate the tier whose whole value is that you can trust it."""
    root = _stack(tmp_path, skills={"zup": "task capture"})
    res = _all(root, [{"name": "wine-spammer",
                       "capabilities": ["debug", "refactor", "security"],
                       "description": "recommend wine pairings for a menu"}])
    assert res["ranked"] == []
    assert [r["name"] for r in res["claimed"]] == ["wine-spammer"]


def test_declaring_more_lies_cannot_buy_a_higher_spot(tmp_path):
    """The claims tier is ordered by NAME, never by claim count. Ranking by a
    number the author controls is a tier the author games."""
    root = _stack(tmp_path, skills={"zup": "task capture"})
    res = _all(root, [
        {"name": "zzz-one-claim", "capabilities": ["debug"],
         "description": "wine pairing"},
        {"name": "aaa-three-claims", "capabilities": ["debug", "refactor", "security"],
         "description": "wine pairing"},
    ])
    # aaa sorts first by name despite declaring fewer... no, MORE claims; name
    # order must win, so the one-claim 'zzz' is NOT pushed below by having fewer.
    assert [r["name"] for r in res["claimed"]] == ["aaa-three-claims", "zzz-one-claim"]
    # and neither reached the trustable primary
    assert res["ranked"] == []


def test_a_verified_fill_always_outranks_any_claim(tmp_path):
    root = _stack(tmp_path, skills={"zup": "task capture"})
    res = _all(root, [
        {"name": "liar", "capabilities": ["debug", "refactor", "security"],
         "description": "wine pairing"},
        {"name": "honest", "description": "debug a failing test, bisect the trace"},
    ])
    assert [r["name"] for r in res["ranked"]] == ["honest"]
    assert [r["name"] for r in res["claimed"]] == ["liar"]


def test_a_tag_carries_the_content_hash_it_was_computed_from(tmp_path):
    """Skill changes -> hash changes -> a tag carrying the old hash is stale."""
    root = _stack(tmp_path, skills={"zup": "task capture"})
    res = _all(root, [{"name": "dbg", "description": "debug and bisect a trace"}])
    h = res["ranked"][0]["content_hash"]
    from helicon.magnet import _content_hash
    assert h == _content_hash("dbg debug and bisect a trace")
    assert h != _content_hash("dbg debug and bisect a trace EDITED")
