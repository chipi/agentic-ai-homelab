# Vendored delivery seam contract — SYNC notes

These files are **vendored copies** of the app↔infra delivery seam contract. The **source
of truth lives in the app repo** (`chipi/podcast_scraper`):

- `docs/api/delivery-envelope.schema.json`
- `tests/fixtures/delivery/your-week-digest.v1.golden.json`
- `tests/fixtures/delivery/resurface-nudge.v1.golden.json`

The delivery worker in this repo is a **pure consumer** of that contract: it validates
against the schema + renders the golden fixtures in its test suite, so the two tracks
cannot drift (mirrors the app-side `test_delivery_envelope_contract.py`).

## Provenance

- Vendored **2026-08-05** from **PR #1441** (`feat/delivery-curation-arc`, head
  `064ff801`) — the app-side delivery+curation arc (epic #1413). The schema + both golden
  fixtures are byte-identical to that branch (verified by diff). Security-review follow-up
  commits (e.g. `graph_refs` minItems) may still land on the PR before merge; the worker
  already tolerates them, but re-sync + re-run the contract test when the PR merges.

## Re-sync procedure (when PR #1441 merges to `main`, or to pull its latest)

```bash
# from the podcast_scraper checkout, after the app PR lands on main:
git show origin/main:docs/api/delivery-envelope.schema.json \
  > <homelab>/infra/delivery/schema/delivery-envelope.schema.json
git show origin/main:tests/fixtures/delivery/your-week-digest.v1.golden.json \
  > <homelab>/infra/delivery/schema/fixtures/your-week-digest.v1.golden.json
git show origin/main:tests/fixtures/delivery/resurface-nudge.v1.golden.json \
  > <homelab>/infra/delivery/schema/fixtures/resurface-nudge.v1.golden.json
```

Then run the worker's contract test. If it fails, the contract changed — align the worker
(envelope model + templates), don't edit the vendored copy to make it pass.
