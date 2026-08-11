"""`report --json` must refuse to exit 0 on a document that says nothing.

The sibling test (test_report_json_is_only_json.py) pins that stdout carries the
document and nothing else. That fixed the corruption but not the accountability:
a report that produced an empty dict, or one missing the very numbers it exists
to publish, would still print something JSON-shaped, still exit 0, and the
nightly would promote it over a good baseline and go green on nothing.

A command that produces no usable output and calls that success is the exact
defect this project exists to catch.
"""
import json

import pytest

from helicon.cli import _REPORT_GRADED_PATHS, _report_must_say_something


def _good_report():
    """The shape docdrift.EVAL_CLAIMS actually reads."""
    return {
        "track": "MemoryAgent",
        "overall": "DEGRADED",
        "sub_goals": {
            "efficient_storage_retrieval": {"precision_at_3": 0.6, "mrr": 0.59, "query_count": 13},
            "timely_forgetting": {"decay_predicts_human_kills_auc": 0.78},
        },
    }


def _check(rep):
    _report_must_say_something(rep, json.dumps(rep, default=str))


def test_a_complete_report_passes():
    _check(_good_report())  # must not raise


@pytest.mark.parametrize("empty", [{}, None, [], "", 0])
def test_an_empty_report_exits_nonzero(empty):
    with pytest.raises(SystemExit) as e:
        _check(empty)
    assert e.value.code != 0


@pytest.mark.parametrize("path", _REPORT_GRADED_PATHS)
def test_a_report_missing_a_graded_field_exits_nonzero(path):
    """Each of the four independently. Dropping one and still exiting 0 would
    let docdrift check a prose claim against a hole."""
    rep = _good_report()
    parent, _, leaf = path.rpartition(".")
    node = rep
    for part in parent.split("."):
        node = node[part]
    del node[leaf]

    with pytest.raises(SystemExit) as e:
        _check(rep)
    assert e.value.code != 0
    assert path in str(e.value.code), "the message must name the field that is missing"


def test_a_measured_null_is_a_real_answer():
    """Present-and-null is PRESENT. `decay_predicts_human_kills_auc: null` means
    the benchmark ran and could not score — an honest unmeasured number. Failing
    on it would push the report toward inventing one, which is the failure this
    repo exists to prevent, not a stricter version of the guard."""
    rep = _good_report()
    rep["sub_goals"]["timely_forgetting"]["decay_predicts_human_kills_auc"] = None
    _check(rep)  # must not raise


def test_cmd_report_actually_calls_the_guard(monkeypatch, tmp_path, capsys):
    """Pins the WIRING, not just the helper.

    Every test above calls `_report_must_say_something` directly, so all of them
    stay green if someone deletes the one line in `cmd_report` that calls it —
    and the command goes back to exiting 0 on nothing with a full green suite
    vouching for it. This test drives the command itself.
    """
    import helicon.config
    import helicon.db
    import helicon.report
    from helicon.cli import cmd_report

    monkeypatch.setattr(helicon.config, "load_config", lambda *a, **k: {"db_path": str(tmp_path / "t.db")})
    monkeypatch.setattr(helicon.report, "memoryagent_report", lambda *a, **k: {})

    class _Args:
        llm = False
        json = True

    with pytest.raises(SystemExit) as e:
        cmd_report(_Args())
    assert e.value.code != 0
    assert not capsys.readouterr().out.strip(), "nothing may reach stdout when the report is refused"


def test_an_unserializable_document_exits_nonzero():
    """Belt and braces on the original failure mode: whatever reaches stdout
    must parse, and this command finds that out rather than the shell guard in
    scripts/nightly.sh finding out for it six hours later."""
    with pytest.raises(SystemExit) as e:
        _report_must_say_something(_good_report(), "No Qwen key; running deterministic-only.\n{}")
    assert e.value.code != 0
