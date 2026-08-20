# Cloud build log (append only)

## [Cursor 2026-08-20]

Prompt pack created. Witness JSON path:

```bash
helicon measurement-bench --json
```

Cloud agent: paste `FOR-CURSOR-CLOUD.md` into Cursor Cloud.

## [Cursor 2026-08-20b] Local witness path

- `seed_demo_db.py` — creates `demo/helicon.db` (15,001 cubes, UNMEASURABLE wedge)
- `run_local.py` — subprocess bench --json, validates schema
- `trigger.sh` — stub for Cloud Run POST after deploy

Verified:

```bash
python3 hackathon/adk/seed_demo_db.py
python3 hackathon/adk/run_local.py -o /tmp/run.json
# science.unmeasurable_count >= 1, store_truth.findings non-empty
```

**Not built yet:** ADK agent, Dockerfile, Firestore write, brief UI, deploy.

## [Cursor Cloud Agent 2026-08-20] Slice 1 — ADK wrapper

**Objective:** Thin `POST /run` agent subprocesses `helicon measurement-bench --json` on demo store; zero probe reimplementation.

**Added:**
- `hackathon/adk/agent/main.py` — FastAPI `/healthz`, `/run`
- `hackathon/adk/agent/Dockerfile` — stub (python:3.12, pip install -e ., demo db)
- `hackathon/adk/agent/README.md` — curl examples

**Verified local witness path:**
```bash
python3 hackathon/adk/seed_demo_db.py
python3 hackathon/adk/run_local.py --seed -o /tmp/run.json
# science.unmeasurable_count >= 1 ✓
```

**Agent curl (localhost:8080):**
```bash
curl -s -X POST localhost:8080/run | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('unmeasurable_count:', d['science']['unmeasurable_count'])
for v in d['science']['verdicts']:
    if v['verdict']=='UNMEASURABLE':
        print(v['id'], v['verdict'])
"
# unmeasurable_count: 1
# memory-accuracy-10k UNMEASURABLE
```

**pytest:** `tests/test_hackathon_adk.py` — **2 passed**. Full suite: **1055 passed**, 4 failed (`test_doc_drift.py` — pre-existing doc baseline drift, unrelated to slice 1).

**Probe reimplementation count:** 0 (subprocess only).

## [Cursor Agent 2026-08-20] Slice 2 — GCP deploy wiring

**Objective:** After subprocess witness, write `runs/{uuid}` to Firestore; add Cloud Run deploy scripts, Pub/Sub topic, static brief UI (no Gemini v1).

**Added:**
- `hackathon/adk/agent/firestore_store.py` — optional Firestore write/read via `GOOGLE_CLOUD_PROJECT`
- `hackathon/adk/agent/main.py` — Firestore doc on `POST /run`, `GET /runs/latest`, `X-Trigger` header
- `hackathon/adk/deploy/` — `Dockerfile`, `Dockerfile.brief`, `cloudbuild.*.yaml`, `deploy.sh`, `trigger.sh`
- `hackathon/adk/brief/index.html` + `serve.py` — UNMEASURABLE headline, repro command, `/api/run`
- `hackathon/adk/spin-up.md` — exact deploy steps + IAM table

**pytest:** `tests/test_hackathon_adk.py` — **4 passed**.

**Local verify (no GCP):**
```bash
python3 hackathon/adk/run_local.py -o /tmp/run.json
python3 hackathon/adk/brief/serve.py &
curl -s localhost:8080/api/run | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['science']['unmeasurable_count'])"
# 1
```

**Deploy:** `bash hackathon/adk/deploy/deploy.sh` — **not executed in this VM** (`gcloud` not installed). Oscar runs once with `GOOGLE_CLOUD_PROJECT` set; append URLs here:

```
Agent URL:  (run deploy.sh)
Brief URL:  (run deploy.sh)
```

**IAM:** Cloud Run SAs → `roles/datastore.user` (automated in deploy.sh).

**Not built yet (slice 3):** Gemini narrator, Pub/Sub push → Cloud Run Eventarc, scheduled tick.

## [Cursor Cloud Agent 2026-08-20] Slice 1 re-verify — `--db` without user config

**Arm:** A (hosted Cloud VM). Oscar away. Slice 1 only (no new GCP).

**Objective:** Prove the ADK wrapper subprocesses `helicon measurement-bench --json` on the seeded demo store and returns UNMEASURABLE without inventing interaction counts.

**Blocker found:** On a bare VM (`~/.helicon` absent), `measurement-bench --db …` hit the CLI config gate (`No config at …/config.json`) before the `--db` override could apply. Prior CLOUD-LOG entries assumed a config that this environment does not have.

**Fix (helicon/, not hackathon/adk probes):**
- `helicon/cli.py` — bypass config gate when `measurement-bench --db` is set; build `{db_path}` (optionally merged with present config)
- `tests/test_hackathon_adk.py` — regression: empty HOME + `--db` still emits UNMEASURABLE

**Agent surface (already on branch):** `hackathon/adk/agent/main.py` POST `/run`, GET `/healthz`, Dockerfile stub, README curl example. Probe reimplementation count: **0**.

**Verified:**
```bash
python3 hackathon/adk/seed_demo_db.py
python3 hackathon/adk/run_local.py --seed -o /tmp/run.json
# science.unmeasurable_count >= 1 ✓  (no ~/.helicon)

python3 hackathon/adk/agent/main.py   # :8080
curl -s -X POST localhost:8080/run | python3 -m json.tool
```

**curl stdout snippet (UNMEASURABLE):**
```json
{
  "status": "ok",
  "science": {
    "unmeasurable_count": 1,
    "clear_count": 2,
    "inside_count": 0,
    "verdicts": [
      {"id": "rag-precision-500k", "verdict": "CLEAR"},
      {"id": "memory-accuracy-10k", "verdict": "UNMEASURABLE"},
      {"id": "hybrid-1m", "verdict": "CLEAR"}
    ]
  },
  "store_path": "/workspace/hackathon/adk/demo/helicon.db",
  "repro_command": "helicon measurement-bench --json"
}
```

`memory-accuracy-10k` keeps five straddling readings (28 … 15001); no single “interactions” count invented.

**pytest:** `tests/test_hackathon_adk.py` — **5 passed**. Full suite: **1050 passed**, 1 skipped, 2 xfailed, **4 failed** (`tests/test_doc_drift.py` — pre-existing README/CLAUDE count drift, unrelated to slice 1).

