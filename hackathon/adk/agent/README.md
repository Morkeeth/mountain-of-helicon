# ADK agent (slice 1 + 2)

Thin FastAPI wrapper around `helicon measurement-bench --json`. Verdicts come from the subprocess only — this layer never grades thresholds.

Slice 2 adds Firestore write (`runs/{uuid}`) when `GOOGLE_CLOUD_PROJECT` is set.

## Run locally

From repo root:

```bash
python3 hackathon/adk/seed_demo_db.py   # once, or when demo db is missing
python3 hackathon/adk/agent/main.py     # listens on :8080
```

Optional Firestore (needs ADC + project):

```bash
export GOOGLE_CLOUD_PROJECT=your-project
python3 hackathon/adk/agent/main.py
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness — `{"ok": true, "firestore": bool}` |
| POST | `/run` | Run bench on demo store; write Firestore doc; return witness JSON |
| GET | `/runs/latest` | Latest Firestore run (404 if unset/empty) |

## curl example

```bash
# health
curl -s localhost:8080/healthz

# witness run (expect UNMEASURABLE in science.verdicts)
curl -s -X POST localhost:8080/run -H "X-Trigger: manual" | python3 -m json.tool | head -40
```

On subprocess failure, `POST /run` returns HTTP 500 with stderr text — no guessed verdicts.

## Docker (Cloud Run)

```bash
# from repo root — demo db must exist (seed_demo_db.py)
docker build -f hackathon/adk/deploy/Dockerfile -t helicon-adk-agent .
docker run --rm -p 8080:8080 \
  -e GOOGLE_CLOUD_PROJECT=your-project \
  helicon-adk-agent
```

Deploy: `bash hackathon/adk/deploy/deploy.sh` — see `../spin-up.md`.

## IAM

Cloud Run service account needs **`roles/datastore.user`** to write/read `runs/` collection. Granted automatically by `deploy.sh`.
