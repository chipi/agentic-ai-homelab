# Pillar 1 — Project setup

How I scaffold a new project so an agent (and future-me) can be productive
in it immediately.

> **Status: v0.2.** The `templates/new-project/` skeleton is real and
> bootstrap-able. The Makefile's atomic gates (`lint`, `test-*`) are
> language-neutral placeholders by design — fill them in once the stack
> is picked.

## The bootstrap

```bash
cp -r templates/new-project/ ~/Projects/<new-name>/
cd ~/Projects/<new-name>

find . -type f \( -name '*.md' -o -name '*.yml' -o -name 'Makefile' \) \
  -exec sed -i '' \
    -e 's|<project-name>|my-new-project|g' \
    -e 's|<owner>|your-gh-handle|g' \
    -e 's|<project-description>|One-line description|g' {} \;

git init && git add . && git commit -m "v0.1 scaffold"
```

Then enable GH Pages in repo settings → push → site auto-publishes.

The `templates/new-project/README.md` is the canonical reference for
*what files exist and what they do*. This page covers the *why* and
*when to deviate*.

## What each piece is for

### `AGENTS.md` (project-local)

Layers on top of the global `~/.config/opencode/AGENTS.md`. **Never
duplicate, never contradict.** The template's `AGENTS.md` is a skeleton
with placeholders for:

- **Project overview** — 1 paragraph
- **Stack table** — language / framework / CI / docs / secrets / deploy
- **Project-specific rules** — only what doesn't belong globally
- **Domain knowledge** — what an agent can't infer from the code
- **Named ADR anchors** — high-leverage ADRs to read first

Delete the placeholders as you fill them in. Rotting placeholders are
worse than missing sections.

### `Makefile`

Layered tier pattern, ~75 lines, three groups:

1. **Atomic gates** — `format`, `lint`, `test-unit`, `test-integration`.
   Language-specific. Stub `@false` by default so an unwired target
   surfaces as a failure, not silent success.
2. **Composite tiers** — `ci-fast` (every push) = `lint + test-unit`;
   `ci` (every merge) = `ci-fast + test-integration + docs-build`.
3. **Docs targets** — `docs-install`, `docs-serve`, `docs-build`,
   `docs-validate`, `docs-clean`. Self-contained venv at `.venv/`.

Convention: every target's last line should be unambiguous PASS/FAIL.
Composite tiers print `<tier> PASS` on success. The global AGENTS.md #17
codifies invoking via `make <target>; echo "MAKE_EXIT=$?"` for unattended
runs.

### `mkdocs.yml` + `requirements-docs.txt`

MkDocs Material with a single hierarchical left nav (no top tabs, no
section-headers — see [memory: feedback-mkdocs-nav]).

Dependency surface intentionally tiny: just `mkdocs-material>=9.5,<10`.
Material brings in `mkdocs` core + `pymdown-extensions`. Adding plugins
should pass through ADR-light review (per global AGENTS.md #12).

### `.github/workflows/`

- `docs.yml` — push-to-main + PR-strict-build + manual dispatch. Modern
  Pages deploy (configure-pages → upload-pages-artifact → deploy-pages).
  PR runs build only — no deploy.
- `ci-fast.yml` — language-neutral skeleton. The actual gates live in
  `make ci-fast`; this workflow is just "set up language, then call
  make". Pick a setup block (Python/Node/Go) and delete the others.

### `.github/PULL_REQUEST_TEMPLATE.md`

Four sections: **Summary** (why, not what), **Test plan** (mark what you
*did*, not what you'd ideally do), **Risk / rollback** (for non-trivial
changes — under-5-min undo is the bar), **Notes for reviewer** (optional).

### `.pre-commit-config.yaml`

Universal hooks always on:
- whitespace / EOF / line endings
- YAML / JSON / TOML syntax
- merge-conflict markers
- large-file guard (500KB)
- **`gitleaks`** — accidental secret commit catcher (global AGENTS.md #29)

Language hooks (ruff, prettier, gofmt) commented in — uncomment after
stack pick.

### `docs/{adr,rfc,wip,history}/README.md`

Same conventions as this repo. ADRs for structural decisions, RFCs for
proposals under review, WIP for rolling plans with promotion targets,
history for session continuity. See each README for format.

## When to deviate from the template

- **Doc-only repo** — skip `ci-fast.yml` and the `test-*` Makefile
  targets; keep `docs.yml`.
- **Library, not application** — `test-integration` may not exist; let
  the `ci` composite drop it.
- **Mono-repo** — the template assumes a single root. Multi-package
  layouts need a layered Makefile per-package + a top-level orchestrator.
  Worth a new ADR if you hit this.
- **No public docs** — set the GH Pages source to "Disabled" instead of
  "GitHub Actions"; the workflow will still build (catches broken refs)
  but won't deploy.

## Open in v0.2 → v0.3

See [`wip/NEXT_STEPS.md`](wip/NEXT_STEPS.md). Active items relevant to
this pillar:

- Dedupe existing project AGENTS.md files (podcast_scraper / orrery /
  chemigram / oceancanvas) against the new global.
- Eventually distill podcast_scraper's actual 3586L Makefile into the
  template's atomic-gate stubs (currently `@false` placeholders).

## Inspirations

- **podcast_scraper** `Makefile` — layered targets, exit-code reporting.
- **orrery** `AGENTS.md` — stack table pattern locking decisions to ADRs.
- **chemigram** `AGENTS.md` — three foundational disciplines pattern.
- **oceancanvas** `AGENTS.md` — constraint-honoring doctrine.
