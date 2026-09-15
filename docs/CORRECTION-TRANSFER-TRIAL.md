# Correction transfer: local private-corpus trial

This trial runs entirely on the machine that holds the drafts. Helicon reads the
one case file you name, writes only the local state directory you name, and makes
no model or network call.

Create a private JSON file outside this repository:

```json
{
  "example_label": "Private local trial",
  "original_draft": "Exact first agent draft",
  "edited_draft": "Exact human-edited draft",
  "explicit_instruction": "Only an instruction the human actually stated, or an empty string",
  "inferred_reason": "A possible reason, clearly treated as inference, or an empty string",
  "proposed_rule": "The rule the human will accept or reject",
  "scope": {
    "project": "exact-project-id",
    "task": "exact-task-class"
  },
  "operation": {
    "find": "text present in the first draft",
    "replace": "text that exactly reproduces the edited draft"
  },
  "cases": [
    {
      "label": "Later relevant task",
      "draft": "Frozen uncorrected later draft",
      "context": {
        "project": "exact-project-id",
        "task": "exact-task-class"
      }
    },
    {
      "label": "Different context that must not inherit",
      "draft": "Frozen uncorrected unrelated draft",
      "context": {
        "project": "exact-project-id",
        "task": "different-task-class"
      }
    }
  ]
}
```

Preview the authored public example without retaining state:

```bash
helicon teach demo
```

Run the real local trial with an explicit human decision:

```bash
helicon teach trial /absolute/private/path/case.json \
  --decision accept \
  --state ~/.helicon/correction-transfer
```

Use `--decision reject` to prove the proposal does not affect either later
attempt. Add `--json` for a complete machine-readable receipt. The result proves
only that the accepted text operation transferred under the declared scope; one
trial cannot establish reduced editing or personal benefit.
