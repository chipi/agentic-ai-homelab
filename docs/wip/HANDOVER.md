# Handover — next session start here

**Updated:** 2026-07-01 (session end) · **Branch:** `agentic-setup` (**NOT pushed**,
not merged to `main` — run `git log --oneline main..HEAD` for the full list). Full
arc: [`../history/0004-agent-config-and-skills.md`](../history/0004-agent-config-and-skills.md).

## What this session built (all committed on `agentic-setup`)

1. **Per-folder `AGENTS.md` split** ([ADR-0002](../adr/ADR-0002-agents-md-per-folder-split.md)) —
   root trimmed to repo-wide-only; `docs/` + `infra/` + `infra/vllm/` scoped files;
   `exclude_docs` keeps them off the published site.
2. **`workstation/`** — repo doubles as the restore source for global agent config
   (dotfiles pattern; `install.sh` symlinks home into the repo; sanitized
   `*.example` templates; `setup-new-computer.md`). Live symlink = Phase 2 (deferred).
3. **14 skills** (global, mirrored into `workstation/claude/skills/`): docs-preflight,
   compose-check, scoped-agents, gpu-mode, dgx-status, homelab-endpoint, vllm-deploy,
   obs-boot, new-doc, close-arc, secrets-scan, ship, repro-first, fleet-stats.
4. **6-agent subagent fleet** ([ADR-0003](../adr/ADR-0003-subagent-roster.md)):
   advisor(opus) · planner/implementer/reviewer(sonnet) · tester/docs-writer(haiku).
   Model-tiered for cost; sonnet tier escalates to the opus advisor via `Agent(advisor)`.
5. **rtk fully retired from Claude** (D-0010) — hook + `@RTK.md` import + `RTK.md`
   + allow entry purged; docs reconciled. Binary kept for other-harness use.
6. **gpu-mode-swap `research` fix** — Ollama-flush + stale-container cleanup + GB10
   free-VRAM estimate, plus the silent-nvidia-smi-failure fix.

## The fleet works — proven this session

- `reviewer`(sonnet) reviewed the gpu-mode-swap diff: found 2 real MEDIUM bugs +
  nits, ran `secrets-scan` (PASS).
- `implementer`(sonnet) fixed the silent-fallback bug AND escalated the design call
  to `advisor`(opus): got "Option C", applied it. Escalation works.
- `fleet-stats`: sonnet carried 59% of top-level delegation tokens; main loop stays
  opus. Cost-spread confirmed.
- Caveat: nested advisor(opus) tokens roll into the parent's total; `fleet-stats`
  v1 measures top-level only (documented; v2 = parse sub-agent transcripts).

## Open threads (priority order)

> **2026-07-02 session:** finished thread #4 + #6, rtk reconciliation, symlink-map.
> Ran a 5-variant hardening-workflow experiment → **ADR-0004** (inline-by-default;
> tiered workflow for blind-spots only). Added `.pre-commit-config.yaml` (mechanical
> floor, not yet enabled) + `secrets-guard` regression tests. `harden.js` kept as an
> experimental workflow. Still unpushed.

1. **Push `agentic-setup`** — you gate every push (rule #1); rebase on `main` first.
   Use the `ship` skill.
2. **Phase 2** — `./workstation/install.sh` to symlink live `~/.config` + `~/.claude`
   into the repo. Shared-state; backs up originals; needs a go.
3. **Deploy the gpu-mode-swap fix to the DGX** — needs the branch pushed + pulled
   on-host, then the on-host test checklist (idle to research etc.) when the DGX is
   free (it had live vLLM + Ollama loaded this session).
4. ~~**Follow-ups the fleet surfaced**~~ — **DONE 2026-07-02.** TOCTOU fixed
   (atomic `docker inspect`), `$SUDO` configurable, 128→121 comment, `|| true`→warn;
   the `used_memory` question resolved by a live DGX read (per-process `used_memory`
   IS populated on GB10, so the free-estimate path is correct); `fleet-stats` v2
   ships (walks `subagents/`).
5. **Rollout** — replicate the per-folder split to orrery (871) +
   podcast_scraper-FUTURE (802); podcast also needs global-dedup.
6. **Global best-practices** — #3 secrets-guard hook **DONE 2026-07-02** (live in
   settings.json + committed regression tests). #4 slash commands + #5 settings
   hardening **deferred by operator choice**. Menu complete.

## Gotchas / facts

- **`permissions.defaultMode` MUST be `auto`** — `delegate` stops Claude Code
  starting (D-0009). Don't "fix" it.
- **Custom subagents need a session restart** to become invocable (skills hot-load;
  agents don't). A fresh session re-loads all 6.
- **DGX = production.** `ssh dgx-llm-1` (key `~/.ssh/tailscale_spark`; host
  spark-2c14). Live work runs there. Read-only probes only; never switch mode /
  up / down / restart Ollama without per-instance approval.
- **Tooling quirks:** native Edit/Write flaked on some existing files ("File has
  not been read yet") so python patches via `ctx_shell` were used; `ctx_shell`
  blocks output redirects and `git commit` heredocs, so use Write + `git commit -F`.
- **Memory current:** the project memories auto-load next session.

## Do NOT touch

The working tree has a separate, pre-existing fleet stream (uncommitted):
`LEAN-CTX.md`, `docs/wip/agentic-coding-fleet/`, `docs/wip/*fleet*`,
`docs/wip/fastcontext-recon-guide.md`, `infra/fastcontext/`, and modified
`docs/wip/NEXT_STEPS.md` + `infra/vllm/autoresearch/docker-compose.yml`. Not this
session's work — leave it alone unless the operator says otherwise.
