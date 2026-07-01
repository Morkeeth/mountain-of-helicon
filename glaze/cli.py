#!/usr/bin/env python3
"""GLAZE CLI - plug-and-play memory audit for AI agent stacks.

Usage:
  glaze init          Auto-detect your AI tools and create config
  glaze scan          Scan all detected sources
  glaze serve         Start the web UI
  glaze triage        Run auto-triage (autonomous decisions)
  glaze score         Show current Glaze Score
  glaze stack         Audit your AI stack setup
  glaze optimize      LLM-powered optimization suggestions
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
    print("GLAZE init - detecting your AI stack...\n")
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
        "db_path": "data/glaze.db",
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
    print("Next: run `glaze scan` to extract memory items")


def cmd_scan(args):
    """Scan all configured sources."""
    from glaze.config import load_config
    from glaze.scanner import run_scan

    config = load_config()
    if not config.get("connectors"):
        print("No connectors configured. Run `glaze init` first.")
        return

    print("GLAZE scan\n")
    stats = run_scan(config)
    print(f"\nFound {stats['total_raw']} items, added {stats['added']}, skipped {stats['skipped']} dupes")
    print(f"Total in DB: {stats['total_in_db']}")
    for source, count in stats.get("by_source", {}).items():
        print(f"  {source}: {count}")


def cmd_serve(args):
    """Start the web UI."""
    port = args.port or 8420
    print(f"Starting GLAZE at http://localhost:{port}")
    print("Press Ctrl+C to stop\n")
    import uvicorn
    uvicorn.run("glaze.api.app:app", host="0.0.0.0", port=port)


def cmd_triage(args):
    """Run auto-triage."""
    from glaze.config import load_config
    from glaze.db import init_db
    from glaze.triage import init_triage_table, run_auto_triage

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
        from glaze.embeddings import _load_all_embeddings
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
    from glaze.db import insert_review
    from glaze.models import Review
    from glaze.context_impact import link_review_to_context
    from glaze.utility import update_reward

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
    from glaze.config import load_config
    from glaze.db import init_db

    config = load_config()
    conn = init_db(config["db_path"])

    pending = conn.execute(
        "SELECT id, title, content, type, source, confidence, created_at "
        "FROM glaze_cubes WHERE review_status = 'pending' AND merged_into IS NULL"
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
        "SELECT COUNT(*) FROM glaze_cubes WHERE review_status = 'pending' AND merged_into IS NULL"
    ).fetchone()[0]
    print(f"Reviewed {reviewed} this session. Pending: {total} -> {remaining}")


def cmd_score(args):
    """Show current Glaze Score."""
    from glaze.config import load_config
    from glaze.db import init_db
    from glaze.score import compute_score
    from glaze.forgetting import get_decay_stats

    config = load_config()
    conn = init_db(config["db_path"])
    score = compute_score(conn)
    decay = get_decay_stats(conn)

    print(f"\nGlaze Score: {score['score']}%")
    print(f"  Total: {score['total']}  Reviewed: {score['reviewed']}  Pending: {score['pending']}")
    print(f"\nDecay by type:")
    for t, d in sorted(decay.items(), key=lambda x: x[1]["avg_confidence"]):
        bar = "=" * int(d["avg_confidence"] * 30)
        print(f"  {t:15s} {bar:30s} {d['avg_confidence']:.0%} ({d['count']})")


def cmd_stack(args):
    """Audit your AI agent stack."""
    print("GLAZE stack audit\n")
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

    from glaze.config import load_config
    config = load_config()
    if config.get("qwen_api_key"):
        print(f"\n  Qwen Cloud: configured")
    else:
        print(f"\n  Qwen Cloud: not configured (set QWEN_API_KEY)")

    print(f"\nStack completeness:")
    total_sources = len(detected)
    has_qwen = bool(config.get("qwen_api_key"))
    has_db = os.path.exists(config.get("db_path", "data/glaze.db"))
    completeness = (total_sources * 20 + (30 if has_qwen else 0) + (20 if has_db else 0))
    print(f"  {min(completeness, 100)}% - {total_sources} source(s), {'Qwen active' if has_qwen else 'no Qwen'}, {'DB seeded' if has_db else 'no DB'}")


def cmd_optimize(args):
    """LLM-powered optimization suggestions for your memory stack."""
    from glaze.config import load_config
    from glaze.db import init_db
    from glaze.score import compute_score
    from glaze.forgetting import get_decay_stats
    from glaze.triage import compute_triage_rules, init_triage_table
    from glaze.qwen import get_client, complete

    config = load_config()
    conn = init_db(config["db_path"])
    init_triage_table(conn)

    score = compute_score(conn)
    decay = get_decay_stats(conn)
    rules = compute_triage_rules(conn)

    type_dist = conn.execute(
        "SELECT type, COUNT(*) as cnt, AVG(confidence) as avg_conf "
        "FROM glaze_cubes WHERE merged_into IS NULL GROUP BY type ORDER BY cnt DESC"
    ).fetchall()

    review_hist = conn.execute(
        "SELECT cube_type, decision, COUNT(*) as cnt FROM reviews GROUP BY cube_type, decision"
    ).fetchall()

    context = f"""Memory system stats:
- Glaze Score: {score['score']}% ({score['reviewed']} reviewed / {score['total']} total, {score['pending']} pending)
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
        print(f"Glaze Score: {score['score']}%")
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
    from glaze.config import load_config
    from glaze.db import init_db
    from glaze.embeddings import embed_all_cubes, get_embedding_stats

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
    from glaze.config import load_config
    from glaze.db import init_db
    from glaze.compiler import write_compiled_files

    config = load_config()
    conn = init_db(config["db_path"])

    output_dir = args.output or "data/compiled"
    print(f"Compiling memory into injectable files -> {output_dir}\n")
    result = write_compiled_files(conn, output_dir)

    for filename, size in result["files"].items():
        print(f"  {filename:30s} {size:>6,} bytes")
    print(f"\n{result['files_written']} files written ({result['total_bytes']:,} bytes total)")


def cmd_playbooks(_args):
    from glaze.config import load_config
    from glaze.db import init_db
    from glaze.playbooks import build_playbooks

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

    print(f"\n{len(results)} playbooks built. Use `glaze_playbook` MCP tool to match tasks.")


def cmd_consolidate(args):
    from glaze.config import load_config
    from glaze.db import init_db
    from glaze.consolidation import find_clusters, run_consolidation

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
        from glaze.qwen import get_client
        qwen_client = get_client(config)

    print(f"\nConsolidating top {max_clusters} clusters...\n")
    result = run_consolidation(conn, qwen_client, max_clusters)

    for r in result["results"]:
        print(f"  {r['title'][:50]} ({r['cube_count']} items merged, conf: {r['confidence']:.0%})")

    print(f"\n{result['consolidated']} clusters consolidated from {result['clusters_found']} found.")


def cmd_eval(_args):
    from glaze.config import load_config
    from glaze.db import init_db
    from glaze.eval import run_eval, init_eval_tables
    from glaze.score import backfill_score_history

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
    from glaze.config import load_config
    from glaze.db import init_db
    from glaze.eval import run_consolidation_eval

    config = load_config()
    conn = init_db(config["db_path"])

    qwen_client = None
    if getattr(args, "qwen", False):
        from glaze.qwen import get_client
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
    parser = argparse.ArgumentParser(description="GLAZE - memory audit for AI agent stacks")
    sub = parser.add_subparsers(dest="command")

    init_p = sub.add_parser("init", help="Auto-detect AI tools and create config")
    init_p.add_argument("--force", action="store_true", help="Overwrite existing config")

    sub.add_parser("scan", help="Scan all configured sources")

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

    sub.add_parser("score", help="Show current Glaze Score")
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
        "serve": cmd_serve,
        "triage": cmd_triage,
        "review": cmd_review,
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
