# Next steps

> Promotion target: this doc itself stays as a rolling plan — content gets
> moved out (to pillar docs / ADRs / templates) as it stabilizes. When
> there's nothing left here, the repo has caught up to v1.0.

Status as of v0.2: all four pillars are real. What's left here is ops
items the operator has to run (live infra), follow-up extractions whose
sanitization cost wasn't worth it yet, and parallel maintenance work.

Full continuity of how v0.2 landed: see
[`history/0003-v0.2-arc.md`](../history/0003-v0.2-arc.md).

## Immediately open (still on the operator)

These need DGX / Grafana Cloud / live-infra access — the recipes are
drafted, but they haven't been run for real yet.

- [x] ~~Fill in `infra/observability/.env` with Grafana Cloud creds →
      `docker compose up -d` → verify in Grafana Cloud Explore.~~
      *Done 2026-06-12; all four dashboards (Node, DCGM, vLLM, cAdvisor)
      confirmed live. Recipe: [`recipes/observability-boot.md`](../recipes/observability-boot.md).*
- [x] ~~Pin the Alloy / DCGM exporter / cAdvisor / ollama-metrics image
      tags after first successful boot (currently `:latest`).~~
      *Done — versions captured after the verified boot.*
- [ ] Symlink `infra/dgx/bin/gpu-mode-swap.sh` into `~/bin/` on the DGX
      and verify (`gpu-mode-swap.sh status`). Defaults assume repo at
      `~/agentic-ai-homelab/` and podcast_scraper at `~/Projects/`; if
      layout differs, drop a `~/.config/gpu-mode.env`.
      *Co-located reference: [`infra/dgx/bin/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/dgx/bin/README.md);
      recipe: [`recipes/gpu-mode-swap.md`](../recipes/gpu-mode-swap.md).*
- [ ] Run `provider-bakeoff/` with your real API keys; pick a primary
      cloud provider for the next round of work. *(Sweep cost ~$2-5.)*

## Dated checks (open on/after the date — we WILL forget otherwise)

- [ ] **2026-08-31+ (any day next week):** verify the docker-prune LaunchAgent
      self-fired Sunday 04:00 on the mini (installed + hand-verified 2026-08-30,
      but the calendar trigger itself has never fired).
      Check: `tail /tmp/docker-prune.log` on the mini shows a `=== docker-prune
      2026-08-31…` header, and the `docker-prune-stale` Grafana alert is still
      inactive. If the run is missing, the dead-man alert fires by ~2026-09-07
      anyway — but check before it has to.
- [ ] **~2026-09-27 (a month out):** colima datadisk regrowth check —
      `sudo du -sh /private/var/_dockerhost/.colima/_lima/_disks/colima/datadisk`
      on the mini. Was 23G after the 2026-08-30 trim (19G live data); if it's
      drifting far above ~30G, the weekly `fstrim -av` isn't holding and the
      job needs a look.
- [ ] **~2026-09-13:** check the two handed-off podcast_scraper issues moved:
      [#1877](https://github.com/chipi/podcast_scraper/issues/1877) (prod-ops-health
      cron → on-VPS systemd timer) and
      [#1879](https://github.com/chipi/podcast_scraper/issues/1879) (63 batched
      signal-fleet proposals, 18 families). If untouched, ping/reassign.

## Maintenance items (parallel, not urgent)

- [ ] **Dedup existing project AGENTS.md files** against the new global.
      Open thread #5 from genesis. Targets: `podcast_scraper-FUTURE`,
      `orrery`, `chemigram`, `oceancanvas`. Each has its own AGENTS.md
      that predates the global rules; the project-level files should now
      keep only project-specific content.
- [x] ~~**Versioning scheme** decision.~~ **Decided 2026-06-13:** HEAD is
      the source of truth + README "Status" line carries the meaningful
      label. Drop lightweight `git tag`s at the moments
      `docs/history/<arc>.md` already marks as significant
      (`v0.1-genesis`, `v0.2-four-pillars-real`, …) — bookmarks, not
      releases. First tag lands once v0.1 is stable; not yet. Revisit if
      the repo gains external consumers who need pinning.
- [ ] **`templates/claude-code/`** — currently deferred (per
      `agent-harnesses.md`). If a clean minimum-viable
      `~/.claude/settings.json` extraction becomes viable, ship it. Hook
      patterns (RTK + lean-ctx) are already covered by the recipes; the
      missing piece is the harness-specific defaults.

## Harden follow-ups (surfaced 2026-08-28 by the pre-close harden audit)

Findings the audit flagged as untracked/parked. Code/doc fixes from the same
audit already landed on the `harden-followups` branch (Brewfile orbstack→colima,
verify.sh oracle path, webpush rs field, signal-fleet README workdir; +Go/Python
test coverage for fleetd chain.go, ci-ops-poller, delivery `_aged_out`). The items
below are decisions/work, not one-line fixes:

- [ ] **bugfix-fleet Langfuse span emission is a no-op stub.**
      `bugfix-fleet/src/observability/langfuse.ts:22` has a `TODO(langfuse)` — the
      per-chain telemetry that feeds the bakeoff Langfuse scores isn't emitted.
- [ ] **Structured-output retry policy for flash workers.** `BAKEOFF.md:603` —
      flash has a ~1/11 structured-output flake; graceful-degrade lands it in
      `stuck` (not a crash), but the retry decision is parked. A flash-worker
      fleet accumulates stuck chains silently without it.
- [ ] **Flash worker under kick-back/advisor path is unmeasured.**
      `BAKEOFF.md:891` — flash won the worker seat on price, but the load-bearing
      kick-back/advisor-pin reliability was only measured with v4-pro.
- [ ] **Trim the obsolete 9443 ACL grant** (PR #1662), superseded by the
      caddy-tailscale plugin. `docs/wip/mac-mini-headless-server.md:302`. Minor
      tailnet hygiene (unnecessary open-port grant).
- [ ] **Land the uncommitted mini changes** (need push approval):
      `infra/reverse-proxy/` (Caddy stack, on mini + local, not committed) and the
      `infra/homelab-home/docker-compose.yml` tailnet-port edit.
      `docs/wip/mac-mini-headless-server.md:29-31`.
- [ ] **bugfix-fleet TypeScript has no test suite** (`bugfix-fleet/src/`, 15
      modules). Highest-value targets: `worker/schemas.ts` (label-schema parsing)
      and `fleet/dispatch.ts` (fallback routing). Blocked on a decision: adding a
      test runner (vitest/jest) is a new dev dependency — needs approval before
      install (rule 30). Not done in the harden pass for that reason.
- [ ] **pi/opencode worker adapters are skeletons** (`bugfix-fleet/src/worker/
      piAdapter.ts`, `opencodeAdapter.ts`, marked `STATUS: skeleton`). Deliberate
      in-progress per the bakeoff MVP design — real harness integration is its own
      work item, not a hardening fix.

## Deferred (intentional)

These were considered and explicitly NOT extracted, because the honest
reference lives elsewhere:

- **`examples/multi-provider-router/`** — provider abstraction shape.
  The honest reference is `podcast_scraper-FUTURE`'s `cloud_balanced` /
  `cloud_thin` / `cloud_with_dgx_*` provider classes, where the
  abstraction has been beaten on by real work. Genericizing it cleanly
  is more work than the derived value here.
- **Claude Code settings.json template** — 127K of operator-specific
  config (permissions, MCP allowlists, hook commands). Load-bearing
  pieces are documented in
  [`recipes/token-management-lean-ctx-rtk.md`](../recipes/token-management-lean-ctx-rtk.md)
  and [`recipes/chrome-devtools-mcp-agent-loop.md`](../recipes/chrome-devtools-mcp-agent-loop.md).

## What's deliberately NOT in scope

Per ADR-0001 — for context if anyone asks why something isn't here.

- Generic "best practices" content not grounded in operator's actual use.
- LangChain / LangGraph / CrewAI orchestration frameworks. The operator
  prefers thin direct API integrations + MCP. If that changes, write an
  ADR.
- Cloud-deployed agentic services (Lambda, Cloud Run, Functions). This
  is a homelab repo.
- **Self-hosted multi-model chat UIs as deploy targets.** Tried in
  genesis, pulled out (see `history/0002-decisions.md` D-0007). Phone
  access to the local vLLM is via Chatbox (OpenAI-compatible client, no
  deploy) — see `agent-harnesses.md`.
- Mobile-native apps (custom iOS / Android dev).
