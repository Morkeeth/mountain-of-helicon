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
        print(f"\nRetired {total} cube(s) as 'superseded'.")
    else:
        print(f"\nWould retire {total} cube(s). Run with --apply to execute.")


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
    from datetime import datetime
    from helicon.db import insert_review
    from helicon.models import Review
    from helicon.context_impact import link_review_to_context
    from helicon.utility import update_reward

    now = datetime.utcnow()
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
        print('usage: helicon battery "<task>"')
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


def cmd_rot(args):
    """The rot exam: ROT.md's 10 documented failure classes checked live
    against the real store. Deterministic, zero LLM calls, free to run daily."""
    from helicon.config import load_config
    from helicon.db import init_db
    from helicon.rot import format_rot, run_rot_exam

    config = load_config()
    conn = init_db(config["db_path"])
    res = run_rot_exam(conn)
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(res, indent=2, default=str))
        return
    print(format_rot(res))


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
    from helicon.stackwatch import stack_scan
    stack = stack_scan(conn)
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
          f"+{stack['output']} dead-path, +{stack['context']} context finding(s)")
    print(f"  golden rules        {prev_rules} -> {gold['total']}"
          + (f"  (+{gold['total'] - prev_rules} learned)"
             if gold["total"] > prev_rules else "  (holding)"))
    print(f"\n  rule on what needs you:  helicon resolve --list")
    print(f"  the law, current:        data/GOLDEN_RULES.md")


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
        rows = conn.execute(
            "SELECT id, finding, severity, audited_at FROM audit_log "
            "WHERE audit_type = 'factual' AND details LIKE '%pair_key%' "
            "AND human_decision IS NULL ORDER BY id").fetchall()
        if not rows:
            print("No open cross-source contradictions.")
            return
        print("Open cross-source contradictions:\n")
        for r in rows:
            print(f"  #{r['id']}  [{r['severity']}]  {r['finding']}")
        print("\nInspect one:  helicon resolve <id>   "
              "(shows the evidence, decides nothing)")
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
            print(f"\n   {d['cube_count']} cube(s) involved across "
                  f"{len(d.get('scopes', []))} source file(s)")
        if not row["human_decision"]:
            vals = d.get("all_dates") or d.get("dates") or []
            print(f"\nDecide:  helicon resolve {row['id']} --truth "
                  f"<{'|'.join(str(v) for v in vals) or 'value'}>"
                  f"\n   or:   helicon resolve {row['id']} --dismiss \"why\"")
        return
    res = resolve_pair(conn, args.id, args.truth, note=args.note or "")
    if not res["ok"]:
        print(f"error: {res['error']}")
        return
    print(f"resolved #{res['audit_id']}: {res['person'].title()} {res['topic']} = {res['truth']}")
    print(f"  wrong date(s) {', '.join(res['wrong_dates'])} ruled out; "
          f"correction cube {res['correction_cube']} (approved, provenance recorded)")
    print("  never-twice armed: new memory asserting a ruled-out date will re-alarm")


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
        print(f"  {t['live_refs']} live cube(s) still say '{t['old_name']}':")
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
        print(f"Rules run ({mode}): {res['total']} cube(s) matched\n")
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
    print(f"  would affect {prev['pending_matches']} pending cube(s)")
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
        print(f"    ! conflicts with rule #{c['rule_id']} \"{c['nl_text'][:44]}\" on {c['overlap']} cube(s)")

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
        checks.append(("OK", f"DB {db_path} — {total} cubes ({total - retired} live, {retired} retired)"))

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
                                 f"({len(scan['connectors'])} connectors, +{scan['cubes_added']} cubes)"))
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

    print("Embedding all cubes with all-MiniLM-L6-v2 (384 dims)...\n")
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
    print(f"\nForgetting accuracy: {f['forgetting_accuracy']:.0%}")
    print(f"  {f['killed_with_low_conf']}/{f['killed_total']} killed items had low confidence (correct)")
    print(f"  {f['approved_with_ok_conf']}/{f['approved_total']} approved items had ok confidence (correct)")

    a = result["audit"]
    print(f"\nAudit recall: {a['audit_recall']:.0%}")
    print(f"  {a['stale_cubes_found']} flagged / {a['stale_cubes_actual']} actually stale")
    print(f"  {a['total_findings']} total findings, {a['human_confirmed']} human-confirmed")


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
    print(f"Consolidation eval: raw cubes vs consolidated synthesis (sample {sample}{', Qwen-judged' if qwen_client else ', tokens only'})...\n")
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
        print(f"    Raw cubes:    {s['avg_raw_quality']}/100")
        print(f"    Consolidated: {s['avg_consolidated_quality']}/100  (delta {s['avg_quality_delta']:+})")
        print(f"    Consolidated >= raw on {s['consolidated_at_least_as_good']}/{s['judged']} queries")

    print("\n  Per-cluster:")
    for d in result["details"][:10]:
        q = ""
        if "consolidated_score" in d:
            q = f"  quality {d['raw_score']:.0f}->{d['consolidated_score']:.0f}"
        print(f"    {d['topic'][:34]:34s} {d['cube_count']:>2} cubes  {d['compression']:>5}x{q}")


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
    review_p.add_argument("--preview", action="store_true",
                          help="Show the queue + suggested actions without prompting or writing")

    snap_p = sub.add_parser("snapshot", help="Regression-test retrieved context (CI for memory)")
    snap_p.add_argument("action", choices=["add", "check", "list"], help="capture / check drift / list")
    snap_p.add_argument("task", nargs="?", help='task or query text (for "add")')
    snap_p.add_argument("-k", type=int, default=5, help="top-K context to snapshot (default 5)")

    battery_p = sub.add_parser("battery", help="Context-quality battery: named tests on retrieved context")
    battery_p.add_argument("task", nargs="?", help="task or query text")
    battery_p.add_argument("-k", type=int, default=5, help="top-K context to test (default 5)")
    battery_p.add_argument("--prompt", action="store_true", help="also print the LLM prompt for subjective tests")
    battery_p.add_argument("--no-llm", action="store_true", help="deterministic tests only; skip live Qwen judging")
    battery_p.add_argument("--json", action="store_true", help="machine-readable result (for scripts/CI)")

    report_p = sub.add_parser("report", help="MemoryAgent compliance report: checks grouped under the track's four sub-goals")
    report_p.add_argument("--llm", action="store_true", help="judge Contradiction/Grounding live with Qwen (slower)")
    report_p.add_argument("--json", action="store_true", help="machine-readable result")

    rot_p = sub.add_parser("rot", help="The rot exam: 10 documented failure classes (ROT.md) checked live")
    rot_p.add_argument("--json", action="store_true", help="machine-readable result")

    gold_p = sub.add_parser("gold", help="Compile GOLDEN_RULES.md: the stack's law from your rulings, with provenance")
    gold_p.add_argument("--inject", action="store_true", help="write to ~/.claude/GOLDEN_RULES.md (.bak kept)")
    gold_p.add_argument("--show", action="store_true", help="print the compiled rules, write nothing")

    evolve_p = sub.add_parser("evolve", help="The night command: scan + exams + gold recompile + the morning delta")
    evolve_p.add_argument("--no-scan", action="store_true", help="skip ingest, just exams + gold")

    resolve_p = sub.add_parser("resolve", help="Close a cross-source contradiction with the truth (correction cube + never-twice guard)")
    resolve_p.add_argument("id", nargs="?", type=int, help="audit finding id (omit to list open ones)")
    resolve_p.add_argument("--truth", help="the true value, one of the asserted dates/values")
    resolve_p.add_argument("--note", help="optional context recorded on the correction cube")
    resolve_p.add_argument("--dismiss", nargs="?", const="", metavar="WHY", help="close as not-rot, reason recorded")
    resolve_p.add_argument("--list", action="store_true", help="list open cross-source contradictions")

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

    sub.add_parser("embed", help="Embed all cubes for semantic search (384-dim, local)")
    sub.add_parser("playbooks", help="Build and show task playbooks from review patterns")
    compile_p = sub.add_parser("compile", help="Compile memories into injectable skill files")
    compile_p.add_argument("--output", "-o", help="Output directory (default: data/compiled)")

    consolidate_p = sub.add_parser("consolidate", help="Find and merge related memories")
    consolidate_p.add_argument("--max", "-m", type=int, default=10, help="Max clusters to consolidate")
    consolidate_p.add_argument("--qwen", action="store_true", help="Use Qwen LLM for synthesis")

    coneval_p = sub.add_parser("eval-consolidation", help="Before/after: raw cubes vs consolidated synthesis (tokens + quality)")
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
        "snapshot": cmd_snapshot,
        "battery": cmd_battery,
        "report": cmd_report,
        "rot": cmd_rot,
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
    cmds[args.command](args)


if __name__ == "__main__":
    main()
