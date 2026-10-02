"""GOLDEN RULES: the stack's law, compiled from human judgment with provenance."""
import json
import os
import re

import pytest

from helicon.aliases import add_alias
from helicon.db import init_db, insert_audit, insert_cube
from helicon.gold import (RULE_MAX, SECTIONS, compile_gold, gather,
                          gold_history, inject, write_gold)
from helicon.models import AuditResult, HeliconCube


def _feedback_cube(conn, slug, title, content="", summary=""):
    """A standing-feedback memory, shaped exactly as the claude-code connector
    files them (that shape is what gather() queries for)."""
    insert_cube(conn, HeliconCube(
        id=f"gc_{slug}", source="claude-code",
        source_ref=f"memory_feedback_{slug}.md", type="memory",
        title=title, content=content, summary=summary,
        content_hash=slug, created_at="2026-07-01T00:00:00",
        valid_from="2026-07-01T00:00:00", review_status="approved"))
    conn.commit()


@pytest.fixture
def env(tmp_path):
    db = str(tmp_path / "data" / "helicon.db")
    conn = init_db(db)
    config = {"db_path": db,
              "claims": {"canonical": {"wins": "mindmap.md"}}}
    add_alias(conn, "oldname", "newname", "2026-07-01T00:00:00", note="test")
    conn.execute("INSERT INTO rules (nl_text, predicate, action, status, "
                 "created_at, approved_at, trust) VALUES "
                 "('kill drafts older than 60 days', '{}', 'kill', 'approved', "
                 "'2026-07-01', '2026-07-02', 0.9)")
    insert_audit(conn, AuditResult(
        audit_type="factual", target_type="cube", target_id="gc_x",
        finding="Cross-source contradiction: Lea birthday 07-13 vs 07-18",
        severity="critical", human_decision="resolved:07-18",
        details={"pair_key": "k", "person": "lea", "topic": "birthday",
                 "dates": ["07-13", "07-18"]},
        audited_at="2026-07-05", resolved_at="2026-07-05T10:00:00"))
    insert_audit(conn, AuditResult(
        audit_type="factual", target_type="cube", target_id="gc_y",
        finding="Cross-source contradiction: Paris birthday",
        severity="warning", human_decision="dismissed",
        details={"pair_key": "k2", "dismiss_reason": "place-as-person bug, fixed"},
        audited_at="2026-07-05", resolved_at="2026-07-05T11:00:00"))
    conn.commit()
    return conn, config


def test_every_rule_has_provenance(env):
    conn, config = env
    _feedback_cube(conn, "voice", title="feedback_voice: keep it plain")
    g = gather(conn, config)
    assert g["canon"] and g["renames"] and g["triage"]
    assert g["resolutions"] and g["precedents"] and g["feedback"]
    for name in SECTIONS:  # the declared rule buckets, not every key in g
        for item in g[name]:
            assert item.get("prov")


def test_compiled_law_reads_like_law(env):
    conn, config = env
    md = compile_gold(conn, config)
    assert "GOLDEN RULES" in md
    assert "lea birthday = 07-18" in md
    assert "oldname -> newname" in md
    assert "NOT rot: " in md
    assert "kill drafts older than 60 days" in md
    assert "A rule without provenance is a vibe" in md


def test_write_appends_history(env):
    conn, config = env
    a = write_gold(conn, config)
    assert os.path.exists(a["path"])
    add_alias(conn, "b", "c", "2026-07-02T00:00:00")
    b = write_gold(conn, config)
    assert b["total"] == a["total"] + 1
    hist = gold_history(config)
    assert [h["total"] for h in hist] == [a["total"], b["total"]]


def test_identity_and_phantom_rulings_compile_to_law(env):
    """R11 canonical + R12 phantom rulings become standing Golden Rules — the moat:
    a ruling governs the next generation. And they must NOT fall through to the
    claims shape and emit '? ? = ...' garbage."""
    conn, config = env
    insert_audit(conn, AuditResult(
        audit_type="identity", target_type="cube", target_id="aurora",
        finding="Identity fork: 'aurora' is defined as protocol vs market",
        severity="critical", human_decision="resolved:a payments protocol",
        details={"pair_key": "identity|aurora", "name": "aurora",
                 "genus_b": "market", "canonical_genus": "protocol",
                 "genera": {"protocol": ["obsidian"], "market": ["claude-code"]}},
        audited_at="2026-07-05", resolved_at="2026-07-05T12:00:00"))
    insert_audit(conn, AuditResult(
        audit_type="provenance", target_type="cube", target_id="helios",
        finding="Phantom association: Helios rides the wave to Solana",
        severity="warning", human_decision="resolved:phantom",
        details={"pair_key": "relation|helios|solana", "subj": "helios",
                 "obj": "solana", "predicate": "rides the wave to"},
        audited_at="2026-07-05", resolved_at="2026-07-05T12:30:00"))
    conn.commit()
    md = compile_gold(conn, config)
    assert "Aurora IS a payments protocol (ruled canonical)" in md
    assert "'market' framing is wrong" in md
    assert "Helios rides the wave to Solana is a phantom association" in md
    assert "? ?" not in md            # never the claims-shape fallthrough
    # every ruling still carries provenance
    g = gather(conn, config)
    for item in g["resolutions"]:
        assert item.get("prov")


def test_ruled_real_relation_emits_no_rule(env):
    """A relation ruled REAL is a clearance, not a guard — it must not add a rule."""
    conn, config = env
    before = len(gather(conn, config)["resolutions"])
    insert_audit(conn, AuditResult(
        audit_type="provenance", target_type="cube", target_id="x",
        finding="Phantom candidate ruled real", severity="warning",
        human_decision="resolved:real",
        details={"pair_key": "relation|a|b", "subj": "a", "obj": "b"},
        audited_at="2026-07-05", resolved_at="2026-07-05T13:00:00"))
    conn.commit()
    assert len(gather(conn, config)["resolutions"]) == before


def test_inject_is_dry_run_by_default(env, tmp_path, monkeypatch):
    conn, config = env
    monkeypatch.setenv("HOME", str(tmp_path))
    res = inject(conn, config, apply=False)
    assert res["applied"] is False
    assert not os.path.exists(res["target"])
    res = inject(conn, config, apply=True)
    assert os.path.exists(res["target"])
    # second apply keeps a .bak of the first
    inject(conn, config, apply=True)
    assert os.path.exists(res["target"] + ".bak")


def test_codex_policy_refresh_preserves_fleet_owned_state_block(env, tmp_path, monkeypatch):
    conn, config = env
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / ".codex" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "<!-- STATE:start -->\nTODAY revision abc\n<!-- STATE:end -->\n\nold law\n"
    )
    inject(conn, config, apply=True, targets=("codex",))
    text = target.read_text()
    assert text.startswith("<!-- STATE:start -->\nTODAY revision abc\n<!-- STATE:end -->")
    assert "GOLDEN RULES (compiled for Codex)" in text
    assert "old law" not in text


# --- the compile path: a rule the human never wrote is worse than no rule ---
# Regression: gold.py used the cube TITLE as the rule text with no fallback, so
# a memory with empty frontmatter compiled a BLANK line into the law and nothing
# said a word. It happened live to feedback_ambition_past_done.

def test_empty_title_never_compiles_a_blank_rule(env):
    """THE bug: no title -> a '- ' line in the law asserting nothing, silently."""
    conn, config = env
    _feedback_cube(conn, "ambition", title="", summary="Treat done as a trigger")
    g = gather(conn, config)
    assert all(f["rule"].strip() for f in g["feedback"]), "blank rule compiled into law"
    assert "Treat done as a trigger" in [f["rule"] for f in g["feedback"]]
    assert any("ambition" in w for w in g["_warnings"]), "fell back but stayed silent"


def test_fallback_walks_title_then_summary_then_content(env):
    conn, config = env
    _feedback_cube(conn, "sum_only", title="", summary="the summary rule")
    _feedback_cube(conn, "body_only", title="", summary="",
                   content="---\ndate: 2026-07-01\n---\n# A heading\n\nthe content rule\n")
    rules = {f["prov"]: f["rule"] for f in gather(conn, config)["feedback"]}
    assert rules["feedback_sum_only.md"] == "the summary rule"
    assert rules["feedback_body_only.md"] == "the content rule"  # not the heading


def test_rule_with_no_text_anywhere_is_refused_and_warned(env):
    """Refuse, don't invent. A memory with nothing to say emits no law."""
    conn, config = env
    _feedback_cube(conn, "hollow", title="", summary="", content="")
    g = gather(conn, config)
    assert not any(f["prov"] == "feedback_hollow.md" for f in g["feedback"])
    assert any("refused" in w for w in g["_warnings"])
    # not "- \n": the renderer emits "-   \n" (rule + two trailing spaces),
    # so that literal never matched and the assertion could not fail.
    assert not re.search(r"^-\s*$", compile_gold(conn, config), re.M)


def test_title_that_is_only_its_own_filename_is_not_a_rule(env):
    """feedback_index compiled to the rule 'feedback_index' — a slug echo."""
    conn, config = env
    _feedback_cube(conn, "index", title="feedback_index",
                   content="60 durable feedback files, grouped by theme")
    rules = {f["prov"]: f["rule"] for f in gather(conn, config)["feedback"]}
    assert rules["feedback_index.md"] == "60 durable feedback files, grouped by theme"


def test_slug_prefix_is_stripped_but_a_real_colon_is_not(env):
    """split(':', 1)[-1] chopped the headline off any title whose colon was
    punctuation. 'Never sync X: it leaks' became 'it leaks' — the inverse rule."""
    conn, config = env
    _feedback_cube(conn, "no_em_dashes",
                   title="feedback_no_em_dashes: Never use em dashes")
    _feedback_cube(conn, "obsidian",
                   title="Obsidian stays local: never sync the vault to GitHub")
    rules = {f["prov"]: f["rule"] for f in gather(conn, config)["feedback"]}
    assert rules["feedback_no_em_dashes.md"] == "Never use em dashes"
    assert rules["feedback_obsidian.md"].startswith("Obsidian stays local:")


def test_long_rules_clip_at_a_word_boundary_and_mark_the_cut(env):
    """A rule chopped mid-word reads as a finished sentence that says something
    else. Every clipped rule must show it was clipped."""
    conn, config = env
    long_rule = ("Never call systems done after one pass because Oscar's projects "
                 "are living systems that shift with one decision and the rule is")
    _feedback_cube(conn, "not_done", title=long_rule)
    rule = next(f["rule"] for f in gather(conn, config)["feedback"]
                if f["prov"] == "feedback_not_done.md")
    assert len(rule) <= RULE_MAX
    assert rule.endswith("…"), "clipped silently — reads as complete"
    assert long_rule.startswith(rule[:-1].rstrip("…").strip())
    assert rule.rstrip("…").strip() in long_rule  # no mid-word fragment


def test_warnings_never_count_as_rules(env):
    """The warning bucket lives in the gather dict; the law's rule count and the
    history point must be computed from the declared sections only."""
    conn, config = env
    _feedback_cube(conn, "hollow", title="", summary="", content="")
    res = write_gold(conn, config)
    assert res["warnings"], "no warning recorded for a refused rule"
    assert "_warnings" not in res
    assert res["total"] == sum(res[k] for k in
                              ("canon", "renames", "triage", "precedents",
                               "resolutions", "taste", "feedback"))
    assert f"{res['total']} rules" in res["md"]
    assert [h["total"] for h in gold_history(config)] == [res["total"]]


def test_precedent_and_dismiss_reason_also_mark_their_cut(env):
    """Same class as the feedback bug: precedents clipped at 118/140 with no
    ellipsis, so a truncated precedent read as the whole precedent."""
    conn, config = env
    insert_audit(conn, AuditResult(
        audit_type="factual", target_type="cube", target_id="gc_z",
        finding="Cross-source contradiction: " + "some long finding text " * 12,
        severity="warning", human_decision="dismissed",
        details={"pair_key": "k3", "dismiss_reason": "because " * 40},
        audited_at="2026-07-05", resolved_at="2026-07-05T12:00:00"))
    conn.commit()
    p = next(x for x in gather(conn, config)["precedents"]
             if x["prov"].endswith("#3, 2026-07-05"))
    assert p["rule"].endswith("…") and p["why"].endswith("…")


# --- what the adversarial pass broke in the FIX itself --------------------
# The first fix traded one silent corruption for two others: it deleted real
# rules whose terse title normalised to their own slug, and it leaked
# frontmatter into the law as law. Both are the same failure class as the
# blank rule: the law asserting something the human never said.

@pytest.mark.parametrize("title, slug", [
    ("No hype", "no_hype"),                  # normalises to its own slug
    ("No em dashes", "no_em_dashes"),
    ("Never wind down", "never_wind_down"),
    ("永远不要使用破折号", "no_em_dashes"),        # normalises to "" — the same branch
    ("→ ← ↔", "arrows"),
    ("!!!", "shouty"),
])
def test_a_terse_or_non_ascii_title_is_a_rule_not_a_slug_echo(env, title, slug):
    """Matching on the normalised form alone DELETED these. A filename echo has
    no spaces; prose does — and a title is not an echo just because it is short."""
    conn, config = env
    _feedback_cube(conn, slug, title=title)
    rules = {f["prov"]: f["rule"] for f in gather(conn, config)["feedback"]}
    assert rules[f"feedback_{slug}.md"] == title


def test_a_literal_filename_echo_is_still_not_a_rule(env):
    conn, config = env
    _feedback_cube(conn, "index", title="feedback_index",
                   content="60 durable feedback files, grouped by theme")
    rules = {f["prov"]: f["rule"] for f in gather(conn, config)["feedback"]}
    assert rules["feedback_index.md"] == "60 durable feedback files, grouped by theme"


@pytest.mark.parametrize("body", [
    "---\r\ndate: 2026-07-01\r\n---\r\nthe real rule\r\n",   # CRLF
    "\n---\ndate: 2026-07-01\n---\nthe real rule\n",         # leading blank line
    "---\ndate: 2026-07-01\ntags: [x]\n---\n\nthe real rule",  # no trailing newline
])
def test_frontmatter_never_compiles_into_the_law_as_a_rule(env, body):
    """A regex anchored on '---\\n...---\\n' missed CRLF, a leading blank line and
    frontmatter running to EOF, leaking `date: 2026-07-01` through as a RULE."""
    conn, config = env
    _feedback_cube(conn, "fm", title="", summary="", content=body)
    rules = {f["prov"]: f["rule"] for f in gather(conn, config)["feedback"]}
    assert rules["feedback_fm.md"] == "the real rule"
    assert "date:" not in compile_gold(conn, config)


def test_a_body_that_is_only_frontmatter_states_no_rule(env):
    conn, config = env
    _feedback_cube(conn, "hollow_fm", title="", summary="",
                   content="---\ndate: 2026-07-01\n---")
    g = gather(conn, config)
    assert not any(f["prov"] == "feedback_hollow_fm.md" for f in g["feedback"])
    assert any("refused" in w for w in g["_warnings"])


# --- multi-target injection: one gather, many scoped consumers ---------------

def test_codex_target_withholds_helicon_internal_calibration(env, monkeypatch,
                                                             tmp_path):
    """triage + precedents tune Helicon's OWN rot detector. Shipping them to
    another agent is noise it cannot act on."""
    conn, config = env
    home = tmp_path / "home"
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    res = inject(conn, config, apply=True, targets=("claude", "codex"))

    claude_md = open(res["targets"]["claude"]["target"], encoding="utf-8").read()
    codex_md = open(res["targets"]["codex"]["target"], encoding="utf-8").read()

    assert "Triage law" in claude_md and "Precedents" in claude_md
    assert "Triage law" not in codex_md and "Precedents" not in codex_md
    # the facts every agent needs still travel
    assert "Renames" in codex_md and "Single sources of truth" in codex_md
    assert len(codex_md) < len(claude_md)


def test_a_scoped_file_declares_what_it_withheld(env, monkeypatch, tmp_path):
    """A filtered file that reads as the whole law quietly becomes a wrong one."""
    conn, config = env
    home = tmp_path / "home"
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    inject(conn, config, apply=True, targets=("codex",))
    codex_md = open(home / ".codex" / "AGENTS.md", encoding="utf-8").read()
    assert "withheld" in codex_md
    assert "triage" in codex_md and "precedents" in codex_md


def test_scoped_header_counts_only_what_it_wrote(env, monkeypatch, tmp_path):
    """The header must count the file's OWN rules, never the full store."""
    conn, config = env
    home = tmp_path / "home"
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    res = inject(conn, config, apply=True, targets=("claude", "codex"))
    full = int(re.search(r"law of this agent stack: (\d+) rules",
                         open(res["targets"]["claude"]["target"]).read()).group(1))
    scoped = int(re.search(r"law of this agent stack: (\d+) rules",
                           open(res["targets"]["codex"]["target"]).read()).group(1))
    assert scoped < full


def test_unknown_target_is_named_not_silently_skipped(env):
    conn, config = env
    res = inject(conn, config, apply=False, targets=("claude", "nope"))
    assert res["targets"]["nope"]["error"].startswith("unknown target")
    assert "claude" in res["targets"]["nope"]["known"]


def test_default_targets_stay_claude_only(env, monkeypatch, tmp_path):
    """Back-compat: an existing caller passing no targets must not suddenly
    start writing into ~/.codex."""
    conn, config = env
    home = tmp_path / "home"
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    res = inject(conn, config, apply=True)
    assert set(res["targets"]) == {"claude"}
    assert not (home / ".codex").exists()
    # top-level keys still describe the claude write, as every caller expects
    assert res["applied"] is True and res["target"].endswith("GOLDEN_RULES.md")
