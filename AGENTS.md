# AGENTS.md — agentic-ai-homelab (repo-scoped)

Loaded by opencode / Claude Code at this repo's root. **Layers on top of
the operator-global file** (`~/.config/opencode/AGENTS.md`; canonical
copy lives at [`templates/opencode/AGENTS.md`](templates/opencode/AGENTS.md)).
This file never duplicates and never contradicts the global — it
captures conventions specific to working *in this repo*.

## Repo conventions

1. **Run docker composes from the repo in place.** No copy-out to
   `~/docker-compose/...`. Every operator deploy reads the repo-root
   `.env` directly (per commit `fa24a27`). Recipes that still tell you
   to copy out are stale — fix the doc when you hit it, don't leave a
   TODO.

2. **Run operator scripts from the repo too — symlink, don't copy.**
   `~/bin/foo` is a symlink into `infra/dgx/bin/foo.sh`, so `git pull`
   ships updates without re-installing. Co-located README next to each
   script carries the agent-invocation contract.

3. **`.env` belongs in `.gitignore`, never in git.** Always. Reasserted
   here because this repo has many compose stacks and the temptation to
   commit "just the example values" comes up regularly.

4. **mkdocs strict is the CI gate — check before every commit that
   touches docs.** If your change touches any of `docs/**`,
   `mkdocs.yml`, `requirements-docs.txt`, or `Makefile`, run
   `make docs-build` locally and confirm green BEFORE the commit. CI
   runs the same `--strict` build; failing locally first costs ~20s,
   failing in CI costs a wasted push + red badge. When linking from
   inside `docs/` to a file outside `docs/` (e.g. `infra/...`, root
   `README.md`, scripts), use absolute
   `https://github.com/chipi/agentic-ai-homelab/blob/main/...` URLs —
   mkdocs strict can't resolve relative paths outside its tree.
   Convention pre-dates this rule:
   `infra/observability/README.md` already uses the github-blob form.

5. **Doc-vs-code divergence is a recurring failure mode in this repo.**
   Recipes drift behind reality (paths, commands, defaults). When you
   spot it: fix the doc inline. Pattern from this session: stale
   `~/docker-compose/...` paths surviving the run-from-repo migration.
   See global rule #28.

6. **DGX work has scoped rules.** Working in `infra/dgx/` or invoking a
   local vLLM? Read [`infra/dgx/AGENTS.md`](infra/dgx/AGENTS.md) —
   specifically: verify GPU mode before pointing a tool at
   `http://<dgx>:9000/v1` (`~/bin/gpu-mode-swap.sh --mode-only`).

7. **`docs/wip/NEXT_STEPS.md` is the live punch list.** Strike items
   inline when done (`- [x] ~~text~~ — *done note (date)*`); don't
   silently delete them — the strikethrough is the paper trail.

8. **`docs/history/<N>-<arc>.md` carries multi-session continuity.**
   When closing an arc, write a new history entry. Versioning: HEAD is
   source of truth; lightweight `git tag v<X>-<arc-name>` lands at the
   commit that closes each history doc (deferred until v0.1 stabilizes
   — see [NEXT_STEPS](docs/wip/NEXT_STEPS.md)).

## Scoped AGENTS.md in this repo

| Path | Scope |
|---|---|
| [`infra/dgx/AGENTS.md`](infra/dgx/AGENTS.md) | DGX-host work, GPU mode coordination |
| [`provider-bakeoff/AGENTS.md`](provider-bakeoff/AGENTS.md) | provider-bakeoff sub-project |

Templates (not active rules — copy-out artifacts):
- `templates/new-project/AGENTS.md` — bootstrap for fresh project repos
- `templates/opencode/AGENTS.md` — canonical operator-global, drops
  into `~/.config/opencode/`

## What overrides this file

Per the operator-global's "What overrides this file" section: direct
chat instruction > persistent memory > scoped AGENTS.md > this file >
operator-global. When in doubt, the more-specific layer wins.
