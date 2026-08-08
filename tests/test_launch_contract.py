from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_launch_surfaces_use_canonical_identity():
    surfaces = [
        "README.md",
        "DEMO.md",
        "action.yml",
        "web/public/welcome.html",
        "web/src/components/Landing.tsx",
    ]
    for path in surfaces:
        text = _read(path)
        assert "MorkeethHQ/mount-helicon" not in text, path
        assert "Mount Helicon" not in text, path
    assert "Morkeeth/mountain-of-helicon" in _read("README.md")


def test_launch_copy_matches_warning_default():
    readme = _read("README.md")
    demo = _read("DEMO.md")
    assert "warns by default" in readme
    assert "run is actually stopped" not in readme
    assert "refuses to let a run start" not in readme
    assert "refused in the terminal" not in demo
    assert "warning in the terminal" in demo


def test_readme_leads_with_working_terminal_demo():
    readme = _read("README.md")
    demo_pos = readme.index("bash scripts/demo.sh")
    dashboard_pos = readme.index("helicon demo")
    assert demo_pos < dashboard_pos


def test_github_action_installs_current_repository():
    action = _read("action.yml")
    assert "github.com/Morkeeth/mountain-of-helicon.git" in action


def test_release_workflow_covers_product_not_only_memory_exam():
    workflow = _read(".github/workflows/memory-ci.yml")
    for command in (
        "python -m pytest -q",
        "npm run lint",
        "npm run build",
        "python -m build",
        "python -m twine check",
    ):
        assert command in workflow


def test_example_server_is_local_only_and_has_no_fake_key():
    config = _read("config.example.json")
    assert '"host": "127.0.0.1"' in config
    assert "sk-your-qwen-api-key" not in config
