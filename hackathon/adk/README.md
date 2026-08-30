# All Things Agentic — cloud layer (ADK + GCP)

**Product brain stays local:** `helicon measurement-bench` is the witness. Cloud is a thin async wrapper + brief UI for judges.

| File | Use |
|---|---|
| [`FOR-CURSOR-CLOUD.md`](FOR-CURSOR-CLOUD.md) | Paste into **Cursor Cloud** — builds the GCP slice |
| [`prompts/adk-orchestrator.system.md`](prompts/adk-orchestrator.system.md) | ADK root agent system instruction |
| [`prompts/gemini-narrator.system.md`](prompts/gemini-narrator.system.md) | Gemini brief narrator (frozen JSON only) |
| [`architecture.md`](architecture.md) | Judge-facing diagram + Firestore schema |
| [`spin-up.md`](spin-up.md) | README section for Devpost reproducibility |

**Track:** Fortified Enterprise Fleet  
**Mandatory stack:** Gemini 3.5+ · ADK · Cloud Run · Firestore · Pub/Sub  

**Do not reimplement probes in Python in `hackathon/adk/`.** Subprocess `helicon measurement-bench --json` (add flag if missing) or parse structured output from existing commands.
