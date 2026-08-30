# Experiment prompt — paste to Cloud Agent (slice 1 only)

You are running **experiment slice 1** for the All Things Agentic hackathon cloud layer.

Read first:
- `hackathon/adk/experiment/EXPERIMENT.md`
- `hackathon/adk/architecture.md`
- `hackathon/adk/prompts/adk-orchestrator.system.md`

## Task (smallest reversible slice)

1. Run and verify:
   ```bash
   python3 hackathon/adk/seed_demo_db.py
   python3 hackathon/adk/run_local.py --seed -o /tmp/run.json
   python3 -m json.tool /tmp/run.json | head -30
   ```
   Confirm `science.unmeasurable_count >= 1`.

2. Create `hackathon/adk/agent/main.py`:
   - `POST /run` → subprocess `python3 -m helicon measurement-bench --json --db hackathon/adk/demo/helicon.db`
   - Return JSON body unchanged
   - `GET /healthz` → `{"ok": true}`
   - On subprocess failure: HTTP 500 + stderr, no guessed verdicts

3. Create `hackathon/adk/agent/Dockerfile` (stub only — does not need to deploy today)

4. Add `hackathon/adk/agent/README.md` with curl example

5. Run `python3 -m pytest tests/test_hackathon_adk.py -q` and full suite if fast enough

6. Append signed entry to `hackathon/adk/CLOUD-LOG.md` with pytest count + curl stdout snippet showing UNMEASURABLE

## Hard constraints

- Do NOT reimplement probes in hackathon/adk/
- Do NOT use Oscar's live ~/.helicon store
- Do NOT add GCP/Firestore yet — that's slice 2
- Do NOT invent interaction counts when verdict is UNMEASURABLE

## Done when

`curl -s -X POST localhost:8080/run | python3 -m json.tool` shows UNMEASURABLE (after starting main.py locally).

Oscar is AWAY. Restate objective before coding. Do not ask questions.
