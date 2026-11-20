# Cloud agent experiment — hackathon ADK slice 1

**Hypothesis:** A Cursor Cloud Agent can implement the ADK wrapper without reimplementing probes, using only `docs/archive/hackathon-adk/` + subprocess witness.

## Arms

| Arm | How | Measures |
|---|---|---|
| **A — Cloud (hosted VM)** | `launch_cloud_agent.py` → `POST /v1/agents` | Time-to-PR, schema compliance, probe reimplementation count (=0) |
| **B — Pool (local worker)** | `agent worker start --pool hackathon-adk` + cloud assign | Same, but sees uncommitted local tree |
| **C — Local control** | `agent --print -f` same prompt | Baseline latency + diff quality |

## Slice 1 scope (this experiment)

NOT full GCP deploy. Only:

1. Verify `python3 docs/archive/hackathon-adk/run_local.py --seed` exits 0
2. Add `docs/archive/hackathon-adk/agent/main.py` — FastAPI (or stdlib HTTP) `POST /run` that:
   - subprocess: `helicon measurement-bench --json --db docs/archive/hackathon-adk/demo/helicon.db`
   - returns parsed JSON
   - never mutates verdict fields
3. Add `docs/archive/hackathon-adk/agent/Dockerfile` stub (FROM python:3.12, pip install -e ., COPY demo db)
4. Append results to `docs/archive/hackathon-adk/CLOUD-LOG.md`

## Success criteria

- [ ] `run_local.py` green on demo db
- [ ] `agent/main.py` exists; curl localhost returns UNMEASURABLE in JSON
- [ ] Zero new threshold/probe logic outside `helicon/`
- [ ] pytest still green (state count in log)

## Fail signals

- Cloud agent reimplements science probes in docs/archive/hackathon-adk/
- Gemini or agent picks one "interaction" reading
- Uses `~/.helicon` instead of demo db
