# ingest

Loads records files. Python 3, no dependencies.

## Usage
- Load a file: `python3 -m ingest.cli FILE`
- Strict validation: `python3 -m ingest.cli --validate strict FILE`. It exits non-zero when a record is invalid.
