# Experiment prompt — slice 2 (GCP deploy)

Read first: `hackathon/adk/architecture.md`, `hackathon/adk/spin-up.md`, `hackathon/adk/agent/README.md`

Slice 1 is done (`hackathon/adk/agent/main.py` subprocesses bench --json). Your job is **slice 2 only**.

## Task

1. Add Firestore write to the run path:
   - After subprocess, write `runs/{uuid}` with full JSON witness
   - Use `GOOGLE_CLOUD_PROJECT` env var; document required IAM

2. Add `hackathon/adk/deploy/`:
   - `Dockerfile` (or extend agent Dockerfile) for Cloud Run
   - `deploy.sh` — gcloud run deploy + Firestore enable
   - Pub/Sub topic + `trigger.sh` that POSTs to Cloud Run `/run`

3. Minimal static brief at `hackathon/adk/brief/index.html`:
   - Fetches latest run from Firestore OR reads bundled `/tmp/run.json` for local demo
   - Shows UNMEASURABLE headline + reproduce command
   - **No Gemini in v1** — static JSON render is fine

4. Update `hackathon/adk/spin-up.md` with exact deploy steps

5. Append to `hackathon/adk/CLOUD-LOG.md` with deploy URL or honest "commands only"

## Hard constraints

- Subprocess `helicon measurement-bench --json --db hackathon/adk/demo/helicon.db` only — no probe reimplementation
- Demo store only, never ~/.helicon
- Scale to zero; no always-on costs
- Do not commit secrets or service account JSON

## Done when

`bash hackathon/adk/deploy/deploy.sh` documented and either deploy URL in CLOUD-LOG or clear blocker noted.

Oscar is AWAY. Restate objective before coding.
