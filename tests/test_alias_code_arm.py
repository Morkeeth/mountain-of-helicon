"""R4: a dead name in prose is rot; a dead name in a code path is an outage.

R4 reported 341 RELAY current-claims as a COUNT, with no way to tell which of
them a code path was executing. The distinction is worth drawing.

CORRECTION 2026-07-15: the motivating exemplar was misattributed. The story was
that agent:relay -> getAgent("relay") -> null blacked out FAVOUR's agent layer
for 13 days. The blackout is real; the rename did not cause it. `relay` was never
a key in AGENT_REGISTRY in any commit, 12 of 41 broken tasks predate the rename,
and getAgent("favour") returns null too. Updating the dead name would REPRODUCE
the outage under a live name — and this check would then say CLEAN. A dead name
is a weak proxy for a dangling reference; the honest check needs the registry.
These tests pin the capability, which stands; they do not endorse the story.

The precision limit is the whole design. "relay" and "glaze" are English words,
so this reports LEADS, not verdicts:
  - git ls-files only (879 files -> 149 in world-relay: no build output, no
    node_modules, no vendored OpenZeppelin governance relay())
  - the name as a COMPLETE quoted token, never a word inside prose
  - not comments (caught by the function flagging its own comments)
  - not lines naming both names (rename-aware, same rule the prose triage uses)
  - tests counted separately: once the outage was fixed, world-relay's
    agent:relay cases became the deliberate legacy contract
"""
import json
import subprocess

import pytest

from helicon.aliases import _code_rx, code_refs


def _repo(tmp_path, name, files: dict):
    r = tmp_path / name
    r.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    for rel, body in files.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "x"], cwd=r, check=True)
    return r


def test_the_real_outage_is_found(tmp_path):
    """world-relay/src/app/api/seed/route.ts:68 — the default that blacked out
    the agent layer for 13 days."""
    _repo(tmp_path, "world-relay", {
        "src/seed.ts": 'const agentId = t.agentId ? t.agentId : "relay";\n'})
    r = code_refs("relay", "favour", repos_dir=str(tmp_path))
    assert len(r["leads"]) == 1
    assert r["leads"][0]["file"] == "src/seed.ts"
    assert r["leads"][0]["line"] == 1


def test_a_dead_name_inside_prose_is_not_a_code_reference(tmp_path):
    """'Try RELAY Favours and tell us what you think' lives in a string literal
    and executes nothing. Matching the word would score it as a code path."""
    _repo(tmp_path, "app", {
        "src/copy.ts": 'const d = "Try RELAY Favours and tell us what you think";\n'})
    assert code_refs("relay", "favour", repos_dir=str(tmp_path))["leads"] == []


def test_a_dead_name_in_a_comment_is_prose(tmp_path):
    """Proven by this very check flagging its own explanatory comments."""
    _repo(tmp_path, "app", {
        "src/a.py": '# the "relay" name is dead, see the rename\nx = 1\n',
        "src/b.ts": '// legacy: "relay" used to be the key\nconst y = 2;\n'})
    assert code_refs("relay", "favour", repos_dir=str(tmp_path))["leads"] == []


def test_a_line_naming_both_names_is_rename_aware(tmp_path):
    """Same rule the prose triage already applies: a migration or an alias
    declaration is ABOUT the rename, not a dead reference."""
    _repo(tmp_path, "app", {
        "src/alias.ts": 'const ALIASES = [["relay", "favour"]];\n'})
    assert code_refs("relay", "favour", repos_dir=str(tmp_path))["leads"] == []


def test_tests_are_the_legacy_contract_not_a_lead(tmp_path):
    """Once the outage was fixed, the agent:relay cases became the deliberate
    legacy contract. Flagging them would make R4 cry wolf about correct code."""
    _repo(tmp_path, "app", {
        "src/__tests__/seeder.test.ts": 'resolve({ poster: "agent:relay" });\n'})
    r = code_refs("relay", "favour", repos_dir=str(tmp_path))
    assert r["leads"] == []
    assert r["legacy_tests"] == 1


def test_vendored_and_generated_code_is_not_ours(tmp_path):
    """Walking the tree found 61 hits in world-relay, nearly all OpenZeppelin's
    governance relay() and .vercel build output. git ls-files excludes what is
    gitignored; the vendor list handles what is committed."""
    _repo(tmp_path, "app", {
        "contracts/lib/oz/Governor.test.js": "describe('relay', function () {});\n",
        "src/real.ts": 'const a = "relay";\n'})
    r = code_refs("relay", "favour", repos_dir=str(tmp_path))
    assert [l["file"] for l in r["leads"]] == ["src/real.ts"]


def test_untracked_build_output_is_invisible(tmp_path):
    r = _repo(tmp_path, "app", {"src/real.ts": 'const a = "relay";\n'})
    (r / ".vercel").mkdir()
    (r / ".vercel" / "chunk.js").write_text('x("relay")\n')  # never committed
    out = code_refs("relay", "favour", repos_dir=str(tmp_path))
    assert [l["file"] for l in out["leads"]] == ["src/real.ts"]


def test_a_namespaced_dead_name_is_caught(tmp_path):
    """poster: "agent:relay" is the exact shape that started the outage."""
    _repo(tmp_path, "app", {"src/post.ts": 'post({ poster: "agent:relay" });\n'})
    assert len(code_refs("relay", "favour", repos_dir=str(tmp_path))["leads"]) == 1


def test_no_repos_is_not_an_error(tmp_path):
    assert code_refs("relay", "favour", repos_dir=str(tmp_path / "nope")) == {
        "leads": [], "legacy_tests": 0, "repos": 0}


@pytest.mark.parametrize("line,hit", [
    ('const a = "relay";', True),
    ("const a = 'relay';", True),
    ('poster: "agent:relay"', True),
    ('const a = "relayed the message";', False),
    ("// relay is dead", False),
    ('const a = "the relay station";', False),
])
def test_the_token_rule(line, hit):
    assert bool(_code_rx("relay").search(line)) is hit


def test_product_copy_naming_the_new_name_does_not_hide_a_dead_reference(tmp_path):
    """D4, found by adversarial review. The new name was matched as a bare word
    while the old one had to be a quoted token — asymmetric, and it dropped a
    real outage. In seed/route.ts lines 11, 12 and 13 all carry agentId:"relay";
    line 12 alone vanished because its product copy reads "What favour would you
    ask someone nearby". Lines 11 and 13 survived by luck: "Favours" and
    "favourite" do not match \\bfavour\\b. In a codebase whose domain vocabulary
    IS the new name, that makes every dead reference near product copy invisible.
    """
    _repo(tmp_path, "app", {"src/seed.ts":
        '{ description: "What favour would you ask someone nearby?", '
        'agentId: "relay" },\n'})
    leads = code_refs("relay", "favour", repos_dir=str(tmp_path))["leads"]
    assert len(leads) == 1, "product copy naming the new name hid a dead reference"


def test_an_alias_declaration_is_still_rename_aware(tmp_path):
    """The token rule must not break the suppression it exists for: both names
    as real tokens is a migration or an alias table, not a dead reference."""
    _repo(tmp_path, "app", {"src/alias.ts": 'const A = [["relay", "favour"]];\n'})
    assert code_refs("relay", "favour", repos_dir=str(tmp_path))["leads"] == []
