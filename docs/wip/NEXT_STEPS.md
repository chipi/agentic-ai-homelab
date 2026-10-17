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
      confirmed live. Recipe (historical, removed 2026-10-02): [observability-boot.md @ 613e465](https://github.com/chipi/agentic-ai-homelab/blob/613e465/docs/recipes/observability-boot.md).*
- [x] ~~Pin the Alloy / DCGM exporter / cAdvisor / ollama-metrics image
      tags after first successful boot (currently `:latest`).~~
      *Done — versions captured after the verified boot.*
- [x] ~~Symlink `infra/dgx/bin/gpu-mode-swap.sh` into `~/bin/` on the DGX
      and verify (`gpu-mode-swap.sh status`).~~ *Superseded:* `~/bin/gpu-mode-swap.sh`
      is a wrapper that runs the `ops` checkout's script as `ops`
      (`/home/ops/agentic-ai-homelab/infra/dgx/bin/gpu-mode-swap.sh`). Checked 2026-10-17.
- [ ] Run `provider-bakeoff/` with your real API keys; pick a primary
      cloud provider for the next round of work. *(Sweep cost ~$2-5.)*

## Planned mini ops (operator picks the window; prep is DONE)

- [ ] **Window ~2026-08-30/31:** run the colima restart —
      [`colima-vcpu-8-to-4-runbook.md`](colima-vcpu-8-to-4-runbook.md):
      one `colima stop && start --cpu 4 --memory 12` (~2–5 min stack gap)
      + the same-window Spotlight disable (`mdutil -a -i off`, instant).
      **Still not done (checked 2026-09-30):** colima is at `cpu: 8`, `memory: 20`, and
      `mdutil -s /` → `Indexing enabled.` Needs an operator-chosen window.
- [x] ~~**Step 2:** desktop-software pruning per
      [`mini-box-pruning.md`](mini-box-pruning.md).~~ **Done 2026-08-30**,
      all 12 vendors, ~8.7G freed, health green throughout. Left behind:
      `org.cindori.AuthHelper` (identified as TRIM Enabler/Sensei helper —
      needs an explicit yes) and `~/Library/Application Support/Adobe`
      (1.1G personal Photoshop/Lightroom/DE data — operator call).
- [ ] **Hardware, someday:** install the +32G RAM the operator has at home
      (2018 mini → 64G total). Full shutdown + physical open; no config
      changes needed after (colima VM stays 12G — sized to guest usage).

- [ ] **Tailscale exit node on the mini** (NL egress for NL-only government
      sites while travelling) — runbook prepared, NOT executed:
      [`tailscale-exit-node-mini.md`](tailscale-exit-node-mini.md). Three steps:
      `--advertise-exit-node` on the mini, one manual approval in the admin
      console, and a one-rule ACL grant in **podcast_scraper**'s
      `tailscale/policy.hujson` (no `autogroup:internet` rule exists today —
      verified 0). **Known risk (corrected 2026-09-30):** the mini's tunnel is
      login-independent since 2026-09-10 (`tailscale-up` LaunchDaemon), so a
      reboot abroad is survivable — *unless* the exit-node flag is added without
      also restating it in `infra/tailscale/tailscale-up.sh`, in which case the
      boot-time `tailscale up` is refused and the mini stays off the tailnet.
      The runbook now does both in one step. The earlier "tunnel only lives while
      logged in" warning here was wrong.

- [ ] **Pin the mini's floating images** (found by `infra-drift`, 2026-10-17). Langfuse's
      `clickhouse-server` and `chainguard/minio` run with no tag, so a pull or recreate can
      change them silently. Pin each to its running digest, as Umami was (4cafb0c), and recreate
      in a window. The `litellm` "drift" (runs `main-stable`, compose pins `v1.96.2`) is
      cosmetic: the container reports 1.96.2, so its next recreate changes nothing.

- [ ] **Skills: the operator's four decisions** from the
      [skills usage review](skills-usage-review-2026-10-17.md):
  1. wire the `skill-nudge` hook — waits for the orrery session's commits on main;
  2. ~~give `secrets-scan` a script and maybe a push hook~~ — *done a21d0d3; the push hook
     already existed (`secrets-guard.sh`), it now adds gitleaks*;
  3. add an install-drift check to `index.py` — waits for the orrery `index.py` change;
  4. ~~shrink `homelab-endpoint`~~ — *done 2026-10-17, now a pointer at the handbook*.
  check: `git log origin/main --oneline | grep -i skill-nudge`

## Planned DGX ops (operator picks a maintenance window)

State on 2026-10-17, checked:
- The `ops` checkout (`/home/ops/agentic-ai-homelab`) is current with `origin/main` and clean.
  It had been 171 commits behind, with three files copied in by hand that matched
  `origin/main`. It was reset to `origin/main`, losing nothing.
- Every running container from that checkout uses the image its compose file names: no drift.
  The stacks are `infra/observability`, `infra/vllm/prod-vllm`, `infra/vllm/translate` and
  `infra/librechat`.
- Mode `prod`. Ollama is stopped and disabled. `ollama-metrics` is stopped, and the
  gpu-mode fix (312e9ba) stops it on later swaps.

**Rule from now on:** deploy to the DGX by pulling as `ops`, never by copying files in:
`sudo -u ops git -C /home/ops/agentic-ai-homelab pull --ff-only`. Copied files made the
checkout look dirty and hid how far behind it was.

**In the window** (each step interrupts serving or a GPU job, so it waits for the operator):

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
- [ ] **After any recreate, verify:**
  - the `dgx-status` skill;
  - `~/bin/gpu-mode-swap.sh --mode-only` → `prod`;
  - the `obs-boot` check (DGX metric freshness);
  - one podcast pipeline call through the gateway (`proj-podcast-dev`, the DGX model).

## Planned X3 ops (operator picks the window; layout codified 2026-10-16)

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
- [ ] Separately: `chmod 0600 /work/orrery/main/.env` (secret-bearing, mode 0644
      on 2026-10-16).
- [ ] **Later, never automatic:** retire the `*.pre-subvol` safety copies with the
      [retirement procedure](../recipes/x3-storage-safety-copy-retirement.md), after
      its readiness checks (normal development, Docker use, a full Workbench stream
      lifecycle and a reboot on the new layout) and explicit approval.

## Dated checks (open on/after the date — we WILL forget otherwise)

- [ ] **Monthly from 2026-11-01:** upgrade lima on the mini once
      [lima-vm/lima#5420](https://github.com/lima-vm/lima/issues/5420) ships —
      keepalives on the SSH ControlMaster plus a loop that re-creates forwards
      when the master breaks (operator approved the upgrade 2026-10-09). As of
      2026-10-09 the issue is open with no merged PR; the mini runs lima 2.2.0,
      latest is v2.2.1 / v2.3.0-beta.1. Check: `gh api repos/lima-vm/lima/issues/5420
      --jq .state` and the release notes. Caveat: #5420 covers a DEAD master; our
      2026-10-08 break was a WEDGED one, so confirm the fix also detects that
      before calling the forward-break class closed. Runbook:
      [colima/lima forwarding recovery](../recipes/colima-lima-forwarding-recovery.md).

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
## Active subprojects

- [ ] **Agentic coding fleet** — multi-agent setup across opencode + Pi,
      OpenRouter cloud gateway with hard model-locks, FastContext-4B as
      local recon. Tracking + progress in
      [`agentic-coding-fleet/README.md`](agentic-coding-fleet/README.md).
      Eventual graduation target: new `docs/agentic-coding/` section.
      Phase 0 (OpenRouter keys) is on the operator; Phase 1+ is the
      harness wiring.

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
- [x] ~~**Trim the obsolete 9443 ACL grant** (PR #1662), superseded by the
      caddy-tailscale plugin. `docs/wip/mac-mini-headless-server.md:302`. Minor
      tailnet hygiene (unnecessary open-port grant).~~ **Done** (checked 2026-10-17): podcast_scraper
      `tailscale/policy.hujson` mentions :9443 only in a comment saying it was removed.
- [x] ~~**Land the uncommitted mini changes** (need push approval):
      `infra/reverse-proxy/` (Caddy stack, on mini + local, not committed) and the
      `infra/homelab-home/docker-compose.yml` tailnet-port edit.
      `docs/wip/mac-mini-headless-server.md:29-31`.~~ **Done** (checked 2026-10-17): the mini's
      checkout has no uncommitted files, and `infra/reverse-proxy/` is in the repo.
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
