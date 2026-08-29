# Handover — render the "Podcast — production" section on the homelab home page

**Date:** 2026-08-29 · **From:** laptop-side session (podcast_scraper deploy arc) · **For:** an
agent with a working session on the mini.

## The one remaining task

Regenerate the served home page from the already-merged template so the new section renders.
On the mini, as `markodragoljevic`:

```sh
cd ~/agentic-ai-homelab && git pull --ff-only && cd infra/homelab-home && ./gen.sh
```

No container restart — `homelab-home` (nginx) serves the regenerated `www/index.html` directly.
That is the entire task. Everything upstream is done and verified below.

## What is DONE and verified (do not redo)

- **`gen.sh` change is on `origin/main`** — commit `89ba40c` (`feat(home): Podcast — production
  section…`). New section ABOVE Triage fleet: aggregate light + per-check lights (LLM gateway,
  logs/metrics/traces flowing, error tracking) + last-check age. New CSS class `.mid` (orange
  dot). New JS `podcastHealth()` wired into `refresh()`. `bash -n` clean.
- **The metrics the page queries are LIVE in this VM right now** (pushed from a real run of
  `prod_ops_health.sh` on the prod VPS, 2026-08-29 ~23:00 UTC; verified by direct query):
  - `prod_ops_health_check{app="podcast",check=...}` — gateway / o11y_logs / o11y_metrics /
    o11y_traces / o11y_glitchtip, all currently `1`
  - `prod_ops_health_aggregate{app="podcast"}` = `1`
  - `prod_ops_health_last_run_timestamp{app="podcast"}`
- **Semantics the page implements:** value 1 green / 0.5 orange (failed, not customer-impacting)
  / 0 red; aggregate = min. **Staleness overrides green** — no sample for >26h renders grey
  STALE ("check not running"), because a dead health check must never look healthy. The pusher
  is a daily 06:00 UTC GitHub workflow in podcast_scraper (`prod-ops-health.yml`, issue #1876
  there).

## Verification once regenerated

Open `https://hub.tail6d0ed4.ts.net` — first section "Podcast — production", seven cards, all
green, "Last check: <n>h ago". If cards show `—`/STALE: the JS queries `/vm/api/v1/query` with
`last_over_time(...[28h])` — check those against the VM directly before touching anything.

## Why the laptop session could not finish this (all verified, not assumed)

- The SERVING checkout is `/Users/markodragoljevic/agentic-ai-homelab` — proven via
  `docker inspect homelab-home`: it bind-mounts that checkout's `www/`, `.htpasswd`,
  `default.conf`. The `claude`-user clone at `~claude/projects/agentic-ai-homelab` is NOT what
  serves.
- `ssh markodragoljevic@homelab` from the laptop: publickey denied.
- The `claude` account cannot read or write the serving dir (`Permission denied` on `ls` and
  `touch` — macOS home-dir perms), and has no passwordless sudo.
- A docker-run workaround (relay socket is 0666 by design; a container mounting the checkout
  could run `gen.sh`) was deliberately NOT executed — blocked pending operator preference for
  the canonical on-mini flow.

## Caveats for the next agent

- `git pull --ff-only` will refuse if the checkout is dirty — earlier tonight
  `workstation/config/lean-ctx/config.toml` showed modified in the claude clone; if the serving
  checkout is dirty too, stash first, do not clobber.
- `gen.sh` reads creds from mini-local `.env` files (observability/backend, glitchtip, langfuse,
  umami) at generation time; run it IN PLACE in `infra/homelab-home` (paths are relative).
- `www/` is gitignored — regeneration does not dirty the repo.
- Template is per-app by design: the next production app clones the HTML block + swaps the
  `app="podcast"` label. Do not hardcode anything podcast-specific outside the block.
