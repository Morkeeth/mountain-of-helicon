# Launch status — present 21 Aug 2026

**Branch (pushed):** `hackathon/adk-cloud`  
**GitHub:** https://github.com/Morkeeth/mountain-of-helicon/tree/hackathon/adk-cloud

---

## Agents

| Agent | Slice | Status | URL / log |
|---|---|---|---|
| Slice 1 ADK wrapper | Done | ✅ Shipped on branch | `hackathon/adk/agent/main.py` |
| Slice 2 GCP deploy | Running overnight | 🔄 Local `agent --print` | `/tmp/hackathon-slice2-agent.log` |
| Hosted cloud slice 1 | Pending | ⏳ Needs `CURSOR_API_KEY` | — |
| Hosted cloud slice 2 | Pending | ⏳ Needs `CURSOR_API_KEY` | — |

---

## Launch hosted cloud agents (morning — 2 min)

```bash
export CURSOR_API_KEY=cursor_...   # cursor.com/dashboard → Integrations

cd ~/CODE/mountain-of-helicon
git checkout hackathon/adk-cloud
git pull

chmod +x hackathon/adk/experiment/launch_all.sh
hackathon/adk/experiment/launch_all.sh hackathon/adk-cloud all
```

Opens two agents on GitHub branch with auto-PR:
1. **slice1** — verify ADK wrapper (likely quick)
2. **slice2** — Firestore + Cloud Run + brief UI

Watch URLs print to terminal → paste into `LAUNCH-STATUS.md` Agent URLs section below.

---

## Present tomorrow

**Runbook:** `hackathon/adk/PRESENT-2026-08-21.md`

**Pre-flight (5 min before):**
```bash
cd ~/CODE/mountain-of-helicon && git checkout hackathon/adk-cloud
helicon measurement-bench
python3 hackathon/adk/agent/main.py &   # optional HTTP demo
```

**8-second open:** "10K interactions, five readings, 536× — UNMEASURABLE, not a guess."

---

## Agent URLs (fill after launch)

```
Slice 1 hosted: 
Slice 2 hosted: 
Slice 2 overnight local log: /tmp/hackathon-slice2-agent.log
```

---

## If hosted launch blocked

Present with CLI only — fully valid. GCP proof can be "deploy script + architecture diagram" without live URL for internal present; Devpost needs video by 31 Aug.
