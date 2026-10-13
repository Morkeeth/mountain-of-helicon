"""Measured learnings reach the store, and so does a fact deep in a long vault note."""
import json
import sqlite3

LONG_NOTE = ("# Comparison readout\n\n" + ("Filler line about nothing in particular.\n" * 60)
             + "\n## Setup cost\n\n| ours | theirs |\n| --- | --- |\n| 77,123 tokens before the first word | none |\n")


def _vault(tmp_path):
    vault = tmp_path / "vault"
    folder = vault / "01 Projects" / "Research" / "study-2026"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "comparison-readout.md").write_text(LONG_NOTE, encoding="utf-8")
    return vault


def test_depth_three_is_reached_but_the_preview_cuts_the_fact(tmp_path):
    from helicon.connectors import obsidian

    found = obsidian.scan({"vault_path": str(_vault(tmp_path)), "max_depth": 3})
    assert [r.source_ref.endswith("comparison-readout.md") for r in found] == [True]
    assert LONG_NOTE.index("77,123") > obsidian.PREVIEW_CHARS
    assert "77,123" not in found[0].content


def test_full_text_paths_holds_the_whole_note_in_sections(tmp_path):
    from helicon.connectors import obsidian

    found = obsidian.scan({"vault_path": str(_vault(tmp_path)), "max_depth": 3,
                           "full_text_paths": ["01 Projects/Research/*/comparison-readout.md"]})
    holding = [r for r in found if "77,123" in r.content]
    assert len(holding) == 1
    assert holding[0].title == "Comparison readout: Setup cost"
    assert holding[0].source_ref.split("#")[0].endswith("comparison-readout.md")
    assert all(len(r.content) <= obsidian.SECTION_CHARS for r in found)
    plain = obsidian.scan({"vault_path": str(_vault(tmp_path)), "max_depth": 3})
    assert found[0].content == plain[0].content  # the note cube itself does not change


def _learnings(tmp_path):
    proof = tmp_path / "report.md"
    proof.write_text("Median of five: 77,123 tokens with the full setup, 31,000 bare.\n", encoding="utf-8")
    rows = [
        {"id": "COST", "claim": "The full setup carries 77,123 tokens before the first word, 31,000 bare.",
         "number": "77,123 vs 31,000", "when": "2026-10-10", "n": "5 trials", "source": str(proof),
         "check": ["77,123", "31,000"]},
        {"id": "MOVED", "claim": "The night run used 55 workers.", "number": "55", "when": "2026-10-12",
         "source": str(proof), "check": ["55 workers"]},
        {"id": "NOSOURCE", "claim": "A number with no source.", "number": "9"},
    ]
    path = tmp_path / "learnings.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    return path, proof


def test_a_learning_carries_its_source_and_a_live_check_of_it(tmp_path):
    from helicon.connectors import CONNECTORS, learnings

    assert CONNECTORS["learnings"] is learnings.scan and learnings.scan({}) == []
    path, proof = _learnings(tmp_path)
    cubes = {r.metadata["id"]: r for r in learnings.scan({"files": [str(path)]})}
    assert set(cubes) == {"COST", "MOVED"}  # no source, no learning
    assert cubes["COST"].metadata["source_path"] == str(proof)
    assert cubes["COST"].metadata["source_verified"] is True
    assert cubes["COST"].title.startswith("Measured: ")
    assert cubes["MOVED"].metadata["source_verified"] is False
    assert cubes["MOVED"].title.startswith("UNVERIFIED measurement")
    assert cubes["MOVED"].metadata["missing_in_source"] == ["55 workers"]


def test_ask_returns_the_measured_number_with_its_source(tmp_path, monkeypatch):
    from helicon.connectors import learnings
    from helicon.db import init_db, insert_cube
    from helicon.retrieve_guard import guarded_context
    from helicon.scanner import result_to_cube

    monkeypatch.setenv("HELICON_RULINGS_FILE", "")
    path, proof = _learnings(tmp_path)
    db = str(tmp_path / "store.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    for result in learnings.scan({"files": [str(path)]}):
        insert_cube(conn, result_to_cube(result))
    conn.commit()
    res = guarded_context(conn, "How many tokens does the full setup carry before the first word?")
    hit = [m for m in res["safe_context"] if "77,123" in m["title"]]
    assert hit and str(proof) in hit[0]["content_preview"]
