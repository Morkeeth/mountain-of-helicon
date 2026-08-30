#!/usr/bin/env bash
# Delegates to deploy/trigger.sh (slice 2).
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy/trigger.sh" "$@"
