"""Two false alarms found on 20 Nov 2026 by running `helicon review` on public repos.

Both shapes were copied from real instruction files, then cut down:

1. mattpocock/skills CLAUDE.md says "bucket folders under `skills/`" and then lists
   `engineering/`, `misc/` and the others on their own lines. Every one exists under
   skills/. Helicon graded all five as missing, because a single-segment directory has
   no tail for the suffix rule and the parent was named on an earlier line.
2. benchflow-ai/agents acp-registry/AGENTS.md writes "config.toml [[providers]]".
   That is a TOML array-of-tables header, not an Obsidian note link. Helicon graded
   three of them as missing notes.

Each fix keeps its red path: a child that is not under the named parent, and a real
missing wikilink, are still flagged.
"""
from __future__ import annotations

import os
import tempfile

from helicon import pointers


def _repo(files: dict[str, str]) -> str:
    d = tempfile.mkdtemp()
    for rel, body in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    return d


BUCKETS = (
    "Skills are organized into bucket folders under `skills/`:\n"
    "\n"
    "- `engineering/`: daily code work\n"
    "- `misc/`: rarely used\n"
    "\n"
    "Skills in `misc/` get no docs page.\n"
)


def test_dirs_listed_under_a_parent_named_earlier_in_the_file_resolve():
    d = _repo({
        "skills/engineering/a/SKILL.md": "x\n",
        "skills/misc/b/SKILL.md": "x\n",
        "CLAUDE.md": BUCKETS,
    })
    res = pointers.check_pointers(d)
    raws = {r["raw"] for r in res["receipts"]}
    assert "`engineering/`" not in raws, res["receipts"]
    assert "`misc/`" not in raws, res["receipts"]
    assert res["verdict"] == "CLEAN", res


def test_a_listed_dir_missing_under_the_named_parent_is_still_flagged():
    d = _repo({
        "skills/engineering/a/SKILL.md": "x\n",
        "CLAUDE.md": BUCKETS,                      # misc/ exists nowhere
    })
    res = pointers.check_pointers(d)
    raws = {r["raw"] for r in res["receipts"]}
    assert "`misc/`" in raws, res["receipts"]
    assert "`engineering/`" not in raws


TOML_LINE = (
    "| VT Code | routes via a launch-written vtcode.toml [[custom_providers]] (base_url) |\n"
    "| Vibe | writes ~/.vibe/config.toml [[providers]] and [[models]] active_model |\n"
)


def test_toml_array_of_tables_on_a_toml_line_is_not_a_note_link():
    d = _repo({"AGENTS.md": TOML_LINE})
    res = pointers.check_pointers(d)
    raws = {r["raw"] for r in res["receipts"]}
    assert not any(r.startswith("[[") for r in raws), res["receipts"]


def test_a_missing_note_link_is_still_flagged_next_to_toml_words():
    d = _repo({"AGENTS.md": TOML_LINE + "Read [[Deploy Runbook]] before a release.\n"})
    res = pointers.check_pointers(d)
    raws = {r["raw"] for r in res["receipts"]}
    assert "[[Deploy Runbook]]" in raws, res["receipts"]
    assert "[[providers]]" not in raws
