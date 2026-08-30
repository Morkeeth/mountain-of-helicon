# Cursor log — measurement bench merge (2026-08-20)

**[Cursor 2026-08-20]** Merged Claude's `measurement-bench` into MoH per Oscar lock.

- `helicon/store_truth.py` — wrong-object ratios (Claude's `portrait.py`; renamed to avoid Qwen portrait)
- `helicon/measurement_bench.py` — unified runner
- `helicon measurement-bench` — CLI entry
- Kept existing `helicon/science.py` (richer classify logic + 3 thresholds)
- Kept existing `helicon measure` for adoption ledger series (Claude's magnet reader)
- Tests: `tests/test_store_truth.py`
- `measurement-bench/FOR-CURSOR.md` → pointer to MoH

**Next:** store adapter · adoption MOVED/FLAT write path · ADK thin wrapper
