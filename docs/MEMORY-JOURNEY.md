# Inspect a memory's journey

Open **Your setup → Memory history and project instructions**, select a configured
project, then **Review sources** and **Save this review**. The memory journey shows
saved explicit assertions by subject and predicate. Search a belief, open its source
quote and revision, then follow any correction to receiving-run evidence.

The current file matching a saved assertion is not proof that assertion is true.
Multiple current values remain a disagreement. Changed or unavailable files retain
historical evidence without being presented as current. A correction is joined to
its exact source revision and overlapping assertion span; a neighboring assertion
in the same file does not inherit that correction.

Use the existing correction preview/apply/undo controls and save a new review after
an edit. Prepare a selected-source packet for a named consumer with the existing
packet controls. A local consumer must actually request that packet. Reloading or
refreshing the journey reads existing records; it neither delivers a packet nor
creates a new memory database.

Read/delivery, acknowledgment and behavior are distinct:

- Preparation is not delivery. A consumption receipt means the local interface
  returned the exact bytes, not that the model comprehended them.
- This packet contract does not record a separate acknowledgment. The view says so.
- Behavior is an attributed reviewer observation bound to an artifact hash. Changed
  or unavailable artifacts cannot retain a current verification claim. Packet-level
  review does not establish use of every assertion in a multi-source packet.
- These observations do not establish that memory caused an improvement.

## Local read contract

`GET /api/context-review/journey?project_id=<configured-id>` with
`X-Helicon-Local: 1`, on a loopback host and same origin. Schema:
`helicon.memory-journey/1`. Uses configured project scope, not submitted file paths.

The response includes `journeys` (current source values, pinned observations,
corrections and exact-revision consumers), `receipt_errors` and explicit `scope`.
Errors are not an empty-history conclusion. A consumer such as ZUP can link to
this history; this route grants no write, execution, posting or delivery authority.

The route exposes local source quotes and private paths. Do not proxy it to a
public app. Demonstrations must use an explicitly synthetic project or separately
reviewed public-safe material. Free-form assertions and unsaved memory are outside
this initial connection's coverage; no complete-memory claim is made.
