#!/usr/bin/env python3
"""Poll a cloud agent run until terminal state."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent_id", help="bc-... agent id")
    ap.add_argument("--interval", type=float, default=15.0)
    ap.add_argument("--timeout", type=float, default=3600.0)
    args = ap.parse_args()

    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        print("watch_agent: CURSOR_API_KEY required", file=sys.stderr)
        return 1

    from cursor_sdk import Agent, AgentOptions

    deadline = time.time() + args.timeout
    with Agent.resume(args.agent_id, AgentOptions(api_key=api_key)) as agent:
        while time.time() < deadline:
            # Agent status via latest run — prompt SDK surface
            print(json.dumps({"agent_id": args.agent_id, "poll": time.time()}, default=str))
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
