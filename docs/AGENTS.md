# AGENTS.md — docs/ (scoped rules)

Loaded when working under `docs/`. Layers on top of the repo-root
[`AGENTS.md`](../AGENTS.md); never duplicates or contradicts it.

`docs/` is the MkDocs source tree published to GitHub Pages. These rules
keep that build green and the docs honest.

## mkdocs `--strict` is the CI gate — validate before every doc commit

If your change touches any of `docs/**`, `mkdocs.yml`,
`requirements-docs.txt`, or `Makefile`, run `make docs-build` locally and
confirm green BEFORE the commit. CI runs the same `--strict` build;
failing locally first costs ~20s, failing in CI costs a wasted push + red
badge.

When linking from inside `docs/` to a file *outside* `docs/` (e.g.
`infra/...`, root `README.md`, scripts), use absolute
`https://github.com/chipi/agentic-ai-homelab/blob/main/...` URLs — mkdocs
strict can't resolve relative paths outside its tree. Convention
pre-dates this rule: `infra/observability/README.md` already uses the
github-blob form.

The `nav:` in `mkdocs.yml` is explicit. A new `.md` under `docs/` that
isn't in the nav builds as an orphan (logged at INFO — not a strict
failure) but still publishes to the public site. So: add it to `nav:` if
it's real docs, or to `exclude_docs:` if it's a working file. This
`AGENTS.md` is excluded that way — it's agent-facing, not published.

## Doc-vs-code divergence is a recurring failure mode here

Recipes drift behind reality (paths, commands, defaults). When you spot
it: fix the doc inline. Pattern from a prior session: stale
`~/docker-compose/...` paths surviving the run-from-repo migration. See
global rule #28.

## `wip/NEXT_STEPS.md` is the live punch list

Strike items inline when done (`- [x] ~~text~~ — *done note (date)*`);
don't silently delete them — the strikethrough is the paper trail. Struck items move to its "Done (paper trail)" section.

## Other wip notes are closed when their work ships

Handovers, plans and runbooks in `docs/wip/` don't live forever. When a note's work ships or is
dropped, fold what's still needed into the living doc, move open items to `NEXT_STEPS.md`,
repoint links, delete the note, and record it in `docs/history/`. Procedure:
[`wip/README.md`](wip/README.md) "Closing a note" (D-0016). Before closing a note, check its items
against the live system and git, not its own status line.

## `history/<N>-<arc>.md` carries multi-session continuity

When closing an arc, write a new history entry. Versioning: HEAD is the
source of truth; lightweight `git tag v<X>-<arc-name>` lands at the commit
that closes each history doc (deferred until v0.1 stabilizes — see
[`wip/NEXT_STEPS.md`](wip/NEXT_STEPS.md)).
