# Mount Helicon — FINAL Devpost copy-paste pack

Verified 2026-07-20 against commit `3707c8b`, the local seeded demo, the full
test suite, the production web build, and the public ECS endpoints.

## Five human actions left

1. Record/export a **public demo shorter than 3:00**. Target 2:35–2:50. Follow
   [../docs/archive/DEMO-SCRIPT.md](../docs/archive/DEMO-SCRIPT.md).
2. Repair the stale seeded state on ECS using the command under **ECS final repair**,
   then run its verification probe.
3. Upload the video publicly to YouTube, Vimeo, or Youku and paste its URL below.
4. Upload `Mount-Helicon-Qwen-Cloud-Deck.pptx` and
   `Mount-Helicon-Architecture.png` from this folder.
5. In Devpost, confirm the project is named **Mount Helicon**, select
   **MemoryAgent**, complete the country/age/eligibility attestations, preview, and
   submit.

## ECS final repair

Run this in the Alibaba ECS workbench:

```bash
cd /root/mount-helicon
git pull --ff-only origin main
python3 - <<'PY'
from helicon.demo import seed
for path in ("data/helicon.db", "data/helicon-demo.db"):
    print(seed(path))
PY
sudo systemctl restart helicon.service
sleep 3
curl -s localhost:8420/api/findings | python3 -c "import json,sys; f=json.load(sys.stdin)['findings'][0]; print(f['title']); print(f.get('question')); print(f.get('consequence'))"
curl -s localhost:8420/api/health
```

Required output: first title `demo-stripe-live`, the Stripe question and
consequence are non-empty, and health contains `"status":"ok"`.

If the question is still empty, inspect the actual unit rather than retrying blindly:

```bash
sudo systemctl status helicon.service --no-pager
sudo systemctl cat helicon.service
sudo journalctl -u helicon.service -n 80 --no-pager
```

## Core Devpost fields

**Project name**

Mount Helicon

**Tagline / elevator pitch**

A governance layer for agent memory: Qwen catches stale contradictions, a human
rules once, and a write-time guard keeps the wrong fact from returning.

**Track**

MemoryAgent

**Submission type**

Individual

**Project status**

Newly built during the hackathon. First commit: 07-01-26.

**Start date**

07-01-26

**Country of residence**

France — confirm before submitting.

**Repository**

https://github.com/MorkeethHQ/mount-helicon

**Live demo**

http://47.237.3.97:8420

**Demo video**

PASTE PUBLIC VIDEO URL HERE

**Alibaba Cloud code proof**

https://github.com/MorkeethHQ/mount-helicon/blob/main/helicon/qwen.py

Additional embedding proof:

https://github.com/MorkeethHQ/mount-helicon/blob/main/helicon/embeddings.py

**Built with**

Python, FastAPI, SQLite, FTS5, NumPy, Qwen, Alibaba Cloud Model Studio,
DashScope, text-embedding-v4, Alibaba Cloud ECS, MCP, React, TypeScript, Vite,
Uvicorn, Swift, SwiftUI, Pydantic

**AI tools used while building**

Claude Code, Codex, and Qwen. Qwen is also part of the shipped product.

**Learning level**

Choose the highest honest option available.

## Project story — paste into “About the project”

### Inspiration

My work had spread across Claude Code, Cursor, Codex, local models, cloud agents,
Git repositories, and notes. The memory kept growing, while a more important
question got harder to answer: what is true now?

Agent memory becomes dangerous when it confidently preserves something that
should no longer be believed. A store can retrieve an old fact perfectly and
still cause the agent to take the wrong action.

### What it does

Mount Helicon is a governance layer for agent memory. It audits a memory store
for twelve classes of rot, including stale claims, contradictions, identity
forks, retrieval regressions, and ungrounded context. Routine repairs can be
applied automatically. Genuine truth conflicts go to a human with the question,
the consequence, and the competing answers.

A human ruling becomes durable policy. Mount Helicon records the decision with
provenance, compiles it into Golden Rules, and checks later writes against it.
If the ruled-wrong value returns, the guard blocks it and cites the ruling. Every
applied batch has a receipt and can be undone.

The demo uses a simple, high-stakes example. One memory says Stripe is in test
mode. Another says Stripe is live and every charge is real money. Qwen judges
that the two claims contradict each other. The operator chooses the current
truth once. A later attempt to write the stale claim is blocked.

Mount Helicon also reports its own health. On my full store, the current
LLM-assisted report is DEGRADED: grounding is 0.385 and one task is broken. That
failure stays visible because trustworthy memory infrastructure needs honest
limits.

### How I built it

The backend is Python and FastAPI over a local-first SQLite store with FTS5 and
NumPy-based retrieval. A deterministic exam covers twelve memory-rot classes.
Qwen handles the semantic judgments that similarity scores cannot settle:
logical contradiction and grounding.

Qwen inference runs through Alibaba Cloud Model Studio in
`helicon/qwen.py`. Embeddings use Alibaba DashScope
`text-embedding-v4` in `helicon/embeddings.py`. The public backend runs on
Alibaba Cloud ECS in Singapore and serves a separate seeded demonstration with
no personal data.

The same core is exposed through a React/TypeScript dashboard, a CLI, a native
SwiftUI macOS menu-bar app, and an MCP server with sixteen tools. The governance
path is audit → inspect evidence → human ruling → compiled policy → write-time
guard → receipt or undo.

### Challenges

The hardest technical problem was distinguishing related claims from claims that
cannot both be true. Vector similarity finds the two Stripe memories because
they discuss the same subject. Qwen supplies the logical judgment.

The hardest product problem was making review cheap enough to use. An audit dump
creates more work. The final review surface asks one direct question, explains
the consequence, and offers the actual competing answers.

The third challenge was demo integrity. My real store contains personal paths
and private operating history. I built a labelled, deterministic demo database
so judges can reproduce the governed loop without receiving my personal data.
The production report shown in the video is aggregate-only.

Deployment also forced a practical choice. The attempted serverless path was
blocked by the available build environment, so I deployed the working FastAPI
backend on an Alibaba Cloud ECS instance and kept the Function Compute
configuration in the repository as a reproducible deployment option.

### Accomplishments

- A complete governed-memory loop: detect, rule, enforce, verify, and undo.
- Twelve of twelve rot classes covered by the deterministic exam.
- Sixteen MCP tools for agent integration.
- A native macOS menu-bar surface, CLI, web dashboard, and public ECS backend.
- Live Qwen contradiction and grounding judgments through Alibaba Model Studio.
- 393 automated tests passing.
- Honest degraded-state reporting instead of a staged all-green result.
- A public demo store isolated from private memory.

### What I learned

Memory quality needs a decision mechanism, not only better retrieval. Detection
creates value when the operator can settle a conflict quickly and that ruling
changes future system behavior.

I also learned to separate evidence types. Automated checks can handle mechanical
rot. Qwen can judge semantic conflict. A human remains the authority for the
current truth. Provenance connects those layers without pretending that one
model call creates ground truth.

### What’s next

The next version will consolidate the product around a calmer cockpit and six
core CLI actions. The governance loop remains the center. I will add stronger
read-only retrieval integration, type-aware forgetting for durable rulings,
better cross-session outcome evidence, and deployment hardening without
expanding the review burden.

## Testing instructions — paste where Devpost asks judges how to run it

```bash
git clone https://github.com/MorkeethHQ/mount-helicon.git
cd mount-helicon
pip install -e .
helicon demo
```

Open http://127.0.0.1:8420. This creates and uses a labelled demo database; it
does not scan the judge’s files and requires no credentials.

For a complete clean-machine check:

```bash
bash scripts/judge-check.sh
```

For the terminal governance loop:

```bash
helicon heal --demo --reset
helicon heal --demo --apply
```

Qwen-powered judgments require a Qwen API key. Without one, deterministic tests
still run and the LLM-dependent checks report that they are unavailable.

## Media uploads

**Presentation deck**

`submission/Mount-Helicon-Qwen-Cloud-Deck.pptx`

**Architecture diagram**

`submission/Mount-Helicon-Architecture.png`

**Recommended gallery order**

1. Start Here: Stripe question, consequence, and two answers.
2. Locked ruling receipt.
3. Terminal guard blocking the stale Stripe claim.
4. Twelve-class exam or aggregate DEGRADED report.
5. Architecture diagram.

Do not upload screenshots of the real Golden Rules, Brief, findings, Memory →
Consistency, local paths, configuration files, environment variables, or API
keys.

## Final preview checklist

- Title says **Mount Helicon** everywhere.
- Track says **MemoryAgent**.
- Video is public and its duration is below 3:00.
- Repository is public and the MIT license is visible.
- Live URL and `/api/health` load.
- ECS Start Here opens with Stripe first and a non-empty question/consequence.
- Architecture image and PPT deck are attached.
- Alibaba code-proof URL points directly to `helicon/qwen.py`.
- No claim says zero broken tasks; current verified truth is one.
- Counts used in submission: 12 rot classes, 16 MCP tools, 393 passing tests.
- The public demo contains seeded data only.
- Country, age, individual-submitter, originality, and eligibility fields are
  confirmed.
- Final Devpost preview has no empty required field.

