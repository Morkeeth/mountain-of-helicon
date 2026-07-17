"""The rot exam — ROT.md as an executable test suite.

Twelve named failure classes (R1-R12), each grounded in the public record (see
ROT.md), each checked live against the real store. One command answers
"which documented ways of going wrong is MY memory going wrong in right now?"

Statuses are honest three ways:
  - coverage:  TESTED (a real check ran) or PARTIAL (known gap, said out loud)
  - verdict:   CLEAN / ROT FOUND / UNMEASURED per class
  - receipts:  every verdict carries the number and where it came from

Zero LLM calls by default — the exam is deterministic and free to run daily.
"""
import sqlite3
from datetime import datetime, timezone

from helicon.forgetting import DEFAULT_STABILITY


def _check(rid, name, coverage, found, receipt):
    return {
        "id": rid, "name": name, "coverage": coverage,
        "verdict": ("ROT FOUND" if found else "CLEAN") if found is not None else "UNMEASURED",
        "receipt": receipt,
    }


def run_rot_exam(conn: sqlite3.Connection, repo_root: str | None = None,
                 judge_client=None, judge_model: str = "qwen3.6-flash") -> dict:
    """judge_client (Qwen) upgrades R11 from the cosine gate to the judge that
    actually separates a fork from a rephrasing. Optional: without it R11 reports
    cosine survivors and says so, rather than pretending the weaker gate is the
    same exam."""
    checks = []

    # R1 cross-source contradiction — the pair selector (helicon.pairing)
    # finds disjoint dated facts about the same person across source files;
    # the Qwen detector rules on what it finds.
    # Verdict scope: live conflicts + open PAIRING findings only. An open
    # agent-flag about something else must not pin R1 at ROT FOUND forever
    # (that would mute watch's flip alert for real contradictions).
    open_pairing = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE audit_type = 'factual' "
        "AND details LIKE '%pair_key%' AND human_decision IS NULL"
    ).fetchone()[0]
    try:
        from helicon.pairing import find_conflicts
        from helicon.claims import find_claim_conflicts
        conflicts = find_conflicts(conn)
        claim_conflicts = find_claim_conflicts(conn)
        sample = "; ".join(
            [f"{c['person'].title()} {c['topic']}: {' vs '.join(c['dates'])}"
             for c in conflicts[:2]]
            + [f"{c['metric']}[{c['subject']}]: {' vs '.join(c['values'])}"
               for c in claim_conflicts[:2]])
        total = len(conflicts) + len(claim_conflicts)
        checks.append(_check(
            "R1", "Cross-source contradiction", "TESTED",
            total > 0 or open_pairing > 0,
            f"{total} live cross-source conflict(s) "
            f"({len(conflicts)} dated-fact, {len(claim_conflicts)} claim)"
            + (f" ({sample})" if sample else "")
            + f"; {open_pairing} unresolved pairing finding(s)"))
    except Exception as e:
        checks.append(_check("R1", "Cross-source contradiction", "TESTED", None,
                             f"unmeasured: {e}"))

    # R2 doc-drift — doc claims vs source truth: stated counts, the lists under
    # them, and eval metrics vs data/eval-latest.json, across every checked doc.
    try:
        from helicon.docdrift import check_docs
        drift = [r for r in (check_docs(repo_root) if repo_root else check_docs())
                 if not r["ok"]]
        checked = len({r["doc"] for r in (check_docs(repo_root) if repo_root else check_docs())})
        checks.append(_check(
            "R2", "Doc-drift", "TESTED", bool(drift),
            f"{checked} docs match source" if not drift else
            "; ".join(f"{d['doc']} {d['claim']}: {d['why']}" for d in drift)))
    except Exception as e:
        checks.append(_check("R2", "Doc-drift", "TESTED", None, f"unmeasured: {e}"))

    # R3 staleness/expiry — live memories past their type's half-life, unreinforced.
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    expired = 0
    for ctype, eta in DEFAULT_STABILITY.items():
        expired += conn.execute(
            "SELECT COUNT(*) FROM helicon_cubes WHERE type = ? "
            "AND review_status IN ('pending', 'revised') AND merged_into IS NULL "
            "AND COALESCE(NULLIF(last_reinforced, ''), created_at) < datetime(?, ?)",
            (ctype, now, f"-{eta} days"),
        ).fetchone()[0]
    checks.append(_check(
        "R3", "Staleness / expiry", "TESTED", expired > 0,
        f"{expired} live memories past their type's half-life without reinforcement "
        "(decay runs on every scan; battery test 'Expiry' covers retrieval)"))

    # R4 supersession — declared aliases triage every dead-name reference:
    # pre-rename history is kept, post-rename current-claims are the rot,
    # and serving the dead name for a current-name query is the proof.
    superseded = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status = 'superseded'"
    ).fetchone()[0]
    try:
        from helicon.aliases import alias_rot
        triages = alias_rot(conn)
        if not triages:
            checks.append(_check(
                "R4", "Supersession / rename", "TESTED", None,
                f"{superseded} memories retired by reconcile; no renames declared "
                "yet — helicon alias add <old> <new>"))
        else:
            found = any(t["current_claims"] > 0 or t["leaked"]
                        or t.get("code_leads") for t in triages)
            # A dead name in prose is rot you can read past. A dead name a lookup
            # EXECUTES is an outage: agent:relay -> getAgent("relay") -> no such
            # key -> null, silently, and 107 production tasks carried agent:null
            # for 13 days. R4 had been reporting 341 dead names as a count with
            # no way to tell which one was load-bearing. Code leads are named
            # first and carry file:line, because that is the one a human must
            # look at today.
            receipt = "; ".join(
                f"{t['old_name']}->{t['new_name']}: "
                + (f"{len(t['code_leads'])} IN CODE ("
                   + ", ".join(f"{l['repo']}/{l['file']}:{l['line']}"
                               for l in t["code_leads"][:3])
                   + (", …" if len(t["code_leads"]) > 3 else "")
                   + f") — a dead name in a code path executes; "
                   if t.get("code_leads") else "")
                + f"{t['live_refs']} live dead-name "
                f"ref(s) in prose = {t['history']} history + {t['rename_aware']} "
                f"rename-aware + {t['current_claims']} current-claim(s)"
                + (f", {len(t['leaked'])}/{t['retrieved_for_new_name']} top-K hits "
                   f"for '{t['new_name']}' serve the dead name" if t["leaked"] else "")
                for t in triages)
            checks.append(_check(
                "R4", "Supersession / rename", "TESTED", found,
                receipt + f" ({superseded} memories retired by reconcile)"))
    except Exception as e:
        checks.append(_check("R4", "Supersession / rename", "TESTED", None,
                             f"unmeasured: {e}"))

    # R5 duplicate/echo — identical content stored more than once, live.
    dupes = conn.execute(
        "SELECT COUNT(*) FROM (SELECT content_hash FROM helicon_cubes "
        "WHERE review_status IN ('pending', 'revised', 'approved') AND merged_into IS NULL "
        "GROUP BY content_hash HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    checks.append(_check(
        "R5", "Duplicate / echo memory", "TESTED", dupes > 0,
        f"{dupes} content hash(es) stored more than once among live memories"))

    # R6 title-only grounding — live memories that are stubs (no substance).
    stubs = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status IN ('pending', 'revised') "
        "AND merged_into IS NULL AND length(content) < 40"
    ).fetchone()[0]
    total_live = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status IN ('pending', 'revised') "
        "AND merged_into IS NULL"
    ).fetchone()[0]
    thin_share = (stubs / total_live) if total_live else 0
    checks.append(_check(
        "R6", "Title-only grounding", "TESTED", thin_share > 0.10,
        f"{stubs}/{total_live} live memories are stubs (<40 chars); "
        "battery tests Thinness+Grounding cover retrieval"))

    # R7 wrong eviction — the regret ledger.
    try:
        from helicon.regret import get_regrets
        regrets = get_regrets(conn, limit=100)
        checks.append(_check(
            "R7", "Wrong eviction (regret)", "TESTED", len(regrets) > 0,
            f"{len(regrets)} retired memories retrieval has wanted back "
            "(time-decayed, blame on the kill decision)"))
    except Exception as e:
        checks.append(_check("R7", "Wrong eviction (regret)", "TESTED", None, f"unmeasured: {e}"))

    # R8 retrieval regression — snapshots vs baseline.
    #
    # A snapshot regresses only when a memory that is STILL LIVE stopped being
    # retrieved. A baseline memory that left the top-K because Helicon retired
    # it as rot is the product working, and counting that as regression is how
    # this once read 12/13 while `report` printed DEGRADED off the same number.
    # The retired count is reported next to it, because "16 baseline memories
    # retired since baseline" is the loop, not a fault.
    try:
        from helicon.snapshots import check_all
        snaps = check_all(conn)
        regressed = sum(1 for s in snaps if s["regressed"])
        retired = sum(len(s["stale"]) for s in snaps)
        fossils = sum(1 for s in snaps if s.get("fossil"))
        detail = (f"{regressed}/{len(snaps)} snapshot(s) regressed "
                  f"(a LIVE memory stopped being retrieved)")
        if retired:
            detail += (f"; {retired} baseline memory(s) retired as rot since "
                       f"baseline — retrieval correctly stops serving those, "
                       f"which is the loop working, not a regression")
        if fossils:
            detail += (f"; {fossils} baseline(s) are fossils (every memory "
                       f"retired) — re-capture: helicon snapshot add \"<task>\"")
        checks.append(_check(
            "R8", "Retrieval regression", "TESTED",
            (regressed > 0) if snaps else None,
            detail if snaps
            else "no baselines captured — run: helicon snapshot add"))
    except Exception as e:
        checks.append(_check("R8", "Retrieval regression", "TESTED", None, f"unmeasured: {e}"))

    # R9 self-evidence loops — the guard must hold: no non-human session may
    # appear in what the rule learner counts as human evidence. The guard is
    # ONE written predicate (db.human_evidence_sql); this check audits it.
    from helicon.db import human_evidence_sql
    leaked = conn.execute(
        f"SELECT COUNT(*) FROM reviews WHERE {human_evidence_sql()} "
        "AND (session_id LIKE 'auto%' OR session_id LIKE 'agent%')"
    ).fetchone()[0]
    non_human = conn.execute(
        f"SELECT COUNT(*) FROM reviews WHERE NOT ({human_evidence_sql()})"
    ).fetchone()[0]
    checks.append(_check(
        "R9", "Self-evidence loops", "TESTED", leaked > 0,
        f"{non_human} automated review(s) correctly quarantined from rule learning; "
        f"{leaked} leaked past the guard"))

    # R10 instruction-file drift — agent-rules/skills memories retired or duplicated.
    rules_retired = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE source IN ('agent-rules', 'skills') "
        "AND review_status = 'superseded'"
    ).fetchone()[0]
    rules_live = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE source IN ('agent-rules', 'skills') "
        "AND review_status NOT IN ('killed', 'superseded')"
    ).fetchone()[0]
    checks.append(_check(
        "R10", "Instruction-file drift", "TESTED", rules_retired > 0,
        f"{rules_retired} rules/skills section(s) retired as drifted; {rules_live} live "
        "(section-level memories, covered by reconcile + snapshots)"))

    # R11 identity coherence — one entity's DEFINITION forks across sources (same
    # name, incompatible genera). R1 is blind: no scalar slot to compare. Deterministic.
    try:
        from helicon.identity import find_identity_forks
        # Semantic-confirmed forks = exactly what `resolve --list` lets you rule.
        # The exam must count the SAME set the loop can act on; the fast
        # genus-only pass over-reports the false positives the semantic gate
        # (local embeddings, no LLM) exists to kill. Candidates it drops are
        # reported as an unconfirmed sub-signal, never as ROT.
        forks = find_identity_forks(conn, semantic=True, judge_client=judge_client,
                                    judge_model=judge_model)
        candidates = find_identity_forks(conn, semantic=False)
        unconfirmed = max(0, len(candidates) - len(forks))
        # Name the gate that produced the number. Cosine cannot separate a fork
        # from a rephrasing (real 0.354 vs artifact 0.367 on the live store), so
        # a cosine-only R11 is over-reporting and must say so rather than sell
        # its candidates as confirmed rot.
        gate = "qwen-judged" if judge_client else "cosine-only, unjudged"
        note = (f" (+{unconfirmed} genus candidate(s) dropped by the {gate} gate)"
                if unconfirmed else f" [{gate}]")
        checks.append(_check(
            "R11", "Identity coherence", "TESTED", len(forks) > 0,
            (f"{len(forks)} entity definition(s) forked across sources: "
             + ", ".join(f"{x['name']} ({x['genus_a']}/{x['genus_b']})" for x in forks[:3])
             + note)
            if forks else f"no confirmed entity definition forks{note}"))
    except Exception as e:
        checks.append(_check("R11", "Identity coherence", "TESTED", None, f"unmeasured: {e}"))

    # R12 phantom association — a relation asserted by a single speculative source
    # that nothing else grounds. R1/R11 blind: no scalar slot, no definition fork.
    try:
        from helicon.relations import find_phantom_relations
        phantoms = find_phantom_relations(conn)
        checks.append(_check(
            "R12", "Phantom association", "TESTED", len(phantoms) > 0,
            (f"{len(phantoms)} ungrounded relation(s): "
             + ", ".join(f"{x['subj']}->{x['obj']}" for x in phantoms[:3]))
            if phantoms else "no ungrounded single-source relations between entities"))
    except Exception as e:
        checks.append(_check("R12", "Phantom association", "TESTED", None, f"unmeasured: {e}"))

    found = sum(1 for c in checks if c["verdict"] == "ROT FOUND")
    unmeasured = sum(1 for c in checks if c["verdict"] == "UNMEASURED")
    tested = sum(1 for c in checks if c["coverage"] == "TESTED")
    return {
        "exam": "ROT", "classes": len(checks), "tested": tested,
        "partial": len(checks) - tested, "rot_found": found, "unmeasured": unmeasured,
        "checks": checks,
    }


def format_rot(res: dict) -> str:
    lines = [
        f"The rot exam — {res['classes']} documented failure classes, checked live (see ROT.md)",
        "",
    ]
    for c in res["checks"]:
        cov = "" if c["coverage"] == "TESTED" else "  [partial coverage]"
        lines.append(f"  {c['id']:>3}  {c['name']:<28} {c['verdict']:<10}{cov}")
        lines.append(f"       {c['receipt']}")
    lines.append("")
    lines.append(f"{res['rot_found']}/{res['classes']} classes show rot right now · "
                 f"{res['tested']}/{res['classes']} fully tested, "
                 f"{res['partial']} partial (gaps named in ROT.md)")
    return "\n".join(lines)
