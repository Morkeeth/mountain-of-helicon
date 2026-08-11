# HELICON-BENCH

**Memory scored against commands that execute.**

Every published agent-memory benchmark scores memory against the user's own
conversation — text vs text:

| Benchmark | Scores a memory against | Executes anything? |
|-----------|-------------------------|--------------------|
| LOCOMO | the conversation it was extracted from | no |
| LongMemEval | a long chat history | no |
| STALE | the dialogue's own later turns | no |
| PersistBench | prior sessions' text | no |

So a memory that is internally consistent but **wrong about the running system**
passes all of them. That is the failure mode that actually bites: a `CLAUDE.md`
that tells every agent the escrow is live while the code retired it, so every
agent plans around a capability that no longer exists.

HELICON-BENCH is the eval for exactly that gap. It scores a repo's instruction
docs by **executed verdict**:

- **CONTRADICTED** — a probe ran and the running code disagrees; its stdout is the receipt.
- **UPHELD** — a probe ran and the code agrees.
- **UNVERIFIABLE** — no probe could run (no RPC, an elided address, an unprobeable claim). Never a silent pass.

## Reproduce it

The corpus and the probes both ship in this repo, so anyone can rerun it and get
the same verdicts — because the verdicts come from commands, not from a label:

```bash
helicon bench            # human scorecard
helicon bench --json     # machine-readable
```

The corpus is `bench/repos/` (four small repos); the probes are `helicon/probes.py`
(R13). Each repo is staged into a throwaway `git` checkout at run time so every
probe kind (kill-switch, path, command, chain) runs identically on any machine.

## Result (this corpus)

```
4 repos · 6 probes executed
3 contradicted · 1 unverifiable · 2 upheld

repo                 probes  contra  unver  upheld
chain-authority           1       0      1       0
escrow-retired            2       2      0       0
honest-service            1       0      0       1
stale-paths               2       1      0       1
```

The receipts (excerpt) — each CONTRADICTED verdict carries the command it ran:

```
CONTRADICTED  escrow-retired  CLAUDE.md:4  [killswitch]
   claim   "The on-chain USDC escrow is a current capability and user self-funding is live."
   probe   $ git grep -n -- "CUSTODY_RETIRED"
   stdout  src/custody.ts:2:export const CUSTODY_RETIRED = true;

CONTRADICTED  stale-paths  CLAUDE.md:4  [path]
   claim   "Configuration lives in `config/settings.yaml`."
   probe   $ git ls-files -- config/settings.yaml
   stdout  (no output)
```

`chain-authority` is UNVERIFIABLE by design — the doc elides the owner address
(`0xAbc1…9f2`), so there is nothing to call; write it in full and set an RPC to
make it checkable. An unverifiable claim is not a passing claim.
