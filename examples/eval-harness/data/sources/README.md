# sources/ — raw inputs, IMMUTABLE

Whatever your system consumes. File-shaped: transcripts, tickets, documents,
diffs, payloads.

**Never edit a file here once a dataset references it.** A dataset records the
sha256 of every item; a published number was measured on those exact bytes. If
an input genuinely changes, create a new dataset version (`_v2`) — editing in
place silently invalidates every number already reported, and nothing warns you.

`make dataset-materialize` re-verifies every hash and fails if one drifted.
