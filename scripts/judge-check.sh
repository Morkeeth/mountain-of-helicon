#!/usr/bin/env bash
# judge-check: the definition of "works".
# Simulates a judge: fresh clone, pip install, boot the server, load the
# dashboard. Anything that fails here fails on the judge's machine, no matter
# what works on this Mac. Exits nonzero on the first crack.
#
# Usage: bash scripts/judge-check.sh [--full]
#   default: venv with --system-site-packages (fast; torch etc. come from host)
#   --full:  clean venv, every dep installed from scratch (the Cloud Shell view)
set -uo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
PORT=8431
TMP="$(mktemp -d)"
SERVER_PID=""
cleanup() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; rm -rf "$TMP"; }
trap cleanup EXIT

fail() { echo "FAIL: $1"; exit 1; }
ok()   { echo "  ok: $1"; }

echo "== judge-check: fresh clone =="
git clone --quiet "$SRC" "$TMP/repo" || fail "git clone"
cd "$TMP/repo"
ok "cloned to $TMP/repo (only committed files from here on)"

echo "== frontend builds from source =="
npm ci --silent || fail "npm ci"
npm run build --silent || fail "npm run build"
test -f web/dist/index.html || fail "web/dist/index.html missing after build"
for ref in $(grep -o '/assets/[^"]*' web/dist/index.html); do
  test -f "web/dist$ref" || fail "index.html references missing $ref (blank dashboard)"
  ok "web/dist$ref"
done

echo "== install =="
if [ "${1:-}" = "--full" ]; then
  python3 -m venv "$TMP/venv"
else
  python3 -m venv --system-site-packages "$TMP/venv"
fi
"$TMP/venv/bin/pip" install --quiet -e . || fail "pip install -e ."
"$TMP/venv/bin/helicon" --help >/dev/null 2>&1 || fail "CLI entry point missing after install"
ok "pip install -e . gives a working CLI"

echo "== boot (the golden path: helicon demo -> seeded, keyless, localhost) =="
export HELICON_DEMO_DIR="$TMP/demo"
"$TMP/venv/bin/helicon" demo --port "$PORT" >"$TMP/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  kill -0 "$SERVER_PID" 2>/dev/null || { cat "$TMP/server.log"; fail "server died on boot"; }
  sleep 1
done

HEALTH="$(curl -sf "http://127.0.0.1:$PORT/api/health")" || { cat "$TMP/server.log"; fail "/api/health"; }
ok "/api/health -> $HEALTH"
echo "$HEALTH" | grep -q '"cubes":0' && { cat "$TMP/server.log"; fail "dashboard opened EMPTY — the demo must seed a populated store"; }
ok "seeded store is populated (not an empty warehouse)"
NEEDS="$(curl -sf "http://127.0.0.1:$PORT/api/findings?lane=decision")" || fail "/api/findings"
echo "$NEEDS" | grep -q '"finding' || fail "review queue is empty — no finding to rule on"
echo "$NEEDS" | grep -qi 'qwencloud\|/Users/\|/home/' && fail "personal data leaked into the demo review queue"
ok "review queue has rulings and leaks no personal data"

INDEX="$(curl -sf "http://127.0.0.1:$PORT/")" || fail "GET /"
echo "$INDEX" | grep -q "Mountain of Helicon" || fail "GET / did not return the dashboard"
ASSET="$(echo "$INDEX" | grep -o '/assets/index[^"]*\.js' | head -1)"
[ -n "$ASSET" ] || fail "no JS asset referenced by GET /"
curl -sf -o /dev/null "http://127.0.0.1:$PORT$ASSET" || fail "GET $ASSET is 404 — blank dashboard"
ok "GET / serves the dashboard and $ASSET resolves"

echo
echo "PASS: a fresh clone installs, boots, and serves the dashboard."
