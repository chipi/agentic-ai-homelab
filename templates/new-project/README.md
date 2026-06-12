# new-project template

A `cp -r`-able skeleton for new projects. Lifts the conventions from this
repo into a working starting point: docs site (MkDocs Material + GH
Pages), layered Makefile gates, project-local AGENTS.md, ADR/RFC/WIP/
history docs scaffolding, minimal CI + pre-commit baseline.

## Bootstrap a new project

```bash
cp -r templates/new-project/ ~/Projects/<new-name>/
cd ~/Projects/<new-name>

# Substitute placeholders in one pass:
find . -type f \( -name '*.md' -o -name '*.yml' -o -name 'Makefile' \) \
  -exec sed -i '' \
    -e 's|<project-name>|my-new-project|g' \
    -e 's|<owner>|your-gh-handle|g' \
    -e 's|<project-description>|One-line description here|g' {} \;

git init
git add .
git commit -m "v0.1 scaffold from agentic-ai-homelab/templates/new-project"
```

Then enable GH Pages: **Repo Settings → Pages → Source = "GitHub Actions"**.
Push to `main` and the `docs` workflow will publish at
`https://<owner>.github.io/<project-name>/`.

## What's in here

| Path | Purpose |
|------|---------|
| `AGENTS.md` | Project-local agent rules — layers on global, never duplicates |
| `Makefile` | Layered gates: `lint` / `test-unit` / `test-integration` / `ci-fast` / `ci` + `docs-*` |
| `mkdocs.yml` | MkDocs Material config (single hierarchical left nav) |
| `requirements-docs.txt` | `mkdocs-material` pin |
| `.gitignore` | Multi-language baseline including `site/` and `.env` |
| `.pre-commit-config.yaml` | Universal hooks + gitleaks secrets scan; language hooks commented |
| `.github/workflows/docs.yml` | Build (strict) + deploy to GH Pages |
| `.github/workflows/ci-fast.yml` | Skeleton calling `make ci-fast` — fill in language setup |
| `.github/PULL_REQUEST_TEMPLATE.md` | Summary / test plan / risk / reviewer notes |
| `docs/index.md` | Site landing page |
| `docs/adr/README.md` | ADR convention (Status / Context / Decision / Consequences / Alternatives) |
| `docs/rfc/README.md` | RFC convention (proposals not yet decided) |
| `docs/wip/README.md` | WIP convention (rolling plans, with promotion targets) |
| `docs/history/README.md` | Session continuity convention |

## First-week checklist

The skeleton is generic. Specialize it before the first real PR lands:

- [ ] Pick the language stack; fill `AGENTS.md` "Stack" table.
- [ ] Wire `format` / `lint` / `test-unit` / `test-integration` targets in
      the Makefile to real commands.
- [ ] Uncomment the matching language setup block in
      `.github/workflows/ci-fast.yml`.
- [ ] Uncomment matching language hooks in `.pre-commit-config.yaml`.
- [ ] Write `docs/history/0001-genesis.md` capturing project intent + the
      first session's decisions.
- [ ] Pick a `LICENSE`.
- [ ] If using `mkdocs-material` 9.x heavily: revisit pin when 10.x
      ships (currently `>=9.5,<10`).

## Verifying locally

```bash
make docs-serve       # → http://127.0.0.1:8765
make docs-build       # → strict build into ./site
make ci-fast          # will fail until atomic gates are wired (expected)
```

## Conventions inherited from this repo

See [`docs/project-setup.md`](../../docs/project-setup.md) in
agentic-ai-homelab for the narrative — what each piece is for, when to
deviate.
