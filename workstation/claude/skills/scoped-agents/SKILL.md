---
name: scoped-agents
description: Scaffold a per-folder AGENTS.md and wire it into the repo-root AGENTS.md scoped table. Use when adding folder-specific agent rules, splitting a monolithic root AGENTS.md into per-folder files, or when asked to create or scope an AGENTS.md for a subdirectory. Enforces that AGENTS.md is the source of truth and CLAUDE.md stays a thin @-import.
---

# scoped-agents

Create a folder-scoped `AGENTS.md` and register it in the repo-root `AGENTS.md`,
following the layering rules below. Use it to add new scoped rules, or to split
an overgrown root `AGENTS.md` into per-folder files.

## Load-bearing rules (do not violate)

- **`AGENTS.md` is the source of truth** — harness-agnostic, carries the real
  rules. `CLAUDE.md` is a THIN layer that `@AGENTS.md`-imports and adds only
  Claude-specific notes. Never invert this. If a repo has a fat `CLAUDE.md` and
  no `AGENTS.md`, fix that first (move the rules into `AGENTS.md`, reduce
  `CLAUDE.md` to the import + Claude-only notes).
- **Scoped files never duplicate the root or the global rules.** A folder
  `AGENTS.md` holds only what is specific to that folder. Repo-wide rules stay at
  the root; cross-repo operator rules stay in the global `~/.config/AGENTS.md`.
- **More-specific wins.** Precedence: direct chat > memory > deeper scoped
  (`a/b/AGENTS.md`) > shallower scoped (`a/AGENTS.md`) > root > global.

## Steps

1. **Confirm the pattern.** Repo root has `AGENTS.md`; if Claude Code is used,
   `CLAUDE.md` is thin and imports it (`@AGENTS.md`). Establish that before scoping.
2. **Create `<folder>/AGENTS.md`** from the template below — only rules that truly
   belong to that folder. If those rules currently live in the root, MOVE them
   (don't leave a duplicate).
3. **Register it** in the root `AGENTS.md` under `## Scoped AGENTS.md` (create the
   section + table if missing). One row: linked path + one-line scope.
4. **If splitting the root:** verify every moved rule lands in exactly one scoped
   file and the root still links to it. The root shrinks; nothing is lost. Grep
   for stale references to any rule you moved (e.g. "rule #N").
5. **Validate.** If the scoped file sits inside a docs tree built by mkdocs/etc.,
   make sure it doesn't publish as an orphan page (exclude it) — then run the
   `docs-preflight` skill.

## Template — `<folder>/AGENTS.md`

```markdown
# AGENTS.md — <folder>/ (scoped rules)

Loaded when working under `<folder>/`. Layers on top of the repo-root
[`AGENTS.md`](<relative-path-to-root>AGENTS.md); never duplicates or contradicts it.

<one sentence: what this folder is and what the rules here govern>

## <Rule heading>

<the folder-specific rule; include the WHY when it is non-obvious>
```

## Root registration — add under `## Scoped AGENTS.md`

```markdown
## Scoped AGENTS.md in this repo

Folder-specific rules live next to the code they govern. More-specific folder
wins (e.g. `a/b/` over `a/` over root).

| Path | Scope |
|---|---|
| [`<folder>/AGENTS.md`](<folder>/AGENTS.md) | <one-line scope> |
```
