# Cursor Cloud handoff — build the GCP slice (paste this whole file)

**Oscar is AWAY.** Restate objective + done-when before writing code. Never ask clarifying questions — make the smallest reversible slice and document assumptions in `hackathon/adk/CLOUD-LOG.md`.

---

## Objective

Deploy a **thin async wrapper** on Google Cloud that runs `helicon measurement-bench --json` on a **seeded demo store**, writes the JSON witness to **Firestore**, and serves a **static brief page** that can optionally call **Gemini 3.5 Flash** to narrate the frozen JSON (never to change verdicts).

## Context

- **Repo:** `Morkeeth/mountain-of-helicon` (branch: `hackathon/adk-cloud` or work on main if Oscar says so)
- **Witness CLI (already shipped):**
  ```bash
  helicon measurement-bench              # human output
  helicon measurement-bench --json       # Firestore payload
  helicon measurement-bench --db PATH    # demo store override
  ```
- **Prompt files (read, do not rewrite verdict logic):**
  - `hackathon/adk/prompts/adk-orchestrator.system.md`
  - `hackathon/adk/prompts/gemini-narrator.system.md`
  - `hackathon/adk/architecture.md`
- **Hackathon:** All Things Agentic — Fortified Enterprise Fleet track
- **Mandatory:** Gemini 3.5+ · Google ADK · Cloud Run · Firestore · Pub/Sub

## Constraints

1. **Do NOT reimplement probes** in `hackathon/adk/`. Subprocess `helicon measurement-bench --json` only.
2. **Do NOT use Oscar's live `~/.helicon/helicon.db` in cloud.** Ship `hackathon/adk/demo/helicon.db` — seeded, sanitized, must include ≥1 UNMEASURABLE interactions threshold.
3. **Gemini is narrator-only.** Verdicts live in Firestore from CLI JSON; narrator output goes to `brief_text` only.
4. **Scale to zero.** No always-on costs; Pub/Sub schedule + manual trigger for demo.
5. **Source-only PR.** Do not commit secrets, `.env`, or service account JSON.
6. **Do not touch** `helicon/science.py` verdict logic unless JSON schema is broken — fix schema, not probes.
7. **pytest green** before PR; state count in PR body.

## Definition of done

1. `hackathon/adk/` contains:
   - ADK agent (Python) that runs on Cloud Run
   - Dockerfile that installs `pip install -e .` + copies demo DB
   - Firestore write on trigger (`runs/{runId}`)
   - Pub/Sub topic + push/manual trigger script (`hackathon/adk/trigger.sh`)
   - Minimal brief UI (`hackathon/adk/brief/`) reading latest run from Firestore
2. **Local proof (no GCP bill required to merge):**
   ```bash
   python3 hackathon/adk/run_local.py
   # writes /tmp/run.json with same schema as Firestore
   ```
3. **Deploy proof (for video, can be separate commit):**
   - Cloud Run URL or Console screenshot in `hackathon/adk/CLOUD-LOG.md`
   - Demo video beat: trigger → Cloud Run log → Firestore doc → brief page
4. `hackathon/adk/spin-up.md` filled with reproducible deploy steps
5. Architecture diagram committed (mermaid from `architecture.md` is fine)

## Ranked queue

| # | Task | Why first |
|---|---|---|
| 1 | `run_local.py` — subprocess bench --json, validate schema | Proves witness path before GCP |
| 2 | Seeded `demo/helicon.db` + script to build it | Cloud must not use live store |
| 3 | ADK agent + Firestore write | Core async story |
| 4 | Dockerfile + Cloud Run deploy | Judge proof |
| 5 | Pub/Sub trigger | "Runs while you're away" |
| 6 | Brief UI + Gemini narrator endpoint | Optional for v1 PR; required before submit |

## Do NOT

- Build OpsPilot, DemandOps, or generic fleet chatbots
- Let Gemini pick one "interaction" count when verdict is UNMEASURABLE
- Fork `measurement-bench` repo — everything lives in MoH

## Start by

```bash
git fetch origin && git checkout -b hackathon/adk-cloud
python3 -m helicon measurement-bench --json | head -80
cat hackathon/adk/prompts/adk-orchestrator.system.md
```

Then implement `hackathon/adk/run_local.py` that wraps the same subprocess call and writes JSON to stdout.

## Autonomy contract

Oscar will rate this on whether **witness JSON matches CLI** and **GCP proof exists**. If blocked on GCP credentials, ship local runner + deploy script + CLOUD-LOG with exact commands Oscar runs once — do not stop at "needs credentials."

## Secrets (Cursor Cloud)

Set in environment before deploy:

- `GOOGLE_CLOUD_PROJECT`
- `GEMINI_API_KEY` or Vertex credentials (narrator only)
- Application default credentials for Firestore

## Handback format

Append to `hackathon/adk/CLOUD-LOG.md`:

```
## [Agent YYYY-MM-DD]
- branch / commit
- pytest: N passed
- local: run_local.py output path
- deploy: URL or "not deployed — commands in spin-up.md"
- blockers: ...
```
