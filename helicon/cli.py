#!/usr/bin/env python3
"""Mount Helicon CLI - plug-and-play memory audit for AI agent stacks.

Usage:
  helicon init          Auto-detect your AI tools and create config
  helicon scan          Scan all detected sources
  helicon reconcile     Retire memory a re-scan no longer sees (dry-run by default)
  helicon fix-skills    Write descriptions into SKILL.md files missing one (dry-run by default)
  helicon serve         Start the web UI
  helicon triage        Run auto-triage (autonomous decisions)
  helicon doctor        Health check: PATH, config, Qwen key, DB, last scan
  helicon mcp           Run the MCP server on stdio (for agent clients)
  helicon score         Show current Helicon Score
  helicon stack         Audit your AI stack setup
  helicon optimize      LLM-powered optimization suggestions
"""

import argparse
import json
import os
import sys
import platform


def _detect_sources() -> dict:
    """Auto-detect AI tools and their data locations."""
    home = os.path.expanduser("~")
    detected = {}

    claude_dir = os.path.join(home, ".claude")
    if os.path.isdir(claude_dir):
        projects_dir = os.path.join(claude_dir, "projects")
        jsonl_dirs = []
        if os.path.isdir(projects_dir):
            for root, dirs, files in os.walk(projects_dir):
                for f in files:
                    if f.endswith(".jsonl"):
                        jsonl_dirs.append(root)
                        break
        memory_dir = os.path.join(claude_dir, "memory") if os.path.isdir(os.path.join(claude_dir, "memory")) else None
        if not memory_dir:
            for root, dirs, _ in os.walk(projects_dir):
                if "memory" in dirs:
                    memory_dir = os.path.join(root, "memory")
                    break

        if jsonl_dirs or memory_dir:
            detected["claude_code"] = {
                "enabled": True,
                "jsonl_dir": jsonl_dirs[0] if jsonl_dirs else "",
                "memory_dir": memory_dir or "",
            }
            sessions_index = os.path.join(claude_dir, "sessions-index.json")
            if os.path.exists(sessions_index):
                detected["claude_code"]["sessions_index"] = sessions_index

    cursor_dir = os.path.join(home, ".cursor")
    if os.path.isdir(cursor_dir):
        detected["cursor"] = {"enabled": True, "cursor_dir": cursor_dir}

    if platform.system() == "Darwin":
        obsidian_base = os.path.join(home, "Library", "Mobile Documents", "iCloud~md~obsidian", "Documents")
        if os.path.isdir(obsidian_base):
            vaults = [d for d in os.listdir(obsidian_base) if os.path.isdir(os.path.join(obsidian_base, d))]
            if vaults:
                detected["obsidian"] = {
                    "enabled": True,
                    "vault_path": os.path.join(obsidian_base, vaults[0]),
                    "vaults_found": vaults,
                }
    else:
        for candidate in [
            os.path.join(home, "Documents", "Obsidian"),
            os.path.join(home, "Obsidian"),
            os.path.join(home, ".obsidian"),
        ]:
            if os.path.isdir(candidate):
                detected["obsidian"] = {"enabled": True, "vault_path": candidate}
                break

    code_dirs = [
        os.path.join(home, "CODE"),
        os.path.join(home, "code"),
        os.path.join(home, "projects"),
        os.path.join(home, "src"),
        os.path.join(home, "dev"),
        os.path.join(home, "repos"),
        os.path.join(home, "workspace"),
    ]
    for d in code_dirs:
        if os.path.isdir(d):
            git_count = sum(1 for item in os.listdir(d)
                          if os.path.isdir(os.path.join(d, item, ".git")))
            if git_count > 0:
                detected["git"] = {"enabled": True, "repos_dir": d, "repos_found": git_count}
                break

    chatgpt_exports = [
        os.path.join(home, "Downloads"),
        os.path.join(home, "Documents"),
    ]
    for d in chatgpt_exports:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if "chatgpt" in f.lower() and f.endswith(".json"):
                    detected["chatgpt"] = {
                        "enabled": True,
                        "export_path": os.path.join(d, f),
                    }
                    break

    return detected


def cmd_init(args):
    """Auto-detect AI tools and create config.json."""
    print("Mount Helicon init - detecting your AI stack...\n")
    detected = _detect_sources()

    if not detected:
        print("No AI tools detected. Supported:")
        print("  - Claude Code (~/.claude/)")
        print("  - Cursor (~/.cursor/)")
        print("  - Obsidian (iCloud or ~/Documents/Obsidian/)")
        print("  - Git repos (~/CODE/, ~/projects/, ~/src/)")
        print("  - ChatGPT exports (~/Downloads/*.json)")
        return

    print(f"Found {len(detected)} source(s):\n")
    for name, info in detected.items():
        print(f"  {name}")
        for k, v in info.items():
            if k == "enabled":
                continue
            if isinstance(v, list):
                print(f"    {k}: {', '.join(str(x) for x in v[:3])}")
            else:
                print(f"    {k}: {v}")
        print()

    config = {
        "db_path": "data/helicon.db",
        "qwen_api_key": os.environ.get("QWEN_API_KEY", ""),
        "connectors": {},
        "audit": {"temporal_stale_days": 7},
        "weibull": {
            "code": {"eta": 5, "kappa": 1.5},
            "draft": {"eta": 10, "kappa": 1.8},
            "dashboard": {"eta": 3, "kappa": 2.0},
            "decision": {"eta": 30, "kappa": 0.8},
            "pattern": {"eta": 60, "kappa": 0.7},
            "archive": {"eta": 90, "kappa": 0.5},
        },
    }

    for name, info in detected.items():
        conn = {k: v for k, v in info.items() if k != "vaults_found" and k != "repos_found"}
        config["connectors"][name] = conn

    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    if os.path.exists(config_path) and not args.force:
        print(f"config.json already exists. Use --force to overwrite.")
        return

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"Wrote config.json with {len(detected)} connector(s)")
    print("Next: run `helicon scan` to extract memory items")


def cmd_scan(args):
    """Scan all configured sources."""
    from helicon.config import load_config
    from helicon.scanner import run_scan

    config = load_config()
    if not config.get("connectors"):
        print("No connectors configured. Run `helicon init` first.")
        return

    print("Mount Helicon scan\n")
    stats = run_scan(config)
    print(f"\nFound {stats['total_raw']} items, added {stats['added']}, skipped {stats['skipped']} dupes")
    print(f"Total in DB: {stats['total_in_db']}")
    for source, count in stats.get("by_source", {}).items():
        print(f"  {source}: {count}")


def cmd_reconcile(args):
    """Retire cubes a re-scan no longer sees. Dry-run by default; --apply to
    mark them superseded. Never touches human-reviewed (approved/killed) cubes."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.reconcile import reconcile_scan
    from helicon.scanner import collect_present_hashes

    config = load_config()
    if not config.get("connectors"):
        print("No connectors configured. Run `helicon init` first.")
        return
    conn = init_db(config["db_path"])

    mode = "APPLY" if args.apply else "dry-run"
    print(f"Mount Helicon reconcile ({mode})\n")
    print("Re-scanning sources to compute present hashes...")
    scopes = collect_present_hashes(config, source=args.source)
    if not scopes:
        target = f"source '{args.source}'" if args.source else "any configured source"
        print(f"Re-scan found nothing for {target}. Not retiring anything.")
        return
    print(f"  {len(scopes)} (source, file) scope(s) scanned")

    total = 0
    for (source, scope), hashes in sorted(scopes.items()):
        rec = reconcile_scan(conn, source=source, present_hashes=hashes,
                             scope_prefix=scope, dry_run=not args.apply)
        if not rec["count"]:
            continue
        total += rec["count"]
        verb = "would retire" if not args.apply else "retired"
        print(f"\n{source} :: {scope} — {verb} {rec['count']}:")
        for r in rec["retired"]:
            row = conn.execute(
                "SELECT source_ref FROM helicon_cubes WHERE id = ?", (r["id"],)
            ).fetchone()
            ref = row["source_ref"] if row else "?"
            print(f"  {r['id']}  {r['title'][:60]:60s}  ({ref})")

    if total == 0:
        print("\nNothing to retire. Memory matches the re-scan.")
    elif args.apply:
        print(f"\nRetired {total} memories as 'superseded'.")
    else:
        print(f"\nWould retire {total} memories. Run with --apply to execute.")


def cmd_fix_skills(args):
    """Write back Qwen-generated descriptions into SKILL.md files that the
    skills audit flags as missing one. Dry-run by default; --apply writes with
    a .bak backup per modified file."""
    from helicon.config import load_config
    from helicon.qwen import get_client, resolve_model
    from helicon.writeback import DEFAULT_SKILLS_DIR, fix_skills

    config = load_config()
    client = get_client(config)
    model = resolve_model("fast", config)
    skills_dir = args.skills_dir or DEFAULT_SKILLS_DIR

    mode = "APPLY" if args.apply else "dry-run"
    print(f"Mount Helicon fix-skills ({mode})  dir: {skills_dir}\n")
    if client is None:
        print("No Qwen key configured (set QWEN_API_KEY). Descriptions can't be "
              "generated; listing files that need one:\n")

    result = fix_skills(skills_dir, client=client, model=model, apply=args.apply)
    if not result["records"]:
        print("No skill files found.")
        return

    for r in result["records"]:
        if r["action"] == "has_description":
            continue
        if r["action"] == "skipped_no_client":
            print(f"  [skip] {r['rel']}  (missing description; no Qwen key)")
        elif r["action"] == "failed":
            print(f"  [fail] {r['rel']}  (Qwen returned nothing usable)")
        elif r["action"] == "proposed":
            print(f"  [would fix] {r['rel']}")
            print(f"      description: {r['description']}")
        elif r["action"] == "fixed":
            print(f"  [fixed] {r['rel']}  (.bak written)")
            print(f"      description: {r['description']}")

    c = result["counts"]
    ok = c.get("has_description", 0)
    print(f"\n{sum(c.values())} skill file(s): {ok} already described, "
          f"{c.get('proposed', 0)} proposed, {c.get('fixed', 0)} fixed, "
          f"{c.get('skipped_no_client', 0)} skipped (no key), {c.get('failed', 0)} failed")
    if c.get("proposed"):
        print("Dry-run: nothing written. Run with --apply to write (creates .bak backups).")


def cmd_serve(args):
    """Start the web UI."""
    port = args.port or 8420
    print(f"Starting Mount Helicon at http://localhost:{port}")
    print("Press Ctrl+C to stop\n")
    import uvicorn
    uvicorn.run("helicon.api.app:app", host="0.0.0.0", port=port)


def cmd_triage(args):
    """Run auto-triage."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.triage import init_triage_table, run_auto_triage

    config = load_config()
    conn = init_db(config["db_path"])
    init_triage_table(conn)

    result = run_auto_triage(conn, dry_run=args.dry_run)
    mode = "Preview" if args.dry_run else "Executed"
    print(f"\n{mode}: {result['triaged']} items triaged using {result['rules_applied']} rule(s)")
    for a in result["actions"][:10]:
        print(f"  {a['action']:8s} {a['title'][:60]}")
    if len(result["actions"]) > 10:
        print(f"  ... and {len(result['actions']) - 10} more")


def _cluster_pending(conn, pending, threshold):
    """Group pending cubes so one decision can clear many.

    Uses embedding cosine similarity (vectors are stored normalized, so a dot
    product is the cosine). Seeds the biggest clusters first by picking the
    highest-degree unassigned cube each round, so the most leverage surfaces at
    the top. Cubes without embeddings become singletons.
    Returns a list of {"rep": row, "similar": [rows]}.
    """
    pend_ids = [r["id"] for r in pending]
    row_by_id = {r["id"]: r for r in pending}

    try:
        import numpy as np
        from helicon.embeddings import _load_all_embeddings
        ids, matrix = _load_all_embeddings(conn)
    except Exception:
        ids, matrix = [], None

    clusters = []
    assigned = set()

    if matrix is not None and len(ids):
        idx_by_id = {cid: i for i, cid in enumerate(ids)}
        emb_ids = [cid for cid in pend_ids if cid in idx_by_id]
        if emb_ids:
            sub = matrix[[idx_by_id[c] for c in emb_ids]]
            sim = sub @ sub.T
            m = len(emb_ids)
            # order seeds by neighbor count (degree) so large clusters lead
            degree = sorted(
                ((int((sim[i] >= threshold).sum()), i) for i in range(m)),
                reverse=True,
            )
            for _, i in degree:
                cid = emb_ids[i]
                if cid in assigned:
                    continue
                neighbors = [
                    emb_ids[j] for j in range(m)
                    if j != i and sim[i, j] >= threshold and emb_ids[j] not in assigned
                ]
                assigned.add(cid)
                assigned.update(neighbors)
                clusters.append({"rep": row_by_id[cid],
                                 "similar": [row_by_id[n] for n in neighbors]})

    for cid in pend_ids:
        if cid not in assigned:
            assigned.add(cid)
            clusters.append({"rep": row_by_id[cid], "similar": []})

    return clusters


def _record_cli_review(conn, row, decision, session):
    """Write one human review the same way the web API does (updates cube status,
    reinforcement, Q-value reward, context link). Non-'auto-triage' session so it
    counts as human evidence for triage learning."""
    from datetime import datetime, timezone
    from helicon.db import insert_review
    from helicon.models import Review
    from helicon.context_impact import link_review_to_context
    from helicon.utility import update_reward

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        clean = (row["created_at"] or "").replace("Z", "").split("+")[0]
        age = (now - datetime.fromisoformat(clean)).total_seconds() / 86400
    except (ValueError, AttributeError, TypeError):
        age = 0.0

    insert_review(conn, Review(
        id=None, cube_id=row["id"], decision=decision, notes="",
        time_to_review_seconds=0.0, cube_age_days=round(age, 1),
        cube_type=row["type"], cube_source=row["source"],
        reviewed_at=now.isoformat(), session_id=session,
    ))
    reward = {"approved": 1.0, "revised": 0.8, "killed": 0.0}.get(decision, 0.3)
    for fn in (lambda: link_review_to_context(conn, row["id"], decision),
               lambda: update_reward(conn, row["id"], reward)):
        try:
            fn()
        except Exception:
            pass  # learning side-effects are best-effort; never block a review


def cmd_review(args):
    """Fast, keyboard-driven review. Surfaces the highest-leverage pending items
    (biggest similar-clusters first); one decision can be taught to all similar
    items at once, so the backlog shrinks fast."""
    from helicon.config import load_config
    from helicon.db import init_db

    config = load_config()
    conn = init_db(config["db_path"])

    if getattr(args, "terminals", False):
        from helicon.review_terminals import review_terminals, format_queue
        only = set(x.lower() for x in (getattr(args, "only", None) or []))
        filed = getattr(args, "file", False)
        queue = review_terminals(conn, config, file=filed, only=only,
                                 run=getattr(args, "run", False))
        print(format_queue(queue, filed=filed))
        return

    pending = conn.execute(
        "SELECT id, title, content, type, source, confidence, created_at "
        "FROM helicon_cubes WHERE review_status = 'pending' AND merged_into IS NULL"
    ).fetchall()

    total = len(pending)
    if not total:
        print("\nInbox zero. Nothing pending to review.")
        return

    clusters = _cluster_pending(conn, pending, args.threshold)
    clusters.sort(key=lambda cl: -len(cl["similar"]))
    batch = clusters[: args.batch]

    def _suggest(conf):
        if conf < 0.10:
            return "kill?"
        if conf >= 0.60:
            return "keep?"
        return "review"

    if getattr(args, "preview", False):
        clearable = sum(1 + len(cl["similar"]) for cl in batch)
        print(f"\n{total} pending · {len(clusters)} distinct topics")
        print(f"Top {len(batch)} decisions would clear up to {clearable} items (teach-once).\n")
        for n, cl in enumerate(batch, 1):
            rep, sim = cl["rep"], cl["similar"]
            conf = rep["confidence"] or 0.0
            preview = " ".join((rep["content"] or "").split())[:110]
            reach = f"  ->teaches {len(sim)}" if sim else ""
            print(f"{n:2}. [{_suggest(conf):6}] {rep['title'][:60]:60} {conf:>4.0%}{reach}")
            print(f"    {rep['type']}/{rep['source']}  {preview}")
        print(f"\n(preview only, nothing written. run without --preview to decide.)")
        return

    print(f"\n{total} pending. {len(clusters)} distinct topics. "
          f"Showing the {len(batch)} highest-leverage.")
    print("[a]pprove  [k]ill  [r]evise  [s]kip  [q]uit\n")

    reviewed = 0
    try:
        for n, cl in enumerate(batch, 1):
            rep, similar = cl["rep"], cl["similar"]
            conf = rep["confidence"] or 0.0
            hint = "  (very low confidence)" if conf < 0.1 else ""
            preview = " ".join((rep["content"] or "").split())[:200]
            print(f"[{n}/{len(batch)}] {rep['title'][:72]}")
            print(f"    {rep['type']} · {rep['source']} · conf {conf:.0%}{hint}")
            if preview:
                print(f"    {preview}")
            if similar:
                print(f"    +{len(similar)} similar pending items would be taught the same call")

            choice = input("  > ").strip().lower()
            if choice in ("q", "quit"):
                break
            decision = {"a": "approved", "k": "killed", "r": "revised"}.get(choice)
            if not decision:
                print("    skipped\n")
                continue

            _record_cli_review(conn, rep, decision, "cli-review")
            reviewed += 1

            if similar:
                ans = input(f"    Teach '{decision}' to {len(similar)} similar? [Y/n] ").strip().lower()
                if ans in ("", "y", "yes"):
                    for s in similar:
                        _record_cli_review(conn, s, decision, "cli-review-taught")
                    reviewed += len(similar)
                    print(f"    ✓ {decision} +{len(similar)} taught\n")
                else:
                    print(f"    ✓ {decision}\n")
            else:
                print(f"    ✓ {decision}\n")
            conn.commit()
    except (KeyboardInterrupt, EOFError):
        print("\n  interrupted, saving...")

    conn.commit()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes WHERE review_status = 'pending' AND merged_into IS NULL"
    ).fetchone()[0]
    print(f"Reviewed {reviewed} this session. Pending: {total} -> {remaining}")


def cmd_route(args):
    """Routing recommendation as a read of the eval store: which model has the best
    verified track record per task-class. --record first builds the evidence from
    `review --terminals` (add --run to verify test counts too)."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.route import record_evidence, route, format_route

    config = load_config()
    conn = init_db(config["db_path"])

    if getattr(args, "record", False):
        only = set(x.lower() for x in (getattr(args, "only", None) or []))
        summ = record_evidence(conn, config, run=getattr(args, "run", False), only=only)
        print(f"recorded {summ['rows']} verdict(s) into route_evidence  "
              f"({summ['by_verdict']})")
        print(f"  models seen: {summ['models']}")

    if getattr(args, "per_token", False):
        from helicon.route import per_token, format_per_token
        jsonl_dir = (config.get("connectors", {}).get("claude-code", {}) or {}).get(
            "jsonl_dir") or "~/.claude/projects"
        print(format_per_token(per_token(conn, jsonl_dir, since=getattr(args, "since", None))))
        return

    routed = route(conn, task_class=getattr(args, "task", None),
                   min_n=getattr(args, "min_n", 5))
    print(format_route(routed))
    if not getattr(args, "record", False) and routed["total_classes"] == 0:
        print("  (no evidence yet - run:  helicon route --record --run)\n")


def cmd_score_runs(args):
    """Run Ratings (building): the cost + identity of runs. Parse Claude Code
    transcripts into per-session cost, cluster sessions into runs (slice 1.2).
    Yield + score land in later slices. Default view = runs; --sessions = raw."""
    from helicon.config import load_config
    from helicon.runs import (scan_session_costs, group_runs,
                              format_session_costs, format_runs)

    config = load_config()
    jsonl_dir = (config.get("connectors", {}).get("claude-code", {}) or {}).get(
        "jsonl_dir") or "~/.claude/projects"
    recs = scan_session_costs(jsonl_dir, since=getattr(args, "since", None))
    limit = getattr(args, "limit", 20)
    if getattr(args, "sessions", False):
        print(format_session_costs(recs, limit=limit))
        return
    runs = group_runs(recs, gap_min=getattr(args, "gap", 300))
    if getattr(args, "card", False):
        from helicon.db import init_db
        from helicon.runs import build_run_card, format_run_card, persist_run_card
        if not runs:
            print("\n  No runs to card.\n"); return
        conn = init_db(config["db_path"])
        card = build_run_card(conn, runs[0], damage=getattr(args, "damage", 0.0) or 0.0)
        print(format_run_card(card))
        if getattr(args, "persist", False):
            persist_run_card(conn, card)
            print(f"  persisted to run_cards ({card['run_id']}). See:  helicon runs\n")
        return
    print(format_runs(runs, limit=limit))


def cmd_runs(args):
    """Slice 1.6/1.7: the Latest-runs surface. Renders the scored run-card history
    from run_cards, and (1.7) the suggestions read off it."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.runs import latest_run_cards, format_latest

    config = load_config()
    conn = init_db(config["db_path"])
    if getattr(args, "close", False):
        from helicon.runs import close_run
        card = close_run(conn, config, run_tests=getattr(args, "run", False),
                         damage=getattr(args, "damage", 0.0) or 0.0)
        if card:
            print(f"  closed run {card['run_id']}: {card['verified']}/{card['checkable']} "
                  f"verified, score {card['score']}  ->  persisted to run_cards")
        else:
            print("  no run to close.")
        return
    cards = latest_run_cards(conn, limit=getattr(args, "limit", 15))
    print(format_latest(cards))
    if getattr(args, "suggest", False):
        from helicon.runs import suggest_runs, format_suggestions
        print(format_suggestions(suggest_runs(conn, config)))


def cmd_guard(args):
    """Live guard: check a proposed output against the law (rulings) before it's
    written. The write-time enforcement of GOLDEN_RULES (also the helicon_guard
    MCP tool)."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.guard import guard_output, format_guard

    config = load_config()
    conn = init_db(config["db_path"])
    print(format_guard(guard_output(conn, args.text)))


def cmd_attribute(args):
    """Auto-attribution: trace a contradicted output finding back to the memory
    cube(s) that caused it, so you can retire the actual cause when you rule."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.attribution import attribute_finding

    config = load_config()
    conn = init_db(config["db_path"])
    row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (args.id,)).fetchone()
    if row is None:
        print(f"  no finding #{args.id}")
        return
    res = attribute_finding(conn, row, limit=getattr(args, "limit", 5))
    print(f"\n  ATTRIBUTION — finding #{args.id}")
    print(f"  claim: {res['claim'][:100]}")
    if not res["candidates"]:
        print("  no pre-existing memory matches this claim (keywords: "
              f"{', '.join(res['keywords']) or 'none'}).\n")
        return
    print(f"  memories that most likely CAUSED it (retire the real one when you rule):\n")
    for c in res["candidates"]:
        print(f"    {c['id']}  [{c['source']}]  {c['title'][:50]}")
        print(f"        {c['snippet']}")
    print(f"\n  rule + retire the cause:  helicon resolve {args.id} --truth \"<the truth>\" --retire <memory_id>\n")


def cmd_move(args):
    """Slice 5: the context-mover. Read memory, verify it, render into another
    platform's format. Dry-run by default; --apply writes (backs up first)."""
    from helicon.config import load_config
    from helicon.mover import move, format_move

    config = load_config()
    res = move(args.from_path, args.to, out_path=getattr(args, "out", None),
               apply=getattr(args, "apply", False),
               verify_contradictions_flag=getattr(args, "verify_contradictions", False),
               config=config)
    print(format_move(res))


def cmd_judge_bench(args):
    """Slice 1: benchmark Qwen tiers as the memory-rot judge vs human labels."""
    from helicon.config import load_config
    from helicon.judge_bench import run_judge_bench, format_judge_bench, TIERS

    config = load_config()
    tiers = (getattr(args, "tiers", None) or ",".join(TIERS)).split(",")
    res = run_judge_bench(config, tiers=[t.strip() for t in tiers],
                          which=getattr(args, "set", "ruled"))
    if "error" in res:
        print(f"  judge-bench: {res['error']}")
        return
    print(format_judge_bench(res["scored"]))
    for note in res.get("notes", []):
        print(f"  note: {note}")

    # --save persists the run so the dashboard has something real to render. The
    # dashboard never runs a bench itself (live cross-provider calls cost money),
    # so this command is the only way that surface gets data.
    if getattr(args, "save", False):
        from helicon.db import init_db
        from helicon.judge_bench import save_judge_run

        conn = init_db(config.get("db_path", "data/helicon.db"))
        rid = save_judge_run(conn, res, which=getattr(args, "set", "ruled"))
        print(f"  saved run #{rid} — the JUDGE tab now reads this run.")


def cmd_leaderboard(args):
    """Population-scale model reliability from git history (execution-free): rank
    models by how often their commits survive vs get reverted, across repos."""
    import os
    from helicon.leaderboard import build_leaderboard, format_leaderboard

    repos = list(getattr(args, "repos", None) or [])
    if not repos:
        code = os.path.expanduser("~/CODE")
        repos = [os.path.join(code, d) for d in sorted(os.listdir(code))
                 if os.path.isdir(os.path.join(code, d, ".git"))] if os.path.isdir(code) else []
    repos = [r for r in repos if os.path.isdir(os.path.join(r, ".git"))]
    if not repos:
        print("  No git repos to scan (pass paths, or populate ~/CODE).")
        return
    lb = build_leaderboard(repos, max_commits=getattr(args, "max", 500),
                           by_task=getattr(args, "by_task", False))
    print(format_leaderboard(lb))


def cmd_snapshot(args):
    """Regression-test retrieved context: capture baselines, check for drift."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.snapshots import init_snapshot_table, capture_snapshot, check_all

    config = load_config()
    conn = init_db(config["db_path"])
    init_snapshot_table(conn)

    if args.action == "add":
        if not args.task:
            print('usage: helicon snapshot add "<task>"')
            return
        r = capture_snapshot(conn, args.task, k=args.k)
        print(f"\nSnapshot #{r['id']} captured for: \"{args.task}\"  (top {r['top_k']})")
        for i, h in enumerate(r["hits"], 1):
            print(f"  {i}. {h['title'][:66]}")

    elif args.action == "list":
        rows = conn.execute(
            "SELECT id, task, top_k, created_at FROM context_snapshots ORDER BY id"
        ).fetchall()
        if not rows:
            print('No snapshots yet. Add one:  helicon snapshot add "<task>"')
            return
        for r in rows:
            print(f"  #{r['id']:<3} k={r['top_k']}  \"{r['task']}\"")

    elif args.action == "check":
        results = check_all(conn)
        if not results:
            print("No snapshots to check.")
            return
        regr = 0
        for res in results:
            mark = "REGRESSED" if res["regressed"] else "stable"
            sym = "x" if res["regressed"] else "."
            print(f"\n[{sym}] #{res['snapshot_id']} \"{res['task']}\"  "
                  f"{int(res['overlap']*100)}% overlap  -> {mark}")
            for t in res["dropped"]:
                print(f"    - dropped:   {t[:60]}")
            for t in res["added"]:
                print(f"    + added:     {t[:60]}")
            if res["reordered"]:
                print(f"    ~ reordered top-K")
            for t, why in res["stale"]:
                print(f"    ! stale ({why}): {t[:52]}")
            regr += 1 if res["regressed"] else 0
        print(f"\n{regr}/{len(results)} snapshots regressed.")


def cmd_battery(args):
    """Context-quality battery: named tests on what a task retrieves."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.battery import run_battery, format_battery_prompt
    from helicon.snapshots import _retrieve

    if not args.task:
        print('usage: helicon check "<task>"')
        return
    config = load_config()
    conn = init_db(config["db_path"])
    # Build a Qwen client when possible so Contradiction/Grounding are judged
    # live; --no-llm forces deterministic-only.
    client = None
    if not getattr(args, "no_llm", False):
        from helicon.qwen import get_client, set_cache_db, resolve_model
        set_cache_db(conn)
        client = get_client(config)
    model = resolve_model("default", config) if client else "qwen3.6-plus"
    # Freshness half-life = the fastest-decaying cube type's stability. Scans
    # older than that make any verdict ambiguous (stale memory vs stale scan).
    stability = config.get("forgetting", {}).get("stability", {})
    half_life_days = min(stability.values()) if stability else 7.0
    res = run_battery(conn, args.task, k=args.k, client=client, model=model,
                      stale_after_hours=half_life_days * 24)

    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(res, indent=2, default=str))
        return

    print(f"\nContext battery for: \"{args.task}\"  (top {res['top_k']})")
    print(f"Verdict: {res['verdict']}\n")
    for r in res["results"]:
        crit = " *" if r.get("critical") and r["status"] == "FAIL" else ""
        judged = " (qwen)" if r.get("judged_by") == "qwen" else ""
        print(f"  [{r['status']}] {r['name']:<13} {r['reason']}{crit}{judged}")

    print(f"\n  context cost: ~{res['context_tokens']} tokens for top-{res['top_k']}")
    scan = res["last_scan"]
    if scan["hours_ago"] is None:
        print("\n  ! no completed scan logged — this verdict may reflect a stale "
              "scan, not stale memory. Run: helicon scan")
    else:
        age = scan["hours_ago"]
        age_str = f"{age:.1f}h ago" if age < 48 else f"{age / 24:.1f}d ago"
        print(f"\n  last scan: {age_str}")
        if scan["stale"]:
            print(f"  ! scan age exceeds the freshness half-life ({half_life_days:.0f}d) — "
                  "this verdict may reflect a stale scan, not stale memory. Run: helicon scan")
    if not res.get("llm_ran") and res["llm_tests"]:
        print(f"\n  llm-judged (needs a Qwen key): {', '.join(res['llm_tests'])}")
    if getattr(args, "prompt", False):
        print("\n--- LLM battery prompt ---")
        print(format_battery_prompt(args.task, _retrieve(conn, args.task, args.k)))


def cmd_taste(args):
    """Taste-verdict memory: remember Taste Machine rulings + the never-twice guard."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.taste import ingest_file, taste_guard
    config = load_config()
    conn = init_db(config["db_path"])
    if args.ingest:
        res = ingest_file(conn, args.ingest)
        print(f"ingested {res['ingested']} verdict(s); {res['already_had']} already remembered")
        return
    if args.hash or args.move:
        g = taste_guard(conn, artifact_hash=args.hash, move=args.move)
        if g["already_ruled"]:
            print(f"ALREADY RULED ({g['match']}): {g.get('prior_verdict')} \u2014 {g.get('reason')}")
        else:
            print("not yet ruled \u2014 fresh output")
        return
    print('usage: helicon taste --ingest <verdicts.json>  |  --hash <h> | --move <name>')


def cmd_lens(args):
    """Memory Causal Lens: the memories behind an answer, with provenance."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.provenance import memory_provenance, format_provenance
    if not args.task:
        print('usage: helicon lens "<task or answer>"')
        return
    config = load_config()
    conn = init_db(config["db_path"])
    rows = memory_provenance(conn, args.task, k=args.k)
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(rows, indent=2, default=str))
        return
    print(format_provenance(args.task, rows))


def cmd_rot(args):
    """The rot exam: ROT.md's 12 documented failure classes checked live
    against the real store. Deterministic, zero LLM calls, free to run daily.

    --judge opts R11 into the Qwen identity judge. Off by default on purpose:
    the exam's contract is deterministic-and-free (a daily cron runs it), and
    the judge costs a call per fork candidate. Without it R11 prints
    'cosine-only, unjudged' rather than passing the weaker gate off as the exam."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.rot import format_rot, run_rot_exam

    config = load_config()
    conn = init_db(config["db_path"])

    judge_client, judge_model = None, "qwen3.6-flash"
    if getattr(args, "judge", False):
        try:
            from helicon.qwen import get_client, resolve_model, set_cache_db
            set_cache_db(conn)
            judge_client = get_client(config)
            judge_model = resolve_model("fast", config)
            if judge_client is None:
                print("No Qwen key; R11 stays on the cosine gate.\n")
        except Exception as e:
            print(f"judge unavailable ({e}); R11 stays on the cosine gate.\n")

    if getattr(args, "file", False):
        # File the rulable findings so `resolve --list` can surface them without
        # a full `evolve`. The exam itself is read-only; this is the opt-in write
        # that turns a detected fork/contradiction into something you can rule.
        client = None
        try:
            from helicon.qwen import get_client, set_cache_db
            set_cache_db(conn)
            client = get_client(config)
        except Exception:
            pass
        from helicon.pairing import pair_scan
        from helicon.claims import claim_scan
        from helicon.aliases import alias_scan
        from helicon.identity import identity_scan
        from helicon.relations import relation_scan
        pair_scan(conn, client=client)
        claim_scan(conn, config)
        alias_scan(conn)
        identity_scan(conn, judge_client=judge_client, judge_model=judge_model)
        relation_scan(conn)
        n = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE human_decision IS NULL").fetchone()[0]
        print(f"filed findings — {n} open to rule.  Next:  helicon resolve --list\n")

    res = run_rot_exam(conn, judge_client=judge_client, judge_model=judge_model)
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(res, indent=2, default=str))
        return
    print(format_rot(res))

    # The exam found rot and stopped. `resolve --list` is the best surface in
    # the product and the exam never named it, so the loop's centre link lived
    # only in the docs: the classes that found NOTHING printed a next step
    # (alias add, snapshot add) and the ones that found ROT printed none. A user
    # who cannot get from "here are your problems" to "you ruled it and the law
    # recompiled" never sees the moat — which is the whole thesis.
    if not getattr(args, "file", False) and res.get("rot_found"):
        open_n = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE human_decision IS NULL"
        ).fetchone()[0]
        if open_n:
            print(f"  {open_n} finding(s) waiting on your ruling:  helicon resolve --list")
        else:
            print("  file what the exam found, so you can rule it:  helicon audit --file")


def _portrait_palette():
    import os
    import sys
    if sys.stdout.isatty() and os.environ.get("NO_COLOR") is None and os.environ.get("TERM") != "dumb":
        return {"acc": "\033[38;5;131m", "gold": "\033[38;5;179m", "dim": "\033[38;5;245m",
                "ink": "\033[38;5;250m", "good": "\033[38;5;108m", "b": "\033[1m", "r": "\033[0m"}
    return {k: "" for k in ("acc", "gold", "dim", "ink", "good", "b", "r")}


def _render_portrait(res: dict):
    import textwrap
    c = _portrait_palette()
    d = res["digest"]
    h = d["health"]
    reading = res.get("reading")

    def label(s):
        return f"{c['acc']}{s}{c['r']}"

    def wrap(s, indent="  "):
        return textwrap.fill(s, width=76, initial_indent=indent, subsequent_indent=indent)

    print()
    print(f"{c['dim']}       /\\{c['r']}")
    print(f"{c['dim']}      /  \\{c['r']}      {c['b']}MOUNT HELICON{c['r']}")
    print(f"{c['dim']}     / {c['gold']}/\\{c['dim']} \\{c['r']}     {c['dim']}the reading · who the record shows you are{c['r']}")
    print(f"{c['dim']}    /_/  \\_\\{c['r']}")
    print()

    if reading:
        if reading.get("opening"):
            print(f"  {c['gold']}{reading['opening']}{c['r']}")
            print()
        if reading.get("who"):
            print(label("  WHO THE RECORD SHOWS"))
            print(wrap(reading["who"]))
            print()
        if reading.get("builder"):
            print(label("  THE BUILDER"))
            print(wrap(reading["builder"]))
            print()

    # the grounding — the digest, so the reading is never floating
    ent = " · ".join(e["name"] for e in d["entities"][:8])
    mix = " · ".join(f"{m['kind']} {m['pct']}%" for m in d["output_mix"][:5])
    areas = " · ".join(a["name"] for a in d["areas"][:6])
    if ent:
        print(f"  {c['dim']}recurring{c['r']}    {ent}")
    if mix:
        print(f"  {c['dim']}you make{c['r']}     {mix}")
    if areas:
        print(f"  {c['dim']}you invest{c['r']}   {areas}")
    print()

    # the process at work — grounded improvement arc, colored deltas
    proc = d.get("process")
    if proc and proc.get("reviewed_now"):
        print(label("  THE PROCESS AT WORK"))
        if reading and reading.get("process"):
            print(wrap(reading["process"]))
        gained = proc["reviewed_now"] - proc.get("reviewed_start", 0)
        print(f"  {c['dim']}memories judged{c['r']}   "
              f"{c['dim']}{proc.get('reviewed_start', 0)}{c['r']} "
              f"{c['dim']}→{c['r']} {c['good']}{c['b']}{proc['reviewed_now']}{c['r']}"
              f"  {c['good']}(+{gained}){c['r']}  "
              f"{c['dim']}human rulings taught auto-triage, decay retired the stale{c['r']}")
        print()

    print(label("  STANDING"))
    if reading and reading.get("standing"):
        print(wrap(reading["standing"]))

    def num(v, tone):
        return f"{c[tone]}{c['b']}{v}{c['r']}{c['dim']}"
    rot_tone = "acc" if h["rot_classes"] > 0 else "good"
    rev_tone = "good" if h["reviewed_pct"] >= 50 else "gold"
    reviewed_str = f"{h['reviewed_pct']}%"
    gold_word = "golden rule" + ("s" if h["gold_rules"] != 1 else "")
    print(f"  {c['dim']}{num(h['live'], 'gold')} live memories · "
          f"{num(reviewed_str, rev_tone)} reviewed · "
          f"{num(h['rot_classes'], rot_tone)} of {h['rot_total']} rot classes firing · "
          f"{num(h['volatile'], 'acc')} carry volatile facts · "
          f"{num(h['gold_rules'], 'gold')} {gold_word}{c['r']}")
    print()

    if reading and reading.get("moves"):
        print(label("  WHAT THE RECORD ARGUES FOR"))
        for i, m in enumerate(reading["moves"], 1):
            print(f"  {c['gold']}{i}.{c['r']} {c['b']}{m.get('title','')}{c['r']}")
            if m.get("why"):
                print(wrap(m["why"], indent="     "))
        print()

    if not reading:
        print(f"  {c['dim']}(no Qwen key — the reading needs one. The record above is real.){c['r']}")
        print(f"  {c['dim']}run helicon volatility and helicon audit for the full audit.{c['r']}")
        print()


def cmd_consistency(args):
    """The consistency gate: does your memory INDEX still match its directory?
    Deterministic, no key. Catches the drift that hides in plain sight, a
    pointer to a deleted file or a file the index never lists."""
    from helicon.config import load_config
    from helicon.consistency import audit_index, default_index

    config = load_config()
    index = getattr(args, "index", None) or default_index(config)
    if not index:
        print("No index given and no Claude Code auto-memory MEMORY.md found.")
        print("Usage: helicon consistency <path/to/INDEX.md>")
        return
    res = audit_index(index, getattr(args, "dir", None))
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(res, indent=2, default=str))
        return
    if not res.get("ok"):
        print(res.get("reason", "could not read the index"))
        return

    print(f"The consistency gate — does your index match its directory?\n")
    print(f"  index   {res['index']}")
    print(f"  dir     {res['dir']}")
    ext = res.get("external", [])
    ext_note = f" · {len(ext)} external (cross-vault, not checked)" if ext else ""
    print(f"  {res['pointers']} pointers · {res['on_disk']} files on disk{ext_note}\n")
    if res["consistent"]:
        print("  index and directory agree. Nothing points at a ghost, nothing hides.")
        return
    if res["dangling"]:
        print(f"  DANGLING ({len(res['dangling'])}) — the index points to files that are gone:")
        for f in res["dangling"][:20]:
            print(f"    ✗ {f}")
    if res["dangling_wikilinks"]:
        print(f"  DANGLING WIKILINKS ({len(res['dangling_wikilinks'])}):")
        for w in res["dangling_wikilinks"][:20]:
            print(f"    ✗ [[{w}]]")
    if res["unlisted"]:
        print(f"  UNLISTED ({len(res['unlisted'])}) — files on disk the index never names:")
        for f in res["unlisted"][:20]:
            print(f"    ? {f}")
    print(f"\n  Loaded every session, checked by nobody. This is the drift that survives.")


def cmd_heal(args):
    """The self-healing audit loop: score the four truth gates on a store, show
    every drift with its evidence and a proposed repair, apply the accepted
    ones, and re-score so the gates move. The thing no retriever can do."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.heal import heal, DEMO_DB

    demo = getattr(args, "demo", False)
    apply = getattr(args, "apply", False)
    # Safety guard: --apply on the REAL store marks cubes killed (retires live
    # memories). Refuse unless explicitly confirmed with --yes-really. The demo
    # store is always safe (re-seedable), so it never needs confirmation.
    if apply and not demo and not getattr(args, "yes_really", False):
        print("\n  ⚠  refusing to --apply on your REAL store "
              "(would kill / retire live memories).")
        print("     • see it safely first:    helicon repair --demo --apply")
        print("     • really apply for real:  helicon repair --apply --yes-really\n")
        return
    if demo:
        _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _repo_root not in sys.path:
            sys.path.insert(0, _repo_root)
        import scripts.demo_seed as seed_mod
        if getattr(args, "reset", False) or not os.path.exists(DEMO_DB):
            seed_mod.seed()
        conn = init_db(DEMO_DB)
        label = "demo"
        config = None
    else:
        config = load_config()
        conn = init_db(config["db_path"])
        label = "oscar:vault+memory"

    env = heal(conn, config=config, apply=apply, store_label=label)

    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(env, indent=2, default=str))
        return
    _render_heal(env, applied=apply)


def _bar(score, width=18):
    if score is None:
        return "—" * 6
    filled = int(round(width * score / 100))
    return "█" * filled + "·" * (width - filled)


def _render_heal(env, applied: bool):
    b = env["gate_scores"]["before"]
    a = env["gate_scores"].get("after")
    order = ["consistency", "freshness", "volatility", "retrieval"]
    print(f"\n  THE SELF-HEALING AUDIT LOOP   ·   store: {env['store']}\n")
    print(f"  {'gate':<13} {'before':>7}      {'after':>7}   move")
    print(f"  {'─'*13} {'─'*7}      {'─'*7}   {'─'*5}")
    for g in order:
        bv = b[g]
        av = a[g] if a else None
        bs = f"{bv:>5}%" if bv is not None else "  n/a"
        as_ = (f"{av:>5}%" if av is not None else "  n/a") if a else ""
        if a and av is not None and bv is not None:
            d = round(av - bv, 1)
            move = f"+{d}" if d > 0 else (f"{d}" if d < 0 else "·")
        else:
            move = ""
        arrow = "→" if a else " "
        print(f"  {g:<13} {bs:>7} {_bar(bv)} {arrow} {as_:>7} {_bar(av) if a else ''}  {move}")
    print()
    print(f"  {env['summary']['findings']} evidenced findings"
          + (f"  ·  {env['summary']['applied']} repairs applied" if applied else "  ·  proposed (dry-run)"))
    print()
    for f in env["findings"]:
        tag = {"consistency": "CONTRADICTION", "freshness": "STALE",
               "volatility": "VOLATILE"}.get(f["gate"], f["gate"].upper())
        print(f"  [{f['id']}] {tag:<13} {f['subject']}")
        print(f"        drift:   {f['drift']}")
        for e in f["evidence"]:
            when = (e.get("created_at") or "")[:10]
            print(f"        source:  {e['source']}:{e['ref']}  ({when})  \"{e['text']}\"")
        print(f"        repair:  {f['repair']['kind'].upper()} — {f['repair']['reason']}")
        for line in f["repair"]["diff"].splitlines():
            print(f"                 {line}")
        print(f"        status:  {f['status'].upper()}")
        print()
    if applied and env.get("gate_delta"):
        gains = " · ".join(f"{g} +{d}" for g, d in env["gate_delta"].items() if d > 0)
        print(f"  Loop closed. Gates moved: {gains}.")
    elif not applied:
        print("  Re-run with --apply to accept the repairs and watch the gates move.")
    print()


def cmd_read(args):
    """The reading: open the record and it tells you who you are. Composes a
    grounded portrait from your memory (who recurs, what you make, the record's
    health) and lets Qwen narrate it in the Court's voice."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.portrait import build_portrait
    from helicon.qwen import get_client

    config = load_config()
    conn = init_db(config["db_path"])
    res = build_portrait(conn, config, client=get_client(config))
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(res, indent=2, default=str))
        return
    _render_portrait(res)


def cmd_volatility(args):
    """The volatility gate: truth = fact + timestamp + decay. Flags stored
    memories that are fast facts (a %, a live count, a price, a ranking,
    "currently") and belong in the live layer, not memory. Deterministic
    suspects, then Qwen sentences each with a tier + when it goes wrong."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.qwen import get_client
    from helicon.volatility import scan_volatility

    config = load_config()
    conn = init_db(config["db_path"])
    res = scan_volatility(conn, config, client=get_client(config))
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(res, indent=2, default=str))
        return

    if res["suspects"] == 0:
        print("No fast-fact signals in your memory. Nothing volatile stored as durable.")
        return
    if res.get("keyless"):
        print(f"Volatility gate (no Qwen key — suspects only, unsentenced):\n")
        for s in res.get("unsentenced", [])[:20]:
            print(f"  • {s['title'][:70]}")
            print(f"      signal: {', '.join(s['signals'])}  ·  {s['source']}")
        print(f"\n{res['suspects']} suspect(s). Add a Qwen key to sentence them (tier + stale_when).")
        return

    print(f"Volatility gate — {res['suspects']} suspects, {res['judged']} sentenced by Qwen\n")
    fast = res["fast"]
    print(f"FAST FACTS IN MEMORY ({len(fast)}) — these belong in the live layer, not memory:")
    for f in fast[:20]:
        print(f"  ✗ {f['title'][:70]}")
        print(f"      {f['reason']}  ·  goes wrong when: {f['stale_when'] or 'soon'}")
        print(f"      {f['source']} · {f['source_ref']}")
    slow = res["slow_undated"]
    if slow:
        print(f"\nSLOW FACTS MISSING DECAY ({len(slow)}) — keep, but stamp as_of + stale_when:")
        for f in slow[:10]:
            print(f"  ~ {f['title'][:70]}  ·  stale when: {f['stale_when'] or 'a named event'}")
    print(f"\n{res['static']} static fact(s) — durable, correctly in memory.")


def cmd_ci(args):
    """CI for agent memory: scan THIS repo's committed rules files
    (CLAUDE.md / AGENTS.md / .cursorrules / .clinerules / copilot-instructions)
    and run the deterministic rot exam. Emits GitHub Actions annotations + a job
    summary and exits non-zero on rot. Slim: no embeddings, no Qwen, no torch."""
    import os
    import sys
    import tempfile
    from helicon.db import init_db
    from helicon.scanner import run_scan
    from helicon.rot import run_rot_exam, format_rot

    repo = os.path.abspath(getattr(args, "path", None) or os.getcwd())
    fail_on = getattr(args, "fail_on", "rot")
    db = os.path.join(tempfile.gettempdir(), "helicon-ci.db")
    try:
        if os.path.exists(db):
            os.remove(db)
    except OSError:
        pass

    config = {
        "db_path": db,
        "connectors": {"agent-rules": {"enabled": True, "repos": [repo], "max_repos": 1}},
    }
    conn = init_db(db)
    print(f"Mount Helicon CI — scanning agent-memory files in {repo}\n")
    run_scan(config)
    res = run_rot_exam(conn, repo_root=repo)

    rot = [c for c in res["checks"] if c["verdict"] == "ROT FOUND"]
    level = "error" if fail_on == "rot" else "warning"

    if os.environ.get("GITHUB_ACTIONS") == "true":
        for c in rot:
            msg = (c["receipt"] or "").replace("\n", " ").replace("\r", " ")
            print(f"::{level} title=Memory rot {c['id']} {c['name']}::{msg}")
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as fh:
                fh.write("## Mount Helicon — agent memory rot exam\n\n")
                fh.write(f"**{res['rot_found']}/{res['classes']} rot classes firing** "
                         f"in `{os.path.basename(repo)}`\n\n")
                fh.write("| Class | Verdict | Detail |\n|---|---|---|\n")
                for c in res["checks"]:
                    d = (c["receipt"] or "")[:140].replace("|", "\\|").replace("\n", " ")
                    fh.write(f"| {c['id']} {c['name']} | {c['verdict']} | {d} |\n")

    print(format_rot(res))
    if fail_on == "rot" and rot:
        print(f"\n✗ CI FAIL: {len(rot)} rot class(es) firing. "
              f"Rule on them, or set --fail-on none for report-only.")
        sys.exit(1)
    print(f"\n✓ CI PASS ({res['rot_found']}/{res['classes']} classes firing; fail-on={fail_on})")


def cmd_gold(args):
    """GOLDEN RULES: compile the stack's law from human judgment — rulings,
    precedents, approved rules, renames, canon, standing feedback. Every
    rule carries its provenance. --inject writes ~/.claude/GOLDEN_RULES.md
    (with .bak) so every session can obey it."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.gold import write_gold, inject, compile_gold

    config = load_config()
    conn = init_db(config["db_path"])
    if getattr(args, "show", False):
        print(compile_gold(conn, config))
        return
    res = write_gold(conn, config)
    print(f"GOLDEN_RULES.md compiled: {res['total']} rules "
          f"({res['canon']} canon, {res['renames']} renames, "
          f"{res['resolutions']} rulings, {res['triage']} triage, "
          f"{res['precedents']} precedents, {res['feedback']} feedback) "
          f"-> {res['path']}")
    for w in res.get("warnings", []):
        # a memory that could not state its own rule used to compile a blank
        # line into the law in total silence. Never again silently.
        print(f"  [WARN] {w}")
    inj = inject(conn, config, apply=getattr(args, "inject", False),
                 md=res.get("md"))
    if inj["applied"]:
        print(f"injected -> {inj['target']}"
              + (" (.bak kept)" if inj.get("bak") else "")
              + f". {inj['hint']}")
    else:
        print(f"not injected (dry-run). {inj['hint']}")


def cmd_evolve(args):
    """The night command: scan everything, run every selector and the rot
    exam, recompile the golden rules, and report the DELTA — what your
    stack learned while you slept."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.gold import write_gold, gold_history
    from helicon.rot import run_rot_exam
    from helicon.pairing import pair_scan
    from helicon.claims import claim_scan
    from helicon.aliases import alias_scan

    config = load_config()
    conn = init_db(config["db_path"])

    before_open = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE human_decision IS NULL").fetchone()[0]
    before_cubes = conn.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]

    added = 0
    if not getattr(args, "no_scan", False) and config.get("connectors"):
        from helicon.scanner import run_scan
        stats = run_scan(config)
        added = stats.get("added", 0)

    client = None
    try:
        from helicon.qwen import get_client, set_cache_db
        set_cache_db(conn)
        client = get_client(config)
    except Exception:
        pass
    pair_scan(conn, client=client)
    claim_scan(conn, config)
    alias_scan(conn)
    from helicon.identity import identity_scan
    identity_scan(conn)          # R11: file confirmed identity forks (semantic-gated)
    from helicon.relations import relation_scan, store_asserts_edges
    relation_scan(conn)          # R12: file phantom associations
    store_asserts_edges(conn)    # R12: persist relation provenance as 'asserts' edges
    from helicon.stackwatch import stack_scan
    stack = stack_scan(conn, config)
    exam = run_rot_exam(conn)

    hist = gold_history(config, limit=2)
    prev_rules = hist[-1]["total"] if hist else 0
    gold = write_gold(conn, config)

    after_open = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE human_decision IS NULL").fetchone()[0]

    print("\nSTACK EVOLUTION — while you were away")
    after_cubes = conn.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]
    delta_open = after_open - before_open
    print(f"  memories ingested   +{added}  (store: {before_cubes} -> {after_cubes})")
    print(f"  findings delta      {'+' if delta_open >= 0 else ''}{delta_open}  "
          f"(open now: {after_open}; negative = rulings landed mid-run)")
    print(f"  rot classes firing  {exam['rot_found']}/10")
    print(f"  stack surfaces      +{stack['routine']} routine, "
          f"+{stack['output']} dead-path, +{stack['context']} context, "
          f"+{stack.get('nightly', 0)} nightly finding(s)")
    print(f"  golden rules        {prev_rules} -> {gold['total']}"
          + (f"  (+{gold['total'] - prev_rules} learned)"
             if gold["total"] > prev_rules else "  (holding)"))
    print(f"\n  rule on what needs you:  helicon resolve --list")
    print(f"  the law, current:        data/GOLDEN_RULES.md")
    # obey path: rulings only govern the agent once they reach ~/.claude. Detect
    # automatically; apply on --obey (writing the operator's home dir stays opt-in).
    new_rulings = gold["total"] > prev_rules
    if getattr(args, "obey", False):
        from helicon.gold import inject
        res = inject(conn, config, apply=True)
        print(f"  obey:                    wrote {res['target']} "
              f"({res['chars']} chars, .bak kept) — the agent obeys it next session")
    elif new_rulings:
        print(f"  make the agent obey:     helicon policy --inject  "
              f"(pushes {gold['total'] - prev_rules} new ruling(s) to ~/.claude)")


def cmd_resolve(args):
    """Close a cross-source contradiction with the truth. Files the human
    decision, writes a correction cube (approved, full provenance) so
    retrieval serves the answer instead of the argument, and arms the
    never-twice guard: the ruled-out date resurfacing in NEW memory
    re-alarms instead of being grandfathered in."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.pairing import resolve_pair

    config = load_config()
    conn = init_db(config["db_path"])

    if args.list or args.id is None:
        # One "needs ruling" list across every rulable class, so the loop is
        # discoverable: R1 cross-source contradictions, R11 identity forks,
        # R12 phantom associations. Each carries the resolve verb it expects.
        contradictions = conn.execute(
            "SELECT id, finding, severity FROM audit_log "
            "WHERE audit_type = 'factual' AND details LIKE '%pair_key%' "
            "AND human_decision IS NULL ORDER BY id").fetchall()
        forks = conn.execute(
            "SELECT id, finding, severity FROM audit_log "
            "WHERE audit_type = 'identity' AND human_decision IS NULL ORDER BY id").fetchall()
        phantoms = conn.execute(
            "SELECT id, finding, severity FROM audit_log "
            "WHERE audit_type = 'provenance' AND human_decision IS NULL ORDER BY id").fetchall()
        if not (contradictions or forks or phantoms):
            print("Nothing open to rule. (Findings are filed by `helicon evolve`; "
                  "`helicon audit` detects read-only.)")
            return
        if contradictions:
            print("Cross-source contradictions (R1):\n")
            for r in contradictions:
                print(f"  #{r['id']}  [{r['severity']}]  {r['finding']}")
            print("  rule:  helicon resolve <id> --truth \"<the true value>\"\n")
        if forks:
            print("Identity forks (R11) — same name, incompatible definitions:\n")
            for r in forks:
                print(f"  #{r['id']}  [{r['severity']}]  {r['finding']}")
            print("  rule:  helicon resolve <id> --truth \"<the canonical definition>\"\n")
        if phantoms:
            print("Phantom associations (R12) — a relation no source grounds:\n")
            for r in phantoms:
                print(f"  #{r['id']}  [{r['severity']}]  {r['finding']}")
            print("  rule:  helicon resolve <id> --truth phantom   (or: --truth real)\n")
        print("Inspect one:  helicon resolve <id>   (shows the evidence, decides nothing)")
        return

    if args.dismiss is not None:
        from helicon.pairing import dismiss_finding
        res = dismiss_finding(conn, args.id, args.dismiss or "dismissed by human")
        print(f"dismissed #{args.id} (reason recorded)" if res["ok"]
              else f"error: {res['error']}")
        return

    if not args.truth:
        # The verify surface: full evidence card, decides nothing.
        import json as _json
        from helicon.pairing import format_pair_evidence
        row = conn.execute("SELECT * FROM audit_log WHERE id = ?",
                           (args.id,)).fetchone()
        if row is None:
            print(f"no audit finding #{args.id}")
            return
        try:
            d = _json.loads(row["details"])
        except (ValueError, TypeError):
            d = {}
        print(f"#{row['id']}  [{row['severity']}]  filed {row['audited_at'][:16]}"
              + (f"  decided: {row['human_decision']}" if row["human_decision"] else ""))
        print(f"{row['finding']}\n")
        print(format_pair_evidence(d) if d.get("pair_key")
              else (row["finding"]))
        if d.get("cube_count"):
            print(f"\n   {d['cube_count']} memories involved across "
                  f"{len(d.get('scopes', []))} source file(s)")
        if not row["human_decision"]:
            atype = row["audit_type"]
            if atype == "identity":
                hint = "--truth \"<the canonical definition>\""
            elif atype == "provenance":
                hint = "--truth phantom   (or: --truth real)"
            else:
                vals = d.get("all_dates") or d.get("dates") or []
                hint = f"--truth <{'|'.join(str(v) for v in vals) or 'value'}>"
            print(f"\nDecide:  helicon resolve {row['id']} {hint}"
                  f"\n   or:   helicon resolve {row['id']} --dismiss \"why\"")
        return
    # identity forks (R11) resolve with a canonical definition, not a scalar value
    _row = conn.execute("SELECT audit_type FROM audit_log WHERE id = ?", (args.id,)).fetchone()
    if _row and _row["audit_type"] == "identity":
        from helicon.identity import resolve_identity
        ri = resolve_identity(conn, args.id, args.truth or "")
        if not ri["ok"]:
            print(f"error: {ri['error']}")
            return
        print(f"resolved #{ri['audit_id']}: {ri['name'].title()} is canonically \"{ri['canonical']}\"")
        print(f"  correction memory {ri['correction_cube']} (approved, provenance); the fork is settled")
        return
    if _row and _row["audit_type"] == "provenance":
        from helicon.relations import resolve_relation
        rr = resolve_relation(conn, args.id, args.truth or "phantom")
        if not rr["ok"]:
            print(f"error: {rr['error']}")
            return
        print(f"resolved #{rr['audit_id']}: {rr['subj']} -/-> {rr['obj']} ruled {rr['verdict']}")
        if rr["verdict"] == "phantom" and rr["correction_cube"]:
            print(f"  phantom recorded (memory {rr['correction_cube']}); the scan will not re-file it")
        return
    if _row and _row["audit_type"] == "review":
        # the OUTPUT -> memory edge: a false claim ruling writes the reality
        # verdict back into the store as a correction (dismiss = it was true).
        from helicon.review_terminals import resolve_review
        rv = resolve_review(conn, args.id, args.truth or "",
                            retire_cube_id=getattr(args, "retire", None))
        conn.commit()
        if not rv["ok"]:
            print(f"error: {rv['error']}")
            return
        print(f"resolved #{rv['audit_id']}: output claim from '{rv['terminal']}' corrected")
        print(f"  correction memory {rv['correction_cube']} (approved) now serves the reality-checked truth")
        if rv.get("retired_cube"):
            print(f"  retired the cause: memory {rv['retired_cube']} superseded (the one that drove the bad output)")
        return
    res = resolve_pair(conn, args.id, args.truth, note=args.note or "")
    if not res["ok"]:
        print(f"error: {res['error']}")
        return
    print(f"resolved #{res['audit_id']}: {res['person'].title()} {res['topic']} = {res['truth']}")
    print(f"  wrong value(s) {', '.join(res['wrong_dates'])} ruled out; "
          f"correction memory {res['correction_cube']} (approved, provenance recorded)")
    print("  never-twice armed: new memory asserting a ruled-out value will re-alarm")


def cmd_watch(args):
    """Drift notifies YOU: run the full loop headlessly, speak only when
    something is NEW (fresh findings or a rot class flipping). --install
    writes the crontab line so it runs every N hours without you."""
    import os as _os
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon import watch as W

    repo_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(W.__file__)))

    if args.install:
        line = W.install_cron(repo_root, every_hours=args.every)
        print(f"installed crontab line (every {args.every}h):\n  {line}")
        return
    if args.uninstall:
        print("removed" if W.uninstall_cron() else "no watch crontab line found")
        return

    config = load_config()
    conn = init_db(config["db_path"])
    res = W.watch_once(conn, config, scan=not args.no_scan,
                       notify=not args.quiet, repo_root=repo_root)
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(res, indent=2, default=str))
        return
    if res["spoke"]:
        print(f"DRIFT: {res['new_findings']} new finding(s), "
              f"{len(res['flips'])} rot class flip(s) -> {res['report_path']}")
        for f in res["flips"]:
            print(f"  {f['id']} {f['name']}: {f['from']} -> {f['to']}")
    else:
        print(f"quiet: no new findings, no flips "
              f"({res['rot_found']}/10 classes still showing known rot)")


def cmd_alias(args):
    """Supersession aliases (rot class R4): declare a rename, then every
    dead-name reference in live memory triages by written rule — pre-rename
    history is kept, post-rename current-claims are the rot, and serving the
    dead name for a current-name query is the proof."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.aliases import add_alias, alias_rot, alias_scan, list_aliases

    config = load_config()
    conn = init_db(config["db_path"])

    if args.add:
        old, new = args.add
        if not args.renamed_at:
            print("--renamed-at YYYY-MM-DD[THH:MM:SS] is required: the triage "
                  "rule is 'written before or after the rename', so the rename "
                  "needs a timestamp.")
            return
        if add_alias(conn, old, new, args.renamed_at, note=args.note or ""):
            print(f"alias recorded: {old} -> {new} (renamed {args.renamed_at})")
        else:
            print(f"alias {old} -> {new} already declared")
        return

    aliases = list_aliases(conn)
    if not aliases:
        print("No renames declared. Declare one:\n"
              "  helicon alias --add <old> <new> --renamed-at <when>")
        return

    if args.scan:
        res = alias_scan(conn)
        for f in res["filed"]:
            print(f"filed: {f['finding']}")
        for k in res["already_filed"]:
            print(f"already filed: {k}")
        for k in res["clean"]:
            print(f"clean: {k}")
        return

    for t in alias_rot(conn):
        print(f"\n{t['old_name']} -> {t['new_name']}   (renamed {t['renamed_at']})")
        print(f"  {t['live_refs']} live memories still say '{t['old_name']}':")
        print(f"    history        {t['history']:>5}  (pre-rename; true when written, kept)")
        print(f"    rename-aware   {t['rename_aware']:>5}  (post-rename, name both names)")
        print(f"    current-claims {t['current_claims']:>5}  (post-rename, dead name only — the rot)")
        for s in t["current_claim_samples"]:
            print(f"      - {s['created_at'][:10]}  {s['title']}")
        if t["leaked"]:
            print(f"  SERVING: {len(t['leaked'])}/{t['retrieved_for_new_name']} top-K hits "
                  f"for '{t['new_name']}' speak only the dead name:")
            for h in t["leaked"]:
                print(f"      - {h['title']}")
        else:
            print(f"  serving: 0/{t['retrieved_for_new_name']} top-K hits for "
                  f"'{t['new_name']}' leak the dead name")


def cmd_rule(args):
    """Prompted rules: state a triage rule in natural language, see exactly
    what it would do (coverage, samples, precision vs your own history,
    conflicts), then approve. Applied rules are never human evidence."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon import rules as R

    config = load_config()
    conn = init_db(config["db_path"])

    if args.list:
        rs = R.list_rules(conn)
        if not rs:
            print("No rules yet. Author one: helicon rule \"kill code edits older than 30 days\"")
            return
        for r in rs:
            print(f"  #{r['id']} [{r['status']:<8}] {r['action']:<7} \"{r['nl_text'][:70]}\""
                  f"  {json.dumps(r['predicate']['match'])}")
        return

    if args.approve:
        ok = R.approve_rule(conn, args.approve)
        print(f"Rule #{args.approve} approved." if ok
              else f"Rule #{args.approve} not found or not in 'proposed'.")
        return

    if args.retire:
        ok = R.retire_rule(conn, args.retire)
        print(f"Rule #{args.retire} retired." if ok else f"Rule #{args.retire} not found.")
        return

    if args.run:
        res = R.apply_rules(conn, dry_run=not args.apply)
        mode = "APPLY" if args.apply else "dry-run"
        print(f"Rules run ({mode}): {res['total']} memories matched\n")
        for r in res["rules"]:
            verb = "acted on" if args.apply else "would act on"
            print(f"  #{r['rule_id']} {r['action']:<7} {verb} {r['matched']:>4}  \"{r['nl_text'][:60]}\"")
        if not args.apply and res["total"]:
            print("\nDry-run: nothing written. Run with --run --apply to execute.")
        return

    if not args.text:
        print('usage: helicon rule "<natural language rule>" | --list | --approve N | --run [--apply]')
        return

    from helicon.qwen import get_client, resolve_model, set_cache_db
    set_cache_db(conn)
    client = get_client(config)
    if client is None:
        print("Rule compilation needs a Qwen key (BYOK — set QWEN_API_KEY).")
        return
    model = resolve_model("default", config)

    pred = R.compile_rule(client, args.text, model=model)
    if "error" in pred:
        print(f"Could not compile: {pred['error']}")
        return

    print(f"Compiled: {pred['action']} WHERE {json.dumps(pred['match'])}\n")
    prev = R.preview(conn, pred)
    print(f"  would affect {prev['pending_matches']} pending memories")
    if prev["precision_vs_history"] is not None:
        print(f"  precision vs your history: {prev['precision_vs_history']:.0%} "
              f"({prev['history_agree']}/{prev['history_n']} past decisions agree)")
    else:
        print("  no reviewed history matches this predicate — precision unmeasured")
    for s in prev["samples"]:
        print(f"    ~ {s['title'][:64]}  (conf {s['confidence']:.2f})")
    for d in prev["disagreeing_samples"]:
        print(f"    ! you decided '{d['review_status']}' on: {d['title'][:56]}")
    for c in prev["conflicts"]:
        print(f"    ! conflicts with rule #{c['rule_id']} \"{c['nl_text'][:44]}\" on {c['overlap']} memories")

    rule_id = R.save_rule(conn, args.text, pred, model, prev)
    print(f"\nSaved as rule #{rule_id} (proposed). Approve: helicon rule --approve {rule_id}")


def cmd_doctor(_args):
    """Health check: PATH, config, Qwen key, DB, last scan. The front door —
    if any line here is broken, nothing else enters a daily loop."""
    import shutil
    from helicon.config import CONFIG_FILE, load_config

    checks = []  # (level, message) where level is OK / WARN / FAIL

    path_hit = shutil.which("helicon")
    if path_hit:
        checks.append(("OK", f"helicon on PATH ({path_hit})"))
    else:
        checks.append(("FAIL", "helicon not on PATH — run: pip install -e ."))

    config = load_config()
    if not config:
        checks.append(("FAIL", f"no config.json at {CONFIG_FILE} — run: helicon init"))
    else:
        n = len(config.get("connectors", {}))
        level = "OK" if n else "WARN"
        checks.append((level, f"config.json loaded ({n} connector(s))"))

    if config.get("qwen_api_key"):
        src = "QWEN_API_KEY env" if os.environ.get("QWEN_API_KEY") else "config.json"
        checks.append(("OK", f"Qwen key configured ({src})"))
    else:
        checks.append(("WARN", "no Qwen key — deterministic tests still run; "
                               "Contradiction/Grounding won't (BYOK: set QWEN_API_KEY)"))

    db_path = config.get("db_path", "data/helicon.db")
    if not os.path.exists(db_path):
        checks.append(("FAIL", f"no DB at {db_path} — run: helicon scan"))
    else:
        from helicon.db import init_db, last_scan_info
        conn = init_db(db_path)
        total = conn.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]
        retired = conn.execute(
            "SELECT COUNT(*) FROM helicon_cubes WHERE review_status IN ('killed', 'superseded')"
        ).fetchone()[0]
        checks.append(("OK", f"DB {db_path} — {total} memories ({total - retired} live, {retired} retired)"))

        # Liveness, asserted rather than inferred. This line prints healthy or
        # not on purpose: the Jul 15 skip hid because the only signal was the
        # ABSENCE of an alarm, and a silent check and a silent failure look the
        # same. An age you can read cannot go quiet.
        from helicon.stackwatch import nightly_status
        night = nightly_status(config)
        checks.append(("OK" if night["ok"] else "FAIL",
                       f"nightly {night['reason']}"))

        # The hands. Helicon's own MCP server was registered and silently dead
        # for every session (invoked via `bash -lc`; the login profile blocks on
        # stdin, which is the channel MCP speaks over). Nothing surfaced it,
        # because nothing checked the surface that connects the tool to the
        # agent. A process that starts is not a server that speaks, so this
        # speaks the real protocol at it.
        from helicon.stackwatch import mcp_status
        for st in mcp_status():
            checks.append(("OK" if st["ok"] else "FAIL",
                           f"mcp '{st['name']}' — {st['reason']}"))

        # Retrieval calls a remote reranker and silently keeps the hybrid order
        # when it fails, so a dead reranker and a healthy one look identical.
        # Retrieval is what R8 exists to test, so a silently-degraded reranker is
        # a silently-degraded exam. Printed healthy or not, same as the nightly.
        from helicon.embeddings import rerank_health
        rr = rerank_health()
        checks.append(("OK" if rr["ok"] else ("WARN" if rr["ok"] is None else "FAIL"),
                       f"rerank — {rr['reason']}"))

        # `serve` prefers static/ over web/dist (app.py). static/ is gitignored
        # and populated by a manual copy, so a rebuild that nobody copies leaves
        # the dashboard serving a stale bundle with no signal at all: Oscar's
        # phone showed a UI from the previous night while every fix landed in
        # web/dist, and no amount of rebuilding could reach him. Same seam as the
        # rest of today. Assert it instead of remembering it.
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _static = os.path.join(_root, "static", "index.html")
        _dist = os.path.join(_root, "web", "dist", "index.html")
        if os.path.isfile(_static) and os.path.isfile(_dist):
            if open(_static, "rb").read() != open(_dist, "rb").read():
                checks.append(("FAIL", "dashboard: static/ is serving a "
                                       "DIFFERENT build than web/dist — serve "
                                       "prefers static/, so the browser gets the "
                                       "stale one. Fix: cp -r web/dist/. static/"))
            else:
                checks.append(("OK", "dashboard: static/ matches web/dist"))

        scan = last_scan_info(conn)
        stability = config.get("forgetting", {}).get("stability", {})
        half_life_days = min(stability.values()) if stability else 7.0
        if scan is None:
            checks.append(("WARN", "no completed scan logged — run: helicon scan"))
        elif scan["hours_ago"] > half_life_days * 24:
            checks.append(("WARN", f"last scan {scan['hours_ago'] / 24:.1f}d ago, past the "
                                   f"freshness half-life ({half_life_days:.0f}d) — run: helicon scan"))
        else:
            age = scan["hours_ago"]
            age_str = f"{age:.1f}h" if age < 48 else f"{age / 24:.1f}d"
            checks.append(("OK", f"last scan {age_str} ago "
                                 f"({len(scan['connectors'])} connectors, +{scan['cubes_added']} memories)"))
        conn.close()

    print("Mount Helicon doctor\n")
    for level, msg in checks:
        print(f"  [{level:<4}] {msg}")
    fails = sum(1 for level, _ in checks if level == "FAIL")
    warns = sum(1 for level, _ in checks if level == "WARN")
    if fails:
        print(f"\n{fails} check(s) failed.")
        sys.exit(1)
    print(f"\nAll checks passed." if not warns else f"\n{warns} warning(s).")


def cmd_mcp(_args):
    """Run the MCP server on stdio (for agent clients). Kept behind a
    subcommand so `python -m helicon` / bare `helicon` stay a CLI, never a
    silent server."""
    from helicon.mcp_server import main as mcp_main
    mcp_main()


def cmd_report(args):
    """MemoryAgent compliance report: existing checks grouped under the track's
    four sub-goals. Numbers live from the DB, thresholds printed with them."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.report import format_report, memoryagent_report

    config = load_config()
    conn = init_db(config["db_path"])
    client = None
    model = "qwen3.6-plus"
    if getattr(args, "llm", False):
        from helicon.qwen import get_client, resolve_model, set_cache_db
        set_cache_db(conn)
        client = get_client(config)
        model = resolve_model("default", config)
        if client is None:
            print("No Qwen key; running deterministic-only.\n")

    rep = memoryagent_report(conn, client=client, model=model)
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(rep, indent=2, default=str))
        return
    print(format_report(rep))


def cmd_score(args):
    """Show current Helicon Score."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.score import compute_score
    from helicon.forgetting import get_decay_stats

    config = load_config()
    conn = init_db(config["db_path"])
    score = compute_score(conn)
    decay = get_decay_stats(conn)

    print(f"\nHelicon Score: {score['score']}%")
    print(f"  Total: {score['total']}  Reviewed: {score['reviewed']}  Pending: {score['pending']}")
    print(f"\nDecay by type:")
    for t, d in sorted(decay.items(), key=lambda x: x[1]["avg_confidence"]):
        bar = "=" * int(d["avg_confidence"] * 30)
        print(f"  {t:15s} {bar:30s} {d['avg_confidence']:.0%} ({d['count']})")


def cmd_stack(args):
    """Audit your AI agent stack."""
    print("Mount Helicon stack audit\n")
    detected = _detect_sources()

    if not detected:
        print("No AI tools detected.")
        return

    home = os.path.expanduser("~")

    print("Detected tools:")
    for name, info in detected.items():
        status = "active" if info.get("enabled") else "disabled"
        print(f"  [{status}] {name}")

    if "claude_code" in detected:
        claude_dir = os.path.join(home, ".claude")
        session_count = 0
        memory_count = 0
        projects_dir = os.path.join(claude_dir, "projects")
        if os.path.isdir(projects_dir):
            for root, _, files in os.walk(projects_dir):
                for f in files:
                    if f.endswith(".jsonl"):
                        session_count += 1
        mem_dir = detected["claude_code"].get("memory_dir", "")
        if mem_dir and os.path.isdir(mem_dir):
            memory_count = len([f for f in os.listdir(mem_dir) if f.endswith(".md")])

        print(f"\n  Claude Code:")
        print(f"    Sessions: {session_count}")
        print(f"    Memory files: {memory_count}")

        claude_md = os.path.join(claude_dir, "CLAUDE.md")
        if os.path.exists(claude_md):
            size = os.path.getsize(claude_md)
            print(f"    CLAUDE.md: {size} bytes")
        else:
            print(f"    CLAUDE.md: missing (recommended)")

    if "obsidian" in detected:
        vault = detected["obsidian"]["vault_path"]
        md_count = sum(1 for _, _, files in os.walk(vault) for f in files if f.endswith(".md"))
        print(f"\n  Obsidian:")
        print(f"    Vault: {os.path.basename(vault)}")
        print(f"    Files: {md_count}")

    if "git" in detected:
        repos_dir = detected["git"]["repos_dir"]
        repos = [d for d in os.listdir(repos_dir)
                if os.path.isdir(os.path.join(repos_dir, d, ".git"))]
        print(f"\n  Git:")
        print(f"    Repos: {len(repos)}")
        print(f"    Directory: {repos_dir}")

    from helicon.config import load_config
    config = load_config()
    if config.get("qwen_api_key"):
        print(f"\n  Qwen Cloud: configured")
    else:
        print(f"\n  Qwen Cloud: not configured (set QWEN_API_KEY)")

    print(f"\nStack completeness:")
    total_sources = len(detected)
    has_qwen = bool(config.get("qwen_api_key"))
    has_db = os.path.exists(config.get("db_path", "data/helicon.db"))
    completeness = (total_sources * 20 + (30 if has_qwen else 0) + (20 if has_db else 0))
    print(f"  {min(completeness, 100)}% - {total_sources} source(s), {'Qwen active' if has_qwen else 'no Qwen'}, {'DB seeded' if has_db else 'no DB'}")


def cmd_optimize(args):
    """LLM-powered optimization suggestions for your memory stack."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.score import compute_score
    from helicon.forgetting import get_decay_stats
    from helicon.triage import compute_triage_rules, init_triage_table
    from helicon.qwen import get_client, complete, set_cache_db

    config = load_config()
    conn = init_db(config["db_path"])
    set_cache_db(conn)
    init_triage_table(conn)

    score = compute_score(conn)
    decay = get_decay_stats(conn)
    rules = compute_triage_rules(conn)

    type_dist = conn.execute(
        "SELECT type, COUNT(*) as cnt, AVG(confidence) as avg_conf "
        "FROM helicon_cubes WHERE merged_into IS NULL GROUP BY type ORDER BY cnt DESC"
    ).fetchall()

    review_hist = conn.execute(
        "SELECT cube_type, decision, COUNT(*) as cnt FROM reviews GROUP BY cube_type, decision"
    ).fetchall()

    context = f"""Memory system stats:
- Helicon Score: {score['score']}% ({score['reviewed']} reviewed / {score['total']} total, {score['pending']} pending)
- Triage rules: {len(rules)} active

Type distribution:
{chr(10).join(f"  {r['type']}: {r['cnt']} items, avg confidence {r['avg_conf']:.1%}" for r in type_dist)}

Review history:
{chr(10).join(f"  {r['cube_type']} -> {r['decision']}: {r['cnt']}" for r in review_hist)}

Decay stats:
{chr(10).join(f"  {t}: avg {d['avg_confidence']:.0%}, {d['count']} items" for t, d in decay.items())}
"""

    client = get_client(config)
    if not client:
        print("Qwen API key not set. Showing rule-based analysis:\n")
        print(f"Helicon Score: {score['score']}%")
        if score['pending'] > score['reviewed']:
            print(f"  Issue: {score['pending']} pending vs {score['reviewed']} reviewed. Review backlog growing.")
        for t, d in decay.items():
            if d["avg_confidence"] < 0.1 and d["count"] > 10:
                print(f"  Issue: {t} type is nearly dead ({d['avg_confidence']:.0%} avg, {d['count']} items). Consider bulk triage.")
        if not rules:
            print(f"  Tip: Review 5+ items of the same type to unlock auto-triage rules.")
        return

    print("Running LLM optimization analysis...\n")
    result = complete(
        client,
        "You are a memory system optimization advisor. Analyze the user's memory audit stats and give specific, actionable recommendations. Focus on: what to review first, what to auto-triage, what decay settings to adjust, and what patterns suggest about the user's workflow. Be direct and specific. No fluff.",
        context,
        model="qwen-plus",
        operation="optimize",
    )
    print(result)


def cmd_embed(args):
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.embeddings import embed_all_cubes, get_embedding_stats

    config = load_config()
    conn = init_db(config["db_path"])

    print("Embedding all memories with all-MiniLM-L6-v2 (384 dims)...\n")
    result = embed_all_cubes(conn)
    print(f"  Embedded: {result['embedded']} new")
    print(f"  Skipped: {result['skipped']} (already done)")
    print(f"  Total: {result['total']}")

    stats = get_embedding_stats(conn)
    print(f"  Coverage: {stats['coverage']}%")


def cmd_compile(args):
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.compiler import write_compiled_files

    config = load_config()
    conn = init_db(config["db_path"])

    output_dir = args.output or "data/compiled"
    print(f"Compiling memory into injectable files -> {output_dir}\n")
    result = write_compiled_files(conn, output_dir)

    for filename, size in result["files"].items():
        print(f"  {filename:30s} {size:>6,} bytes")
    print(f"\n{result['files_written']} files written ({result['total_bytes']:,} bytes total)")


def cmd_playbooks(_args):
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.playbooks import build_playbooks

    config = load_config()
    conn = init_db(config["db_path"])

    print("Building task playbooks from review patterns...\n")
    results = build_playbooks(conn)

    for pb in results:
        print(f"{'=' * 60}")
        print(f"  {pb['label']}")
        print(f"  Feedback rules: {pb['feedback_count']}")
        stats = pb['review_stats']
        if stats['reviewed'] > 0:
            print(f"  Review stats: {stats['reviewed']} reviewed, {stats['ship_rate']:.0%} ship, {stats['kill_rate']:.0%} kill")
        else:
            print(f"  Review stats: no reviews yet for this category")
        print()

    print(f"\n{len(results)} playbooks built. Use `helicon_playbook` MCP tool to match tasks.")


def cmd_consolidate(args):
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.consolidation import find_clusters, run_consolidation

    config = load_config()
    conn = init_db(config["db_path"])

    print("Finding memory clusters...\n")
    clusters = find_clusters(conn)
    print(f"Found {len(clusters)} clusters:")
    for c in clusters[:15]:
        print(f"  [{c['method'][:10]:>10}] {c['topic'][:40]:<40} ({c['count']} items)")

    max_clusters = args.max if hasattr(args, "max") else 10
    qwen_client = None
    if hasattr(args, "qwen") and args.qwen:
        from helicon.qwen import get_client, set_cache_db
        set_cache_db(conn)
        qwen_client = get_client(config)

    print(f"\nConsolidating top {max_clusters} clusters...\n")
    result = run_consolidation(conn, qwen_client, max_clusters)

    for r in result["results"]:
        print(f"  {r['title'][:50]} ({r['cube_count']} items merged, conf: {r['confidence']:.0%})")

    print(f"\n{result['consolidated']} clusters consolidated from {result['clusters_found']} found.")


def cmd_eval(_args):
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.eval import run_eval, init_eval_tables
    from helicon.score import backfill_score_history

    config = load_config()
    conn = init_db(config["db_path"])
    init_eval_tables(conn)

    backfill_score_history(conn)

    print("Running evaluation benchmarks...\n")
    result = run_eval(conn)

    print(f"COMPOSITE SCORE: {result['composite_score']}%\n")

    r = result["retrieval"]
    print(f"Retrieval ({r['query_count']} queries):")
    print(f"  Precision@3: {r['precision_at_3']:.0%}")
    print(f"  Precision@5: {r['precision_at_5']:.0%}")
    print(f"  MRR:         {r['mrr']:.3f}")
    for d in r["details"][:5]:
        rank = d.get("found_at_rank")
        status = f"rank {rank}" if rank else "NOT FOUND"
        print(f"    {d['query'][:40]:40s} -> {status}")
    if len(r["details"]) > 5:
        print(f"    ... and {len(r['details']) - 5} more queries")

    f = result["forgetting"]
    print(f"\nForgetting — {f.get('metric', 'rank_auc')}: {f['forgetting_accuracy']:.3f}")
    if f.get("mean_conf_killed") is not None:
        print(f"  mean confidence: killed {f['mean_conf_killed']} vs approved "
              f"{f.get('mean_conf_approved')} "
              f"({f.get('killed_total', 0)} killed, {f.get('approved_total', 0)} approved)")

    a = result["audit"]
    if a.get("audit_recall") is not None:
        print(f"\nAudit precision: {a['audit_recall']:.0%}  ({a.get('note', '')})")
    else:
        print(f"\nAudit: {a.get('note', 'not scored')}")
    print(f"  {a.get('stale_cubes_found', 0)} flagged / {a.get('stale_cubes_actual', 0)} "
          f"actually stale, {a.get('total_findings', 0)} total findings")


def cmd_consolidation_eval(args):
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.eval import run_consolidation_eval

    config = load_config()
    conn = init_db(config["db_path"])

    qwen_client = None
    if getattr(args, "qwen", False):
        from helicon.qwen import get_client, set_cache_db
        set_cache_db(conn)
        qwen_client = get_client(config)

    sample = getattr(args, "sample", 12)
    print(f"Consolidation eval: raw memories vs consolidated synthesis (sample {sample}{', Qwen-judged' if qwen_client else ', tokens only'})...\n")
    result = run_consolidation_eval(conn, qwen_client, sample)

    if result.get("error"):
        print(f"  {result['error']}")
        return

    s = result["summary"]
    print(f"  Consolidations evaluated: {s['consolidations_evaluated']}")
    print(f"  Raw memory:          {s['raw_tokens_total']:>7,} tokens")
    print(f"  Consolidated memory: {s['consolidated_tokens_total']:>7,} tokens")
    print(f"  ── {s['avg_compression']}x more token-efficient ({s['token_reduction_pct']}% reduction) ──")
    if "avg_quality_delta" in s:
        print(f"\n  Answer quality (Qwen-judged, {s['judged']} queries):")
        print(f"    Raw memories: {s['avg_raw_quality']}/100")
        print(f"    Consolidated: {s['avg_consolidated_quality']}/100  (delta {s['avg_quality_delta']:+})")
        print(f"    Consolidated >= raw on {s['consolidated_at_least_as_good']}/{s['judged']} queries")

    print("\n  Per-cluster:")
    for d in result["details"][:10]:
        q = ""
        if "consolidated_score" in d:
            q = f"  quality {d['raw_score']:.0f}->{d['consolidated_score']:.0f}"
        print(f"    {d['topic'][:34]:34s} {d['cube_count']:>2} memories  {d['compression']:>5}x{q}")


def main():
    parser = argparse.ArgumentParser(description="Mount Helicon - memory audit for AI agent stacks")
    sub = parser.add_subparsers(dest="command")

    init_p = sub.add_parser("init", help="Auto-detect AI tools and create config")
    init_p.add_argument("--force", action="store_true", help="Overwrite existing config")

    sub.add_parser("scan", help="Scan all configured sources")

    rec_p = sub.add_parser("reconcile", help="Retire memory a re-scan no longer sees (dry-run by default)")
    rec_p.add_argument("--apply", action="store_true", help="Actually mark orphans superseded (default: dry-run)")
    rec_p.add_argument("--source", help="Only reconcile this source (e.g. agent-rules, obsidian, skills)")

    fix_p = sub.add_parser("fix-skills", help="Write Qwen descriptions into SKILL.md files missing one (dry-run by default)")
    fix_p.add_argument("--apply", action="store_true", help="Write files (creates .bak backups; default: dry-run)")
    fix_p.add_argument("--skills-dir", help="Skills directory to fix (default: ~/.claude/skills, the dir the audit scans)")

    serve_p = sub.add_parser("serve", help="Start the web UI")
    serve_p.add_argument("--port", type=int, default=8420)

    triage_p = sub.add_parser("triage", help="Run auto-triage")
    triage_p.add_argument("--dry-run", action="store_true", help="Preview without acting")

    review_p = sub.add_parser("review", help="Fast teach-once review of pending items")
    review_p.add_argument("--batch", "-n", type=int, default=5, help="How many to surface (default 5)")
    review_p.add_argument("--threshold", "-t", type=float, default=0.80,
                          help="Similarity for teach-once grouping (default 0.80)")
    review_p.add_argument("--terminals", action="store_true",
                          help="Review AGENT OUTPUT: verify each terminal's closeout/diff claims against reality")
    review_p.add_argument("--file", action="store_true",
                          help="with --terminals: persist findings so ruled claims are never re-surfaced")
    review_p.add_argument("--only", nargs="+", metavar="NAME",
                          help="with --terminals: limit to these terminals/repos")
    review_p.add_argument("--run", action="store_true",
                          help="with --terminals: actually run each repo's test suite to verify claimed counts (pytest / npm test)")
    review_p.add_argument("--preview", action="store_true",
                          help="Show the queue + suggested actions without prompting or writing")

    route_p = sub.add_parser("route", help="Routing recommendation: which model has the best verified track record per task-class (a read of the eval store)")
    route_p.add_argument("--record", action="store_true",
                         help="Build/refresh evidence from `review --terminals` before ranking")
    route_p.add_argument("--run", action="store_true",
                         help="with --record: actually run test suites to verify test-count claims")
    route_p.add_argument("--only", nargs="+", metavar="NAME",
                         help="with --record: limit to these terminals/repos")
    route_p.add_argument("--task", metavar="CLASS",
                         help="Filter to one task-class (testing / delivery / api-surface / claims)")
    route_p.add_argument("--min-n", type=int, default=5, dest="min_n",
                         help="Min pass/fail samples before a pick is made (default 5); below this: insufficient evidence")
    route_p.add_argument("--per-token", action="store_true", dest="per_token",
                         help="Cost-aware routing: rank models by verified output per million tokens (joins yield to transcript cost)")
    route_p.add_argument("--since", metavar="ISO",
                         help="with --per-token: window the token denominator to this ISO date")

    scoreruns_p = sub.add_parser("score-runs", help="Score whole runs: cost + identity from Claude Code transcripts (yield + score land in later slices)")
    scoreruns_p.add_argument("--since", metavar="ISO", help="Only sessions active at/after this ISO date")
    scoreruns_p.add_argument("--limit", type=int, default=20, help="Rows to show (default 20)")
    scoreruns_p.add_argument("--sessions", action="store_true", help="Show the raw per-session cost table instead of clustered runs")
    scoreruns_p.add_argument("--gap", type=int, default=300, help="Minutes between session starts that split one run from the next (default 300)")
    scoreruns_p.add_argument("--card", action="store_true", help="Emit ONE full run card for the latest run (cost + verified yield + score)")
    scoreruns_p.add_argument("--damage", type=float, default=0.0, help="with --card: incident penalty for this run (e.g. a machine freeze); disclosed on the card")
    scoreruns_p.add_argument("--persist", action="store_true", help="with --card: write the card to run_cards (the Latest-runs history)")

    move_p = sub.add_parser("move", help="Context-mover: read memory, verify it, render into another platform's format (dry-run by default)")
    move_p.add_argument("--from", dest="from_path", required=True, metavar="PATH", help="Source file or dir (rules/memory)")
    move_p.add_argument("--to", required=True, choices=["claude-code", "cursor", "markdown"], help="Target platform format")
    move_p.add_argument("--out", metavar="FILE", help="Target file (required with --apply)")
    move_p.add_argument("--apply", action="store_true", help="Write the target file (backs up an existing one to .bak); default is dry-run")
    move_p.add_argument("--verify-contradictions", action="store_true", dest="verify_contradictions", help="Also run the Qwen judge to hold items that contradict earlier ones")

    jb_p = sub.add_parser("judge-bench", help="Benchmark Qwen tiers as the memory-rot judge against human-labeled ground truth")
    jb_p.add_argument("--tiers", help="Comma list of tiers (default fast,default,deep)")
    jb_p.add_argument("--set", choices=["ruled", "hard", "all"], default="ruled",
                      help="Probe set: ruled (easy, from rulings) | hard (paraphrase/overlap/dead-name) | all")
    jb_p.add_argument("--save", action="store_true",
                      help="Persist this run so the dashboard's JUDGE tab can render it")

    lb_p = sub.add_parser("leaderboard", help="Population model-reliability leaderboard from git history (execution-free: survived vs reverted)")
    lb_p.add_argument("repos", nargs="*", help="Repo paths to scan (default: git repos under ~/CODE)")
    lb_p.add_argument("--max", type=int, default=500, help="Max commits per repo (default 500)")
    lb_p.add_argument("--by-task", action="store_true", dest="by_task", help="Break the ranking down by task-class")

    runs_p = sub.add_parser("runs", help="Latest runs: the scored run-card history (+ --suggest for what to run next)")
    runs_p.add_argument("--limit", type=int, default=15, help="Cards to show (default 15)")
    runs_p.add_argument("--suggest", action="store_true", help="Also show suggestions read off the history (shape, model/route, next run)")
    runs_p.add_argument("--close", action="store_true", help="Closeout hook: refresh eval evidence + cut & persist the current run's card (compounds the ledger)")
    runs_p.add_argument("--run", action="store_true", help="with --close: run test suites to verify test claims (slower, more evidence)")
    runs_p.add_argument("--damage", type=float, default=0.0, help="with --close: incident penalty for this run")

    snap_p = sub.add_parser("snapshot", help="Regression-test retrieved context (CI for memory)")
    snap_p.add_argument("action", choices=["add", "check", "list"], help="capture / check drift / list")
    snap_p.add_argument("task", nargs="?", help='task or query text (for "add")')
    snap_p.add_argument("-k", type=int, default=5, help="top-K context to snapshot (default 5)")

    taste_p = sub.add_parser("taste", help="Taste-verdict memory: remember Taste Machine rulings + the never-twice guard")
    taste_p.add_argument("--ingest", metavar="JSON", help="ingest a JSON array of Taste Machine verdicts")
    taste_p.add_argument("--hash", help="guard: has this exact output (artifact hash) been ruled?")
    taste_p.add_argument("--move", help="guard: has this move/shape usually been killed?")
    lens_p = sub.add_parser("lens", help="Memory Causal Lens: the memories behind an answer, with provenance")
    lens_p.add_argument("task", nargs="?", help="task or answer text")
    lens_p.add_argument("-k", type=int, default=8, help="how many memories to trace (default 8)")
    lens_p.add_argument("--json", action="store_true", help="machine-readable result")
    battery_p = sub.add_parser("check", aliases=["battery"], help="Check retrieval quality: named tests on the context a task retrieves")
    battery_p.add_argument("task", nargs="?", help="task or query text")
    battery_p.add_argument("-k", type=int, default=5, help="top-K context to test (default 5)")
    battery_p.add_argument("--prompt", action="store_true", help="also print the LLM prompt for subjective tests")
    battery_p.add_argument("--no-llm", action="store_true", help="deterministic tests only; skip live Qwen judging")
    battery_p.add_argument("--json", action="store_true", help="machine-readable result (for scripts/CI)")

    report_p = sub.add_parser("report", help="MemoryAgent compliance report: checks grouped under the track's four sub-goals")
    report_p.add_argument("--llm", action="store_true", help="judge Contradiction/Grounding live with Qwen (slower)")
    report_p.add_argument("--json", action="store_true", help="machine-readable result")

    rot_p = sub.add_parser("audit", aliases=["rot"], help="Memory audit: 12 documented staleness/contradiction failure classes, checked live")
    rot_p.add_argument("--json", action="store_true", help="machine-readable result")
    rot_p.add_argument("--file", action="store_true", help="file the rulable findings (R1/R4/R11/R12) so `resolve --list` can surface them (opt-in write)")
    rot_p.add_argument("--judge", action="store_true", help="R11: confirm identity forks with the Qwen judge (the cosine gate cannot separate a fork from a rephrasing); costs one call per candidate")

    heal_p = sub.add_parser("repair", aliases=["heal"], help="Self-repair loop: score the 4 truth gates, propose repairs, apply, re-score")
    heal_p.add_argument("--demo", action="store_true", help="Run on the seeded demo store (universally-legible drift), not your real store")
    heal_p.add_argument("--apply", action="store_true", help="Accept the proposed repairs, apply them, and re-score")
    heal_p.add_argument("--yes-really", action="store_true", help="Required to --apply on your REAL store (safety guard; not needed with --demo)")
    heal_p.add_argument("--reset", action="store_true", help="Re-seed the demo store before running (with --demo)")
    heal_p.add_argument("--json", action="store_true", help="Emit the raw envelope")

    read_p = sub.add_parser("read", help="The reading: open the record and it tells you who you are (portrait + Qwen narration)")
    read_p.add_argument("--json", action="store_true", help="Emit JSON")

    cons_p = sub.add_parser("consistency", help="The consistency gate: does your memory index still match its directory? (deterministic)")
    cons_p.add_argument("index", nargs="?", help="Path to the index markdown (default: Claude Code auto-memory MEMORY.md)")
    cons_p.add_argument("--dir", dest="dir", help="Directory the index indexes (default: the index's own folder)")
    cons_p.add_argument("--json", action="store_true", help="Emit JSON")

    vol_p = sub.add_parser("volatility", help="The volatility gate: flag fast facts stored as durable memory (truth = fact + timestamp + decay)")
    vol_p.add_argument("--json", action="store_true", help="Emit JSON")

    ci_p = sub.add_parser("ci", help="CI for agent memory: scan this repo's rules files + run the rot exam (GitHub annotations, exit 1 on rot)")
    ci_p.add_argument("--path", help="repo to check (default: current directory)")
    ci_p.add_argument("--fail-on", dest="fail_on", choices=["rot", "none"], default="rot",
                      help="'rot' (default) exits 1 if any class fires; 'none' is report-only")

    gold_p = sub.add_parser("policy", aliases=["gold"], help="Compile the policy the agent obeys, built from your rulings, with provenance")
    gold_p.add_argument("--inject", action="store_true", help="write to ~/.claude/GOLDEN_RULES.md (.bak kept)")
    gold_p.add_argument("--show", action="store_true", help="print the compiled rules, write nothing")

    evolve_p = sub.add_parser("evolve", help="The night command: scan + exams + gold recompile + the morning delta")
    evolve_p.add_argument("--no-scan", action="store_true", help="skip ingest, just exams + gold")
    evolve_p.add_argument("--obey", action="store_true", help="also push the compiled policy to ~/.claude so the agent obeys it (.bak kept)")

    resolve_p = sub.add_parser("resolve", help="Close a cross-source contradiction with the truth (correction memory + never-twice guard)")
    resolve_p.add_argument("id", nargs="?", type=int, help="audit finding id (omit to list open ones)")
    resolve_p.add_argument("--truth", help="the true value, one of the asserted dates/values")
    resolve_p.add_argument("--note", help="optional context recorded on the correction memory")
    resolve_p.add_argument("--dismiss", nargs="?", const="", metavar="WHY", help="close as not-rot, reason recorded")
    resolve_p.add_argument("--list", action="store_true", help="list open cross-source contradictions")
    resolve_p.add_argument("--retire", metavar="MEMORY_ID", help="with an output-review ruling: retire the memory that caused the bad output (from `helicon attribute`)")

    guard_p = sub.add_parser("guard", help="Check a proposed output against the law (rulings) before it's written")
    guard_p.add_argument("text", help="the output/claim you're about to assert")

    attr_p = sub.add_parser("attribute", help="Trace a contradicted output finding back to the memory that caused it")
    attr_p.add_argument("id", type=int, help="the review finding id (from `helicon review --terminals --file`)")
    attr_p.add_argument("--limit", type=int, default=5, help="max candidate memories (default 5)")

    watch_p = sub.add_parser("watch", help="Ambient mode: scan + exam on a timer, notify only on NEW drift")
    watch_p.add_argument("--install", action="store_true", help="write the crontab line (idempotent)")
    watch_p.add_argument("--uninstall", action="store_true", help="remove the crontab line")
    watch_p.add_argument("--every", type=int, default=6, help="with --install: run every N hours (default 6)")
    watch_p.add_argument("--no-scan", action="store_true", help="skip the ingest scan, just diff and report")
    watch_p.add_argument("--quiet", action="store_true", help="no desktop notification (cron logs only)")
    watch_p.add_argument("--json", action="store_true", help="machine-readable result")

    alias_p = sub.add_parser("alias", help="Supersession aliases (R4): declare renames, triage dead-name refs into history vs current-claims")
    alias_p.add_argument("--add", nargs=2, metavar=("OLD", "NEW"), help="declare a rename: old name, new name")
    alias_p.add_argument("--renamed-at", help="when the rename happened (ISO date/datetime) — required with --add")
    alias_p.add_argument("--note", help="optional note on the rename")
    alias_p.add_argument("--scan", action="store_true", help="file one audit finding per alias showing rot (idempotent)")

    rule_p = sub.add_parser("rule", help="Prompted rules: author a triage rule in natural language, preview, approve, run")
    rule_p.add_argument("text", nargs="?", help='the rule, e.g. "kill code edits older than 30 days"')
    rule_p.add_argument("--list", action="store_true", help="list all rules")
    rule_p.add_argument("--approve", type=int, metavar="N", help="approve proposed rule N")
    rule_p.add_argument("--retire", type=int, metavar="N", help="retire rule N")
    rule_p.add_argument("--run", action="store_true", help="run approved rules (dry-run unless --apply)")
    rule_p.add_argument("--apply", action="store_true", help="with --run: actually write decisions")

    sub.add_parser("doctor", help="Health check: PATH, config, Qwen key, DB, last scan")
    sub.add_parser("mcp", help="Run the MCP server on stdio (for agent clients)")
    sub.add_parser("score", help="Show current Helicon Score")
    sub.add_parser("stack", help="Audit your AI stack setup")
    sub.add_parser("optimize", help="LLM-powered optimization suggestions")
    sub.add_parser("eval", help="Run evaluation benchmarks (retrieval, forgetting, audit)")

    sub.add_parser("embed", help="Embed all memories for semantic search (384-dim, local)")
    sub.add_parser("playbooks", help="Build and show task playbooks from review patterns")
    compile_p = sub.add_parser("compile", help="Compile memories into injectable skill files")
    compile_p.add_argument("--output", "-o", help="Output directory (default: data/compiled)")

    consolidate_p = sub.add_parser("consolidate", help="Find and merge related memories")
    consolidate_p.add_argument("--max", "-m", type=int, default=10, help="Max clusters to consolidate")
    consolidate_p.add_argument("--qwen", action="store_true", help="Use Qwen LLM for synthesis")

    coneval_p = sub.add_parser("eval-consolidation", help="Before/after: raw memories vs consolidated synthesis (tokens + quality)")
    coneval_p.add_argument("--qwen", action="store_true", help="Qwen-judge answer quality (raw vs consolidated)")
    coneval_p.add_argument("--sample", "-n", type=int, default=12, help="Consolidations to evaluate")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cmds = {
        "init": cmd_init,
        "scan": cmd_scan,
        "reconcile": cmd_reconcile,
        "fix-skills": cmd_fix_skills,
        "serve": cmd_serve,
        "triage": cmd_triage,
        "review": cmd_review,
        "route": cmd_route,
        "score-runs": cmd_score_runs,
        "runs": cmd_runs,
        "judge-bench": cmd_judge_bench,
        "attribute": cmd_attribute,
        "guard": cmd_guard,
        "move": cmd_move,
        "leaderboard": cmd_leaderboard,
        "snapshot": cmd_snapshot,
        "taste": cmd_taste,
        "lens": cmd_lens,
        "check": cmd_battery,
        "battery": cmd_battery,
        "report": cmd_report,
        "audit": cmd_rot,
        "rot": cmd_rot,
        "repair": cmd_heal,
        "heal": cmd_heal,
        "read": cmd_read,
        "consistency": cmd_consistency,
        "volatility": cmd_volatility,
        "ci": cmd_ci,
        "policy": cmd_gold,
        "gold": cmd_gold,
        "evolve": cmd_evolve,
        "resolve": cmd_resolve,
        "watch": cmd_watch,
        "alias": cmd_alias,
        "rule": cmd_rule,
        "doctor": cmd_doctor,
        "mcp": cmd_mcp,
        "score": cmd_score,
        "stack": cmd_stack,
        "optimize": cmd_optimize,
        "eval": cmd_eval,
        "embed": cmd_embed,
        "playbooks": cmd_playbooks,
        "compile": cmd_compile,
        "consolidate": cmd_consolidate,
        "eval-consolidation": cmd_consolidation_eval,
    }

    # One gate instead of 36 tracebacks. Every command below reads
    # config["db_path"], and with no config that raised a raw KeyError from deep
    # inside the command — so a stranger following the README hit a stack trace
    # on `helicon audit`, the exam that IS the product. `init` detecting nothing
    # and exiting 0 sent them back to `scan`, which sent them back to `init`: a
    # closed loop with no exit and no mention of the config.example.json or the
    # demo seed sitting in the same clone. Name the way out.
    # Commands that BUILD their own config and need no user config.json. `ci`
    # belongs here and was missed: it constructs a temp DB and an agent-rules
    # connector for the repo it is handed, which is the entire point of running
    # it on a fresh checkout in GitHub Actions where no config.json exists. The
    # first version of this gate ran before dispatch for every other command and
    # killed `helicon ci --fail-on none` on every push. A gate meant to stop a
    # stranger hitting a traceback broke the one caller that was already right.
    SELF_CONFIGURING = ("init", "doctor", "mcp", "ci")

    from helicon.config import CONFIG_FILE, load_config as _load
    if args.command not in SELF_CONFIGURING:
        try:
            _cfg = _load()
        except FileNotFoundError as e:
            sys.exit(f"{e}")
        if not _cfg:
            sys.exit(
                f"No config at {CONFIG_FILE}.\n\n"
                f"  see it work in 60s:  python3 scripts/demo_seed.py\n"
                f"                       HELICON_CONFIG=config-demo.json helicon audit\n"
                f"  point it at yours:   helicon init\n"
                f"  or by hand:          cp config.example.json config.json\n"
                f"  what's wrong:        helicon doctor")

    cmds[args.command](args)


if __name__ == "__main__":
    main()
