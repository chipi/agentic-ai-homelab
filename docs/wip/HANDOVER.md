# Handover — next session start here

**Written:** 2026-07-01 · **Branch:** `agentic-setup` (9 commits, **NOT pushed**,
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

## Open threads — next actions (priority order)

1. **[requested, NOT done] `.env` location reconciliation.** `infra/AGENTS.md`
   over-generalizes "reads the repo-root `.env`". Reality: `coder-next` +
   `openwebui` read repo-root `.env`; `autoresearch`, `observability`, `template`
   have stack-local `.env`. Fix the doc to describe per-stack (it may be
   intentional — obs has Grafana creds, autoresearch has tuning).
2. **[requested, NOT done] rtk vs lean-ctx Bash-hook overlap.** Both
   `rtk hook claude` and `lean-ctx hook rewrite` fire on `PreToolUse` for Bash
   (see `~/.claude/settings.json`). Investigate whether they double-rewrite or
   compose; decide keep/disable/reorder. Global settings = shared-state → operator
   approval before changing; update `workstation/claude/settings.json.example` too.
3. **Push `agentic-setup`** — operator gates every push (rule #1). Rebase on
   `main` first.
4. **Phase 2** — run `./workstation/install.sh` to symlink live `~/.config` +
   `~/.claude` into the repo. Shared-state; backs up originals; needs a go.
5. **Rollout** — replicate the per-folder split to orrery (871 lines) +
   podcast_scraper-FUTURE (802); podcast also needs global-dedup.

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
