---
name: o11y-dev
description: Read the errors, logs and traces of the branch you are working on, from the dev side of observability (GlitchTip dev projects, environment=dev logs and traces), read-only. Runs on the workstation inside the project's git worktree over the tailnet, no ssh. Never files a GitHub issue, never resolves a GlitchTip issue. Use before opening a PR, after running the dev server or the tests, and for "check my branch's errors", "what did my branch log", "dev errors". For production questions use o11y-prod.
---

# o11y-dev

The dev half of observability: what your branch's dev runs reported. Dev errors are for the agent
working on that branch. They never become GitHub issues (the triage fleet skips dev entirely) and
this skill never resolves or writes anything. Production is `o11y-prod`.

## Run

From inside the project's worktree:

```bash
python3 ~/.claude/skills/o11y-dev/scripts/o11y_dev.py
python3 ~/.claude/skills/o11y-dev/scripts/o11y_dev.py --branch tech-debt/0.9.9 --since 14d
```

- **Project** comes from `git remote get-url origin`, **branch** from `git rev-parse --abbrev-ref HEAD`;
  override with `--project` and `--branch`.
- **Window** starts at the branch's first commit off `origin/main`; `--since 90m|16h|14d|<ISO>` overrides;
  fallback 7 days.
- **Token:** `GLITCHTIP_DEV_TOKEN` in the environment, else `~/.config/glitchtip/dev-agents-read.env`
  (read-only: event:read, project:read, org:read). Never printed.

It ends with one line and exits 0, or 2 when a source could not be read:

```text
O11Y-DEV chipi/orrery tech-debt/0.9.9: errors=10 (branch-filtered), error-logs=0, failed-traces=0
```

`NOT CHECKED <source>: <reason>` means that source was not read: the numbers do not cover it, and zero
there is not "no errors".

## Read it

1. **"not branch-filtered" is every dev error in the window**, from every worktree of that project, not
   only yours. Compare the title and culprit with what you changed before claiming one is yours.
2. **Before a PR:** open each listed issue link, decide whether your change caused it. Fix yours; leave
   the rest. Do not resolve anything.
3. **Dev errors close themselves** 3 days after they were last seen (the daily resolve-stale job); a new
   event reopens the issue.

## Projects

The map is `PROJECTS` in the script. Today: `chipi/orrery` (errors, logs and traces filtered by `worktree`; the server labels need orrery commit 8f62ac7c00a, on its main after the 0.9.9 release, so older dev runs are not branch-filtered), `chipi/podcast_scraper`
(GlitchTip, logs and traces, not branch-filtered). `chipi/humancopilot.eu`, `chipi/eval-harness` and
`chipi/oceancanvas` send no dev telemetry yet. Finding out what dev observability fits is that project's
own job: it either meets the contract or declares why there is nothing to check, in `.o11y-dev.json` at
its repo root (`{"nothing_to_check": "<reason>"}`). With a declaration the script prints the reason and
exits 0 (`nothing to check (declared by the project)`); without one it exits 2. The declaration counts
only for a project the map lists as sending nothing. What every project must send is in
`docs/recipes/o11y-dev.md`.

## Not covered

- **Metrics.** Dev series are not read.
- **Production.** Use `o11y-prod`; after a deploy use `deploy-verify`.
- **Branch filtering of podcast_scraper logs and traces,** until that app adds the `worktree` label; orrery dev runs from before 8f62ac7c00a carry no label.
- **More than 100 issues per dev project** (one page is read) and the newest 1000 error/warn log lines.
- **Issue detail** (stack traces, breadcrumbs): open the printed link.
