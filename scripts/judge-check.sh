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

echo "== frontend assets are in git =="
test -f web/dist/index.html || fail "web/dist/index.html not in git"
for ref in $(grep -o '/assets/[^"]*' web/dist/index.html); do
  test -f "web/dist$ref" || fail "index.html references $ref but it is not in git (blank dashboard)"
  ok "web/dist$ref"
done

echo "== install =="
if [ "${1:-}" = "--full" ]; then
  python3 -m venv "$TMP/venv"
else
  python3 -m venv --system-site-packages "$TMP/venv"
fi
"$TMP/venv/bin/pip" install --quiet -e . || fail "pip install -e ."
"$TMP/venv/bin/glaze" --help >/dev/null 2>&1 || fail "CLI entry point missing after install"
ok "pip install -e . gives a working CLI"

echo "== boot (the Cloud Shell path: web/dist -> static, keyless config) =="
mkdir -p static && cp -r web/dist/. static/
cat > config.json <<JSON
{"db_path": "data/glaze.db", "connectors": {}, "server": {"host": "127.0.0.1", "port": ${PORT}}}
JSON
"$TMP/venv/bin/python" -m uvicorn glaze.api.app:app --port "$PORT" >"$TMP/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  kill -0 "$SERVER_PID" 2>/dev/null || { cat "$TMP/server.log"; fail "server died on boot"; }
  sleep 1
done

HEALTH="$(curl -sf "http://127.0.0.1:$PORT/api/health")" || { cat "$TMP/server.log"; fail "/api/health"; }
ok "/api/health -> $HEALTH"

INDEX="$(curl -sf "http://127.0.0.1:$PORT/")" || fail "GET /"
echo "$INDEX" | grep -q "Mount Helicon" || fail "GET / did not return the dashboard"
ASSET="$(echo "$INDEX" | grep -o '/assets/index[^"]*\.js' | head -1)"
[ -n "$ASSET" ] || fail "no JS asset referenced by GET /"
curl -sf -o /dev/null "http://127.0.0.1:$PORT$ASSET" || fail "GET $ASSET is 404 — blank dashboard"
ok "GET / serves the dashboard and $ASSET resolves"

echo
echo "PASS: a fresh clone installs, boots, and serves the dashboard."
