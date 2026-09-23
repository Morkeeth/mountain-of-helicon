#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m ingest.cli --validate strict "$1"
