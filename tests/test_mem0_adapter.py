"""Mem0 read-side adapter: mapping, temporal tags, opt-in behavior."""
from helicon.connectors import CONNECTORS, mem0

FAKE_ITEMS = [
    {
        "id": "m-1",
        "memory": "Oscar prefers BYOK distribution for Mount Helicon",
        "created_at": "2026-07-01T10:00:00Z",
        "updated_at": "2026-07-01T10:00:00Z",
        "categories": ["preferences"],
    },
    {
        "id": "m-2",
        "memory": "The deploy target is Alibaba ECS",
        "created_at": "2026-06-20T09:00:00Z",
        "updated_at": "2026-07-03T18:00:00Z",  # rewritten later
        "expiration_date": "2026-07-10T00:00:00Z",
        "categories": ["infra"],
    },
    {"id": "m-3", "memory": "   "},  # empty text -> dropped
]


def test_mem0_absent_config_returns_empty():
    assert mem0.scan({}) == []


def test_mem0_registered_as_connector():
    assert "mem0" in CONNECTORS


def test_mem0_platform_mapping(monkeypatch):
    monkeypatch.setattr(mem0, "_fetch_platform", lambda k, u, l: FAKE_ITEMS)
    results = mem0.scan({"api_key": "k", "user_id": "oscar"})

    assert len(results) == 2  # empty memory dropped
    assert all(r.source == "mem0" for r in results)
    assert all(r.type == "mem0_memory" for r in results)
    assert results[0].source_ref == "mem0/oscar/m-1"
    assert results[0].created_at == "2026-07-01T10:00:00Z"
    assert "preferences" in results[0].tags


def test_mem0_temporal_tags(monkeypatch):
    monkeypatch.setattr(mem0, "_fetch_platform", lambda k, u, l: FAKE_ITEMS)
    results = mem0.scan({"api_key": "k", "user_id": "oscar"})

    stable, rewritten = results[0], results[1]
    assert "rewritten" not in stable.tags
    assert "rewritten" in rewritten.tags
    assert "expiring" in rewritten.tags
    assert rewritten.metadata["updated_at"] == "2026-07-03T18:00:00Z"
    assert rewritten.metadata["expiration_date"] == "2026-07-10T00:00:00Z"


def test_mem0_api_error_returns_empty(monkeypatch, capsys):
    def boom(k, u, l):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(mem0, "_fetch_platform", boom)
    assert mem0.scan({"api_key": "k"}) == []
    assert "mem0" in capsys.readouterr().out


def test_mem0_local_mode_without_sdk(capsys):
    # no mem0ai installed in the test env: must hint and return [], not crash
    results = mem0.scan({"local": True, "user_id": "oscar"})
    assert results == []
