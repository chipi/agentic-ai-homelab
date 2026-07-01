---
name: docs-preflight
description: Validate that the docs site builds cleanly in strict mode before committing or pushing docs changes. Detects the project's docs toolchain (Makefile docs target, MkDocs, Sphinx, Docusaurus, mdBook) and runs its strict build, then reports PASS/FAIL with the exact unresolved refs or warnings. Use when about to commit or push changes under docs/, mkdocs.yml, or docs config, or whenever asked to check or validate the docs build.
---

# docs-preflight

Run the project's **strict** docs build locally and report green/red *before* a
docs commit lands. Strict mode is what CI runs — catching a broken cross-
reference here costs ~20s; catching it in CI costs a wasted push and a red badge.

## When this applies

The change touches any docs-affecting path: `docs/**`, `mkdocs.yml`,
`requirements-docs.txt`, a `Makefile` docs target, `conf.py`,
`docusaurus.config.*`, `book.toml`. If in doubt and a docs toolchain exists, run
it — it's cheap.

## Detect the toolchain, then run its strict build

Use the **first** match, top to bottom. A repo's own `make` target is preferred
because it already encodes the venv and the correct strict flags.

1. **Makefile docs target** — `grep -E '^docs-build:|^docs:' Makefile`.
   If present, run `make docs-build` (or `make docs`). This is the common case
   for repos scaffolded from the operator's `new-project` template.
2. **MkDocs** — `mkdocs.yml` at repo root. Prefer the project venv:
   - `.venv/bin/mkdocs build --strict --clean` if `.venv/bin/mkdocs` exists
   - else `python -m mkdocs build --strict --clean`
3. **Sphinx** — `docs/conf.py`. `sphinx-build -W -b html docs /tmp/_docs_preflight`
   (`-W` promotes warnings to errors = strict).
4. **Docusaurus / npm** — `package.json` with a docs build script
   (`docs:build`, `build:docs`, or a `docs` workspace). Run that script;
   Docusaurus fails on broken links by default.
5. **mdBook** — `book.toml`. `mdbook build`.

If none match, say so — there is nothing to preflight. Do not invent a build.

## Report

- Run in the **foreground** and show full output (do not `| tail`), so streaming
  warnings are visible.
- End with one unambiguous line: `DOCS PREFLIGHT: PASS` or `DOCS PREFLIGHT: FAIL`.
- On FAIL, surface the specific offenders — unresolved links, pages missing from
  nav, orphan warnings — not just the exit code.

## Conventions this enforces

- **Green local, then commit.** Never push-and-pray on the docs build; reproduce
  and fix locally first.
- **No new deps** to make a build pass. Use the project's existing toolchain and
  venv. If a dependency is genuinely missing, report it — do not install silently.
- When linking from inside a docs tree to a file *outside* it, strict builders
  can't resolve relative paths — use absolute repo URLs
  (`https://github.com/<org>/<repo>/blob/main/...`).
