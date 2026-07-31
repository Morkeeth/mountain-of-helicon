"""Two retrieval defects, found by root-causing one degraded snapshot.

Snapshot 21, task "Orchestrator Closeout", scored overlap 0.0 and live_overlap
0.0 — all five baseline hits gone, three of them still live. Measured against a
copy of the real 48 MB store:

  gc_417d8dc99346  "Orchestrator Closeout - May 15, 2026"
                   review_status approved, merged_into NULL, confidence 0.2429

A live memory whose TITLE IS THE QUERY did not appear in its own top-5. It sat
at rank 10 on the FTS branch and nowhere on the semantic branch. The slots it
lost went to file-write events for a same-named artifact — four "Created:/
Edited: closeout-2026-07-23-orchestrator.md" cubes with distinct content hashes,
ingested within four minutes of each other across four different sessions.

Two independent defects, and each needs its own fix:

  (a) exact-name recall. Cosine cannot tell a title from a mention, and bm25
      rewards the many short rows that repeat the words. Neither branch can
      recover it alone, so the exact-name signal is its own branch and is
      PINNED — a weight can always be outvoted by a big enough flood, which is
      the failure being fixed.

  (b) near-duplicate diversity. One artifact took 3 of 5 slots in production and
      5 of 5 once the semantic branch was unavailable: 60-100% of an agent's
      top-5 context budget spent re-reading one file. Content-hash dedup cannot
      catch it (the hashes genuinely differ) and source_ref cannot key it (the
      four cubes carry four different session ids).

Measured on the store copy, before -> after:
  retrieval benchmark   P@3 0.462 -> 0.615, MRR 0.434 -> 0.577 (n=13)
  snapshot regressions  11 -> 10 of 13; snapshot 21 live_overlap 0.00 -> 0.33,
                        snapshot 25 0.00 -> 1.00; no snapshot got worse.
"""
import json

import pytest

from helicon.db import init_db, insert_cube, rebuild_fts
from helicon.embeddings import (_subject_key, diversify, semantic_health,
                                title_matches)
from helicon.models import HeliconCube
from helicon.snapshots import _retrieve

FLOOD_FILE = ("/Users/x/Obsidian LIFE/01 Projects/Hackathons/"
              "closeout-2026-07-23-orchestrator.md")


def _cube(cid, title, content, file_path=None, source_ref="session_x",
          status="pending", ctype="memory"):
    meta = {"file_path": file_path} if file_path else {}
    return HeliconCube(
        id=cid, source="claude-code", source_ref=source_ref, type=ctype,
        title=title, content=content, content_hash=cid,
        created_at="2026-07-22T23:36:00", valid_from="2026-07-22T23:36:00",
        last_reinforced="2026-07-22T23:36:00", confidence=0.24,
        tags=[], metadata=meta, review_status=status)


@pytest.fixture
def store(tmp_path):
    """The real shape of the defect: one titled memory, buried under a flood of
    near-duplicate file-write events for a same-named artifact."""
    conn = init_db(str(tmp_path / "t.db"))
    assert insert_cube(conn, _cube(
        "gc_target", "Orchestrator Closeout - May 15, 2026",
        "Marathon session. Five Claude Code windows, orchestrator closeout.",
        file_path="/Users/x/Obsidian LIFE/01 Projects/Hackathons/"
                  "orchestrator-closeout-2026-05-15.md",
        source_ref="01 Projects/Hackathons/orchestrator-closeout-2026-05-15.md",
        status="approved", ctype="project"))
    # four sessions, four content hashes, one file — exactly what was observed
    for i, sess in enumerate(["3d0e6a50", "eedf16ac", "7eb2a4c2", "872514a3"]):
        assert insert_cube(conn, _cube(
            f"gc_flood{i}", "Created: closeout-2026-07-23-orchestrator.md",
            f"File: {FLOOD_FILE}\norchestrator closeout written (write {i})",
            file_path=FLOOD_FILE, source_ref=f"session_{sess}",
            ctype="file_created"))
    for i in range(4):
        assert insert_cube(conn, _cube(
            f"gc_edit{i}", "Edited: closeout-2026-07-23-orchestrator.md",
            f"File: {FLOOD_FILE}\norchestrator closeout edited (edit {i})",
            file_path=FLOOD_FILE, source_ref=f"session_e{i}", ctype="code"))
    # genuinely different memories that deserve the freed slots
    for i, (t, c) in enumerate([
        ("Closeout 2026-07-23 — Orchestrator terminal",
         "last mile of the orchestrator closeout run"),
        ("feedback-parallel-sessions", "Oscar prefers one CC terminal per project"),
        ("Night run orchestrator plan", "orchestrator fans out the night run"),
    ]):
        assert insert_cube(conn, _cube(
            f"gc_other{i}", t, c,
            file_path=f"/Users/x/notes/other-{i}.md", source_ref=f"session_o{i}"))
    conn.commit()
    rebuild_fts(conn)
    return conn


# ---------------------------------------------- (a) exact-name recall
def test_a_memory_whose_title_is_the_query_is_retrieved_for_that_query(store):
    """The headline defect. gc_target is live, approved, and named exactly what
    was asked for; it was absent from its own top-5."""
    hits = _retrieve(store, "Orchestrator Closeout", 5)
    assert "gc_target" in [h["id"] for h in hits], \
        "a live memory whose title IS the query is missing from its own top-5"


def test_the_titled_memory_is_not_merely_present_but_first(store):
    hits = _retrieve(store, "Orchestrator Closeout", 5)
    assert hits[0]["id"] == "gc_target"


def test_title_match_survives_a_qualifier_after_the_name(store):
    """The stored title is 'Orchestrator Closeout - May 15, 2026'; the query is
    the bare name. Exact-equality-only would have missed the real case."""
    assert title_matches(store, "Orchestrator Closeout") == ["gc_target"]


def test_title_match_is_a_name_not_a_substring(store):
    """'Orchestrator Closeouts Weekly' must not match 'Orchestrator Closeout' —
    a prefix that continues into a longer word is a different name."""
    assert insert_cube(store, _cube(
        "gc_plural", "Orchestrator Closeouts Weekly", "a different thing",
        file_path="/Users/x/notes/weekly.md"))
    store.commit()
    assert "gc_plural" not in title_matches(store, "Orchestrator Closeout")


def test_a_retired_memory_is_never_pinned(store):
    """Pinning must not resurrect what the human or reconcile retired — that
    would be R7, wrong eviction, in reverse."""
    store.execute("UPDATE helicon_cubes SET review_status='killed' "
                  "WHERE id='gc_target'")
    store.commit()
    assert title_matches(store, "Orchestrator Closeout") == []


def test_a_short_query_does_not_pin_on_noise(store):
    assert title_matches(store, "the") == []
    assert title_matches(store, "") == []


# ---------------------------------------- (b) near-duplicate diversity
def test_no_single_source_file_takes_more_than_one_of_five_slots(store):
    hits = _retrieve(store, "Orchestrator Closeout", 5)
    files = [_subject_key(h) for h in hits]
    flood = "file:closeout-2026-07-23-orchestrator.md"
    assert files.count(flood) <= 1, (
        f"one artifact took {files.count(flood)} of {len(hits)} slots: {files}")


def test_the_diversity_key_is_the_artifact_not_the_session():
    """The four flooding cubes carried four DIFFERENT source_refs while
    describing writes to one file. Keying on provenance would not have caught
    them."""
    a = {"id": "1", "metadata": {"file_path": "/a/b/closeout.md"},
         "source_ref": "session_3d0e6a50"}
    b = {"id": "2", "metadata": json.dumps({"file_path": "/other/closeout.md"}),
         "source_ref": "session_eedf16ac"}
    assert _subject_key(a) == _subject_key(b) == "file:closeout.md"


def test_a_short_window_of_distinct_memories_beats_a_full_one_of_copies():
    """The cap is HARD by default, and that is the argument: a second copy of an
    artifact already in the window is redundancy, not recall, so padding an
    unfilled slot with one buys nothing. Measured on a copy of the real store,
    the hard cap scores the same P@3 0.615 / MRR 0.577 as the padded version
    while returning strictly fewer redundant rows."""
    hits = [{"id": str(i), "metadata": {"file_path": "/a/one.md"}}
            for i in range(5)]
    assert len(diversify(hits, 5, per_subject_cap=1)) == 1
    # callers that genuinely need exactly `limit` rows can still opt in
    assert len(diversify(hits, 5, per_subject_cap=1, overflow_fill=True)) == 5


def test_diversity_prefers_the_higher_ranked_copy():
    hits = [{"id": "keep", "metadata": {"file_path": "/a/one.md"}},
            {"id": "drop", "metadata": {"file_path": "/a/one.md"}},
            {"id": "other", "metadata": {"file_path": "/a/two.md"}}]
    out = diversify(hits, 2, per_subject_cap=1)
    assert [h["id"] for h in out] == ["keep", "other"]


def test_a_memory_with_no_file_path_is_its_own_subject():
    """Cubes without a file_path must not all collapse into one bucket."""
    hits = [{"id": "a", "metadata": {}}, {"id": "b", "metadata": {}},
            {"id": "c", "metadata": None}]
    assert len(diversify(hits, 3, per_subject_cap=1)) == 3


def test_the_pin_cannot_hijack_the_whole_window(store):
    """Many same-named memories must not spend the entire budget either — the
    pin is capped at limit//3."""
    for i in range(6):
        assert insert_cube(store, _cube(
            f"gc_dup{i}", f"Orchestrator Closeout - May {10 + i}, 2026",
            "another closeout", file_path=f"/Users/x/notes/dup-{i}.md"))
    store.commit()
    rebuild_fts(store)
    hits = _retrieve(store, "Orchestrator Closeout", 6)
    assert len([h for h in hits if h.get("title_pin")]) <= 2


# ------------------------------------- the branch that had no policy at all
def test_the_fts_fallback_obeys_the_same_policy(store):
    """_retrieve falls back to plain FTS whenever nothing is embedded — the
    state every store is in before its first `helicon embed`. That branch had
    no pin and no diversity cap, so a new user's very first retrieval was the
    unprotected one."""
    from helicon.embeddings import get_embedding_stats
    assert get_embedding_stats(store)["embedded"] == 0  # fallback path
    hits = _retrieve(store, "Orchestrator Closeout", 5)
    assert hits[0]["id"] == "gc_target"
    keys = [_subject_key(h) for h in hits]
    assert keys.count("file:closeout-2026-07-23-orchestrator.md") <= 1


# ------------------------------------- the branch that failed silently
def test_a_dimension_mismatch_is_reported_not_silently_dropped(store, monkeypatch):
    """`_load_all_embeddings` filters `ce.dim = <provider dim>`; on a mismatch
    it returns nothing, semantic_search returns [], and hybrid_search quietly
    becomes FTS-only with no error anywhere. On a copy of the real store all
    4,214 vectors are dim=1024 (Qwen) while a config-less checkout resolves to
    local/384 — so 60% of the documented ranking signal was silently absent and
    the answer had exactly the same shape.

    The provider is pinned rather than inherited. This test used to depend on
    the DEVELOPER having no config.json: with one present it resolves to Qwen at
    dim 1024, the "mismatch" matches, and the test fails on a working machine
    while the code is correct. The property under test is the mismatch, not the
    absence of a config file.
    """
    from helicon import embeddings as _emb
    monkeypatch.setattr(_emb, "_embed_provider",
                        lambda: ("local", None, "all-MiniLM-L6-v2", 384))
    assert semantic_health(store)["ok"] is False  # nothing embedded yet
    store.execute(
        "INSERT INTO cube_embeddings (cube_id, embedding, embedded_at, model, dim) "
        "VALUES ('gc_target', ?, '2026-07-01', 'text-embedding-v4', 1024)",
        (b"\x00" * 4096,))
    store.commit()
    health = semantic_health(store)
    assert health["ok"] is False
    assert health["usable"] == 0
    assert "DIMENSION MISMATCH" in health["reason"]
    assert health["stored_dims"] == {1024: 1}
