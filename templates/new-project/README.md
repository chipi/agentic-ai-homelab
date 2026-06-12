# new-project template

> **Status: v0.1 placeholder.** Content lands in v0.2 per
> `docs/wip/NEXT_STEPS.md`. See `docs/project-setup.md` for the full
> target state of this template.

## Target use

```bash
cp -r templates/new-project/ ~/Projects/<new-name>/
cd ~/Projects/<new-name>
git init
$EDITOR AGENTS.md   # add project-specific rules; delete the placeholders
```

## What will be here (v0.2)

- `AGENTS.md` — project-local skeleton. Inherits universal rules from the
  global; project file keeps only project-specific content (stack table,
  named ADR anchors, domain rules).
- `Makefile` — layered gate skeleton (`test-unit` / `test-integration` /
  `ci-fast` / `ci`).
- `.github/workflows/ci-fast.yml` — CI mirroring `make ci-fast`.
- `.github/PULL_REQUEST_TEMPLATE.md` — borrowed from podcast_scraper,
  sanitized.
- `.pre-commit-config.yaml` — minimal baseline (formatters, linters,
  secrets scanner).
- `docs/adr/README.md` — ADR convention (same as this repo's).
- `docs/rfc/README.md` — RFC convention.
- `docs/wip/README.md` — WIP convention.
- `docs/history/README.md` — session continuity convention.
- `.gitignore` — language-appropriate baseline.

## Today (until v0.2)

This dir is intentionally empty. Use `docs/project-setup.md` as the
reference for what each piece would look like.
