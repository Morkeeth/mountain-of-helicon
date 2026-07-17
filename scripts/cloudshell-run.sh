#!/usr/bin/env bash
# Run Mount Helicon inside Alibaba Cloud Shell as proof the backend runs on Alibaba Cloud.
# Slim mode: skips torch/sentence-transformers (~2GB) so it fits Cloud Shell disk.
# The dashboard, scores, cubes, consolidations, reviews all work from the DB;
# only semantic query-search degrades to keyword (fine for a proof/demo).
#
# Prereqs in Cloud Shell (once the shell opens for your account):
#   1. Get the code:   git clone https://github.com/MorkeethHQ/mount-helicon helicon && cd helicon
#   2. Provide the DB: upload data/helicon-demo.db  (Cloud Shell "Upload File")
#   3. Provide the key: export QWEN_API_KEY='sk-...'   (do NOT hardcode)
#   4. Run this:        bash scripts/cloudshell-run.sh
# Then use Cloud Shell "Web Preview" on port 8420 to view + screenshot + record.
#
# STEP 2 SAID data/helicon.db UNTIL 2026-07-17, AND THAT WAS WRONG.
# Cloud Shell is Alibaba's cloud. The real store is 7,799 cubes carrying 4
# 'private key' hits, 20 'passport', 260 'wallet', 90 'journal', 5 'salary'.
# The rule is that journal/finance/wallet data never enters cloud, and an upload
# is not undone by deleting the file afterwards. fc/deploy-fc.sh already refuses
# to publish that store; this script used to ASK FOR IT BY NAME. Same failure
# the FC preflight was written about: the safety note reasoned about the API key
# while the data walked out the door.
#
# So this script now asserts on the artifact too, below. Upload the seeded store
# (scripts/demo_seed.py -> data/helicon-demo.db, 11 planted cubes), or build a
# real-but-public one from a public repo's own git history:
#     bash scripts/demo_public_store.sh
# Either way the proof is the same: the backend RUNS on Alibaba Cloud. Which
# store it serves proves nothing about the platform, so serve the harmless one.
set -euo pipefail

PORT="${PORT:-8420}"

echo "==> Installing slim deps (no torch)"
pip install --quiet --user openai fastapi uvicorn pyyaml gitpython numpy

echo "==> Staging web UI (app serves from ./static)"
mkdir -p static && cp -r web/dist/. static/ 2>/dev/null || echo "  (no web/dist found; API will work, UI limited)"

if [ ! -f config.json ]; then
  echo "==> No config.json; generating one from \$QWEN_API_KEY (connectors off - serve only)"
  : "${QWEN_API_KEY:?set QWEN_API_KEY first: export QWEN_API_KEY='sk-...'}"
  cat > config.json <<JSON
{
  "db_path": "data/helicon.db",
  "qwen_api_key": "${QWEN_API_KEY}",
  "qwen_model": "qwen-plus",
  "qwen_base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
  "connectors": {},
  "server": {"host": "0.0.0.0", "port": ${PORT}, "password": ""}
}
JSON
fi

if [ ! -f data/helicon.db ]; then
  echo "!! data/helicon.db missing. Upload data/helicon-demo.db and rename it:"
  echo "     mv data/helicon-demo.db data/helicon.db"
  echo "   (or build a real-but-public store: bash scripts/demo_public_store.sh)"
  exit 1
fi

# The gate, not the comment. A comment did not stop this the first time: the FC
# Dockerfile baked the real store while the docs said "seeded". Assert on the
# bytes actually about to be served, and refuse rather than warn.
echo "==> Preflight: what this shell is about to serve"
python3 - <<'PY' || exit 1
import sqlite3, sys
db = "data/helicon.db"
c = sqlite3.connect(db)
n = c.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]
hits = {}
for t in ("private key", "seed phrase", "passport", "salary", "recruiter",
          "journal", "wallet", "0x"):
    k = c.execute("SELECT COUNT(*) FROM helicon_cubes WHERE lower(content) LIKE ?",
                  (f"%{t}%",)).fetchone()[0]
    if k:
        hits[t] = k
print(f"    {n} cubes; sensitive-term hits: {hits or 'none'}")
if n > 500 or hits:
    sys.exit(
        f"    REFUSED: this looks like the REAL store, not the demo seed.\n"
        f"    Cloud Shell is Alibaba's cloud, and journal/finance/wallet data does\n"
        f"    not go there. Upload data/helicon-demo.db instead (python3\n"
        f"    scripts/demo_seed.py rebuilds it), or run scripts/demo_public_store.sh.")
print("    clean -> safe to serve")
PY

echo "==> Starting Mount Helicon on 0.0.0.0:${PORT}"
echo "    Open Cloud Shell 'Web Preview' -> port ${PORT} to view, then screenshot + record."
exec python3 -m uvicorn helicon.api.app:app --host 0.0.0.0 --port "${PORT}"
