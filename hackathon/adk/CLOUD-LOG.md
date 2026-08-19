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

**Not built yet (slice 2):** Firestore write, Pub/Sub trigger, Cloud Run deploy, brief UI, Gemini narrator.
