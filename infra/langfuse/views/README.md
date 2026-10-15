# Langfuse dashboards and saved views (as code)

`build.py` creates, in the homelab Langfuse (`langfuse.<tailnet>`), the same way the UI does
(tRPC as the init admin):

| Project | Dashboard | Saved views |
|---|---|---|
| `podcast-prod` | **Podcast LLM traffic**: model calls, tokens, cost and errors; calls, tokens and p95 latency by stage; calls by model; errors by stage; `/tokenize` counts per day; traces by environment; traces per day by name | Model traces (no token counts), Model calls by stage, Errors, Slowest calls, Storyline summaries, Token counts (/tokenize), Pipeline runs |
| `agents` | **Fleets & homelab gateway**: model calls, cost, triage decisions and errors; cost by model per day; cost by call name; triage decisions per day by source; triage cost per decision (p95); calls by model; p95 latency by model; traces by environment; calls per day by call name | Triage decisions, Triage turns (gateway, with cost), Gateway calls outside the fleets, Errors, Most expensive calls |

"Model calls" always excludes `litellm-pass_through_endpoint` (the pipeline's `/tokenize` token
counts) and the gateway's `/v1/models` / `/health` probes. Those stay in Langfuse on purpose and
have their own widget and view.

**Versioned and portable.** These definitions are the source of truth; a change made in the
Langfuse UI is overwritten by the next run, so make it here. Rerunnable: a dashboard or view
with the same name is replaced (dashboard first, then its widgets; no orphans), not
duplicated. Projects are found by NAME, since ids differ per instance; a missing project stops
the run before anything changes.

```sh
# the homelab instance (run from the laptop; the mini cannot resolve its own tailnet name)
infra/langfuse/views/run.sh build.py                 # both projects
infra/langfuse/views/run.sh build.py podcast-prod    # one project

# any other Langfuse 3.x: its web URL (= its NEXTAUTH_URL) and an admin there; it needs
# projects named podcast-prod and agents
LF_UI=https://langfuse.example LANGFUSE_INIT_USER_EMAIL=... LANGFUSE_INIT_USER_PASSWORD=... \
  infra/langfuse/views/run.sh build.py
```

Without those variables, `run.sh` loads the homelab admin (`LANGFUSE_INIT_USER_EMAIL`/`_PASSWORD`)
from the mini's `infra/langfuse/.env` over SSH and never prints them. The Langfuse session cookie is `Secure` and bound to `NEXTAUTH_URL`,
so a client on `http://127.0.0.1:4000` gets `UNAUTHORIZED`.

Formats (Langfuse 3.225): a widget is `view` (`traces` / `observations` / `scores-*`),
`dimensions` `[{field}]`, `metrics` `[{measure, agg}]`, `filters` (the table filter shape,
e.g. `{type: "stringOptions", column: "name", operator: "none of", value: [...]}`), `chartType`
and `chartConfig`. A saved view is `tableName`, `filters`, `orderBy`, `columnOrder`,
`columnVisibility`. A `number` filter on `latency` is not read as a minimum by the table UI
(it shows a 0–60 s range), which is why "Slowest calls" sorts by latency instead.
