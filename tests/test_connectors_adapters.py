"""Tests for the Letta MemFS and Graphiti store adapters.

Letta: real temp git repo fixture (fixtures in unit tests are fine — the
zero-fake-data rule is about demos/stats, not test scaffolding).
Graphiti: neo4j driver fully mocked; verifies field mapping incl. the
bi-temporal metadata and every graceful-degrade path.
"""
import builtins
import os
import subprocess

import pytest

from glaze.connectors import CONNECTORS, letta_memfs, graphiti
from glaze.models import ConnectorResult


# ---------------------------------------------------------------- letta-memfs

MEMFS_COMMIT_DATE = "2026-06-15T10:30:00+02:00"


@pytest.fixture
def memfs_repo(tmp_path):
    """A minimal Letta Code context repository: git repo of markdown memory
    files with YAML frontmatter and a system/ dir."""
    repo = tmp_path / "memfs"
    (repo / "system").mkdir(parents=True)

    (repo / "system" / "persona.md").write_text(
        "---\n"
        "description: Core persona block, always loaded\n"
        "---\n"
        "# Persona\n"
        "You are a careful coding agent.\n"
        "\n"
        "# Tone\n"
        "Terse, no cheerleading.\n"
    )
    (repo / "project-notes.md").write_text(
        "---\n"
        "description: Notes about the demo project\n"
        "---\n"
        "# Build\n"
        "Run make build before tests.\n"
    )
    # No frontmatter at all — must still parse.
    (repo / "scratch.md").write_text("# Scratch\nRemember to rotate the API key.\n")

    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": MEMFS_COMMIT_DATE,
        "GIT_COMMITTER_DATE": MEMFS_COMMIT_DATE,
        "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
    }
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-q", "-m", "seed memfs"]):
        subprocess.run(cmd, cwd=repo, env=env, check=True, capture_output=True)
    return repo


def test_letta_memfs_absent_config_returns_empty():
    assert letta_memfs.scan({}) == []


def test_letta_memfs_missing_dir_returns_empty(tmp_path, capsys):
    assert letta_memfs.scan({"memfs_dir": str(tmp_path / "nope")}) == []
    assert "letta-memfs" in capsys.readouterr().out


def test_letta_memfs_section_level_cubes(memfs_repo):
    results = letta_memfs.scan({"memfs_dir": str(memfs_repo)})
    # persona.md has 2 sections, project-notes.md 1, scratch.md 1
    assert len(results) == 4
    assert all(isinstance(r, ConnectorResult) for r in results)
    assert all(r.source == "letta-memfs" for r in results)
    assert all(r.type == "letta_memory" for r in results)
    assert all("letta-memfs" in r.tags for r in results)

    by_ref = {r.source_ref: r for r in results}
    persona = by_ref["memfs/system/persona.md#persona"]
    tone = by_ref["memfs/system/persona.md#tone"]
    assert persona.content == "You are a careful coding agent."
    assert tone.content == "Terse, no cheerleading."
    assert persona.metadata["heading"] == "Persona"
    assert persona.metadata["is_system"] is True
    assert "system" in persona.tags

    notes = by_ref["memfs/project-notes.md#build"]
    assert notes.metadata["is_system"] is False
    assert "system" not in notes.tags


def test_letta_memfs_frontmatter_description_in_metadata(memfs_repo):
    results = letta_memfs.scan({"memfs_dir": str(memfs_repo)})
    by_file = {}
    for r in results:
        by_file.setdefault(r.metadata["file"], r)
    assert by_file[os.path.join("system", "persona.md")].metadata["description"] == \
        "Core persona block, always loaded"
    assert by_file["project-notes.md"].metadata["description"] == \
        "Notes about the demo project"
    assert by_file["scratch.md"].metadata["description"] == ""


def test_letta_memfs_created_at_from_git(memfs_repo):
    results = letta_memfs.scan({"memfs_dir": str(memfs_repo)})
    assert results
    for r in results:
        assert r.created_at == MEMFS_COMMIT_DATE
        assert r.metadata["created_from"] == "git"


def test_letta_memfs_mtime_fallback_when_not_git(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    (d / "note.md").write_text("# A\nbody\n")
    results = letta_memfs.scan({"memfs_dir": str(d)})
    assert len(results) == 1
    assert results[0].metadata["created_from"] == "mtime"
    assert results[0].created_at  # non-empty ISO string


def test_letta_memfs_uncommitted_file_falls_back_to_mtime(memfs_repo):
    (memfs_repo / "fresh.md").write_text("# Fresh\nnot committed yet\n")
    results = letta_memfs.scan({"memfs_dir": str(memfs_repo)})
    fresh = [r for r in results if r.metadata["file"] == "fresh.md"]
    assert len(fresh) == 1
    assert fresh[0].metadata["created_from"] == "mtime"


# ------------------------------------------------------------------- graphiti

class FakeRecord:
    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class FakeSession:
    def __init__(self, records, fail=False):
        self.records = records
        self.fail = fail
        self.last_query = None
        self.last_params = None

    def run(self, query, **params):
        if self.fail:
            raise RuntimeError("connection refused")
        self.last_query = query
        self.last_params = params
        return iter(self.records)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeDriver:
    def __init__(self, session):
        self._session = session

    def session(self, database=None):
        return self._session

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def fake_neo4j(monkeypatch):
    """Patch graphiti's lazy `from neo4j import GraphDatabase` and hand the
    test control of the returned records."""
    state = {"session": FakeSession([])}

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth=None):
            state["uri"] = uri
            state["auth"] = auth
            return FakeDriver(state["session"])

    import sys
    import types
    mod = types.ModuleType("neo4j")
    mod.GraphDatabase = FakeGraphDatabase
    monkeypatch.setitem(sys.modules, "neo4j", mod)
    return state


VALID_EDGE = {
    "uuid": "edge-1",
    "name": "USES_STACK",
    "fact": "Mount Helicon uses SQLite with FTS5 for cube storage",
    "group_id": "helicon",
    "created_at": "2026-06-01T09:00:00+00:00",
    "valid_at": "2026-05-20T00:00:00+00:00",
    "invalid_at": None,
    "expired_at": None,
    "episodes": ["ep-1", "ep-2"],
    "source_entity": "Mount Helicon",
    "target_entity": "SQLite",
}

INVALIDATED_EDGE = {
    "uuid": "edge-2",
    "name": "DEPLOYED_ON",
    "fact": "Helicon is deployed on Render",
    "group_id": "helicon",
    "created_at": "2026-06-01T09:00:00+00:00",
    "valid_at": "2026-05-01T00:00:00+00:00",
    "invalid_at": "2026-06-20T00:00:00+00:00",
    "expired_at": "2026-06-21T08:00:00+00:00",
    "episodes": ["ep-3"],
    "source_entity": "Helicon",
    "target_entity": "Render",
}


def test_graphiti_absent_config_returns_empty():
    assert graphiti.scan({}) == []


def test_graphiti_missing_driver_prints_hint(monkeypatch, capsys):
    real_import = builtins.__import__

    def no_neo4j(name, *args, **kwargs):
        if name == "neo4j":
            raise ImportError("No module named 'neo4j'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_neo4j)
    assert graphiti.scan({"uri": "bolt://localhost:7687"}) == []
    assert "pip install neo4j" in capsys.readouterr().out


def test_graphiti_connection_error_degrades(fake_neo4j, capsys):
    fake_neo4j["session"] = FakeSession([], fail=True)
    out = graphiti.scan({"uri": "bolt://localhost:7687", "user": "neo4j", "password": "x"})
    assert out == []
    assert "graphiti" in capsys.readouterr().out


def test_graphiti_field_mapping(fake_neo4j):
    fake_neo4j["session"] = FakeSession([FakeRecord(VALID_EDGE)])
    results = graphiti.scan({
        "uri": "bolt://localhost:7687", "user": "neo4j", "password": "pw",
    })
    assert len(results) == 1
    r = results[0]
    assert r.source == "graphiti"
    assert r.source_ref == "graphiti/edge-1"
    assert r.type == "graph_fact"
    assert r.title == "USES_STACK"
    assert r.content == VALID_EDGE["fact"]
    # created_at prefers valid_at (world time) over created_at (graph time)
    assert r.created_at == "2026-05-20T00:00:00+00:00"
    assert r.tags == ["graphiti"]
    # full bi-temporal fields + episode provenance in metadata
    m = r.metadata
    assert m["uuid"] == "edge-1"
    assert m["created_at"] == "2026-06-01T09:00:00+00:00"
    assert m["valid_at"] == "2026-05-20T00:00:00+00:00"
    assert m["invalid_at"] == ""
    assert m["expired_at"] == ""
    assert m["episodes"] == ["ep-1", "ep-2"]
    assert m["source_entity"] == "Mount Helicon"
    assert m["target_entity"] == "SQLite"
    assert m["group_id"] == "helicon"
    assert fake_neo4j["auth"] == ("neo4j", "pw")


def test_graphiti_invalidated_edge_gets_tag(fake_neo4j):
    fake_neo4j["session"] = FakeSession([FakeRecord(INVALIDATED_EDGE)])
    results = graphiti.scan({"uri": "bolt://x:7687"})
    assert len(results) == 1
    r = results[0]
    assert "invalidated" in r.tags
    assert r.metadata["invalid_at"] == "2026-06-20T00:00:00+00:00"
    assert r.metadata["expired_at"] == "2026-06-21T08:00:00+00:00"


def test_graphiti_created_at_falls_back_when_no_valid_at(fake_neo4j):
    edge = {**VALID_EDGE, "valid_at": None}
    fake_neo4j["session"] = FakeSession([FakeRecord(edge)])
    results = graphiti.scan({"uri": "bolt://x:7687"})
    assert results[0].created_at == "2026-06-01T09:00:00+00:00"


def test_graphiti_neo4j_temporal_objects_converted(fake_neo4j):
    class Neo4jDateTime:
        def iso_format(self):
            return "2026-06-05T12:00:00+00:00"

    edge = {**VALID_EDGE, "valid_at": Neo4jDateTime()}
    fake_neo4j["session"] = FakeSession([FakeRecord(edge)])
    results = graphiti.scan({"uri": "bolt://x:7687"})
    assert results[0].created_at == "2026-06-05T12:00:00+00:00"
    assert results[0].metadata["valid_at"] == "2026-06-05T12:00:00+00:00"


def test_graphiti_group_id_passed_to_query(fake_neo4j):
    session = FakeSession([])
    fake_neo4j["session"] = session
    graphiti.scan({"uri": "bolt://x:7687", "group_id": "my-group"})
    assert session.last_params["group_id"] == "my-group"
    graphiti.scan({"uri": "bolt://x:7687"})
    assert session.last_params["group_id"] is None


def test_graphiti_empty_fact_skipped(fake_neo4j):
    fake_neo4j["session"] = FakeSession([FakeRecord({**VALID_EDGE, "fact": "  "})])
    assert graphiti.scan({"uri": "bolt://x:7687"}) == []


# ------------------------------------------------------------------- registry

def test_adapters_registered_and_opt_in():
    assert CONNECTORS["letta-memfs"] is letta_memfs.scan
    assert CONNECTORS["graphiti"] is graphiti.scan
    # scan_all passes {} when a connector has no config block: both must
    # no-op silently in that case (opt-in behavior).
    assert letta_memfs.scan({}) == []
    assert graphiti.scan({}) == []
