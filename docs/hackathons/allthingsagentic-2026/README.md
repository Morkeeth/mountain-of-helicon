# All Things Agentic 2026

**Product home:** this repo (`mountain-of-helicon`). Claude's hackathon prototype
(`measurement-bench`) is merged here — do not maintain two science implementations.

## Run the measurement bench

```bash
helicon measurement-bench          # science + weekly series + store truth
helicon measurement-bench --json     # Firestore / ADK witness payload
helicon science                    # published thresholds only
helicon measure                    # adoption ledger series only
```

## Cloud layer (ADK + GCP)

Prompt pack for Cursor Cloud and Gemini/ADK system instructions:

`hackathon/adk/FOR-CURSOR-CLOUD.md` — **paste this into a Cursor Cloud run**

## Vault lanes (strategy — do not merge files)

- Hub: `vault/01 Projects/Hackathons/allthingsagentic-2026-helicon-science-magnet.md`
- Cursor draft: `allthingsagentic-2026-CURSOR-draft.md` (Cursor edits; Claude read-only)
- Claude review: `allthingsagentic-2026-CLAUDE-review.md` (Claude edits; Cursor read-only)

Code and receipts live here. Strategy lives in vault lane files — never overwrite the other lane's file.

## What merged from Claude's measurement-bench

| Prototype file | MoH home |
|---|---|
| `agent_science.py` | `helicon/science.py` (already richer — kept) |
| `magnet.py` (ledger reader) | `helicon measure` (already ships) |
| `portrait.py` (wrong-object) | `helicon/store_truth.py` |
| `bench.py` | `helicon measurement-bench` |

## Next slices (open)

- Store adapter so probes run against non-helicon stores
- Adoption write path: predict → re-probe → MOVED/FLAT/WITHDRAWN
- Thin ADK/GCP wrapper for Devpost async proof
