# Onboarding — Mountain of Helicon (strangers)

Three steps. No vault, no ZUP, no API key for the deterministic tier.

## Step 1 — Verify your repo (30 seconds)

```bash
pip install mountain-of-helicon
helicon review .
# or without install:
uvx --from mountain-of-helicon helicon-review .
```

Reads `AGENTS.md` / `CLAUDE.md` / `.cursorrules`, checks pointers and claims against the tree. **Non-zero exit = something in your agent docs is wrong.**

## Step 2 — CI on every PR

Copy `.github/workflows/helicon-ci.yml` from this repo, or use the composite action:

```yaml
- uses: Morkeeth/mountain-of-helicon@main
  with:
    path: .
    fail-on: none   # start report-only; use rot when clean
```

## Step 3 — Optional memory lab

Only if you want scan, dashboard, nightly evolve:

```bash
helicon init && helicon scan && helicon serve
```

---

**Stack harness** (crons, SLASK, ZUP receipts) is Oscar-only — see [HARNESS.md](./HARNESS.md). Strangers never need it.
