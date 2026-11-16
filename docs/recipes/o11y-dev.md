# Dev observability: the contract and the lifecycle

Observability is part of every coding agent's dev cycle, kept apart from production observability.
A branch's dev runs report to dev targets; the agent working on that branch reads them with the
[`o11y-dev`](https://github.com/chipi/agentic-ai-homelab/tree/main/workstation/claude/skills/o11y-dev)
skill before opening a PR. Production is read with `o11y-prod`.

Decided 2026-11-16:

- **A dev error never becomes a GitHub issue.** The triage fleet skips dev entirely. Dev errors are for
  the agent working on that branch.
- **Dev agents only read GlitchTip.** They never resolve, ignore, delete or write. Their token
  (`GLITCHTIP_DEV_TOKEN`, token id 11, scopes `event:read`, `project:read`, `org:read`) cannot:
  a resolve returns 403. See the [handbook](agent-access.md) credentials table.

## The contract every project follows

| Signal | Where | What it carries |
|---|---|---|
| Errors | GlitchTip project `<project>-dev` (org `homelab`) | event `environment=dev`, tag `worktree` = the git branch |
| Logs | VictoriaLogs | labels `environment=dev`, `worktree=<branch>`, plus the app or service label |
| Traces | VictoriaTraces (OTLP) | resource attributes `deployment.environment=dev` and `worktree=<branch>` |
| Metrics (optional) | VictoriaMetrics | the same labels on every series |

Dev never uses a prod DSN or a prod target: a dev run that lands in a prod project, or a prod run
labelled dev, breaks both reviews. Prove a new wiring with the `telemetry-probe` skill (it checks the
signal is absent from the sibling target).

## What each project sends today

| Project | Sends today | Missing |
|---|---|---|
| orrery | Browser errors to GlitchTip `orrery-dev` (`src/lib/observability/sentry.ts`), and, since orrery commit `8f62ac7c00a` (branch `fix/dev-o11y-worktree`, reaches orrery main after the 0.9.9 release), the dev server tier (`orrery-lab-api`, `orrery-mcp`) too: pushed log lines carry a `worktree` field (in the push URL's `_stream_fields`), trace resources carry `worktree` beside `deployment.environment`, GlitchTip events carry the tag. The value is `ORRERY_WORKTREE`, which `scripts/workspace/with-env.mjs` sets from the git branch. | Nothing, once that commit is on orrery main: fully on the contract. Dev runs from before it have no label on server logs and traces and are not branch-filtered. |
| podcast_scraper | GlitchTip dev projects `podcast-pipeline-dev`, `podcast-api-dev`, `player-dev`, `gi-kg-viewer-dev`; since podcast_scraper b647d1633 the dev errors (pipeline, API, viewer) carry the tag `worktree` = branch, dev log pushes carry `worktree` as a VictoriaLogs stream field and dev traces as a resource attribute. | Dev runs from before b647d1633 carry no label and are not branch-filtered. |
| closelistening-player | Since closelistening-player PR #26: the app's web and native dev errors go to GlitchTip `player-dev` with the tag `worktree` = branch. `player-api` runs inside podcast_scraper's server, so its dev logs and traces carry that server's labels. | `player-api` logs and traces have no `worktree` label yet (podcast_scraper is adding it), so they are not branch-filtered. Dev errors from before PR #26 have no tag. |
| humancopilot.eu | Nothing. | No dev telemetry and no dev GlitchTip project. |
| eval-harness | Since eval-harness e6662bf6c (branch 080, on main with 0.8.0): `make serve-dev` and `make mcp-dev` send errors to GlitchTip `evals-dev` (tags `service`, `worktree`), log lines with `service`, `environment=dev` and `worktree`, and traces with `deployment.environment=dev` and `worktree`. | Nothing: on the contract. |
| oceancanvas | Nothing. | No dev telemetry and no dev GlitchTip project. |

A project that sends nothing finds out, through its own agent, what dev observability fits it, and either
meets the contract or declares why there is nothing to check: a file `.o11y-dev.json` at its repo root,
`{"nothing_to_check": "static pages; local checks send nothing"}`. `o11y-dev` then prints that reason
and passes. The declaration counts only for a project `o11y-dev`'s map lists as sending nothing, so it
cannot hide telemetry that exists. The project revisits it when it changes (for example when a static
site gains real JavaScript). Exceptions to the contract are not made; a project that cannot meet it
says so in the declaration.

Creating a GlitchTip project needs the GlitchTip superuser session on the mini
([handbook section 7](agent-access.md)); the agents' tokens cannot create projects. That is the
homelab session's lane.

Until a project labels its telemetry with `worktree`, `o11y-dev` says "not branch-filtered": the list is
every dev error of that project in the window, not only the branch's.

## The lifecycle

| Stage | Skill | What it reads | Who reads it | Issues |
|---|---|---|---|---|
| Dev (before every PR) | `o11y-dev` | the branch's dev errors, logs and traces; read-only | the agent on that branch | None. A dev error never becomes a GitHub issue. |
| CI | the repo's own gates, `ci-watch` | CI checks on the pushed commit | the agent that pushed | None from telemetry |
| Deploy | `deploy-verify`, `telemetry-probe` | prod telemetry before and after the deploy | the agent deploying | None; a red gate is fixed or rolled back |
| Prod | `o11y-prod` | prod logs, errors, traces over a window | humans and agents | The triage fleet turns prod signals into GitHub issues |

## How dev errors get closed

Agents never resolve a dev error. An issue in a `-dev` GlitchTip project clears on its own:

- `infra/glitchtip/resolve-stale.py` runs daily at 05:15 on the mini (LaunchDaemon
  `com.homelab.glitchtip-resolve-stale`, `--apply`). It runs as the GlitchTip superuser and resolves
  any issue not seen for 3 days in a `-dev` project (`--dev-days`, operator 2026-11-16) and for 14 days
  everywhere else (`--days`). It lists issues project by project: the org-wide listing it used before
  skipped some (two podcast-pipeline-dev issues from 2026-10-15 were never resolved).
- A resolved issue that gets a new event is reopened by GlitchTip (a regression).

So a dev error stays in the unresolved list for up to 3 days after it was last seen, whoever caused it.

GlitchTip's retention is not used for this (it is instance-wide, default 90 days, and deletes issues at
about 97 days), and neither is the GitHub sync (it acts only on issues the fleet filed).
