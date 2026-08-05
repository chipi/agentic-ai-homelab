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

- Vendored **2026-08-05** from app-repo commit **`064ff801`** (the state of
  `podcast_scraper` `main` just before the app-delivery commits were removed for a clean
  re-PR — the seam content is unchanged by that rework, only its git history).

## Re-sync procedure (do this once the app re-PRs the delivery seam to `main`)

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
