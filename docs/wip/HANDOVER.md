# Handover — next session start here

**Written:** 2026-07-01 · **Branch:** `agentic-setup` (15 commits, **NOT pushed**,
not merged to `main`). Full arc: [`../history/0004-agent-config-and-skills.md`](../history/0004-agent-config-and-skills.md).

## Where we are

Three connected pieces landed this session, all committed on `agentic-setup`:

1. **Per-folder `AGENTS.md` split** ([ADR-0002](../adr/ADR-0002-agents-md-per-folder-split.md)) —
   root trimmed to repo-wide-only; new `docs/`, `infra/`, `infra/vllm/` scoped
   files; `exclude_docs: AGENTS.md` keeps them off the published site.
2. **`workstation/`** — repo is now the restore source for global agent config
   (dotfiles pattern; `install.sh` symlinks home into the repo; sanitized
   `*.example` templates; `setup-new-computer.md`). Live symlinking is Phase 2
   (deferred).
3. **10 authored skills** (all global in `~/.claude/skills/`, all mirrored into
   `workstation/claude/skills/`): `docs-preflight`, `compose-check`,
   `scoped-agents`, `gpu-mode`, `dgx-status`, `homelab-endpoint`, `vllm-deploy`,
   `obs-boot`, `new-doc`, `close-arc`. Read-only ones tested live; mutating ones
   gate their state-changing steps.
4. **Config hygiene** — per-stack `.env` documented (`infra/AGENTS.md`); rtk
   fully retired from the Claude path (hook + `@RTK.md` import + `RTK.md` +
   allow entry purged; docs reconciled; `D-0010`). rtk binary kept for
   other-harness use.

## Open threads — next actions (priority order)

*Both original top items are DONE (2026-07-01):* `.env`-location reconciled in
`infra/AGENTS.md`; rtk retired from the Claude path (`D-0010`). Remaining:

0. **Activate + prove the subagent fleet.** The 6 agents (ADR-0003) are built
   + committed but need a **session restart** to become invocable (skills
   hot-load; agents don't). After restart: run a fleet task (e.g. `reviewer`
   on a diff → escalates to `advisor`), then run the `fleet-stats` skill to
   see per-agent token/cost spread by model tier — validates the cost model.
1. **Push `agentic-setup`** — operator gates every push (rule #1); rebase on
   `main` first (now ~22 commits).
2. **Phase 2** — `./workstation/install.sh` to symlink live `~/.config` +
   `~/.claude` into the repo. Shared-state; backs up originals; needs a go.
3. **Rollout** — replicate the per-folder split to orrery (871) +
   podcast_scraper-FUTURE (802); podcast also needs global-dedup.
4. **Global best-practices** (before project-specific) — custom subagents /
   commands / rule-enforcing skills; see the next-opportunities discussion.

## Gotchas / facts for next session

- **`permissions.defaultMode` MUST be `auto`** — `delegate` stops Claude Code
  from starting (D-0009). Don't "fix" it.
- **DGX access:** `ssh dgx-llm-1` (key `~/.ssh/tailscale_spark`; host = spark-2c14).
  **Treat as production** — LibreChat + observability + speech-ML + a python GPU
  process run there (mode `idle` but `gpu_compute_app_count=1`). Read-only probes
  only; never switch mode / up / down without per-instance approval.
- **Tooling quirks seen this session:** native Edit/Write flaked on some existing
  files ("File has not been read yet") → used python patches via `ctx_shell`;
  `ctx_shell` blocks `>`/`>>` redirects and `git commit` heredocs → use the Write
  tool + `git commit -F <tmpfile>`.
- **Memory is current:** `project-agent-config-restructure`,
  `project-custom-skills`, `project-workstation-config-backup` all updated —
  they auto-load next session.

## Do NOT touch

The working tree has a **separate, pre-existing fleet stream** (uncommitted):
`LEAN-CTX.md`, `docs/wip/agentic-coding-fleet/`, `docs/wip/*fleet*`,
`docs/wip/fastcontext-recon-guide.md`, `infra/fastcontext/`, and modified
`docs/wip/NEXT_STEPS.md` + `infra/vllm/autoresearch/docker-compose.yml`. Not part
of this session's work — leave it alone unless the operator says otherwise.
