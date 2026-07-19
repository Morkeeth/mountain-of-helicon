"""(Re)build the demo store. Thin wrapper — the demo now lives in the package
(`helicon/demo.py`) so `helicon demo` works from a fresh clone. This script is
kept so `python3 scripts/demo_seed.py` still seeds + resets as before.

The demo is a separate, labelled `helicon-demo.db` of PLANTED memories (a
vegetarian-then-chicken contradiction, a passed marathon date, a balance stored
as durable memory, an Aurora identity fork, …). Only the data is seeded; the
detectors that fire on it are the real ones. Keyless. Idempotent (doubles as
reset).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helicon.demo import seed, write_demo_config  # noqa: E402

if __name__ == "__main__":
    result = seed()
    cfg_path, created = write_demo_config()
    rel = os.path.relpath(cfg_path)
    print(f"seeded {result['cubes']} demo cubes -> {result['db']}")
    print(f"{'wrote' if created else 'kept existing'} keyless config -> {rel}")
    print()
    print("one command does all of this:")
    print("  helicon demo        # seed + open the dashboard on http://127.0.0.1:8420")
