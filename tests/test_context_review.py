import hashlib
from datetime import datetime, timezone

from helicon.context_review import context_review


def setup(tmp_path, text):
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    project.mkdir()
    (project / ".git").mkdir()
    (project / "AGENTS.md").write_bytes(text.encode())
    return home, project


def test_signal_exact_subject_and_noise_other_subject(tmp_path):
    home, project = setup(tmp_path, "Alpha phase = Build\nAlpha phase = Review\nBeta phase = Build\nGamma phase = Review\n")
    report = context_review(home, project)
    assert len(report["findings"]) == 1  # One physical issue, two candidate routes.
    assert report["findings"][0]["harnesses"] == ["codex", "cursor"]
    assert len(report["findings"][0]["check_ids"]) == 2
    assert all("Alpha" in f["title"] for f in report["findings"])
    assert all(len(f["evidence"]) == 2 for f in report["findings"])
    assert not any(s["loading"]["state"] == "observed" for s in report["sources"])


def test_exact_utf8_crlf_spans_and_stable_finding(tmp_path):
    home, project = setup(tmp_path, "é\r\nAlpha phase = Build\r\nAlpha phase = Review\r\n")
    first = context_review(home, project)
    data = (project / "AGENTS.md").read_bytes()
    for evidence in first["findings"][0]["evidence"]:
        assert data[evidence["start_byte"]:evidence["end_byte"]].decode() == evidence["quote"]
        assert evidence["quote"].endswith("\r\n")
    (project / "AGENTS.md").write_bytes(b"Intro\n" + data)
    second = context_review(home, project)
    assert first["findings"][0]["id"] == second["findings"][0]["id"]
    assert first["findings"][0]["evidence_revision"] != second["findings"][0]["evidence_revision"]


def test_history_examples_quotes_and_conditions_are_not_current_claims(tmp_path):
    home, project = setup(tmp_path, "Alpha phase = Build\n```\nAlpha phase = Review\n```\n> Alpha phase = Review\nIf Alpha phase = Review\n## History\nAlpha phase = Review\n## Current\nBeta phase = Review\n")
    assert context_review(home, project)["findings"] == []


def test_path_probe_is_exact_no_basename_rescue_and_no_commands(tmp_path):
    home, project = setup(tmp_path, "`docs/current.md` exists\nRead `docs/guide.md`\n`../other.md` exists\n`$(touch hacked)` exists\n")
    (project / "current.md").write_text("different object")
    report = context_review(home, project)
    probes = [c["probe"] for c in report["claims"]]
    assert all(p["command"] is None for p in probes)
    assert any(p["verdict"] == "unknown" for p in probes)
    assert any(p["verdict"] == "contradicted" and p["object"].endswith("docs/current.md") for p in probes)
    assert not (project / "hacked").exists()


def test_missing_empty_invalid_utf8_are_separate(tmp_path):
    home, project = setup(tmp_path, "")
    (project / "CLAUDE.md").write_bytes(b"\xff")
    sources = context_review(home, project)["sources"]
    assert any(s["status"] == "empty" for s in sources)
    assert any(s["status"] == "unreadable" and s["sha256"] is None for s in sources)
    assert any(s["status"] == "missing" and not s["checks_completed"] for s in sources)


def test_receipts_bind_run_project_harness_path_and_current_hash(tmp_path):
    home, project = setup(tmp_path, "Alpha phase = Build\n")
    receipt = dict(schema="helicon.context-loading-receipt/1", project=str(project), harness="codex",
                   path=str(project / "AGENTS.md"), sha256=hashlib.sha256((project / "AGENTS.md").read_bytes()).hexdigest(),
                   run_id="synthetic-test-run", event="context_loaded", observed_at=datetime.now(timezone.utc).isoformat())
    sources = context_review(home, project, [receipt])["sources"]
    assert sum(s["loading"]["state"] == "observed" for s in sources) == 1
    for key, wrong in (("project", str(home)), ("sha256", "0" * 64), ("run_id", ""), ("schema", "bogus"), ("observed_at", "2999-01-01T00:00:00Z")):
        assert not any(s["loading"]["state"] == "observed" for s in context_review(home, project, [dict(receipt, **{key: wrong})])["sources"])


def test_unrelated_memory_and_skill_claims_do_not_conflict(tmp_path):
    home, project = setup(tmp_path, "Alpha phase = Build\n")
    memory = home / ".claude/projects/foreign/memory/MEMORY.md"
    memory.parent.mkdir(parents=True)
    memory.write_text("Alpha phase = Review\n")
    assert context_review(home, project)["findings"] == []


def test_changed_source_invalidates_evidence(monkeypatch, tmp_path):
    import helicon.context_review as module
    home, project = setup(tmp_path, "Alpha phase = Build\nAlpha phase = Review\n")
    original, calls = module._read, {}

    def moving(path):
        calls[str(path)] = calls.get(str(path), 0) + 1
        if path.name == "AGENTS.md" and path.parent == project and calls[str(path)] >= 3:
            path.write_text("Alpha phase = Build\n")
        return original(path)

    monkeypatch.setattr(module, "_read", moving)
    report = context_review(home, project)
    assert report["findings"] == []
    assert any(s["status"] == "changed" for s in report["sources"])
    assert any(c["status"] == "unknown" for c in report["coverage"]["checks"])


def test_natural_static_count_binds_exact_object_not_other_server(tmp_path):
    home, project = setup(tmp_path, "- MCP Server (23 tools for local use)\n- Other MCP Server (99 tools for remote use)\n")
    target = project / "helicon/mcp_server.py"
    target.parent.mkdir()
    target.write_text("TOOLS = [{'name':'first'}, {'name':'second'}]\nraise RuntimeError('must not execute')\n")
    report = context_review(home, project)
    assert len(report["claims"]) == 2  # One declaration per candidate harness.
    assert all(c["value"] == 23 and c["probe"]["output"]["declared_tools"] == 2 for c in report["claims"])
    assert len(report["findings"]) == 1
    assert all(f["probe"]["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest() for f in report["findings"])
    target.write_text("TOOLS = generate_dynamically()\n")
    unknown = context_review(home, project)
    assert all(c["probe"]["verdict"] == "unknown" for c in unknown["claims"])
    assert all(c["status"] == "unknown" for c in unknown["coverage"]["checks"] if c["id"].startswith("instruction-claims:") and c["id"] != "instruction-claims:claude")


def test_claim_removed_keeps_complete_extractor_population(tmp_path):
    home, project = setup(tmp_path, "Alpha phase = Build\nAlpha phase = Review\n")
    first = context_review(home, project)
    (project / "AGENTS.md").write_text("Nothing declared here.\n")
    second = context_review(home, project)
    assert not second["findings"]
    before = next(c for c in first["coverage"]["checks"] if c["id"] == "instruction-claims:codex")
    after = next(c for c in second["coverage"]["checks"] if c["id"] == "instruction-claims:codex")
    assert before == after


def test_home_pointer_uses_reviewed_home_not_process_home(tmp_path):
    home, project = setup(tmp_path, "Read `~/.claude/reference/missing.md`\n")
    report = context_review(home, project)
    assert any(c["subject"] == str(home / ".claude/reference/missing.md") for c in report["claims"])
    assert all("/~" not in c["subject"] for c in report["claims"])


def test_probe_failure_is_unknown_not_negative(monkeypatch, tmp_path):
    import helicon.context_review as module
    home, project = setup(tmp_path, "`docs/current.md` exists\n")
    monkeypatch.setattr(module, "_exists", lambda path: None)
    report = context_review(home, project)
    assert all(c["probe"]["verdict"] == "unknown" for c in report["claims"])
    assert all(c["status"] == "unknown" for c in report["coverage"]["checks"] if c["id"] in report["findings"][0]["check_ids"])


def test_probe_object_changed_invalidates_finding(monkeypatch, tmp_path):
    import helicon.context_review as module
    home, project = setup(tmp_path, "MCP Server (23 tools)\n")
    target = project / "helicon/mcp_server.py"
    target.parent.mkdir()
    target.write_text("TOOLS = [{'name':'first'}]\n")
    original, calls = module._read, []

    def changing(path):
        if path == target:
            calls.append(path)
            if len(calls) >= 3:
                target.write_text("TOOLS = []\n")
        return original(path)

    monkeypatch.setattr(module, "_read", changing)
    report = context_review(home, project)
    assert not report["findings"]
    assert any(s["status"] == "changed" and s["path"] == str(target) for s in report["sources"])
