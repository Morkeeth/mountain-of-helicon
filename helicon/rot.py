"""The rot exam — ROT.md as an executable test suite.

Thirteen named failure classes (R1-R13), each grounded in the public record (see
ROT.md), each checked live against the real store. One command answers
"which documented ways of going wrong is MY memory going wrong in right now?"

Statuses are honest three ways:
  - coverage:  TESTED (a real check ran) or PARTIAL (known gap, said out loud)
  - verdict:   CLEAN / ROT FOUND / UNMEASURED per class
  - receipts:  every verdict carries the number and where it came from

Zero LLM calls by default — the exam is deterministic and free to run daily.
"""
import os
import re
import sqlite3
from datetime import datetime, timezone

from helicon.forgetting import DEFAULT_STABILITY


def _scrub(exc: Exception, repo_root: str | None = None) -> str:
    """An exception message printed by `helicon ci` is user-facing copy.

    A stranger's first run used to open with an absolute path from the machine
    that ran it — on 2026-08-14, `helicon ci` against openai/codex printed
    "[Errno 2] No such file or directory: '/private/tmp/.../codex/CLAUDE.md'".
    The path is noise to the reader and it leaks the runner's filesystem, so
    every path in an unmeasured receipt is reduced to its basename.
    """
    text = str(exc)
    for token in sorted(re.findall(r"/[^\s'\"]+", text), key=len, reverse=True):
        text = text.replace(token, os.path.basename(token.rstrip("/")) or "/")
    return text


def _is_own_repo(repo_root: str) -> bool:
    """docdrift's claims are written against THIS package's own files, so the
    only repository they can grade is a checkout of Mountain of Helicon."""
    return os.path.isfile(os.path.join(repo_root, "helicon", "docdrift.py"))


def _title_only(title: str | None, content: str | None) -> bool:
    """True when the heading is all the memory has.

    Deliberately not a length test. "Format with black, line length 100." is 35
    characters and is a whole rule; a section that is nothing but `## Security`
    is 200 characters of nothing if you pad it. The old cutoff read the first
    as rot and the second as fine.
    """
    body = (content or "").strip()
    if not body:
        return True
    # Every line is a markdown heading — a table of contents, not an instruction.
    if all(not line.strip() or line.lstrip().startswith("#")
           for line in body.splitlines()):
        return True
    # The body restates the title and adds nothing. Titles arrive decorated by
    # the scanner ("[repo] CLAUDE.md — Rules"), so compare on the last segment.
    head = (title or "").strip().rsplit("—", 1)[-1].strip().lstrip("#").strip()
    return bool(head) and body.lstrip("#").strip().rstrip(".") == head.rstrip(".")


def _nothing_to_grade(rid: str, name: str, why: str) -> dict:
    """A class whose population is empty has not passed, it has not run.

    Five classes reported CLEAN on a stranger's first run because their
    populations were empty: no retired memories to regret, no reviews to leak,
    no memory old enough to expire. Zero-of-nothing landed on the healthy end of
    the scale and a reader counted it as a check. R4 and R8 already answered the
    same emptiness with UNMEASURED, so the exam gave two different answers to
    one situation and only one of them was true.

    The rule, stated once here and applied at five call sites: any metric over a
    set needs an explicit answer for the empty set, and that answer is never
    CLEAN.
    """
    return _check(rid, name, "PARTIAL", None, f"nothing to grade: {why}")


def _check(rid, name, coverage, found, receipt):
    return {
        "id": rid, "name": name, "coverage": coverage,
        "verdict": ("ROT FOUND" if found else "CLEAN") if found is not None else "UNMEASURED",
        "receipt": receipt,
    }


def run_rot_exam(conn: sqlite3.Connection, repo_root: str | None = None,
                 judge_client=None, judge_model: str = "qwen3.6-flash",
                 config: dict | None = None) -> dict:
    """judge_client (Qwen) upgrades R11 from the cosine gate to the judge that
    actually separates a fork from a rephrasing. Optional: without it R11 reports
    cosine survivors and says so, rather than pretending the weaker gate is the
    same exam.

    config carries the declared repos_dir for R4's code arm. Without it the code
    arm does not run and R4 says so — it used to walk ~/CODE implicitly, which
    made the exam's verdict depend on whose laptop it ran on."""
    checks = []

    # R1 cross-source contradiction — the pair selector (helicon.pairing)
    # finds disjoint dated facts about the same person across source files;
    # the Qwen detector rules on what it finds.
    # Verdict scope: live conflicts + open PAIRING findings only. An open
    # agent-flag about something else must not pin R1 at ROT FOUND forever
    # (that would mute watch's flip alert for real contradictions).
    open_pairing = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE audit_type = 'factual' "
        "AND details LIKE '%pair_key%' AND human_decision IS NULL "
        "AND machine_decision IS NULL"
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
        # The empty-set rule, call site seven. R1 compares dated facts and
        # scalar claims; it has no opinion about two prose rules disagreeing.
        # A repo whose instruction files contain neither gives R1 nothing to
        # compare, and "0 conflicts" then describes the extractor's reach, not
        # the repo. Measured 2026-08-14: the sweep's R1 fixture plants two files
        # naming different release managers and opposite deploy rules, and R1
        # said CLEAN — true, and read by a stranger as "no contradictions here".
        from helicon.pairing import extract_assertions
        from helicon.claims import extract_metric_claims
        comparable = 0
        for title, content in conn.execute(
                "SELECT title, content FROM helicon_cubes WHERE review_status IN "
                "('pending', 'revised', 'approved') AND merged_into IS NULL"):
            comparable += len(extract_assertions(content or "", title or ""))
            comparable += len(extract_metric_claims(content or "", title or ""))
        if not comparable and not open_pairing:
            checks.append(_nothing_to_grade(
                "R1", "Cross-source contradiction",
                "no dated fact and no scalar claim was extracted from this "
                "repo's instruction files, so there is nothing to compare "
                "across sources. Two prose rules disagreeing is not yet "
                "detected by any class"))
        else:
            checks.append(_check(
                "R1", "Cross-source contradiction", "TESTED",
                total > 0 or open_pairing > 0,
                f"{total} live cross-source conflict(s) among {comparable} "
                f"comparable assertion(s) "
                f"({len(conflicts)} dated-fact, {len(claim_conflicts)} claim)"
                + (f" ({sample})" if sample else "")
                + f"; {open_pairing} unresolved pairing finding(s)"))
    except Exception as e:
        checks.append(_check("R1", "Cross-source contradiction", "TESTED", None,
                             f"unmeasured: {e}"))

    # R2 doc-drift — doc claims vs source truth: stated counts, the lists under
    # them, and eval metrics vs data/eval-latest.json, across every checked doc.
    #
    # Scope, learned on a stranger's repo 2026-08-14: every claim in docdrift is
    # written against THIS repository's docs and counted from THIS package's
    # source ("MCP Server (N tools)", web/src/App.tsx). Pointed at a repo we do
    # not own it can only crash on a doc that was never meant to be there. It
    # did exactly that on openai/codex, and the FileNotFoundError was the first
    # thing a first-time reader saw. A foreign repo now gets a sentence saying
    # the class did not run, which is the truth; silence would have read as pass.
    if repo_root and not _is_own_repo(repo_root):
        checks.append(_check(
            "R2", "Doc-drift", "PARTIAL", None,
            "not run here: the doc-drift claims are written against Mountain of "
            "Helicon's own docs, so this class cannot grade another repository. "
            "Your docs are unchecked, not clean"))
    else:
        try:
            from helicon.docdrift import check_docs
            results = check_docs(repo_root) if repo_root else check_docs()
            drift = [r for r in results if not r["ok"]]
            checked = len({r["doc"] for r in results})
            checks.append(_check(
                "R2", "Doc-drift", "TESTED", bool(drift),
                f"{checked} docs match source" if not drift else
                "; ".join(f"{d['doc']} {d['claim']}: {d['why']}" for d in drift)))
        except Exception as e:
            checks.append(_check("R2", "Doc-drift", "TESTED", None,
                                 f"unmeasured: {_scrub(e, repo_root)}"))

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
    # Nothing in the store is old enough for a half-life to have passed, so
    # "0 expired" is the question being unaskable, not an answer. On a first run
    # every memory is seconds old and this class cannot fire by construction.
    # The denominator has to be the same set as the numerator. The loop above
    # only counts types that HAVE a half-life, so counting every live memory
    # here would grade rules and agent-instruction sections — types with no
    # half-life defined — as permanently fresh. Found by the guard test: a
    # memory of type 'rule' aged to 2020 still reported CLEAN.
    shortest = min(DEFAULT_STABILITY.values())
    typed = ",".join("?" * len(DEFAULT_STABILITY))
    gradeable = conn.execute(
        f"SELECT COUNT(*) FROM helicon_cubes WHERE type IN ({typed}) "
        "AND review_status IN ('pending', 'revised') AND merged_into IS NULL "
        "AND COALESCE(NULLIF(last_reinforced, ''), created_at) < datetime(?, ?)",
        (*DEFAULT_STABILITY, now, f"-{shortest} days"),
    ).fetchone()[0]
    if not gradeable:
        checks.append(_nothing_to_grade(
            "R3", "Staleness / expiry",
            f"no live memory of a type that has a half-life is older than the "
            f"shortest one ({shortest} days), so none could have expired yet"))
    else:
        checks.append(_check(
            "R3", "Staleness / expiry", "TESTED", expired > 0,
            f"{expired}/{gradeable} live memories old enough to expire are past "
            "their type's half-life without reinforcement "
            "(decay runs on every scan; battery test 'Expiry' covers retrieval)"))

    # R4 supersession — declared aliases triage every dead-name reference:
    # pre-rename history is kept, post-rename current-claims are the rot,
    # and serving the dead name for a current-name query is the proof.
    superseded = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status = 'superseded'"
    ).fetchone()[0]
    try:
        from helicon.aliases import alias_rot
        triages = alias_rot(conn, config=config)
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
                + ("" if t.get("code_scanned")
                   else "code arm not configured (aliases.repos_dir unset) — "
                        "unmeasured, not clean; ")
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
    # A duplicate needs two memories. With fewer than two live, the count is
    # zero for arithmetic reasons and says nothing about the repo.
    live_for_dupes = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status IN "
        "('pending', 'revised', 'approved') AND merged_into IS NULL"
    ).fetchone()[0]
    # And a harder limit, found on 2026-08-14 while writing the guard test that
    # R5 must still be able to fire: it cannot. helicon_cubes declares
    # UNIQUE(content_hash) (db.py), so two rows can never share a hash and this
    # query's HAVING COUNT(*) > 1 can never match — on any repo, ever. R5 has
    # been reporting CLEAN for a check the schema makes unfailable. Identical
    # content is already prevented at write time; the rot the class NAMES, an
    # echo that is the same memory in different words, needs a near-duplicate
    # test that does not exist yet. Until it does, this says so.
    hash_is_unique = any(
        row[2] and any(c[2] == "content_hash"
                       for c in conn.execute(f"PRAGMA index_info({row[1]!r})"))
        for row in conn.execute("PRAGMA index_list(helicon_cubes)"))
    if hash_is_unique and not dupes:
        checks.append(_nothing_to_grade(
            "R5", "Duplicate / echo memory",
            "helicon_cubes declares UNIQUE(content_hash), so two live memories "
            "cannot share a hash and this class cannot fire. Byte-identical "
            "duplicates are blocked at write time; near-duplicate echo is "
            "untested"))
    elif live_for_dupes < 2:
        checks.append(_nothing_to_grade(
            "R5", "Duplicate / echo memory",
            f"{live_for_dupes} live memory(s) stored; a duplicate needs two"))
    else:
        checks.append(_check(
            "R5", "Duplicate / echo memory", "TESTED", dupes > 0,
            f"{dupes} content hash(es) stored more than once among "
            f"{live_for_dupes} live memories"))

    # R6 title-only grounding — a memory whose title is all there is.
    #
    # Rewritten 2026-08-14, after a 13-fixture sweep caught it firing in both
    # wrong directions on a stranger's first run. Two defects, one line each:
    #
    #   length(content) < 40  called "Format with black, line length 100." a
    #   stub. That is a complete rule, and the tool reported a first-time
    #   reader's own correct instruction to them as rot.
    #
    #   (stubs / total_live) if total_live else 0  scored a CLAUDE.md of four
    #   empty headings as CLEAN, because it stored no memories at all and an
    #   empty denominator fell through to 0. Emptiness read as health.
    #
    # Title-only is a shape, not a length: the body is missing, or it only
    # repeats the heading. Short and complete is not a stub. The 10% threshold
    # is unchanged and now says so out loud, because a share with a hidden
    # cutoff is a number nobody can check.
    rows = conn.execute(
        "SELECT title, content FROM helicon_cubes "
        "WHERE review_status IN ('pending', 'revised') AND merged_into IS NULL"
    ).fetchall()
    total_live = len(rows)
    stubs = sum(1 for title, content in rows if _title_only(title, content))
    if not total_live:
        checks.append(_check(
            "R6", "Title-only grounding", "TESTED", None,
            "no live memories to grade: nothing was stored from this repo's "
            "instruction files, so this class is unmeasured, not clean"))
    else:
        checks.append(_check(
            "R6", "Title-only grounding", "TESTED",
            (stubs / total_live) > 0.10,
            f"{stubs}/{total_live} live memories are title-only "
            f"(no body, or a body that only repeats the heading); "
            f"fires above 10%; battery tests Thinness+Grounding cover retrieval"))

    # R7 wrong eviction — the regret ledger.
    try:
        from helicon.regret import get_regrets
        # Regret is measured over memories this store has retired. A store that
        # has never killed anything cannot have regretted it.
        retired = conn.execute(
            "SELECT COUNT(*) FROM helicon_cubes "
            "WHERE review_status IN ('killed', 'superseded')"
        ).fetchone()[0]
        if not retired:
            checks.append(_nothing_to_grade(
                "R7", "Wrong eviction (regret)",
                "no memory has been retired here, so none can have been "
                "retired wrongly"))
        else:
            regrets = get_regrets(conn, limit=100)
            checks.append(_check(
                "R7", "Wrong eviction (regret)", "TESTED", len(regrets) > 0,
                f"{len(regrets)} of {retired} retired memories retrieval has "
                "wanted back (time-decayed, blame on the kill decision)"))
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
    # The guard can only be audited against reviews that exist. A store with no
    # review history has not held the line, it has never been asked to.
    reviews_total = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    if not reviews_total:
        checks.append(_nothing_to_grade(
            "R9", "Self-evidence loops",
            "no reviews recorded here, so the human-evidence guard has never "
            "been exercised"))
    else:
        checks.append(_check(
            "R9", "Self-evidence loops", "TESTED", leaked > 0,
            f"{non_human} of {reviews_total} review(s) are automated and correctly "
            f"quarantined from rule learning; {leaked} leaked past the guard"))

    # R10 instruction-file drift — agent-rules/skills memories retired or duplicated.
    rules_retired = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE source IN ('agent-rules', 'skills') "
        "AND review_status = 'superseded'"
    ).fetchone()[0]
    rules_live = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE source IN ('agent-rules', 'skills') "
        "AND review_status NOT IN ('killed', 'superseded')"
    ).fetchone()[0]
    # The empty-set rule, call site eight, and the last one in the exam. R10
    # counts sections this store has RETIRED as drifted, which is history. A
    # first run has retired nothing, so "0 retired" is the store's age, not the
    # repo's health. The sweep's R10 fixture plants CLAUDE.md saying black/100
    # against .cursorrules saying ruff/79 — the exact rot the class is named
    # for — and R10 answered CLEAN. Detecting that disagreement live, rather
    # than noticing it was retired later, is not built.
    prior_scans = conn.execute("SELECT COUNT(*) FROM scan_log").fetchone()[0]
    if not rules_retired and prior_scans < 2:
        checks.append(_nothing_to_grade(
            "R10", "Instruction-file drift",
            f"{rules_live} rules/skills section(s) live and none retired yet; "
            "drift is measured against a previous scan, so a first run has no "
            "baseline to drift from"))
    else:
        checks.append(_check(
            "R10", "Instruction-file drift", "TESTED", rules_retired > 0,
            f"{rules_retired} rules/skills section(s) retired as drifted; {rules_live} live "
            "(section-level memories, covered by reconcile + snapshots)"))

    # R11 identity coherence — one entity's DEFINITION forks across sources (same
    # name, incompatible genera). R1 is blind: no scalar slot to compare. Deterministic.
    try:
        from helicon.identity import find_identity_forks
        # Same empty-set rule as R3/R5/R7/R9/R12, and R11 hid best of the six:
        # it fires correctly whenever definitions exist, so its own sweep
        # fixture passed. On openai/codex it printed CLEAN over a corpus that
        # defines nothing — a definition cannot fork when no name has been
        # defined once.
        #
        # The population is names glossed in the LIVE CUBES, not rows in the
        # entities table. My first version gated on entities and a test caught
        # it: find_identity_forks reads cubes and never consults that table, so
        # the gate would have silenced a class that was working. Wrong object,
        # again, and the suite is what found it.
        from helicon.identity import extract_glosses
        glossed = {g["name"] for (title, content) in conn.execute(
            "SELECT title, content FROM helicon_cubes WHERE review_status IN "
            "('pending', 'revised', 'approved') AND merged_into IS NULL")
            for g in extract_glosses(content or "", title or "")}
        # One name defined twice is a fork; two distinct names are not. The
        # threshold is "any definition at all", and I had it at two until the
        # suite failed on a fixture where both cubes define the same name.
        entity_count = len(glossed)
        if not entity_count:
            checks.append(_nothing_to_grade(
                "R11", "Identity coherence",
                "no name is defined anywhere in this repo's instruction files, "
                "so no definition can fork"))
        else:
            # Semantic-confirmed forks = exactly what `resolve --list` lets you
            # rule. The exam must count the SAME set the loop can act on; the
            # fast genus-only pass over-reports the false positives the semantic
            # gate (local embeddings, no LLM) exists to kill. Candidates it
            # drops are reported as an unconfirmed sub-signal, never as ROT.
            forks = find_identity_forks(conn, semantic=True, judge_client=judge_client,
                                        judge_model=judge_model)
            candidates = find_identity_forks(conn, semantic=False)
            unconfirmed = max(0, len(candidates) - len(forks))
            # Name the gate that produced the number. Cosine cannot separate a
            # fork from a rephrasing (real 0.354 vs artifact 0.367 on the live
            # store), so a cosine-only R11 is over-reporting and must say so
            # rather than sell its candidates as confirmed rot.
            gate = "qwen-judged" if judge_client else "cosine-only, unjudged"
            note = (f" (+{unconfirmed} genus candidate(s) dropped by the {gate} gate)"
                    if unconfirmed else f" [{gate}]")
            checks.append(_check(
                "R11", "Identity coherence", "TESTED", len(forks) > 0,
                (f"{len(forks)} entity definition(s) forked across sources: "
                 + ", ".join(f"{x['name']} ({x['genus_a']}/{x['genus_b']})"
                             for x in forks[:3])
                 + note)
                if forks else
                f"no confirmed entity definition forks among {entity_count} "
                f"entities{note}"))
    except Exception as e:
        checks.append(_check("R11", "Identity coherence", "TESTED", None, f"unmeasured: {e}"))

    # R12 phantom association — a relation asserted by a single speculative source
    # that nothing else grounds. R1/R11 blind: no scalar slot, no definition fork.
    try:
        from helicon.relations import find_phantom_relations
        # A relation BETWEEN entities needs two entities to sit between.
        entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        if entities < 2:
            checks.append(_nothing_to_grade(
                "R12", "Phantom association",
                f"{entities} entity(s) extracted; a relation between entities "
                "needs two"))
        else:
            phantoms = find_phantom_relations(conn)
            checks.append(_check(
                "R12", "Phantom association", "TESTED", len(phantoms) > 0,
                (f"{len(phantoms)} ungrounded relation(s): "
                 + ", ".join(f"{x['subj']}->{x['obj']}" for x in phantoms[:3]))
                if phantoms else
                f"no ungrounded single-source relations among {entities} entities"))
    except Exception as e:
        checks.append(_check("R12", "Phantom association", "TESTED", None, f"unmeasured: {e}"))

    # R13 document vs live system — the only class whose counterparty is not
    # another claim. A sentence asserting a live-system fact gets an executable
    # probe; it goes stale when the probe disagrees, not when a second document
    # does. Unverifiable is reported as its own state and never as clean: a
    # probe that could not run has proved nothing.
    if repo_root:
        try:
            from helicon.probes import probe_docs, CONTRADICTED, UNVERIFIABLE
            probes = probe_docs(conn, repo_root, config=config)
            # MOOT is detected as CONTRADICTED and weighted differently —
            # probes.py: "moot findings never gate". That promise was kept by
            # doorway.py and broken here: counting an obsolete sequencing rule
            # as rot set R13 to ROT FOUND and made `helicon ci` exit 1 over a
            # rule the code already agrees with. Obsolete is not false.
            moot = [p for p in probes if p["verdict"] == CONTRADICTED and p.get("moot")]
            bad = [p for p in probes
                   if p["verdict"] == CONTRADICTED and not p.get("moot")]
            unver = [p for p in probes if p["verdict"] == UNVERIFIABLE]
            if not probes:
                checks.append(_check(
                    "R13", "Document vs live system", "TESTED", None,
                    "no probe-able assertion found in this repo's instruction "
                    "docs — unmeasured, not clean"))
            else:
                receipt = (f"{len(bad)} sentence(s) contradicted by the running "
                           f"system, "
                           + (f"{len(moot)} moot, " if moot else "")
                           + f"{len(unver)} unverifiable, "
                           + f"{len(probes) - len(bad) - len(moot) - len(unver)} upheld")
                if bad:
                    receipt += ": " + "; ".join(
                        f"{p['file']}:{p['line']} ({p['kind']})" for p in bad[:3])
                checks.append(_check("R13", "Document vs live system", "TESTED",
                                     bool(bad), receipt))
        except Exception as e:
            checks.append(_check("R13", "Document vs live system", "TESTED", None,
                                 f"unmeasured: {e}"))
    else:
        checks.append(_check(
            "R13", "Document vs live system", "TESTED", None,
            "no repo given — pass repo_root (helicon ci --path <repo>) to probe "
            "instruction docs against the running system"))

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
