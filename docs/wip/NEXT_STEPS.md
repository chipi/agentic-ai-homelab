# Next steps

The live punch list for this repo: every open item, grouped by where the work happens. Strike an
item when it's done (`- [x] ~~text~~ — *done note (date)*`) and move it to
[Done](#done-paper-trail) at the end; don't delete it. Regrouped on 2026-10-29, when 25 other wip
notes were closed and their open items folded in here
([history 0007](../history/0007-wip-notes-closed.md)). "Checked" dates say when an item's
state was last verified against the live system.

## Decisions waiting on the operator

- [ ] **Grafana on Postgres, or stay on SQLite?** Due 2026-10-25, now overdue. WAL went on
      2026-10-18 (c3b0a18) after "database is locked" flapped alert rules (968 locks in one
      hour on 10-18). **Checked 2026-10-29: 2 locks in the last 7 days**, which argues for
      staying on SQLite. Migrate only if locks come back or a second Grafana is wanted.
      - **What a migration has to carry** (checked 2026-10-18): 5 service accounts with 10
        tokens other repos and the fleet use (`podcast-sync` 6, `orrery-sync`,
        `signal-fleet`, `podcast-obs-reader`, `claude-code-obs`) and 15 of the 36 dashboards
        (pushed by the podcast/orrery sync jobs, not in this repo). A fresh DB would break
        every token, so it is a data migration, not a re-provision.
      - **Where:** its own database and role in an existing Postgres (`glitchtip-postgres-1`
        16.4, `langfuse-postgres-1` 17, `litellm-postgres`, `umami`). Sharing one couples
        Grafana's uptime to that app's.
      - check: `docker logs grafana --since 168h 2>&1 | grep -c 'database is locked'` on the mini.
- [ ] **Agentic coding fleet: close it, or do the first test ride?** Dormant since 2026-07-03.
      The opencode fleet was later built from the oh-my-opencode plugin; the Pi team and the
      greenfield test ride never happened. Its decisions are in history 0007.
- [ ] **Operator-preference conflicts** found when the 2026-07-24 preferences review was closed:
  - `make`: global rule 16 says foreground; podcast_scraper's memory says background
    ("REVERSED 2026-06-09"). Which wins there?
  - AI credit in commits: orrery's memory says never credit Claude or AI; this repo's commits
    carry `Co-Authored-By: Claude`. Orrery-only, or global?
  - Project memories with no global rule (no cheating options, never cut scope, never touch
    sudo or host state, never skip tests or add xfail, no lint weakening, no prod
    self-approve, never suggest dropping models): keep them project-scoped, or promote?
- [ ] **`provider-bakeoff/`: run it or drop it?** "Run with your real API keys; pick a primary
      cloud provider" has been open since 2026-06-12. Everything now routes through LiteLLM and
      OpenRouter (`infra/litellm/README.md`), so the question it answered may be gone.
- [ ] **Mini leftovers from the 2026-08-30 pruning:** `org.cindori.AuthHelper` (TRIM
      Enabler/Sensei helper; remove only with a yes) and `~/Library/Application Support/Adobe`
      (1.1 GB of personal Photoshop/Lightroom data; keep or delete).
- [ ] **Smoke-test traffic:** tag the post-deploy Playwright smokes (a user-agent marker in
      podcast_scraper's configs) so edge and log analysis can leave them out; asked 2026-10-29.
- [ ] **Website checks the websites session suggested** (2026-10-29): Adobe's origin 403/429
      trend on airandspacehistory.com, and a probe of Adobe's origin certificate behind
      Cloudflare (valid until 2026-12-08). Cloudflare's own notifications are a dashboard setting.

## Mini (operator picks the window)

- [ ] **colima 8 → 4 vCPU, 20 → 12 GB, and Spotlight off** —
      [`colima-vcpu-8-to-4-runbook.md`](colima-vcpu-8-to-4-runbook.md). **Checked 2026-10-29:**
      still `8 CPUs / 20GiB`, `mdutil` → `Indexing enabled.` The plan predates the dev engine
      (ADR-0009); recheck the 12 GB sizing against it before running.
- [ ] **Install the +32 GB RAM** (2018 mini → 64 GB). **Checked 2026-10-29:** still 32 GB
      (`hw.memsize` 34359738368). Full shutdown and a physical open.
- [ ] **Tailscale exit node on the mini** (NL egress while travelling) —
      [`tailscale-exit-node-mini.md`](tailscale-exit-node-mini.md), not executed. The ACL now
      lives in **chipi/infra** (`tailscale/policy.hujson`, `tailscale-acl.yml`); the mini runs
      the standalone macsys build, which can be an exit node (checked 2026-10-29).
- [ ] **Pin the mini's floating images** (found by `infra-drift`, 2026-10-17): Langfuse's
      `clickhouse-server` and `chainguard/minio` run untagged. Pin each to its running digest,
      as Umami was (4cafb0c), and recreate in a window.
- [ ] **Prove a login-less reboot** since the Tailscale fix (2026-09-10). The 2026-09-08 power
      cut brought containers back in 81 s but left the host off the tailnet for 30 h; the fix
      has not been through a real reboot. check: `last reboot | head -3; tail -20
      /tmp/tailscale-up.log`.
- [ ] **Upgrade lima once [#5420](https://github.com/lima-vm/lima/issues/5420) is released**
      (operator approved the upgrade 2026-10-09). **Checked 2026-10-29:** closed upstream on
      10-27, not in a release yet (latest v2.2.1, v2.3.0-beta.1, both 10-03). Check monthly.
      Caveat: #5420 covers a dead SSH master; the 2026-10-08 break was a wedged one, so confirm
      the fix detects that too. Runbook:
      [colima/lima forwarding recovery](../recipes/colima-lima-forwarding-recovery.md). Related:
      the usernet outbound limit, homelab #118.
- [ ] **Langfuse MinIO retention not verified.** ClickHouse deletes after 30 days (checked
      2026-09-30); confirm the same for MinIO with `mc ls` and credentials (oldest object under
      `lf/langfuse/events`).
- [ ] **Can the caddy-tailscale auth key be revoked?** Tailscale admin console → Settings →
      Keys. `infra/reverse-proxy/docker-compose.yml` requires `TS_AUTHKEY` to be set either way.
- [ ] **Renew the fleet GitHub token before 2027-01-25 19:03 UTC** (chipi/podcast_scraper,
      orrery, agentic-ai-homelab, humancopilot.eu, eval-harness; Issues read/write). check: on
      the mini, `curl -sI -H "Authorization: Bearer $GITHUB_TOKEN"
      https://api.github.com/rate_limit | grep -i token-expiration`.

## DGX

State on 2026-10-17, checked: the `ops` checkout is current with `origin/main` and clean; every
container runs the image its compose names; mode `prod`, Ollama stopped and disabled.

**Rule:** deploy to the DGX by pulling as `ops`, never by copying files in:
`sudo -u ops git -C /home/ops/agentic-ai-homelab pull --ff-only`.

**After any recreate, verify:** the `dgx-status` skill; `~/bin/gpu-mode-swap.sh --mode-only` →
`prod`; the `obs-boot` check (DGX metric freshness); one podcast pipeline call through the
gateway (`proj-podcast-dev`, the DGX model).

- [ ] **Clock cap across a reboot is unproven.** The DGX has not rebooted since 2026-09-18
      (`node_boot_time_seconds`); peak SM clock since then is 2197 MHz, under the 2200 MHz
      cap (checked 2026-10-29 from metrics). Verify after the next reboot:
      `systemctl is-active gpu-clock-cap` and the SM clock under load. Background:
      [`DGX-SPARK-KNOWN-HARDWARE-ISSUE.md`](DGX-SPARK-KNOWN-HARDWARE-ISSUE.md).
- [ ] **Physical, at the box:** NVIDIA's `dgx-spark-fieldiag` PowerStress (blocked by Secure
      Boot, needs the console) and a repaste / chassis-fan orientation check.
- [ ] **Meter the DGX's power** (smart plug). Home Assistant only meters the house's P1 meter
      today (checked 2026-10-29); a HomeWizard socket on the DGX would make power-off
      forensics possible. Home-automation's call.

## Observability

- [ ] **Telemetry pipeline, remaining steps** —
      [`otel-pipeline-end-to-end.md`](otel-pipeline-end-to-end.md), issue #99: ADR-0010 phases B
      and C (container labels and one relabel per box; phase C 30 days later); #99 §2's
      post-deploy checks; a `run_id` tag on errors raised outside a span; write
      `docs/recipes/observability-correlation.md`.
- [ ] **Missing spend alerts:** a per-fleet daily-spend alert and a dead-call alert. The
      fleetd `budget_day_usd` cap and the monthly OpenRouter alert exist.
- [ ] **GlitchTip's stale `prod` / `dgx-prod` environment rows** (cosmetic). check:
      `GET /api/0/organizations/homelab/environments/`.

## Fleets

Where each fleet stands: [fleet architecture → Rollout status](../fleet-architecture.md#rollout-status).

**Triage fleet (Fleet 2)**
- [ ] **Cleanup autonomy** (track A3): cleanup still waits for the operator.
- [ ] **Seeded-defect fixtures** — `signal-fleet/EVAL.md` calls them "still the thin spot".
- [ ] **Client-side corroboration probe** (Umami) for front-end signals.
- [ ] **Ground-truth labels for STAGING-2/3/4** (`signal-fleet/reference/glitchtip-ORRERY-STAGING-*.json`,
      `ground_truth.disposition` is null).
- [ ] **`muted-class` label** for bugs whose fingerprint keeps changing (guide, Known gaps).
- [ ] Delete the stale `~/signal-fleet/fleet.env` on the mini (fleetd loads `fleet-gateway.env`).

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

## Moving app pieces out (D-0014)

The infra session writes the plan in chipi/infra and moves nothing before its arc B. When infra
adopts a piece, delete homelab's copy in the same change (dashboards share uids).
- [ ] `infra/delivery/` (whole) → chipi/infra.
- [ ] `infra/observability/hosts/prod-podcast/` → adopted by chipi/infra, then deleted here.
- [ ] Podcast Player, Podcast Operator and Production Infra (host, containers, edge-security)
      dashboards → chipi/infra, an o11y folder.
- [ ] `infra/vllm/prod-vllm`, `translate`, `autoresearch` → chipi/infra, an ai folder.
- [ ] Product-only skills (corpus-migration, prod-batch-chain, prod-deploy, prod-job-progress,
      extraction-rebase, infra-preflight) → chipi/infra; `install.sh` has to keep linking them.

## X3 (operator picks the window; layout codified 2026-10-16)

- [ ] **Storage separation window** — move `/work`, `/var/lib/docker`,
      `/var/lib/containerd` into `@work`, `@docker`, `@containerd`
      ([ADR-0011](../adr/ADR-0011-workstation-storage-subvolumes.md)) with the
      [runbook](../recipes/x3-storage-separation.md). **Blocked until:** an emergency
      boot path is confirmed (B); the small encrypted off-machine backup of the
      Orrery and OceanCanvas `.env` variants and Orrery's local overrides exists and
      has been decrypted and compared (C); Orrery's live state (detached HEAD
      `41330dd`, the `/tmp/…/replay-baseline-main` worktree) is landed, preserved or
      stopped by its owner; tmux persistence is installed and loaded, its disposable
      restore test is green, and the final `wb-tmux save` + `verify` pass (runbook F, G).
- [ ] **Later, never automatic:** retire the `*.pre-subvol` safety copies with the
      [retirement procedure](../recipes/x3-storage-safety-copy-retirement.md), after
      its readiness checks and explicit approval.

## Maintenance (parallel, not urgent)

- [ ] **Dedup project AGENTS.md files** against the global one (genesis open thread #5):
      podcast_scraper (1,320 lines), orrery (994), chemigram, oceancanvas. Keep only
      project-specific content in each.
- [ ] **Decide a Python standard, then move the mini off 3.9.** Every Python script that runs on the
      mini's host uses macOS's system Python 3.9.6 (Xcode's, `/usr/bin/python3`): the triage
      fleet (fleetd's `python3 orchestrator.py`), hetzner-status, cloudflare-edge, ci-ops-poller,
      the backups, host-run's `.py` scripts. Python 3.9 has been end-of-life since October 2025.
      On 2026-10-30 it broke the dataset builder (3.9's `fromisoformat` rejects 9-digit fractions,
      21bc902). What the rest uses (checked 2026-10-30): podcast_scraper `.python-version`
      3.11.8, CI 3.11.8, containers 3.12, `requires-python >=3.10`; eval-harness 3.11
      everywhere; homelab's delivery container 3.11; DGX system 3.12.3; X3 3.14.7, plus
      3.11.16 via mise. There is **no written standard**: the projects mostly pin and test on
      3.11 while podcast_scraper's containers already run 3.12, and the machines' own Pythons
      (3.9 macOS, 3.12 Ubuntu, 3.14 Arch) are whatever their OS ships.
      **Operator decision first:** which version is the standard, as two numbers: the minimum
      code must support, and the one we run and test on. Candidates: 3.11 (most code tested on
      it today; end of support 2027-10), 3.12 (podcast containers and the DGX already; 2028-10),
      3.13+ (longer, but ML wheels may lag: not checked). Support dates are from memory, not
      verified against python.org. Homelab's suggestion: 3.12.
      Then: write it down (global AGENTS.md); install it on the mini (Homebrew or uv-managed; a
      shared-environment install, so the operator's go first); point the launchd plists,
      fleetd's `cycle_cmd` and host-run at it; run every gate on it before switching. Not checked: the prod box's host Python (prod's lane; its
      apps run in 3.12 containers).

## Deferred (intentional)

These were considered and explicitly NOT extracted, because the honest
reference lives elsewhere:

- **`examples/multi-provider-router/`** — provider abstraction shape.
  The honest reference is `podcast_scraper-FUTURE`'s `cloud_balanced` /
  `cloud_thin` / `cloud_with_dgx_*` provider classes, where the
  abstraction has been beaten on by real work. Genericizing it cleanly
  is more work than the derived value here.
- **Claude Code settings.json template** (`templates/claude-code/`) — 127K of
  operator-specific config (permissions, MCP allowlists, hook commands). Load-bearing
  pieces are documented in
  [`recipes/token-management-lean-ctx-rtk.md`](../recipes/token-management-lean-ctx-rtk.md)
  and [`recipes/chrome-devtools-mcp-agent-loop.md`](../recipes/chrome-devtools-mcp-agent-loop.md).
  Ship a minimum-viable extraction if one becomes viable.

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

## Done (paper trail)

Struck items, kept verbatim as they were written.

- [x] ~~`chmod 0600 /work/orrery/main/.env`~~ — *done; checked 2026-10-29: mode 600.*
- [x] ~~**Triage fleet GitHub token expires 2026-10-27 15:59 UTC**~~ Done 2026-10-27: it lapsed
      (401 on every repo) and the operator regenerated it. Now covers chipi/podcast_scraper, orrery,
      agentic-ai-homelab, humancopilot.eu and eval-harness (all 200, issues listable); **expires
      2027-01-25 19:03 UTC** (`github-authentication-token-expiration`). `filing.REPO_MAP` now
      routes `EVALS` → chipi/eval-harness and `HUMANCOPILOT` / `DEVWHATEVEROPS` → chipi/humancopilot.eu.
- [x] ~~Fill in `infra/observability/.env` with Grafana Cloud creds →
      `docker compose up -d` → verify in Grafana Cloud Explore.~~
      *Done 2026-06-12; all four dashboards (Node, DCGM, vLLM, cAdvisor)
      confirmed live. Recipe (historical, removed 2026-10-02): [observability-boot.md @ 613e465](https://github.com/chipi/agentic-ai-homelab/blob/613e465/docs/recipes/observability-boot.md).*
- [x] ~~Pin the Alloy / DCGM exporter / cAdvisor / ollama-metrics image
      tags after first successful boot (currently `:latest`).~~
      *Done — versions captured after the verified boot.*
- [x] ~~Symlink `infra/dgx/bin/gpu-mode-swap.sh` into `~/bin/` on the DGX
      and verify (`gpu-mode-swap.sh status`).~~ *Superseded:* `~/bin/gpu-mode-swap.sh`
      is a wrapper that runs the `ops` checkout's script as `ops`
      (`/home/ops/agentic-ai-homelab/infra/dgx/bin/gpu-mode-swap.sh`). Checked 2026-10-17.
- [x] ~~**Step 2:** desktop-software pruning per
      `mini-box-pruning.md` (closed 2026-10-29).~~ **Done 2026-08-30**,
      all 12 vendors, ~8.7G freed, health green throughout. Left behind:
      `org.cindori.AuthHelper` (identified as TRIM Enabler/Sensei helper —
      needs an explicit yes) and `~/Library/Application Support/Adobe`
      (1.1G personal Photoshop/Lightroom/DE data — operator call).
- [x] ~~**Skills: the operator's four decisions** from the
      skills usage review (closed 2026-10-29, history 0007)~~ — *all four done 2026-10-17*:
  1. ~~wire the `skill-nudge` hook~~ — *done 2026-10-17 on the laptop and omarchy*;
  2. ~~give `secrets-scan` a script and maybe a push hook~~ — *done a21d0d3; the push hook
     already existed (`secrets-guard.sh`), it now adds gitleaks*;
  3. ~~add an install-drift check to `index.py`~~ — *done 2026-10-17: `index.py --check-install`*;
  4. ~~shrink `homelab-endpoint`~~ — *done 2026-10-17, now a pointer at the handbook*.
  check: `python3 workstation/claude/skills/index.py --check-install` on each machine
- [x] ~~**podcast_scraper DGX converge, the real deploy.**~~ **Not needed (checked 2026-10-17):**
      the #1397 `/dev/shm` guard is already live. pyannote was redeployed on 2026-10-15 13:06 UTC.
      Its `/app/app.py` is byte-identical to podcast_scraper main (md5 `611aefc5…`), and its
      startup log says "sharing strategy: file_system (avoids /dev/shm)". `/dev/shm` holds 16K. The
      converge's other changes (faster-whisper/moss composes) are cosmetic, so it isn't worth a
      window on its own.
- [x] ~~**Decide Ollama:** retire or keep.~~ **Keep** (operator, 2026-10-17). Nothing to do:
      `ollama` mode starts Ollama and its `ollama-metrics` exporter; `prod` mode stops both.
- [x] ~~**Pin `librechat-api`.**~~ **Stays on `:latest`** (operator, 2026-10-17): LibreChat is
      being evaluated, so tracking the newest build is intended.
- [x] ~~*Optional:* align cadvisor v0.52.1 → v0.55.1.~~ **Done 2026-10-17** (77d327c), outside a
      window: a cadvisor recreate only gaps container metrics, so it doesn't interrupt serving.
      A throwaway v0.55.1 on `:18089` first gave identical named series. After the swap, DGX
      container samples reach VictoriaMetrics again (latest 8 s old).
- [x] ~~**2026-08-31+ (any day next week):** verify the docker-prune LaunchAgent
      self-fired Sunday 04:00 on the mini (installed + hand-verified 2026-08-30,
      but the calendar trigger itself has never fired).
      Check: `tail /tmp/docker-prune.log` on the mini shows a `=== docker-prune
      2026-08-31…` header, and the `docker-prune-stale` Grafana alert is still
      inactive. If the run is missing, the dead-man alert fires by ~2026-09-07
      anyway — but check before it has to.~~ **Verified 2026-09-30:** now a system
      LaunchDaemon (since 567bd21); `launchctl print` → `runs = 3`, `last exit code
      = 0` (three Sundays since 09-10); last log header `2026-09-27T02:00:04Z`.
- [x] ~~**After the prod_dgx_full run completes:** apply the widened cadvisor
      keep-list on the DGX. It's already in `infra/observability/config.alloy`
      (PSI, cpu_user/system, scrape_error, and the `container_memory_rss` fix)
      but deliberately NOT deployed — the box was mid-run and changing collection
      mid-measurement would muddy its own data. Deploy is a reload, not a restart:
      copy the file into the ops checkout's config path and
      `docker kill -s HUP alloy`, then confirm `container_pressure_io_waiting_seconds_total{instance="dgx-llm-1",name!=""}`
      returns series. PSI is directly relevant to #1886 co-tenancy.
      *Optional, low priority:* align the DGX cadvisor pin v0.52.1 → v0.55.1. It is
      NOT affected by the containerd-snapshotter bug (it uses overlay2 with a real
      layerdb), so this is consistency only — validate with a throwaway container
      on a spare port first, as the podcast agent did on prod.~~ **Found applied
      2026-09-30:** `count(container_pressure_io_waiting_seconds_total{instance="dgx-llm-1",name!=""})`
      → 12 series. The optional cadvisor v0.52.1 → v0.55.1 alignment was not checked.
- [x] ~~**2026-09-15+ (first data older than 30d):** verify the Langfuse 30-day
      caps actually delete. Set 2026-08-30; nothing was old enough to delete yet,
      so neither has been observed working end-to-end.
      (a) ClickHouse: `select toDate(min(timestamp)) from traces` should stop
      going further back than 30d. (b) MinIO: `mc ls lf/langfuse/events` oldest
      object <30d. Details + commands: [`infra/langfuse/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/langfuse/README.md).~~
      **Verified 2026-09-30 (ClickHouse):** oldest `traces` and `observations` are both
      2026-08-31 = today − 30 d; the worker logs `[Data Retention] Deleted ClickHouse
      and S3 data older than 30 days` daily at 03:15. **MinIO not verified:** listing
      `events/agents` inside `langfuse-minio-1` returned nothing, although the directory
      exists — use `mc ls` with credentials to confirm the oldest object.
- [x] ~~**~2026-09-27 (a month out):** colima datadisk regrowth check —
      `sudo du -sh /private/var/_dockerhost/.colima/_lima/_disks/colima/datadisk`
      on the mini. Was 23G after the 2026-08-30 trim (19G live data); if it's
      drifting far above ~30G, the weekly `fstrim -av` isn't holding and the
      job needs a look.~~ **Checked 2026-09-30 — the trim holds:** the 09-27 run
      trimmed 76 GiB and logged `datadisk allocated: 22G`. The file then regrew to 52G
      in three days of image churn, while the guest used 25G (`df` in the VM).
      Sawtooth: weekly growth, reclaimed each Sunday. Read the size *after* a Sunday
      run, not mid-week.
- [x] ~~**~2026-09-13:** check the two handed-off podcast_scraper issues moved:
      [#1877](https://github.com/chipi/podcast_scraper/issues/1877) (prod-ops-health
      cron → on-VPS systemd timer) and
      [#1879](https://github.com/chipi/podcast_scraper/issues/1879) (63 batched
      signal-fleet proposals, 18 families). If untouched, ping/reassign.
      **Overdue — checked 2026-09-30:** both OPEN, last updated 2026-08-30 (untouched
      for a month). Operator call: ping, reassign, or close.~~ **Resolved 2026-10-17:**
  - #1879 closed as dormant: none of its themes in the last 30 days of logs. Its 63 proposals
    are archived in `~/signal-fleet/queue/archive/1879-dormant-2026-10-17/`.
  - #1877 is still valid, and is handed to the prod session: the GitHub cron runs 4–7 h late,
    though every run succeeds.
- [x] ~~**Versioning scheme** decision.~~ **Decided 2026-06-13:** HEAD is
      the source of truth + README "Status" line carries the meaningful
      label. Drop lightweight `git tag`s at the moments
      `docs/history/<arc>.md` already marks as significant
      (`v0.1-genesis`, `v0.2-four-pillars-real`, …) — bookmarks, not
      releases. First tag lands once v0.1 is stable; not yet. Revisit if
      the repo gains external consumers who need pinning.
- [x] ~~**Trim the obsolete 9443 ACL grant** (PR #1662), superseded by the
      caddy-tailscale plugin. `docs/wip/mac-mini-headless-server.md:302`. Minor
      tailnet hygiene (unnecessary open-port grant).~~ **Done** (checked 2026-10-17): podcast_scraper
      `tailscale/policy.hujson` mentions :9443 only in a comment saying it was removed.
- [x] ~~**Land the uncommitted mini changes** (need push approval):
      `infra/reverse-proxy/` (Caddy stack, on mini + local, not committed) and the
      `infra/homelab-home/docker-compose.yml` tailnet-port edit.
      `docs/wip/mac-mini-headless-server.md:29-31`.~~ **Done** (checked 2026-10-17): the mini's
      checkout has no uncommitted files, and `infra/reverse-proxy/` is in the repo.
