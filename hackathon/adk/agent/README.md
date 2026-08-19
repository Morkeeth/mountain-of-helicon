# ADK agent (slice 1)

Thin FastAPI wrapper around `helicon measurement-bench --json`. Verdicts come from the subprocess only — this layer never grades thresholds.

## Run locally

From repo root:

```bash
python3 hackathon/adk/seed_demo_db.py   # once, or when demo db is missing
python3 hackathon/adk/agent/main.py     # listens on :8080
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness — `{"ok": true}` |
| POST | `/run` | Run measurement bench on demo store; return JSON witness unchanged |

## curl example

```bash
# health
curl -s localhost:8080/healthz

# witness run (expect UNMEASURABLE in science.verdicts)
curl -s -X POST localhost:8080/run | python3 -m json.tool | head -40
```

On subprocess failure, `POST /run` returns HTTP 500 with stderr text — no guessed verdicts.

## Docker (stub)

```bash
docker build -f hackathon/adk/agent/Dockerfile -t helicon-adk-agent .
docker run --rm -p 8080:8080 helicon-adk-agent
```

Firestore + Pub/Sub wiring is slice 2 — see `../architecture.md`.
