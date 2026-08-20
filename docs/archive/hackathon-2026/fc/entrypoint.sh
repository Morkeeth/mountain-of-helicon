#!/usr/bin/env bash
# FC custom-container entrypoint. Keeps the image keyless: the seeded DB is
# baked in read-only at /app/data/helicon.db, but SQLite needs a writable file
# (WAL + CREATE TABLE IF NOT EXISTS on open), and the two Alibaba Cloud keys are
# injected at runtime from function env vars — never baked into the image layer.
set -euo pipefail

PORT="${PORT:-9000}"

# 1. Writable copy of the seeded store (FC image layers are read-only; /tmp is
#    the writable scratch disk sized by diskSize in s.yaml).
cp /app/data/helicon.db /tmp/helicon.db

# 2. Render the runtime config from the keyless template, injecting the two
#    Alibaba Cloud credentials from env: QWEN_API_KEY -> Model Studio inference,
#    DASHSCOPE_API_KEY -> DashScope text-embedding-v4.
python3 - <<'PY'
import json, os
cfg = json.load(open("/app/fc/config.fc.json"))
cfg["qwen_api_key"] = os.environ.get("QWEN_API_KEY", "")
cfg["embeddings"]["api_key"] = os.environ.get("DASHSCOPE_API_KEY", "")
cfg["db_path"] = "/tmp/helicon.db"
json.dump(cfg, open("/tmp/config.json", "w"))
missing = [k for k in ("QWEN_API_KEY", "DASHSCOPE_API_KEY") if not os.environ.get(k)]
if missing:
    print(f"[entrypoint] WARNING: unset {missing} — Qwen/DashScope calls will fail, "
          "the read-only dashboard still serves the seeded store.", flush=True)
PY

export HELICON_CONFIG=/tmp/config.json

# 3. Serve. FC routes the HTTP trigger to this port; bind all interfaces.
exec python3 -m uvicorn helicon.api.app:app --host 0.0.0.0 --port "${PORT}"
