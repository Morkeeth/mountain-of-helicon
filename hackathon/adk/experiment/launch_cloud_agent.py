#!/usr/bin/env python3
"""Launch a Cursor Cloud Agent for the hackathon ADK experiment.

Requires CURSOR_API_KEY (Cursor Dashboard → Integrations → API Keys).

Usage:
  export CURSOR_API_KEY=cursor_...
  python3 hackathon/adk/experiment/launch_cloud_agent.py
  python3 hackathon/adk/experiment/launch_cloud_agent.py --pool hackathon-adk
  python3 hackathon/adk/experiment/launch_cloud_agent.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROMPT = Path(__file__).resolve().parent / "PROMPT.md"
DEFAULT_REPO = "https://github.com/Morkeeth/mountain-of-helicon"
DEFAULT_BRANCH = "main"


def load_prompt(path: Path | None = None) -> str:
    return (path or DEFAULT_PROMPT).read_text()


def launch(
    *,
    api_key: str,
    prompt_text: str,
    repo_url: str = DEFAULT_REPO,
    starting_ref: str = DEFAULT_BRANCH,
    pool: str | None = None,
    auto_pr: bool = False,
    model: str = "auto",
    name: str = "hackathon-adk",
) -> dict:
    from cursor_sdk import Agent, AgentOptions, CloudAgentOptions, CloudRepository

    cloud_opts: dict = {
        "auto_create_pr": auto_pr,
        "skip_reviewer_request": True,
    }
    if pool:
        cloud_opts["env"] = {"type": "pool", "name": pool}
    else:
        cloud_opts["repos"] = [
            CloudRepository(url=repo_url, starting_ref=starting_ref),
        ]

    result = Agent.prompt(
        prompt_text,
        AgentOptions(
            api_key=api_key,
            model=model,
            cloud=CloudAgentOptions(**cloud_opts),
            name=name,
        ),
    )
    return {
        "status": result.status,
        "agent_id": getattr(result, "agent_id", None),
        "run_id": getattr(result, "run_id", None),
        "result_preview": (result.result or "")[:2000],
        "url": getattr(result, "url", None),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print prompt + config only")
    ap.add_argument("--pool", help="self-hosted pool name (repo-less cloud assign)")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--ref", default=DEFAULT_BRANCH)
    ap.add_argument("--auto-pr", action="store_true")
    ap.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT, help="prompt markdown file")
    ap.add_argument("--name", default="hackathon-adk", help="agent display name")
    ap.add_argument("--model", default="auto")
    args = ap.parse_args()

    prompt_text = load_prompt(args.prompt)

    if args.dry_run:
        print(json.dumps({
            "prompt": str(args.prompt),
            "prompt_chars": len(prompt_text),
            "name": args.name,
            "repo": None if args.pool else args.repo,
            "pool": args.pool,
            "ref": args.ref,
        }, indent=2))
        return 0

    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        print(
            "launch_cloud_agent: set CURSOR_API_KEY "
            "(https://cursor.com/dashboard → Integrations → API Keys)",
            file=sys.stderr,
        )
        return 1

    try:
        out = launch(
            api_key=api_key,
            prompt_text=prompt_text,
            repo_url=args.repo,
            starting_ref=args.ref,
            pool=args.pool,
            auto_pr=args.auto_pr,
            model=args.model,
            name=args.name,
        )
    except Exception as exc:
        print(f"launch failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(out, indent=2))
    if out.get("url"):
        print(f"\nWatch: {out['url']}", file=sys.stderr)
    return 0 if out.get("status") != "error" else 2


if __name__ == "__main__":
    raise SystemExit(main())
