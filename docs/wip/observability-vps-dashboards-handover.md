# Handover — VPS/podcast dashboards via API push

**For:** the podcast project (where VPS infra lives). **Goal:** own the
podcast/VPS **app** dashboards in that repo (dashboards-as-code next to the app)
and deploy them into the **shared** Grafana on the DGX via API push.

Split of ownership:
- **Homelab repo** owns the backend stack + infra dashboards (host, GPU,
  containers, logs) — they observe the shared platform.
- **Podcast repo** owns app-level dashboards (scraper throughput, queue depth,
  job latency, …) and pushes them to the shared Grafana on deploy.

There is ONE Grafana — everything renders there; only the *source* is split.

## Already set up on the shared Grafana (2026-07-19)

- **Endpoint:** `http://dgx-llm-1:3000` (DGX, over Tailscale; `3000` is
  ACL-granted). Datasources available by uid: `victoriametrics` (metrics),
  `victorialogs` (logs).
- **Folder:** `VPS — Podcast`, **folderUid = `vps-podcast`**.
- **Service account:** `podcast-deploy` (Editor role) with a token.
  - The token was handed to the operator out-of-band. Store it as a **secret**
    in the podcast repo (CI secret / gitignored `.env`) as `GRAFANA_TOKEN`.
    **Never commit it.** Rotate by creating a new token on the SA and deleting
    the old one.

## The deploy step (podcast repo)

Keep dashboard JSON under `dashboards/` in the podcast repo. On deploy, push each:

```sh
GRAFANA="http://dgx-llm-1:3000"
for f in dashboards/*.json; do
  # wrap the raw dashboard model in the push envelope, force the folder + overwrite
  jq -c '{dashboard: ., folderUid: "vps-podcast", overwrite: true}' "$f" \
    | curl -sS -H "Authorization: Bearer $GRAFANA_TOKEN" \
           -H 'Content-Type: application/json' \
           "$GRAFANA/api/dashboards/db" -d @- \
    | jq -r '"\(.status)  \(.title // .message)  \(.url // "")"'
done
```

Rules for clean idempotent pushes:
- Give every dashboard a **stable `uid`** (so re-pushes update, not duplicate).
- `overwrite: true` + `folderUid: "vps-podcast"` on every push.
- Strip `id` (leave it null) — it's instance-local.
- Reference datasources by **uid** (`victoriametrics` / `victorialogs`), not name.

## Authoring workflow (dashboards-as-code)

1. Build/edit in the Grafana UI inside the **VPS — Podcast** folder.
2. Export the JSON model and save it to `dashboards/<name>.json` in the podcast repo:
   ```sh
   curl -sS -H "Authorization: Bearer $GRAFANA_TOKEN" \
     "$GRAFANA/api/dashboards/uid/<uid>" | jq '.dashboard | .id=null' \
     > dashboards/<name>.json
   ```
3. Commit. The deploy step re-pushes it — the file in git is the source of truth.

## Notes / gotchas

- Use **modern React panels** (`timeseries`, `stat`, `table`, `logs`,
  `bargauge`, `gauge`) — Grafana 11 disables AngularJS (`graph`/`singlestat`),
  which render broken. (This is why the homelab repo dropped the old vendored
  DCGM/cAdvisor dashboards.)
- VictoriaLogs panels use the `victoriametrics-logs-datasource` plugin: query
  types `instant` (log lines) / `stats` / `statsRange` (need a `| stats …`
  pipe); variables use `fieldValue` → `field_values`. See the homelab
  `Logs — Overview` dashboard for a worked example.
- Ports bind to the tailnet IP — reach Grafana at `dgx-llm-1`, not loopback.
- The podcast VPS should also be shipping metrics/logs first — see
  `observability-vps-collector-handover.md`.
