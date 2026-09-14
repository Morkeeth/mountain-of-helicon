"""A selected lesson travels through the context-packet adapter. Synthetic data only."""
import json

import pytest

from helicon import config
from helicon.context_packet import PacketError


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "helicon-home"
    monkeypatch.setenv("HELICON_HOME", str(h))
    monkeypatch.setattr(config, "helicon_home", lambda: str(h))
    import helicon.lesson_delivery as ld
    monkeypatch.setattr(ld, "helicon_home", lambda: str(h))
    return h


def _deliver(run_id="run-1", lesson="The review note is read-only for agents. Deliver text in chat."):
    from helicon.lesson_delivery import deliver_lesson
    import os
    fake_home = os.path.join(os.environ["HELICON_HOME"], "..", "fake-user-home")
    os.makedirs(os.path.join(fake_home, ".claude"), exist_ok=True)
    with open(os.path.join(fake_home, ".claude", "CLAUDE.md"), "w") as f:
        f.write("GLOBAL INSTRUCTION THAT MUST STAY OUT OF THE PACKET\n")
    from helicon.lesson_delivery import lesson_project
    lesson_project().mkdir(parents=True, exist_ok=True)
    (lesson_project() / "AGENTS.md").write_text("OTHER PROJECT TEXT THAT MUST STAY OUT\n")
    return deliver_lesson(lesson, "Lesson: " + lesson + "\nTask: <task>",
                          [{"path": "/tmp/notes_boundary.md", "line": 5, "date": "2026-09-09"}], run_id=run_id,
                          home=os.path.realpath(fake_home))


def test_packet_carries_only_the_lesson_and_consumes_with_a_receipt(home):
    from helicon.lesson_delivery import lesson_project, packet_state, _state
    from helicon.context_packet import ContextPackets
    d = _deliver()
    assert d["state"] == "issued"
    project = lesson_project()
    store = ContextPackets(_state(project) / "packets", _state(project) / "reviews", project=str(project))
    consumed = store.consume(d["packet_id"], d["recipient"], transport="local-stdio")
    sources = consumed["packet"]["sources"]
    assert [s["path"] for s in sources] == [str(project / "CLAUDE.md")]
    assert "read-only for agents" in sources[0]["content"]
    assert "2026-09-09" in sources[0]["content"]
    blob = json.dumps(consumed)
    assert "MUST STAY OUT" not in blob
    assert packet_state(d["packet_id"], d["recipient"])["state"] == "consumed"


def test_a_newer_lesson_makes_the_old_packet_refuse(home):
    from helicon.lesson_delivery import lesson_project, _state
    from helicon.context_packet import ContextPackets
    old = _deliver("run-old")
    _deliver("run-new", lesson="A different, later lesson for the review note.")
    project = lesson_project()
    store = ContextPackets(_state(project) / "packets", _state(project) / "reviews", project=str(project))
    with pytest.raises(PacketError):
        store.consume(old["packet_id"], old["recipient"])


def test_personal_material_is_never_issued(home):
    with pytest.raises(ValueError):
        _deliver(lesson="Move the wallet seed phrase into the review note.")
    from helicon.lesson_delivery import lesson_project
    assert not (lesson_project() / "CLAUDE.md").exists()
