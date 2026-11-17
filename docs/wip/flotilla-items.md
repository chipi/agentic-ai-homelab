# Flotilla items (owned by the flotilla session)

The flotilla session's backlog from homelab: open items about the fleets' platform and code, moved here from
[`NEXT_STEPS.md`](NEXT_STEPS.md) on 2026-11-17. The fleet code moved to [flotilla](https://github.com/chipi/flotilla)
(`fleetd/`, `signal-fleet/` and `bugfix-fleet/` left this repo on 2026-11-16), so paths below such as
`signal-fleet/` and `fleetd/` are as recorded at the time; some may point at code that is now in flotilla or
retired. Items about running, measuring and tuning the fleets, and the X3 assistant's gaps, moved on to
[fleet items](fleet-items.md) (the fleet session's) the same day. Items marked "Operator" are the operator's
decisions.

Same conventions as `NEXT_STEPS.md`: strike an item when it's done, don't delete it.

## Fleets

Where each fleet stands: [fleet architecture → Rollout status](https://github.com/chipi/flotilla/blob/main/docs/history/homelab/fleet-architecture.md#rollout-status).

**Triage fleet (Fleet 2)**
- [ ] **Client-side corroboration probe** (Umami) for front-end signals.
- [ ] **No CI covers `signal-fleet/`.** No workflow's paths include it; 6a59983 (the open-only count) got 0
      checks. Its only gates are `deploy.sh`'s on the mini.
- [ ] **`deploy.sh` skips a gate it adds.** bash reads the script before its own `git pull`, so the deploy
      that adds a gate runs the old list (2026-11-04: `eval_inbox_open_replay` ran by hand). Fix: re-exec the
      script after the pull.
- [ ] **A plain `git pull` on the mini deploys the fleet without its gates:** the mini's checkout is the
      fleet's live code. Pull it with `bash deploy/mini-deploy.sh`, even for hub-only commits
      (2026-11-04: hub deploys used plain pulls until 6a59983; none carried fleet code).
- [ ] **`muted-class` label** for bugs whose fingerprint keeps changing (guide, Known gaps).
- [x] ~~Delete the stale `~/signal-fleet/fleet.env` on the mini~~ — *done 2026-10-30 (c739792):
      every live value was in `fleet-gateway.env` or the litellm `.env`, its GitHub and Langfuse
      values were dead; `ls` → No such file.*

**Bug-fix fleet (Fleet 1)** — paused by the operator after one real batch
- [ ] **Resume B1/B2** (shadow on the real backlog, then PR mode), and **B3**: add
      podcast_scraper next to orrery in `fleetd/deploy/chain.json`.
- [ ] **Per-vertical OpenRouter keys** (pi / opencode / fleet). Intended since 2026-07-26,
      never done: only 2 OpenRouter keys exist (2fb91ee; `openrouter-spend.sh`).
- [ ] **Langfuse span emission is a stub** (`bugfix-fleet/src/observability/langfuse.ts:22`
      `TODO(langfuse)`). Gateway-side traces exist since e4e396f; the chain's own spans don't.
- [ ] **Structured-output retry policy for flash workers** (`BAKEOFF.md:603`): about 1 in 11
      structured outputs flake; a flash fleet collects silent `stuck` chains without it.
- [ ] **Flash worker under the kick-back/advisor path is unmeasured** (`BAKEOFF.md:891`).
- [ ] **A test for `fleet/dispatch.ts`.** The vitest suite exists since 98420f6; dispatch
      routing is the named target still without a test.
- [ ] **pi/opencode worker adapters are skeletons** (`piAdapter.ts`, `opencodeAdapter.ts`):
      real harness integration is its own work item.
- [ ] **Split advisor consultation** (redirect → glm, confirm → flash), deferred on 2026-07-26;
      `fleetd/chain.go` still has one advisor.

## From the agent platform evaluation (2026-11-08), input for the next cycle

The evaluation that chose flotilla (closed 2026-11-17; kept in flotilla as
[history 0000](https://chipi.github.io/flotilla/history/0000-origin-evaluation/)).
These are what flotilla's RFCs, ADRs and routines did not cover, as checked on 2026-11-17.
Already covered:
- A1-A3 and most of A4 (seo/search-console, seo/site-check);
- A6 and A7 (RFC-0012, seo/traffic's referrers);
- B1 (triage) and the B2 post-incident review (ADR-0016);
- the runtime choice (ADR-0001: no Hermes, no OpenClaw, for now);
- per-routine model policy (RFC-0002 §3);
- Google access (a service account);
- where findings live (the ledger).

- [ ] **Search Console's BigQuery bulk export is not started.** It has no backfill: Search Console keeps
      16 months, then the data is gone. Neither flotilla nor homelab mentions it.
- [ ] **Operator: Bing Webmaster data** (clicks, impressions, position by API key). site-check only checks
      that Bingbot may crawl; whether to add Bing was never decided.
- [ ] **A4, the rest of a crawl audit:** broken links and redirect chains across the site.
      site-check covers fixed pages and one sampled page per prefix.
- [ ] **A5 content and refresh proposals** (what a page should add, which new page is worth
      writing). Not in RFC-0012.
- [ ] **Phase 4 of RFC-0001 §9 is not built:** `ops/daily-brief` (the Hub briefing job still runs
      from homelab) and `ops/postgres-review` (still a scheduled prompt). There are no routines for either.
- [ ] **B3, investigating a slowdown or an incident** (traces, logs, metrics). Only the
      after-the-fact review exists (ADR-0016).
- [ ] **B4, capacity and cost watch** (mini memory and disk, spend per key) as routines with
      proposals. Today spend shows in the UI and the alerts, and capacity has no routine.
- [ ] **C3 a cross-domain weekly digest** (sites, infra, home, spend), **C2 home**, and **D product
      insight** (Umami funnels and feature use, interpreted). None is planned.
- [ ] **When to revisit an agent runtime:** the evaluation's Phase 0 (OpenClaw first, Hermes as the
      challenger, beside a plain routine on the same candidates, for A5 and B3 work). ADR-0001
      rejected both "for now" and names no trigger to look again.
- [ ] **Operator: tool calling on the DGX prod vLLM** (needs a prod vLLM restart). Still not enabled,
      so tool-calling routines can only use the X3's Ollama.
- [ ] **Operator: the X3 as a 24/7 dependency.** The X3 is a workstation, and its always-on model and
      the remote bugfix workers now run there.
