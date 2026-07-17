"""R11 identity coherence — the deterministic genus tier.

Tests run with semantic=False (no embeddings/torch): the genus-mismatch core is
what must be provably correct. A definition that forks across sources fires; status
prose, same-genus, and single-source do not.
"""
import pytest

from helicon.db import init_db, insert_cube
from helicon.models import ConnectorResult
from helicon.scanner import result_to_cube
from helicon.identity import extract_glosses, find_identity_forks, identity_scan


def _cube(conn, content, ref, source="obsidian", created_at="2026-07-01T00:00:00"):
    r = ConnectorResult(source=source, source_ref=ref, type="memory",
                        title=ref, content=content, created_at=created_at)
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    conn.commit()
    return cube.id


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "h.db"))


# --- extraction: the article gate is the precision core --------------------

def test_article_gate_keeps_definitions_drops_status():
    got = {g["genus"] for g in extract_glosses("Yieldbound is a yield treasury.")}
    assert "treasury" in got
    # no article => status/adjective prose, not an identity definition
    assert extract_glosses("Relay is live and shipped.") == []
    assert extract_glosses("node is old now.") == []
    assert extract_glosses("the commit is feat not fix.") == []


def test_genus_is_the_head_noun():
    # head-final compound; the clause is cut at the preposition
    g = extract_glosses("Bagel is a remote automation bot on the VPS.")
    assert any(x["genus"] == "bot" for x in g)


# --- forks: the cross-source, incompatible-genus signal --------------------

def test_cross_source_fork_fires(conn):
    _cube(conn, "Yieldbound is a yield treasury.", "mindmap.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "trades.md")
    forks = find_identity_forks(conn, semantic=False)
    assert len(forks) == 1
    f = forks[0]
    assert f["name"] == "yieldbound"
    assert {f["genus_a"], f["genus_b"]} == {"treasury", "tracker"}
    assert len(f["scopes"]) == 2


def test_same_genus_is_not_a_fork(conn):
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a treasury.", "b.md")
    assert find_identity_forks(conn, semantic=False) == []


def test_single_source_is_not_a_fork(conn):
    # two genera but one source scope — not cross-source, so not a fork
    _cube(conn, "Yieldbound is a treasury. Later: Yieldbound is a tracker.", "one.md")
    assert find_identity_forks(conn, semantic=False) == []


def test_status_prose_does_not_fork(conn):
    _cube(conn, "Relay is live.", "a.md")
    _cube(conn, "Relay is shipped.", "b.md")
    assert find_identity_forks(conn, semantic=False) == []


# --- filing: same audit_log plumbing, idempotent ---------------------------

def test_identity_scan_files_once(conn):
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    r1 = identity_scan(conn, semantic=False)
    assert len(r1["filed"]) == 1
    assert r1["filed"][0]["pair_key"] == "identity|yieldbound"

    r2 = identity_scan(conn, semantic=False)         # idempotent by pair_key
    assert r2["filed"] == []

    n = conn.execute("SELECT COUNT(*) FROM audit_log WHERE audit_type='identity'").fetchone()[0]
    assert n == 1


def test_resolve_identity_settles_the_fork(conn):
    from helicon.identity import resolve_identity
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    assert len(identity_scan(conn, semantic=False)["filed"]) == 1
    audit_id = conn.execute(
        "SELECT id FROM audit_log WHERE audit_type='identity'").fetchone()[0]

    r = resolve_identity(conn, audit_id, "a yield treasury that spends its own yield")
    assert r["ok"] and r["correction_cube"]
    cube = conn.execute(
        "SELECT review_status, source, content FROM helicon_cubes WHERE id=?",
        (r["correction_cube"],)).fetchone()
    assert cube["review_status"] == "approved" and cube["source"] == "human-resolution"
    assert "canonically" in cube["content"]

    # settled: the fork no longer surfaces and a re-scan files nothing
    assert find_identity_forks(conn, semantic=False) == []
    assert identity_scan(conn, semantic=False)["filed"] == []


def test_resolve_identity_rejects_bad_input(conn):
    from helicon.identity import resolve_identity
    assert not resolve_identity(conn, 99999, "x")["ok"]        # no such finding
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    identity_scan(conn, semantic=False)
    aid = conn.execute("SELECT id FROM audit_log WHERE audit_type='identity'").fetchone()[0]
    assert not resolve_identity(conn, aid, "")["ok"]           # empty canonical
    assert resolve_identity(conn, aid, "a treasury")["ok"]
    assert not resolve_identity(conn, aid, "a treasury")["ok"]  # already decided


def test_identity_never_twice_realarms_on_new_divergence(conn):
    from helicon.identity import resolve_identity
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    identity_scan(conn, semantic=False)
    aid = conn.execute("SELECT id FROM audit_log WHERE audit_type='identity'").fetchone()[0]
    resolve_identity(conn, aid, "a yield treasury")     # canonical genus = treasury
    assert find_identity_forks(conn, semantic=False) == []       # settled

    # NEW memory (created after the ruling) asserts a divergent genus -> re-alarm
    _cube(conn, "Yieldbound is a lending protocol.", "fresh.md",
          created_at="2027-01-01T00:00:00")
    forks = find_identity_forks(conn, semantic=False)
    assert len(forks) == 1
    assert forks[0].get("resurfaced") is True
    assert forks[0]["genus_b"] == "protocol"
    # and it files as a NEW finding, not grandfathered under the old key
    assert identity_scan(conn, semantic=False)["filed"]


def test_identity_reasserting_canonical_stays_settled(conn):
    from helicon.identity import resolve_identity
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    identity_scan(conn, semantic=False)
    aid = conn.execute("SELECT id FROM audit_log WHERE audit_type='identity'").fetchone()[0]
    resolve_identity(conn, aid, "a yield treasury")
    # re-stating the canonical genus after the ruling must NOT re-alarm
    _cube(conn, "Yieldbound is a treasury.", "fresh.md", created_at="2027-01-01T00:00:00")
    assert find_identity_forks(conn, semantic=False) == []


def test_rot_exam_reports_r11(conn):
    # The exam counts SEMANTICALLY-CONFIRMED forks (the same set `resolve --list`
    # lets you rule), so the fixture is an unambiguous cross-genus fork. A genus
    # mismatch alone is a candidate, not rot; the semantic gate confirms it.
    from helicon.rot import run_rot_exam
    _cube(conn, "Aurora is a payments protocol.", "a.md")
    _cube(conn, "Aurora is a lending market.", "b.md")
    res = run_rot_exam(conn)
    r11 = next((c for c in res["checks"] if c["id"] == "R11"), None)
    assert r11 is not None and r11["verdict"] == "ROT FOUND"


# --- stage 3: the Qwen judge gate ---------------------------------------------
# Cosine cannot separate a fork from a rephrasing. Measured on the live store
# 2026-07-17: yieldbound (real) 0.354 vs qwen (artifact) 0.367, threshold 0.45,
# so all four candidates survived and three were false positives. The judge got
# 4/4. These tests pin the gate's CONTRACT, not the model: a fake client asserts
# the wiring, so they stay deterministic and keyless.

class _FakeJudge:
    """Stands in for a Qwen client. `verdicts` maps gloss_a -> contradicts."""

    def __init__(self, verdicts, boom=False):
        self.verdicts, self.boom, self.calls = verdicts, boom, []


def _patch_judge(monkeypatch, fake):
    def _fake_detect(client, a, b, model="", **kw):
        client.calls.append((a, b))
        if client.boom:
            raise RuntimeError("judge unreachable")
        return {"contradicts": client.verdicts.get(a, False), "explanation": "x",
                "severity": "critical"}
    monkeypatch.setattr("helicon.qwen.detect_contradictions", _fake_detect)


def test_judge_drops_the_rephrasing_and_keeps_the_real_fork(monkeypatch):
    from helicon.identity import _judge_confirm
    forks = [
        {"name": "yieldbound", "gloss_a": "a treasury", "gloss_b": "a wallet tracker"},
        {"name": "qwen", "gloss_a": "the verification brain", "gloss_b": "a memory judge"},
    ]
    fake = _FakeJudge({"a treasury": True, "the verification brain": False})
    _patch_judge(monkeypatch, fake)
    kept = _judge_confirm(forks, fake, "qwen3.6-flash")
    assert [f["name"] for f in kept] == ["yieldbound"]
    assert kept[0]["judge"]["contradicts"] is True


def test_no_client_keeps_every_candidate(monkeypatch):
    """Honest degradation: over-report to a human, never silently drop."""
    from helicon.identity import _judge_confirm
    forks = [{"name": "qwen", "gloss_a": "a", "gloss_b": "b"}]
    assert _judge_confirm(forks, None, "m") == forks


def test_judge_error_keeps_the_fork(monkeypatch):
    """An unreachable judge must not retire rot the human never saw."""
    from helicon.identity import _judge_confirm
    forks = [{"name": "yieldbound", "gloss_a": "a treasury", "gloss_b": "a tracker"}]
    fake = _FakeJudge({}, boom=True)
    _patch_judge(monkeypatch, fake)
    assert [f["name"] for f in _judge_confirm(forks, fake, "m")] == ["yieldbound"]


def test_a_ruled_name_is_never_re_argued_by_the_model(monkeypatch):
    """resurfaced = a human already ruled it. Never-twice outranks the judge."""
    from helicon.identity import _judge_confirm
    forks = [{"name": "aurora", "gloss_a": "x", "gloss_b": "y", "resurfaced": True}]
    fake = _FakeJudge({"x": False})     # judge would drop it
    _patch_judge(monkeypatch, fake)
    assert [f["name"] for f in _judge_confirm(forks, fake, "m")] == ["aurora"]
    assert fake.calls == []             # and was never asked


def test_the_judge_is_greedy_by_default():
    """A verdict that changes between identical calls is not a verdict."""
    import inspect
    from helicon.qwen import detect_contradictions
    assert inspect.signature(detect_contradictions).parameters["temperature"].default == 0.0


def test_cache_key_separates_greedy_from_sampled():
    from helicon.qwen import _cache_key
    assert _cache_key("s", "u", "m", 0.0) != _cache_key("s", "u", "m", None)
