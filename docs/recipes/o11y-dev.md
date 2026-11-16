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
| podcast_scraper | GlitchTip dev projects `podcast-pipeline-dev`, `podcast-api-dev`, `player-dev`; the dev push (`src/podcast_scraper/obs/dev_push.py`) labels logs and metrics with `service`, `environment` and `instance` = `<worktree dir>-<port>`. | No `worktree` tag on GlitchTip events (being added), and `instance` instead of `worktree` on pushed telemetry, so nothing is branch-filtered. |
| humancopilot.eu | Nothing. | No dev telemetry and no dev GlitchTip project. |
| eval-harness | Nothing. | No dev telemetry and no dev GlitchTip project. |
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
  `com.homelab.glitchtip-resolve-stale`, `--apply`, default `--days 14`). It runs as the GlitchTip
  superuser, covers every project including the `-dev` ones, and resolves any issue not seen for
  14 days.
- A resolved issue that gets a new event is reopened by GlitchTip (a regression).
- The 2026-11-16 05:15 run resolved 4 `orrery-dev` issues and left 33 open.

So a dev error stays in the unresolved list for up to 14 days after it was last seen, whoever caused it.

GlitchTip's retention is not used for this (it is instance-wide, default 90 days, and deletes issues at
about 97 days), and neither is the GitHub sync (it acts only on issues the fleet filed).

### Open question

The operator has not decided whether dev projects need a shorter threshold than 14 days. One option is a
shorter `--days` for the `-dev` projects only; that would mean changing `resolve-stale.py`, since today
one threshold applies to every project. Until it is decided, the 14-day rule above is what happens.
