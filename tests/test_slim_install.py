"""The default install is the deterministic review, and only that.

The README promises `helicon review` needs no key, no database and no upload. A
default install that also pulls openai, fastapi, uvicorn and numpy contradicts the
promise at the one moment a stranger looks: `pip list`. These tests pin the shape
of the install rather than a number of packages, so they fail for the right reason.
"""
import ast
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

# Packages used only by the web app, the memory/retrieval lab, embeddings or
# model-backed commands. None of them may be a default dependency.
HEAVY = {"openai", "fastapi", "uvicorn", "numpy", "starlette", "pydantic",
         "sentence-transformers", "requests"}


def _requirement_name(spec: str) -> str:
    return re.split(r"[\s\[<>=!~;]", spec.strip(), maxsplit=1)[0].lower().replace("_", "-")


# A TOML array of strings, with comments allowed between entries. The array may hold
# `pkg[extra]` inside its quotes, so the closing bracket is found by grammar, not by
# the first `]`.
_ARRAY = r'\[((?:\s|,|#[^\n]*|"[^"\n]*")*)\]'


def _string_list(block: str) -> list[str]:
    body = re.sub(r"(?m)#.*$", "", block)
    return re.findall(r'"([^"]+)"', body)


def _default_dependencies() -> list[str]:
    match = re.search(rf"(?m)^dependencies\s*=\s*{_ARRAY}", PYPROJECT)
    assert match, "pyproject.toml declares no [project].dependencies list"
    return _string_list(match.group(1))


def _extras() -> dict[str, list[str]]:
    section = re.search(
        r"(?ms)^\[project\.optional-dependencies\]\n(.*?)(?=^\[|\Z)", PYPROJECT)
    assert section, "pyproject.toml declares no optional-dependencies"
    extras = {}
    for name, block in re.findall(rf"(?m)^([a-z][a-z-]*)\s*=\s*{_ARRAY}", section.group(1)):
        extras[name] = _string_list(block)
    return extras


def test_default_dependencies_exclude_web_model_and_retrieval_packages():
    default = {_requirement_name(spec) for spec in _default_dependencies()}
    assert default.isdisjoint(HEAVY), (
        f"default install pulls {sorted(default & HEAVY)}; they belong behind an extra")


def test_default_dependencies_are_only_what_the_package_imports():
    """A declared dependency nothing imports is weight for every stranger."""
    unused = {"pyyaml", "gitpython"}
    default = {_requirement_name(spec) for spec in _default_dependencies()}
    assert default.isdisjoint(unused), (
        f"{sorted(default & unused)} are declared but imported nowhere in helicon/")


def _third_party_imports() -> dict[str, set[str]]:
    """top-level third-party module -> files that import it, from the AST."""
    stdlib = set(sys.stdlib_module_names)
    found: dict[str, set[str]] = {}
    for path in (ROOT / "helicon").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top not in stdlib and top != "helicon":
                    found.setdefault(top, set()).add(str(path.relative_to(ROOT)))
    return found


# Modules helicon imports that are NOT ours to declare: `scripts` is the repo's own
# top-level directory; mem0 and neo4j are connectors the user opts into with their
# own driver, and each connector prints its own install line when it is absent.
EXTERNAL_BY_DESIGN = {"scripts", "mem0", "neo4j"}
IMPORT_TO_DISTRIBUTION = {"sentence_transformers": "sentence-transformers"}


def test_every_third_party_import_is_declared_somewhere():
    declared = {_requirement_name(s) for s in _default_dependencies()}
    for specs in _extras().values():
        declared |= {_requirement_name(s) for s in specs}
    missing = {
        module: sorted(files)[:2]
        for module, files in _third_party_imports().items()
        if module not in EXTERNAL_BY_DESIGN
        and IMPORT_TO_DISTRIBUTION.get(module, module).lower() not in declared
    }
    assert not missing, f"imported but declared in no extra: {missing}"


def test_all_extra_is_the_union_of_the_others():
    extras = _extras()
    assert "all" in extras
    named = {n for spec in extras["all"] for n in re.findall(r"\[(.*?)\]", spec)}
    named = {part.strip() for group in named for part in group.split(",")}
    assert {"web", "model", "retrieval", "embeddings"} <= named


# ---- behaviour: run the real command with the optional packages made unimportable ----

BLOCK = textwrap.dedent('''
    import sys
    from importlib.abc import MetaPathFinder

    OPTIONAL = {"openai", "fastapi", "uvicorn", "numpy", "starlette", "pydantic",
                "sentence_transformers", "requests", "yaml", "git"}

    ATTEMPTED = []

    class Block(MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in OPTIONAL:
                ATTEMPTED.append(name)
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    sys.meta_path.insert(0, Block())
''')


def _run_slim(tmp_path: Path, *cli_args: str, code: str | None = None):
    home = tmp_path / "empty-home"
    home.mkdir(exist_ok=True)
    body = code or (
        "import sys\nfrom helicon.cli import main\n"
        f"sys.argv = ['helicon', *{list(cli_args)!r}]\nmain()\n"
    )
    env = {**os.environ, "HOME": str(home), "NO_COLOR": "1", "PYTHONPATH": str(ROOT),
           "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("QWEN_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY", "HELICON_EXECUTE"):
        env.pop(key, None)
    return subprocess.run([sys.executable, "-c", BLOCK + body], env=env,
                          capture_output=True, text=True, cwd=str(tmp_path), timeout=120)


def _fixture(tmp_path: Path, *, broken: bool) -> Path:
    repo = tmp_path / ("broken" if broken else "clean")
    (repo / "docs").mkdir(parents=True)
    # One claim, and it is false: 1 of 1 contradicted is grade F. A clean repo keeps
    # the same shape with a pointer that resolves.
    lines = ["# Agent instructions", ""]
    if broken:
        lines.append("Read [deploy](docs/deployment.md).")
    else:
        (repo / "docs" / "setup.md").write_text("# Setup\n", encoding="utf-8")
        lines.append("Read [setup](docs/setup.md).")
    (repo / "AGENTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return repo


def test_review_finds_the_broken_pointer_with_no_optional_package_importable(tmp_path):
    repo = _fixture(tmp_path, broken=True)
    result = _run_slim(tmp_path, "review", str(repo))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "AGENTS.md:3" in result.stdout
    assert "docs/deployment.md" in result.stdout
    assert "GRADE F" in result.stdout
    assert "Traceback" not in result.stderr


def test_review_passes_a_clean_repo_and_never_asks_for_an_optional_package(tmp_path):
    repo = _fixture(tmp_path, broken=False)
    code = textwrap.dedent(f'''
        import sys
        from helicon.cli import main
        sys.argv = ["helicon", "review", {str(repo)!r}]
        try:
            main()
        finally:
            print("ATTEMPTED:" + ",".join(ATTEMPTED))
    ''')
    result = _run_slim(tmp_path, code=code)
    assert result.returncode == 0, result.stdout + result.stderr
    # An import attempt swallowed by a try/except still counts: the review path must
    # not so much as ask for an optional package.
    assert result.stdout.rstrip().splitlines()[-1] == "ATTEMPTED:"
    assert "GRADE A" in result.stdout


@pytest.mark.parametrize("argv, extra", [
    (["serve"], "web"),
    (["demo"], "web"),
])
def test_a_command_missing_its_extra_prints_one_install_line(tmp_path, argv, extra):
    result = _run_slim(tmp_path, *argv)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr, result.stderr
    message = (result.stdout + result.stderr).strip()
    assert f'pip install "mountain-of-helicon[{extra}]"' in message
    assert len([line for line in message.splitlines() if "pip install" in line]) == 1


def test_the_keyword_only_retrieval_path_imports_without_numpy(tmp_path):
    """embeddings.py holds the context policy every retrieval path ends in, including
    the FTS fallback a store takes before its first `helicon embed`."""
    code = textwrap.dedent('''
        import helicon.embeddings as e
        from helicon import snapshots
        print("imported")
        try:
            e._normalize([1.0])
        except ModuleNotFoundError as missing:
            print("numpy-named:" + missing.name)
    ''')
    result = _run_slim(tmp_path, code=code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "imported" in result.stdout
    assert "numpy-named:numpy" in result.stdout


def test_the_idle_notice_still_speaks_without_the_web_extra(tmp_path):
    """The doorway hook records its once-per-session row without importing fastapi.
    Before this, the import raised, a blanket except swallowed it, and the notice
    silently never fired on a default install."""
    code = textwrap.dedent('''
        import os
        from helicon import fleet
        from helicon.cli import _idle_notice_once
        fleet.idle_notice = lambda exclude_session="": "IDLE THINGS"
        os.environ["HELICON_HOME"] = os.getcwd()
        print("first:" + _idle_notice_once("session-a"))
        print("second:" + _idle_notice_once("session-a"))
    ''')
    result = _run_slim(tmp_path, code=code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "first:IDLE THINGS" in result.stdout
    assert "second:\n" in result.stdout + "\n"
