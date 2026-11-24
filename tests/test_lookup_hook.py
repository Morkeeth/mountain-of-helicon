"""The right-page lookup, the background gate probe, and the two gate gaps.

Every fixture is synthetic. Pins, in the order they matter:
- a prompt about one topic gets the one unit about that topic, and nothing else
- an off-topic prompt gets nothing (a wrong page is worse than none)
- private, superseded and secret-shaped units never enter the index
- the same unit is not handed to the same session twice
- a cold gate verdict never holds the prompt: deferred now, served next prompt
- a path inside a quoted test command is probed
- a moved file with exactly one same-named candidate is stale in the gate
  profile, and stays unverifiable in the strict sweep profile
"""
import json
import subprocess
import time

import pytest

from helicon import capture, doorway, lookup, probes
from helicon.db import init_db


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


def _commit(repo, msg="c"):
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", msg)


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "store.db"))


@pytest.fixture
def corpus(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "KITE-PLAYBOOK.md").write_text(
        "---\ntags: [x]\n---\n# Kite playbook\n\n"
        "## Launch\n"
        "Kites launch from the north meadow. Check the windsock before every launch.\n\n"
        "## Storage\n"
        "Store the spools dry, in the blue crate.\n")
    (pages / "BAKERY-BOOK.md").write_text(
        "# Bakery book\n\n## Sourdough\n"
        "Feed the starter at dawn. The levain rests twelve hours.\n")
    (pages / "SHELF-RULES.md").write_text(
        "# Shelf rules\n\n## Shelf\nThe pottery shelf never holds audition tapes.\n")
    (pages / "NOTES-BOOK.md").write_text(
        "# Notes\n\n## Rehearsal\nThe cello audition rehearsal runs late.\n")
    rulings = tmp_path / "rulings.jsonl"
    rows = [
        {"ts": "2026-01-01T10:00:00+00:00", "private": False,
         "text": "Glazing the vase uses the copper glaze.", "value": "superseded"},
        {"ts": "2026-11-20T10:00:00+00:00", "private": False,
         "text": "Glazing the vase uses the cobalt glaze, fired twice."},
        {"ts": "2026-11-21T10:00:00+00:00", "private": True,
         "text": "The harpsichord tuning stays secret."},
        {"ts": "2026-11-22T10:00:00+00:00", "private": False,
         "text": "The lighthouse keeper password: hunter2 for the lantern room."},
        {"ts": "2026-11-23T10:00:00+00:00",
         "text": "The orchard ladder leans on the walnut tree."},
        {"ts": "2026-11-23T11:00:00+00:00", "private": False,
         "text": "The violin audition for the quartet is on Friday."},
    ]
    rulings.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    cfg = {"db_path": str(tmp_path / "store.db"),
           "lookup": {"db_path": str(tmp_path / "lookup.db"),
                      "pages": [str(pages / "*.md")],
                      "rulings": [str(rulings)],
                      "exclude_text": r"\baudition\b",
                      "trusted_pages": [str(pages / "SHELF-RULES.md")]}}
    built = lookup.build(lookup.settings(cfg))
    assert built["units"] >= 4
    return cfg


def test_prompt_gets_the_one_matching_section(corpus):
    cfg = lookup.settings(corpus)
    hit = lookup.best(cfg, "before the kite launch, what about the windsock?")
    assert hit is not None
    assert hit["path"].endswith("KITE-PLAYBOOK.md")
    assert hit["heading"] == "Launch"
    assert "windsock" in hit["matched"]


def test_off_topic_prompt_gets_nothing(corpus):
    cfg = lookup.settings(corpus)
    assert lookup.best(cfg, "refactor the parser in utils and rename the class") is None
    assert lookup.best(cfg, "hello") is None


def test_long_paste_and_paths_get_nothing(corpus, tmp_path):
    cfg = lookup.settings(corpus)
    brief = ("Read and follow your lane brief: /x/kite/BRIEF-KITE.md\n"
             + "Before starting read these playbooks: /pages/KITE-PLAYBOOK.md /pages/launch/windsock.md\n"
             + " ".join(f"standing{i} rule{i} alternative{i}" for i in range(20)))
    assert lookup.best(cfg, brief) is None
    # folder names in a path are not the topic
    assert lookup.best(cfg, "open /srv/kite/launch/windsock/notes.md now") is None


def test_superseded_private_and_secret_rulings_are_not_indexed(corpus):
    cfg = lookup.settings(corpus)
    hit = lookup.best(cfg, "which glaze for glazing the vase")
    assert hit is not None and "cobalt" in hit["body"]
    assert lookup.best(cfg, "harpsichord tuning secret") is None
    assert lookup.best(cfg, "lighthouse keeper lantern room") is None
    # no private flag at all: unknown is not public
    assert lookup.best(cfg, "orchard ladder walnut tree") is None
    # the operator's own exclusion words
    assert lookup.best(cfg, "violin audition quartet friday") is None
    assert lookup.best(cfg, "cello rehearsal runs late") is None
    # a trusted rule page that only NAMES the topic stays in
    hit = lookup.best(cfg, "what may the pottery shelf hold")
    assert hit and hit["path"].endswith("SHELF-RULES.md")


def test_hook_hands_the_page_once_per_session(conn, corpus, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    prompt = "kite launch windsock check"
    first = capture.hook_lookup(conn, str(work), "s1", prompt, corpus)
    assert first and "KITE-PLAYBOOK.md" in first and "windsock" in first.lower()
    again = capture.hook_lookup(conn, str(work), "s1", prompt, corpus)
    assert again is None                      # no runner-up on a repeat
    other = capture.hook_lookup(conn, str(work), "s2", prompt, corpus)
    assert other and "KITE-PLAYBOOK.md" in other


def test_hook_lookup_off_without_corpus_and_in_private_folder(conn, corpus, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    assert capture.hook_lookup(conn, str(work), "s", "kite launch windsock", {}) is None
    priv = tmp_path / "journal"
    priv.mkdir()
    assert capture.hook_lookup(conn, str(priv), "s", "kite launch windsock", corpus) is None


def test_stale_index_is_rebuilt_in_background_not_inline(corpus, tmp_path):
    cfg = lookup.settings(corpus)
    assert lookup.is_fresh(cfg)
    (tmp_path / "pages" / "NEW-BOOK.md").write_text(
        "# New\n\n## Pottery\nThe kiln door opens only below ninety degrees.\n")
    assert not lookup.is_fresh(cfg)
    t = time.monotonic()
    state = lookup.refresh_in_background(cfg, every_s=0)
    assert state in ("started", "running")
    assert time.monotonic() - t < 0.5
    for _ in range(100):
        if lookup.is_fresh(cfg):
            break
        time.sleep(0.1)
    hit = lookup.best(cfg, "when does the kiln door open, degrees")
    assert hit and hit["path"].endswith("NEW-BOOK.md")
    # a fresh stamp means the next prompt does no checking at all
    for _ in range(50):
        if lookup.refresh_in_background(cfg) == "checked-recently":
            break
        time.sleep(0.1)
    assert lookup.refresh_in_background(cfg) == "checked-recently"


# --------------------------------------------------------------------------
# the gate: background probe and coverage
# --------------------------------------------------------------------------

def _planted_repo(root):
    repo = root / "planted"
    (repo / "src" / "lib" / "__tests__").mkdir(parents=True)
    (repo / "src" / "lib" / "__tests__" / "e2e-api.test.ts").write_text("it('x',()=>{})\n")
    (repo / "app.py").write_text("print('hi')\n")
    (repo / "CLAUDE.md").write_text(
        "# Planted\n\n"
        "Run the tests with `pytest tests/test_app.py`.\n"
        "The live suite is `src/__tests__/e2e-api.test.ts`.\n"
        "Start it with `python3 app.py`.\n"
        "Write the report with `pytest -q --junitxml out/report.py`.\n"
        "Record it with `python3 ~/CODE/other-repo/state/state.py ack`.\n"
        "Or with `python3 /opt/tools/elsewhere.py`.\n")
    _git(repo, "init", "-q")
    _commit(repo)
    return repo


def test_gate_catches_command_path_and_moved_file(conn, tmp_path):
    repo = _planted_repo(tmp_path)
    lines = doorway.contradicted_lines(conn, str(repo))
    refs = {(l["file"], l["line"]) for l in lines}
    assert ("CLAUDE.md", 3) in refs          # pytest tests/test_app.py
    assert ("CLAUDE.md", 4) in refs          # moved to src/lib/__tests__
    assert ("CLAUDE.md", 5) not in refs      # python3 app.py exists
    assert ("CLAUDE.md", 6) not in refs      # an output file is not promised
    assert ("CLAUDE.md", 7) not in refs      # a home path names another tree
    assert ("CLAUDE.md", 8) not in refs      # so does an absolute path


def test_strict_profile_keeps_moved_file_unpublished(conn, tmp_path):
    repo = _planted_repo(tmp_path)
    res = probes._probe_path(str(repo), "src/__tests__/e2e-api.test.ts", True, strict=True)
    assert res["verdict"] == probes.UNVERIFIABLE


def test_two_same_named_candidates_name_nothing(tmp_path):
    repo = tmp_path / "twins"
    for d in ("a", "b"):
        (repo / d).mkdir(parents=True)
        (repo / d / "index.ts").write_text("x\n")
    (repo / "CLAUDE.md").write_text("x\n")
    _git(repo, "init", "-q")
    _commit(repo)
    res = probes._probe_path(str(repo), "src/index.ts", True)
    assert res["verdict"] == probes.UNVERIFIABLE


def test_cold_verdict_is_deferred_then_served(conn, tmp_path):
    repo = _planted_repo(tmp_path)
    v, state = doorway.verdict_within(conn, str(repo), wait_s=0.0)
    assert v is None and state == "deferred"
    for _ in range(200):
        v = doorway.cached_verdict(conn, str(repo))
        if v is not None:
            break
        time.sleep(0.05)
    assert v is not None, "the background probe never wrote its verdict"
    assert any(c["line"] == 3 for c in v["contradicted"])
    v2, state2 = doorway.verdict_within(conn, str(repo), wait_s=0.0)
    assert state2 == "cached" and v2["contradicted"] == v["contradicted"]


def test_hook_gate_with_budget_never_runs_probe_inline(conn, tmp_path):
    repo = _planted_repo(tmp_path)
    t = time.monotonic()
    g = capture.hook_gate(conn, str(repo), "s", "go", mode="warn", wait_s=0.0)
    assert time.monotonic() - t < 0.5
    assert g is None
