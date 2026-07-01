# 0004 — agent-config + skills arc

**Date:** 2026-07-01 (single session)
**Operator:** Marko (chipi)
**Agent:** Claude Opus 4.8 (1M ctx), via Claude Code
**Outcome:** Root + per-folder `AGENTS.md` split landed (ADR-0002); a
`workstation/` restore backup added; and the operator's first 10 authored skills
built, tested, and mirrored into the backup.

> Sibling to [`0003-v0.2-arc.md`](0003-v0.2-arc.md). Future session opening this
> repo cold: read this + the "Open threads" below before resuming the AGENTS.md
> rollout to sibling repos.

Operator opened pointing at the paused agent-config restructure (Step 3 of a
multi-repo initiative). The session moved through three connected pieces.

## What landed

- **Per-folder `AGENTS.md` split** ([ADR-0002](../adr/ADR-0002-agents-md-per-folder-split.md)).
  Root trimmed 92→55 lines to repo-wide-only; new `docs/AGENTS.md`,
  `infra/AGENTS.md`, `infra/vllm/AGENTS.md`; `exclude_docs: AGENTS.md` so scoped
  rules don't publish to the site.
- **`workstation/`** — the repo now doubles as the restore source for global agent
  config (dotfiles pattern; home symlinks into the repo via `install.sh`).
  Sanitized `*.example` templates for secret-bearing config; a repo-root master
  `.env.example`; a `setup-new-computer.md` guide. Live-home symlinking (Phase 2)
  is deferred.
- **10 operator-authored skills** (all global, all mirrored into
  `workstation/claude/skills/`): `docs-preflight`, `compose-check`,
  `scoped-agents`, `gpu-mode`, `dgx-status`, `homelab-endpoint`, `vllm-deploy`,
  `obs-boot`, `new-doc`, `close-arc`. Read-only skills tested live (docs build,
  compose validation, DGX over ssh); mutating skills keep their state-changing
  steps gated on explicit approval.

## Decisions

- `permissions.defaultMode` must be `auto` — `delegate` prevents Claude Code
  from starting (see D-log).
- The repo is the source of truth for global config; home symlinks in, secrets
  never tracked (sanitized templates + gitignore guard).
- Skill safety pattern: read-only by default; mutating steps gated per-invocation.
  The DGX is treated as production (active work runs there).

## Open threads

- Push `agentic-setup` (nothing pushed this session — operator gates pushes).
- Phase 2: run `workstation/install.sh` to symlink live `~` config.
- Replicate the per-folder split to orrery (871 lines) + podcast_scraper (802).
- `.env` location inconsistency (3 stacks local, 2 repo-root) and the rtk vs
  lean-ctx Bash-hook overlap.
- Later-tier skills shipped; next candidates emerge from the rollout.
