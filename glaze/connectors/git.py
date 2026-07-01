import os
import subprocess
from datetime import datetime

from glaze.models import ConnectorResult


def run_git(repo_path: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path] + list(args),
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def scan(config: dict) -> list[ConnectorResult]:
    repos_dir = config.get("repos_dir", "")
    if not repos_dir or not os.path.exists(repos_dir):
        return []

    max_commits = config.get("max_commits", 30)
    results = []

    for entry in os.scandir(repos_dir):
        if not entry.is_dir():
            continue
        git_dir = os.path.join(entry.path, ".git")
        if not os.path.exists(git_dir):
            continue

        repo_name = entry.name

        log_output = run_git(
            entry.path, "log",
            f"--max-count={max_commits}",
            "--format=%H|%aI|%s",
        )
        if not log_output:
            continue

        for line in log_output.split("\n"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            commit_hash, date, message = parts

            stat = run_git(entry.path, "diff", "--stat", f"{commit_hash}^..{commit_hash}")
            stat_summary = stat.split("\n")[-1].strip() if stat else ""

            results.append(ConnectorResult(
                source="git",
                source_ref=f"{repo_name}/{commit_hash[:8]}",
                type="code",
                title=f"[{repo_name}] {message}",
                content=f"Commit: {message}\nRepo: {repo_name}\n{stat_summary}",
                created_at=date,
                tags=["git", "commit", repo_name.lower()],
                metadata={
                    "repo": repo_name,
                    "commit": commit_hash,
                    "stat": stat_summary,
                },
            ))

        diff_stat = run_git(entry.path, "diff", "--stat")
        if diff_stat.strip():
            files_changed = diff_stat.split("\n")[-1].strip()
            results.append(ConnectorResult(
                source="git",
                source_ref=f"{repo_name}/uncommitted",
                type="code",
                title=f"[{repo_name}] Uncommitted changes",
                content=f"Uncommitted changes in {repo_name}:\n{files_changed}",
                created_at=datetime.utcnow().isoformat(),
                tags=["git", "uncommitted", repo_name.lower()],
                metadata={"repo": repo_name, "diff_stat": files_changed},
            ))

    return results
