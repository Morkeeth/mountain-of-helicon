# Harness — Oscar stack only

**Not for strangers.** This wires Helicon into skills, crons, and the board.

Public onboarding: [ONBOARDING.md](./ONBOARDING.md) (review + CI only).

## Receipts (agents and ZUP read these)

| File | Writer | Reader |
|------|--------|--------|
| `~/.helicon/truth-daily-summary.json` | `scripts/truth-daily.sh` (06:00) | SLASK stamper, `/helicon` skill, future `zup wake` |
| `~/.helicon/truth-daily-latest.txt` | same | humans debugging |
| `~/.helicon/rot-weekly-latest.txt` | `scripts/rot-weekly.sh` (Sun 07:30) | weekly registry/checkouts |
| `~/.helicon/eval-latest.json` | nightly launchd | doc-drift tests |

## G6 metric

**Goal:** board stops lying — `flagged_files` trends down.

```bash
jq .flagged_files,.delta_files ~/.helicon/truth-daily-summary.json
```

SLASK LIVE STATE block includes one line from this JSON when `slask_stamp.py` runs.

## Skill

`~/.claude/skills/helicon/SKILL.md` — product branch (review/truth/witness) vs harness branch (setup/export/crons).

## Crons (macOS)

```
0 6 * * *     truth-daily.sh
30 7 * * 0   rot-weekly.sh
0 */6 * * *   helicon watch
```

Nightly: launchd `com.morkeeth.helicon-nightly.plist`

## Helicon × ZUP

- **Helicon = PAST** — verify, rot, receipts
- **ZUP = FUTURE** — ranked next work
- Share spine via receipts JSON; do not merge UIs
