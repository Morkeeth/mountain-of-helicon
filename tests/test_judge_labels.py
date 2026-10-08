"""Stored provenance labels: what new records write, and how old rows are read.

New records say which model judged (the model id), or "llm" when no id is
known. Rows written before the model layer went neutral carry the first
vendor's name, and they are never rewritten. A reader must accept both.

No test here talks to a network: every completion goes through a fake.
"""
import json
from types import SimpleNamespace

import pytest

from helicon.llm import is_model_judged, judge_label

# The label older versions stored. It stays readable for as long as those
# rows exist, which is for ever: history is not rewritten.
OLD_LABEL = "qwen"


class _FakeClient:
    def __init__(self, reply: dict):
        outer = self
        self.models_seen = []

        class _Completions:
            def create(self, **kwargs):
                outer.models_seen.append(kwargs["model"])
                msg = SimpleNamespace(content=json.dumps(reply))
                return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)

        self.chat = SimpleNamespace(completions=_Completions())


@pytest.fixture(autouse=True)
def clean_llm(monkeypatch):
    import helicon.llm as llm
    monkeypatch.setattr(llm, "_cache", {})
    monkeypatch.setattr(llm, "_call_log", [])
    monkeypatch.setattr(llm, "_route_log", [])
    monkeypatch.setattr(llm, "_cache_stats", {"hits": 0, "misses": 0})
    monkeypatch.setattr(llm, "_db_conn", None)


_REPLY = {"Contradiction": {"status": "FAIL", "reason": "two dates"},
          "Grounding": {"status": "PASS", "reason": "cited"}}
_HITS = [{"id": "c1", "title": "t", "content": "body", "type": "memory"}]


def test_new_battery_verdict_stores_the_model_id():
    from helicon.battery import run_llm_tests
    client = _FakeClient(_REPLY)
    out = run_llm_tests(client, "a task", _HITS, model="judge-model-1")
    assert out and {r["judged_by"] for r in out} == {"judge-model-1"}
    assert client.models_seen == ["judge-model-1"]


def test_new_battery_verdict_uses_the_configured_model_when_none_is_passed():
    from helicon.battery import run_llm_tests
    client = _FakeClient(_REPLY)
    client._helicon_models = {"default": "configured-model"}
    out = run_llm_tests(client, "a task", _HITS)
    assert out and {r["judged_by"] for r in out} == {"configured-model"}


def test_label_without_a_known_model_is_llm_never_a_vendor():
    assert judge_label(object()) == "llm"
    assert judge_label(object(), "m") == "m"


def test_old_and_new_labels_all_read_as_model_judged():
    for label in (OLD_LABEL, OLD_LABEL.upper(), "model", "llm", "judge-model-1",
                  "consensus (a + b)", "split_decision (a vs b)"):
        assert is_model_judged(label), label
    for label in (None, "", "deterministic", "probe", "human", "helicon", 0):
        assert not is_model_judged(label), label


def _print_battery(monkeypatch, tmp_path, capsys, results):
    from helicon import cli
    monkeypatch.setattr("helicon.config.load_config",
                        lambda path=None: {"db_path": str(tmp_path / "h.db")})
    monkeypatch.setattr("helicon.battery.run_battery", lambda *a, **kw: {
        "top_k": 5, "verdict": "x", "results": results, "context_tokens": 0,
        "last_scan": {"hours_ago": None, "stale": False},
        "llm_ran": True, "llm_tests": []})
    cli.cmd_battery(SimpleNamespace(task="a task", k=5, no_llm=True, json=False, prompt=False))
    return capsys.readouterr().out


def test_cli_marks_an_old_row_and_a_new_row_as_model_judged(monkeypatch, tmp_path, capsys):
    out = _print_battery(monkeypatch, tmp_path, capsys, [
        {"name": "Contradiction", "status": "FAIL", "reason": "old row", "judged_by": OLD_LABEL},
        {"name": "Grounding", "status": "PASS", "reason": "new row", "judged_by": "judge-model-1"},
        {"name": "Freshness", "status": "PASS", "reason": "no label"},
        {"name": "Relevance", "status": "PASS", "reason": "by rule", "judged_by": "deterministic"},
    ])
    lines = {ln.split("]")[1].split()[0]: ln for ln in out.splitlines() if ln.startswith("  [")}
    assert lines["Contradiction"].endswith("(model)")
    assert lines["Grounding"].endswith("(model)")
    assert "(model)" not in lines["Freshness"]
    assert "(model)" not in lines["Relevance"]
