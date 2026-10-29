---
name: infra-preflight
description: chipi/infra's gates before a commit or push, in one command — make quality, boundary-check, citations-check and obs-umami-views-check (what the staged infra-quality.yml runs in CI), the secrets scan on unpushed commits, and actionlint over the active workflows plus shellcheck over changed .sh on the dev docker engine. One PASS / FAIL / NOT RUN line per stage. Use when about to commit or push in chipi/infra, after porting public main into it, or when asked "is the infra branch green".
---

# infra-preflight

Each round of the infra split (2026-10-14 to 10-17) ended with the same hand-run checks:
`make quality`, the `./public`-backed checks, gitleaks, and actionlint/shellcheck via
`lint.sh`. `lint.sh` named two shell files, and its docker calls relied on the caller having
unset `DOCKER_HOST` first. This script runs the whole set the same way every time.

## Run it

```bash
bash ~/.claude/skills/infra-preflight/scripts/preflight.sh ~/projects/infra
#   --all-sh       shellcheck every tracked .sh, not only those changed since the base
#   --base REF     the base for "changed" and for gitleaks without an upstream (default origin/main)
```

| stage | what | matches CI |
| --- | --- | --- |
| quality | `make quality` (format-check, lint, type, test, check-prod-secret-staging) | job `quality` |
| boundary-check, citations-check, obs-umami-views-check | the `make` targets that read `./public` | job `boundary` |
| secrets | the `secrets-scan` skill's `scan.sh --push` (gitleaks on unpushed commits) | not in CI |
| actionlint | `.github/workflows` copied into a temp repo with the local actions | not in CI |
| shellcheck | `-S warning`, the `.sh` files changed since `merge-base(REF, HEAD)` | not in CI |

- **The docker stages and the suite's docker-backed tests see only the dev engine.** The script
  unsets `DOCKER_HOST` and sets `DOCKER_CONTEXT=dev` for every stage. It never starts the engine:
  run `devengine start` first, and `devengine stop` after if you started it (ADR-0009). With the
  engine down, actionlint and shellcheck are NOT RUN. `make quality` then **fails**, because
  `test_caddy_config_validates` does not skip when docker is unreachable (its two neighbours do).
- **`./public`** must be mounted (docs/guides/MOUNTING_THE_PUBLIC_REPO.md). Without it the three
  boundary stages are NOT RUN. The script prints the commit `./public` is at next to
  `PUBLIC_APP_REF`, because CI checks out that ref and not your local worktree.
- Exit 0 means every stage passed. 1 means at least one failed (its last 25 log lines are
  printed). 3 means nothing failed but something was NOT RUN, which is not a pass.

## Tested 2026-10-17

- `chore/port-public-main-96963f1` at `006d45a`, dev engine running: all 7 stages PASS, exit 0.
- **Mutation test**, a throwaway worktree of the same commit with a workflow missing `runs-on`,
  a `.sh` with `cd` lacking `|| exit`, and no `./public`:
  - actionlint FAIL (`"runs-on" section is missing`) and shellcheck FAIL (SC2164);
  - quality FAIL, because the extra workflow is in no tier (`test_staged_workflows.py`), which
    is correct;
  - the 3 boundary stages NOT RUN, exit 1.
- Without an upstream, the secrets stage scans `origin/main..HEAD` (the whole branch), not only
  unpushed commits. Read each gitleaks hit before calling it a leak or a false positive.
- **Two bugs fixed during testing:**
  - The first version set the dev context only for the docker stages. `make quality` then
    reached for `/var/run/docker.sock` and got permission denied.
  - `mktemp -d` makes a 700 directory, which the dev engine's VM could not mount.

## Not covered

- It does not run the deploy workflows, `ci-step-local` for a single step, or the docs build.
  Use `docs-preflight` for docs changes.
- The actionlint and shellcheck images are `rhysd/actionlint:latest` and
  `koalaman/shellcheck:stable`, unpinned, so a new release can change results.
- It is chipi/infra only: it refuses a repo without `config/prod-settings.env` and a
  `quality` target.
