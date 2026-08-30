#!/usr/bin/env python3
"""Local ADK stand-in — run measurement bench JSON witness without GCP.

Same payload shape Firestore will store. Use before Cloud Run deploy:

    python3 hackathon/adk/run_local.py
    python3 hackathon/adk/run_local.py -o /tmp/run.json
    python3 hackathon/adk/run_local.py --seed
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
DEFAULT_DB = ROOT / "demo" / "helicon.db"

REQUIRED_TOP = ("repro_command", "store_path", "recorded_at", "science", "measure", "store_truth")


def validate(payload: dict) -> None:
    for key in REQUIRED_TOP:
        if key not in payload:
            raise ValueError(f"missing top-level key: {key}")
    science = payload["science"]
    if science.get("unmeasurable_count", 0) < 1:
        raise ValueError("science.unmeasurable_count must be >= 1 for demo wedge")
    if not science.get("verdicts"):
        raise ValueError("science.verdicts empty")
    if not payload["store_truth"].get("findings"):
        raise ValueError("store_truth.findings empty")
    measures = payload["measure"].get("metrics") or payload["measure"].get("weeks")
    if not measures:
        raise ValueError("measure series empty — seed demo db with weekly rows")


def run(db_path: Path, *, seed: bool = False) -> dict:
    if seed or not db_path.is_file():
        spec = ROOT / "seed_demo_db.py"
        proc_seed = subprocess.run(
            [sys.executable, str(spec)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
        )
        if proc_seed.returncode != 0:
            raise RuntimeError(f"seed failed:\n{proc_seed.stderr}")

    proc = subprocess.run(
        [
            sys.executable, "-m", "helicon", "measurement-bench",
            "--json", "--db", str(db_path),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"helicon measurement-bench failed (exit {proc.returncode}):\n{proc.stderr}")

    payload = json.loads(proc.stdout)
    validate(payload)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Local measurement bench witness runner")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="demo SQLite store")
    ap.add_argument("-o", "--output", default="-", help="write JSON here (- = stdout)")
    ap.add_argument("--seed", action="store_true", help="reseed demo db before run")
    args = ap.parse_args()

    try:
        payload = run(args.db, seed=args.seed or not args.db.is_file())
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"run_local: {exc}", file=sys.stderr)
        return 1

    text = json.dumps(payload, indent=2)
    if args.output == "-":
        print(text)
    else:
        Path(args.output).write_text(text + "\n")
        print(f"wrote {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
