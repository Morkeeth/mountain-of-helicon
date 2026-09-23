"""Evidence committed under bench/ must not carry a machine owner's home paths.

The adversarial eval of 22 Sep 2026 saved child-agent output verbatim. Its first
commit carried absolute home paths and a quote of the operator's private user-level
instruction files. Those were redacted to `$HOME` before the branch was pushed.
This test is the gate that keeps the next saved transcript from reintroducing them.
It has been seen failing: against the unredacted branch it lists 17 lines in three
result files.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent / "bench"
# An absolute home directory with a real user name. `$HOME`, `~` and `<user>` pass.
HOME_PATH = re.compile(r"(?:/Users|/home)/(?!runner\b|<)[A-Za-z0-9._-]+/")
TEXT = {".md", ".json", ".jsonl", ".py", ".txt", ".sh", ".toml", ".yaml", ".yml"}


def offending_lines(root: pathlib.Path = ROOT) -> list[str]:
    hits = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in TEXT:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for n, line in enumerate(text.splitlines(), 1):
            if HOME_PATH.search(line):
                hits.append(f"{p.relative_to(root)}:{n}")
    return hits


def test_no_home_paths_in_bench():
    hits = offending_lines()
    assert not hits, "absolute home paths in bench/ evidence:\n" + "\n".join(hits[:40])


def test_pattern_catches_a_home_path(tmp_path):
    # The control: a check nobody has seen fail is not a check.
    (tmp_path / "row.jsonl").write_text('{"bash_cmds": ["ls /Users/alice/repo"]}\n')
    (tmp_path / "ok.md").write_text("run root under $HOME/.local/state and ~/CODE\n")
    assert offending_lines(tmp_path) == ["row.jsonl:1"]
