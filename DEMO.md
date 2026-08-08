# Mountain of Helicon — the 3-minute demo

One command tells the whole story:

```bash
bash scripts/demo.sh
```

Keyless and deterministic (git-only probes). Network is used only to clone the
public repos in steps 1–2. It writes nothing to your real `~/.claude/settings.json`
or your real store — it uses a throwaway `settings.json` and an isolated
`$HELICON_DEMO_DIR` (default `/tmp/helicon-demo`).

## The arc (what you say while it runs)

**1. REACH — the problem is real, and everywhere.**
`helicon sweep` points the checker at real public repos. It finds lines in their
`CLAUDE.md` / `AGENTS.md` that the repo's own code disproves — each with the exact
`git` command and its stdout as proof. Not an opinion: an executed check.
> "Every one of these repos ships an agent-rules file that tells an agent to read
> a file the repository does not contain. Here's the command that proves it."

**2. CONTROL — Helicon becomes the preflight, not another dashboard.**
`helicon doorway install` wires the gate into Claude Code as a `UserPromptSubmit`
hook — shown as a diff, backed up first, confirmed, reversible. Then a real prompt
in a contradicted repo receives a **warning in the terminal** with the probe
evidence inline. The run continues by default; enforcement is explicit opt-in.
> "The context is wrong before the first model token. Here is the command that proves it."

**3. RECORD — the human decision is explicit and logged.**
Retype the prompt starting with `helicon-override: <reason>` when you want the
reason preserved. The run already continues in warning mode; this records the
operator's judgment against the exact contradictions. `helicon doctor` shows the
doorway's own store and when it last fired.
> "The warning is automatic. The reason for proceeding can be durable."

**4. SCOPE — the honest limit, said out loud.**
The gate settles what the **filesystem** can settle: a named path that is gone, a
retired-capability kill-switch, a quoted command's output, an on-chain owner. A
*truthfulness* claim ("the record doesn't support this") is a **different
mechanism** — the contradiction judge — not this checker. **Silence is a verdict:**
it means no executable probe could bind, not that everything is fine.
> "We show you exactly how far the executed check reaches. Knowing the edge beats
> discovering it on stage."

## If a live repo was fixed since recording

Step 2 falls back to a representative repo so the gate always fires, and says so.
To gate a currently-flagged real repo instead, pick one from a fresh sweep:

```bash
helicon sweep --from bench/corpus/agent-context-2026-08.txt --jobs 16 --timeout 60 --save out.json
# then point the gate at any repo whose `contradicted` count is > 0
```

## The written evidence behind the pitch

`docs/agent-context-report-2026-08.md` — the full public run over 576 repos, with
hand-verified precision reported next to every rate (and the false-positive classes
named and fixed). The demo is the live version of that report.
