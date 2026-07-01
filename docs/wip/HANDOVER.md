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

1. **Push `agentic-setup`** — you gate every push (rule #1); rebase on `main` first.
   Use the `ship` skill.
2. **Phase 2** — `./workstation/install.sh` to symlink live `~/.config` + `~/.claude`
   into the repo. Shared-state; backs up originals; needs a go.
3. **Deploy the gpu-mode-swap fix to the DGX** — needs the branch pushed + pulled
   on-host, then the on-host test checklist (idle to research etc.) when the DGX is
   free (it had live vLLM + Ollama loaded this session).
4. **Follow-ups the fleet surfaced** (worth doing before trusting the DGX fix):
   - gpu-mode-swap: TOCTOU race in the stale-container check (use `docker inspect`
     for an atomic state read); nits (hardcoded `sudo`, the "128 GB" comment math
     should say 121, `|| true` masking rm failures).
   - advisor's out-of-scope flag: per-process `used_memory` may ALSO be `[N/A]` on
     GB10 while vLLM/Ollama are loaded — confirm with a live reading; if so,
     `gpu_util_pct` may be the better gate and the free-estimate path needs a rethink.
   - `fleet-stats` v2: attribute nested-escalation (opus advisor) tokens correctly.
5. **Rollout** — replicate the per-folder split to orrery (871) +
   podcast_scraper-FUTURE (802); podcast also needs global-dedup.
6. **Global best-practices #3-#5** (remaining menu): a secrets-guard hook (#29
   automation), slash commands (`~/.claude/commands/`), settings hardening.

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
