# Helicon launch receipt · 1 Sep 2026 (IDE night)

**Repo:** Morkeeth/mountain-of-helicon · `main`  
**Lane:** IDE + harness `Morkeeth/mountain-of-helicon`

## Gates

```text
$ python3 scripts/launch_check.py
READY: source-controlled gates pass.

$ python3 -m pytest tests/test_launch_contract.py tests/test_new_user_onboarding.py tests/test_python_version_gate.py -q
18 passed
```

## Shipped tonight

| Item | Path |
|------|------|
| DEMO.md restored | `DEMO.md` |
| CLAUDE.md launch-surface clean | `CLAUDE.md` |
| BYOK rerank doctor fix | `helicon/embeddings.py` |
| Release notes | `RELEASE-NOTES-0.2.0.md` |
| Subtraction ruling | `docs/SUBTRACTION-MEMO.md` |

## Oscar gate

```bash
cd ~/CODE/mountain-of-helicon && python3 -m twine upload dist/mountain_of_helicon-0.2.0-py3-none-any.whl
```

**Do not run until release notes read.**

## Verdict

✅ Launch-ready on disk · ⚠️ PyPI publish is Oscar-only

---

## S2 · subtraction ship (help groups) · 31 Aug 2026

**Slice:** grouped `helicon --help` — Verify · Lab · Harness; product one-liner from `docs/SUBTRACTION-MEMO.md`.

### Before (`helicon --help | head -20`)

```text
usage: helicon [-h]
               {init,scan,reconcile,fix-skills,serve,demo,triage,review,review-queue,route,score-runs,move,judge-bench,leaderboard,runs,run,receipt,hook,snapshot,taste,lens,check,battery,report,complaints,audit,rot,repair,heal,read,consistency,registry,checkouts,volatility,ci,policy,gold,evolve,wager,capture,lift,overboard,magnet,measure,ledger,resolve,fleet,unreviewed,queue,guard,bench,brief,doorway,sweep,board,reflect,ask,attribute,watch,alias,rule,doctor,export,truth,mcp,science,measurement-bench,score,stack,skills-review,witness,setup,optimize,eval,embed,playbooks,compile,consolidate,eval-consolidation}
               ...

Mountain of Helicon - memory audit for AI agent stacks

positional arguments:
  {init,scan,reconcile,fix-skills,serve,demo,triage,review,review-queue,route,score-runs,move,judge-bench,leaderboard,runs,run,receipt,hook,snapshot,taste,lens,check,battery,report,complaints,audit,rot,repair,heal,read,consistency,registry,checkouts,volatility,ci,policy,gold,evolve,wager,capture,lift,overboard,magnet,measure,ledger,resolve,fleet,unreviewed,queue,guard,bench,brief,doorway,sweep,board,reflect,ask,attribute,watch,alias,rule,doctor,export,truth,mcp,science,measurement-bench,score,stack,skills-review,witness,setup,optimize,eval,embed,playbooks,compile,consolidate,eval-consolidation}
    init                Auto-detect AI tools and create config
    scan                Scan all configured sources
    reconcile           Retire memory a re-scan no longer sees (dry-run by
                        default)
    fix-skills          Write Qwen descriptions into SKILL.md files missing
                        one (dry-run by default)
    serve               Start the web UI
    demo                Seed a demo store and open the dashboard (one command,
                        no key, no personal data)
    triage              Run auto-triage
    review              Review a repo's agent setup: does its
                        CLAUDE.md/AGENTS.md lie to the agent?
```

### After (`helicon --help | head -20`)

```text
usage: helicon [-h] <command> ...

Find out which of your agent's documents are lying — with evidence, before the
work starts.

Verify:
  truth Point it at ANY agent memory/notes store (Claude Code / Cursor /
  Cline / an Obsidian vault) -> ranked, evidence-cited staleness+rot report.
  No config, no DB, no key, no LLM.

  witness Claim-witness ledger: agent claims in prose vs the tool evidence
  in the trace (keyless, local)

  review Review a repo's agent setup: does its CLAUDE.md/AGENTS.md lie to
  the agent?

  ci CI for agent memory: scan this repo's rules files + run the rot exam
  (GitHub annotations, exit 1 on rot)

  doctor Health check: PATH, config, Qwen key, DB, last scan
```

### Gates (re-run at object)

```text
$ python3 scripts/launch_check.py
READY: source-controlled gates pass.

$ TMPDIR="$HOME/pytmp" python3 -m pytest tests/test_launch_contract.py -q
8 passed
```

**Done-when:** Verify group lists `truth` first · receipt updated · launch_check READY.
