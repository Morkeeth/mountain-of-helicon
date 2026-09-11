# What changed my mind?

Open the dashboard at `/#mind`. Ask a question, or leave it empty to list every
dated correction in the window. Switch between the past week and the past month.
Pick an item. The page shows four steps:

1. The dated instruction that was later overturned.
2. The returned work that the thread cites, resolved on disk (file hash, excerpt
   or directory listing). A cited path that no longer exists is shown as
   `unavailable`.
3. The current ruling, and any older passage that matches the question better but
   loses because a later ruling exists.
4. An editable next prompt that carries the lesson with its date and source line.

## How it decides

- It reads memory content: markdown memory files split into dated passages, and
  a dated rulings JSONL. It does not read git history, and file presence alone
  is not evidence.
- A passage takes its date from its own text, then from its heading. The
  frontmatter `modified:` is a labelled fallback only.
- Lexical match picks the thread. The latest dated Oscar ruling in that thread,
  at or before `as_of`, is the recommendation. Every earlier match is shown as
  superseded.
- No dated ruling in the window gives an explicit gap and no lesson.

## Local contract

`GET /api/mind-changes?q=&window=7|30&as_of=YYYY-MM-DD` with `X-Helicon-Local: 1`
on loopback. Schema `helicon.mind-changes/1`. Each response carries `served_by`
(repo, branch, head, dirty, module hash, pid, process start) so each surface can
show which build produced the answer.

`POST /api/mind-changes/lesson` saves one edited lesson to
`~/.helicon/lessons/<sha>.json`. It then issues the lesson through the existing
context-packet adapter:

1. The lesson is written as `~/.helicon/lesson-project/CLAUDE.md`.
2. That project is reviewed and saved as an immutable source-review snapshot.
3. A packet is issued for that one file to a named run.

The response includes a pointer (packet ID and recipient) and no lesson text.
A receiving Claude Code session consumes the packet with the local-stdio MCP
tool `helicon_context_packet_consume`, which writes a consumption receipt.
`GET /api/mind-changes/packet?packet_id=&run_id=` reports `issued` or
`consumed`. Issuing is not delivery. Saving a newer lesson makes older packets
refuse to deliver.

The MCP server must list the lesson project in its `context_review.projects`.
A keyless config holding only that project is enough:
`{"context_review": {"projects": [{"id": "lessons", "path": "<home>/.helicon/lesson-project"}]}}`.

Sources default to the Claude Code memory directory and
`~/.local/state/fleet/rulings.jsonl`. Override with `HELICON_MIND_MEMORY` and
`HELICON_MIND_RULINGS`.

## Privacy

The route returns private quotes and paths. Never proxy it. Journal, finance
and wallet shaped paragraphs are replaced on screen and counted by kind.
Private rulings and personal-shaped files are dropped whole. Add your own
file-name patterns in `HELICON_MIND_PRIVATE_FILES` (comma list) or
`~/.helicon/private-file-patterns` (one per line). Both stay out of git. Returned-work paths
are opened only under `~/.local/state` and `~/CODE`, and secret-shaped names are
never read.
