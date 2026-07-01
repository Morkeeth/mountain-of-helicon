#!/usr/bin/env python3
"""Seed the GLAZE database from all configured connectors."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from glaze.config import load_config
from glaze.scanner import run_scan


def main():
    config = load_config()
    print("GLAZE Seed")
    print(f"DB: {config['db_path']}")
    print()

    stats = run_scan(config)

    print()
    print(f"Raw items found: {stats['total_raw']}")
    print(f"Added to DB:     {stats['added']}")
    print(f"Skipped (dupes): {stats['skipped']}")
    print(f"Total in DB:     {stats['total_in_db']}")
    print()
    print("By source:")
    for source, count in stats.get("by_source", {}).items():
        print(f"  {source}: {count}")
    print()
    print("By type:")
    for type_name, count in stats.get("by_type", {}).items():
        print(f"  {type_name}: {count}")


if __name__ == "__main__":
    main()
