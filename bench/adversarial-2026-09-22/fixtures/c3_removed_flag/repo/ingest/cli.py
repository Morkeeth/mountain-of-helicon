"""Load a records file and check it."""
import argparse
import json
import sys


def validate(records):
    errors = []
    for i, rec in enumerate(records):
        if not isinstance(rec.get("id"), int):
            errors.append(f"record {i}: id must be an integer")
        if not rec.get("email") or "@" not in rec["email"]:
            errors.append(f"record {i}: email is missing or invalid")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ingest")
    parser.add_argument("path")
    parser.add_argument("--strict", action="store_true",
                        help="deprecated since 3.0, has no effect; use --validate strict")
    parser.add_argument("--validate", choices=["off", "strict"], default="off")
    args = parser.parse_args(argv)
    with open(args.path) as fh:
        records = json.load(fh)
    if args.validate == "strict":
        errors = validate(records)
        if errors:
            for err in errors:
                print(err, file=sys.stderr)
            return 1
    print(f"loaded {len(records)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
