# Architecture — measurement bench on GCP

## One sentence

Pub/Sub tick → ADK agent on Cloud Run → subprocess `helicon measurement-bench` → JSON to Firestore → static brief reads Firestore; Gemini narrates the frozen JSON, never invents verdicts.

## Diagram (paste into submission)

```mermaid
flowchart LR
  subgraph trigger
    PS[Cloud Pub/Sub schedule]
    MAN[Manual trigger / Console]
  end

  subgraph gcp["Google Cloud"]
    CR[Cloud Run — ADK agent]
    FS[(Firestore)]
    BRIEF[Cloud Run — brief UI]
  end

  subgraph witness["Witness layer — mountain-of-helicon"]
    MB[helicon measurement-bench]
    DB[(SQLite demo store)]
  end

  subgraph model
    GEM[Gemini 3.5 Flash — narrator only]
  end

  PS --> CR
  MAN --> CR
  CR --> MB
  MB --> DB
  MB -->|stdout JSON| CR
  CR -->|runs/{id}| FS
  BRIEF --> FS
  BRIEF --> GEM
  GEM -->|text brief| BRIEF
```

## Firestore schema (v1)

```
runs/{runId}
  started_at: ISO8601
  finished_at: ISO8601
  trigger: "pubsub" | "manual"
  store_path: string          # gs:// or local path in container
  status: "ok" | "error"
  error: string | null
  science: { verdicts: [...], unmeasurable_count, clear_count, inside_count }
  measure: { weeks: [...], metrics: [...] }
  store_truth: { findings: [...] }
  magnet: { ranked: [...] }   # optional v2 — helicon magnet --json
  brief_text: string | null   # Gemini output, if generated
  repro_command: "helicon measurement-bench"
```

## Compliance story (Fortified Fleet)

| Requirement | How we satisfy it |
|---|---|
| Async background execution | Pub/Sub → Cloud Run, scale to zero |
| Cross-session state | Firestore `runs/` history |
| Enterprise catalog | `runs/` is the registry of probe runs |
| Observability | Cloud Logging + run document carries repro command |
| No fake data | Witness from subprocess; Gemini cannot change verdicts |

## Cost control

- Scale Cloud Run to zero; trigger only for demo + scheduled weekly tick
- Demo uses **seeded** SQLite (`hackathon/adk/demo/helicon.db`), not Oscar's live store
- Brief UI is static fetch from Firestore — no always-on Gemini except on-demand narrate
