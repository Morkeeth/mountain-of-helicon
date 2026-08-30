# Cloud agent experiment — results (2026-08-20)

## What we ran

| Arm | Status | Notes |
|---|---|---|
| **A — Hosted cloud (`POST /v1/agents`)** | Blocked | `CURSOR_API_KEY` not set. Launcher ready: `hackathon/adk/experiment/launch_cloud_agent.py` |
| **B — Pool worker (`--pool hackathon-adk`)** | Blocked | Requires **Enterprise service account** API key — personal Pro login insufficient |
| **C — Local agent (`agent --print -f`)** | **Success** | Same prompt as cloud; built slice 1 in ~3.7 min |

## Slice 1 delivered (arm C)

- `hackathon/adk/agent/main.py` — `POST /run` subprocesses bench --json, zero probe reimplementation
- Verified: `memory-accuracy-10k` → **UNMEASURABLE**, `unmeasurable_count: 1`
- `tests/test_hackathon_adk.py`: 2 passed

## To run true hosted cloud experiment

1. Create API key: [cursor.com/dashboard](https://cursor.com/dashboard) → Integrations → API Keys
2. **Push branch** — cloud clones GitHub; local uncommitted work is invisible to hosted VM:
   ```bash
   git push -u origin hackathon/adk-cloud   # after commit
   ```
3. Launch:
   ```bash
   export CURSOR_API_KEY=cursor_...
   python3 hackathon/adk/experiment/launch_cloud_agent.py --ref hackathon/adk-cloud
   ```
4. Or paste `hackathon/adk/experiment/PROMPT.md` into [cursor.com/agents](https://cursor.com/agents) UI

## Pool worker (arm B) — Enterprise only

```bash
export CURSOR_API_KEY=<service-account-key>
agent worker start --pool hackathon-adk --worker-dir ~/CODE/mountain-of-helicon
python3 hackathon/adk/experiment/launch_cloud_agent.py --pool hackathon-adk
```

## Experiment conclusion (so far)

**Witness subprocess pattern works** — cloud agent prompt did not tempt reimplementation when constraints were explicit. Hosted cloud arm pending API key + git push.

Next slice: Firestore write + Cloud Run deploy (slice 2 prompt TBD).
