"""R13 — killswitch polarity. Naming a dead rail is not claiming it.

The heading fallback is the weakest evidence the killswitch probe has: under a
capability heading ("## Context", "## Stack"), a bare noun phrase is treated as
a present-tense capability claim, because in a stack list it genuinely is one.

That fallback has now produced two retracted false-positive storms:

  * 2026-08-02, OpenHands :477 — a doc correctly documenting a deletion.
  * 2026-08-11, world-relay CLAUDE.md — NINE findings, EIGHT of them false. It
    convicted "First-party custody — DEAD, and it stays dead.", it convicted a
    strikethrough correction of an earlier error, and it convicted the sentence
    explaining the false positives. Every one of the nine was heading-only:
    not a single sentence carried an availability verb of its own.

"This rail is available" and "this rail is dead, do not use it" carry the same
nouns and mean opposite things, so token proximity can never separate them. The
rule this file pins: the heading fallback may only convict a sentence whose
polarity is NEUTRAL. A death word, an explicit negation, a past-tense framing,
a struck-through retraction or a gone-status code all mark a sentence that is
describing an absence, and the probe must ABSTAIN on it.

Abstaining costs a real find now and then. Convicting a warning teaches people
to delete their warnings, which is strictly worse: it destroys the very
sentences the probe exists to protect.

An explicit availability verb is NOT covered by this rule. "do NOT open user
self-funding until X" states its own polarity and is judged as before.
"""
import os
import subprocess

import pytest

from helicon.probes import CONTRADICTED, probe_docs


# Every sentence below sits under a capability heading and binds to the switch
# on the same nouns. Only polarity separates them.
DOC = """# WIDGET

## Context
- Next.js app, identity checks, on-chain USDC escrow (Chain 480)
- The USDC escrow still takes deposits from users today.
- **First-party custody — DEAD, and it stays dead.** Do not resurrect it.
- This was the rail where the relayer hot wallet held user escrow funds.
- ~~"The USDC escrow is the live money rail"~~ — corrected, that was wrong.
- The escrow custody rail is switched off; every branch returns 404.
"""

CUSTODY = """/**
 * CUSTODY IS RETIRED. Real money still moves: the campaign unlock pays by
 * plain ERC-20 transfer, and that is not custody. Points are untouched.
 */
export const CUSTODY_RETIRED = true;
"""

ROUTE = """import { CUSTODY_RETIRED } from "@/lib/custody";

export async function POST(req) {
  if (CUSTODY_RETIRED) {
    return Response.json({
      error: "Custody retired",
      detail: "WIDGET no longer holds funds in escrow. Points are unaffected.",
    }, { status: 410 });
  }
}
"""


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "src" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "app" / "api" / "agent" / "fund").mkdir(parents=True)
    (tmp_path / "CLAUDE.md").write_text(DOC)
    (tmp_path / "src" / "lib" / "custody.ts").write_text(CUSTODY)
    (tmp_path / "src" / "app" / "api" / "agent" / "fund" / "route.ts").write_text(ROUTE)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "fixture"]):
        subprocess.run(cmd, cwd=tmp_path, env=env, check=True,
                       capture_output=True)
    return str(tmp_path)


def _convicted(repo):
    return [r["sentence"] for r in probe_docs(None, repo)
            if r["kind"] == "killswitch" and r["verdict"] == CONTRADICTED]


# --- the false positives: a sentence that names the dead thing to warn you ---

@pytest.mark.parametrize("marker,fragment", [
    ("a death word", "DEAD, and it stays dead"),
    ("past tense", "This was the rail"),
    ("a struck-through retraction", "corrected, that was wrong"),
    ("a gone-status code", "switched off; every branch returns 404"),
])
def test_a_warning_about_a_dead_rail_is_not_convicted(repo, marker, fragment):
    """The sentence and the switch AGREE. There is nothing to disprove."""
    hits = [s for s in _convicted(repo) if fragment in s]
    assert hits == [], (
        f"convicted a sentence carrying {marker} — it warns that the rail is "
        f"dead, which is what the switch says too: {hits}")


# --- the true positives: the class must still bite ---

def test_a_bare_capability_bullet_is_still_convicted(repo):
    """In a stack list, a bare noun phrase IS a present-tense claim. This is
    the shape the heading fallback exists for, and it must survive the fix."""
    assert any("on-chain USDC escrow (Chain 480)" in s for s in _convicted(repo)), \
        "the neutral capability bullet must still fire"


def test_a_continuation_claim_is_still_convicted(repo):
    """'still takes deposits' asserts the rail is alive right now."""
    assert any("still takes deposits" in s for s in _convicted(repo)), \
        "a present-tense continuation claim must still fire"


def test_the_storm_is_bounded(repo):
    """Six bindable sentences, two of them real. Four convictions is the bug."""
    assert len(_convicted(repo)) == 2, \
        f"expected exactly the 2 real claims, got: {_convicted(repo)}"
