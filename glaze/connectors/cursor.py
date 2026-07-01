import os
import json
import sqlite3
from glob import glob
from datetime import datetime

from glaze.models import ConnectorResult


def scan(config: dict) -> list[ConnectorResult]:
    workspace_path = os.path.expanduser(config.get("workspace_storage", ""))
    results = []

    if workspace_path and os.path.exists(workspace_path):
        results.extend(_scan_memory_files(workspace_path))
        results.extend(_scan_rules_files(workspace_path))

    cursor_dir = os.path.expanduser(config.get("cursor_dir", "~/.cursor"))
    results.extend(_scan_ai_tracking(cursor_dir))
    results.extend(_scan_conversation_summaries(cursor_dir))

    return results


def _scan_memory_files(workspace_path: str) -> list[ConnectorResult]:
    results = []
    memory_dir = os.path.join(workspace_path, "memory")
    if not os.path.isdir(memory_dir):
        return results

    for md_file in glob(os.path.join(memory_dir, "*.md")):
        with open(md_file) as f:
            content = f.read()

        filename = os.path.basename(md_file)
        mtime = os.path.getmtime(md_file)
        created_at = datetime.fromtimestamp(mtime).isoformat()

        results.append(ConnectorResult(
            source="cursor",
            source_ref=f"cursor/memory/{filename}",
            type="memory",
            title=f"Cursor memory: {filename}",
            content=content[:2000],
            created_at=created_at,
            tags=["cursor", "memory"],
        ))

    return results


def _scan_rules_files(workspace_path: str) -> list[ConnectorResult]:
    results = []
    rules_files = glob(os.path.join(workspace_path, "**", ".cursorrules"), recursive=True)

    for rules_file in rules_files[:10]:
        with open(rules_file) as f:
            content = f.read()

        project = os.path.basename(os.path.dirname(rules_file))
        mtime = os.path.getmtime(rules_file)
        created_at = datetime.fromtimestamp(mtime).isoformat()

        results.append(ConnectorResult(
            source="cursor",
            source_ref=f"cursor/rules/{project}",
            type="memory",
            title=f"Cursor rules: {project}",
            content=content[:2000],
            created_at=created_at,
            tags=["cursor", "rules", project],
        ))

    return results


def _scan_ai_tracking(cursor_dir: str) -> list[ConnectorResult]:
    """Extract AI code tracking data: scored commits with AI/human line attribution."""
    db_path = os.path.join(os.path.expanduser(cursor_dir), "ai-tracking", "ai-code-tracking.db")
    if not os.path.exists(db_path):
        return []

    results = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            "SELECT commitHash, branchName, linesAdded, linesDeleted, "
            "tabLinesAdded, tabLinesDeleted, composerLinesAdded, composerLinesDeleted, "
            "humanLinesAdded, humanLinesDeleted, commitMessage, commitDate, "
            "v2AiPercentage, scoredAt "
            "FROM scored_commits WHERE commitMessage IS NOT NULL AND commitMessage != '' "
            "ORDER BY scoredAt DESC LIMIT 100"
        ).fetchall()

        for row in rows:
            ai_pct = row["v2AiPercentage"] or "0"
            total_added = row["linesAdded"] or 0
            composer_added = row["composerLinesAdded"] or 0
            human_added = row["humanLinesAdded"] or 0
            tab_added = row["tabLinesAdded"] or 0

            commit_date = row["commitDate"] or ""
            try:
                dt = datetime.strptime(commit_date.strip(), "%a %b %d %H:%M:%S %Y %z")
                created_at = dt.isoformat()
            except (ValueError, TypeError):
                created_at = datetime.fromtimestamp(row["scoredAt"] / 1000).isoformat() if row["scoredAt"] else ""

            content = (
                f"Commit: {row['commitMessage']}\n"
                f"Branch: {row['branchName']}\n"
                f"Lines added: {total_added} (composer: {composer_added}, tab: {tab_added}, human: {human_added})\n"
                f"Lines deleted: {row['linesDeleted'] or 0}\n"
                f"AI percentage: {ai_pct}%"
            )

            results.append(ConnectorResult(
                source="cursor",
                source_ref=f"cursor/commit/{row['commitHash'][:12]}",
                type="code",
                title=f"Cursor commit: {(row['commitMessage'] or '')[:60]}",
                content=content,
                created_at=created_at,
                tags=["cursor", "commit", "ai-tracking"],
                metadata={
                    "ai_percentage": ai_pct,
                    "lines_added": total_added,
                    "composer_lines": composer_added,
                    "human_lines": human_added,
                },
            ))

        conn.close()
    except Exception as e:
        print(f"  [!] Cursor AI tracking scan failed: {e}")

    return results


def _scan_conversation_summaries(cursor_dir: str) -> list[ConnectorResult]:
    """Extract Cursor conversation summaries if available."""
    db_path = os.path.join(os.path.expanduser(cursor_dir), "ai-tracking", "ai-code-tracking.db")
    if not os.path.exists(db_path):
        return []

    results = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            "SELECT conversationId, title, tldr, overview, summaryBullets, model, mode, updatedAt "
            "FROM conversation_summaries WHERE title IS NOT NULL "
            "ORDER BY updatedAt DESC LIMIT 50"
        ).fetchall()

        for row in rows:
            parts = [row["title"] or ""]
            if row["tldr"]:
                parts.append(f"TLDR: {row['tldr']}")
            if row["overview"]:
                parts.append(row["overview"][:500])
            if row["summaryBullets"]:
                parts.append(row["summaryBullets"][:500])

            content = "\n".join(parts)
            created_at = datetime.fromtimestamp(row["updatedAt"] / 1000).isoformat() if row["updatedAt"] else ""

            results.append(ConnectorResult(
                source="cursor",
                source_ref=f"cursor/conversation/{row['conversationId'][:16]}",
                type="session",
                title=f"Cursor session: {(row['title'] or 'Untitled')[:60]}",
                content=content[:2000],
                created_at=created_at,
                tags=["cursor", "conversation", row.get("mode") or "unknown"],
                metadata={"model": row["model"] or "", "mode": row["mode"] or ""},
            ))

        conn.close()
    except Exception:
        pass

    return results
