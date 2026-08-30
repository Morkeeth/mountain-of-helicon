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
| POST | `/run` | Run bench on the demo store; return its JSON body unchanged |

## curl example

```bash
# health
curl -s localhost:8080/healthz

# witness run (expect UNMEASURABLE in science.verdicts)
curl -s -X POST localhost:8080/run | python3 -m json.tool
```

On subprocess failure, `POST /run` returns HTTP 500 with stderr text — no guessed verdicts.

## Docker (stub)

```bash
# from repo root — demo db must exist (seed_demo_db.py)
docker build -f hackathon/adk/agent/Dockerfile -t helicon-adk-agent .
docker run --rm -p 8080:8080 helicon-adk-agent
```

Cloud deployment and persistence are intentionally outside slice 1.
