# homelab-home — tailnet start page

A single-page overview of the homelab machines, served on the mini at
`https://hub.tail6d0ed4.ts.net` (tailnet-only, HTTPS via Tailscale node). Two symmetric columns —
**Mac mini** and **DGX** — each showing: host stat row, CPU/GPU charts,
service health traffic-lights, a Docker line, and a services table. Every
chart/badge deep-links to the matching Grafana dashboard or service.

## Pieces
- `gen.sh` — regenerates `www/index.html`. Reads service creds from the stack
  `.env` files (`observability/backend`, `glitchtip`, `langfuse`, `umami`) at
  generation time; **contains no secrets itself**. Run it to refresh the static
  shell (the live numbers are fetched client-side).
- `docker-compose.yml` — `nginx:alpine` serving `www/`, bound to the **tailnet
  IP** (`100.87.33.61:8888`), joined to `backend_default` so it can proxy VM.
- `default.conf` — nginx, no auth of its own (tailnet-only since 2026-10-24) + a `/vm/`
  reverse-proxy to `victoriametrics:8428` (same-origin, so the page's JS queries
  VM without CORS).

- `hub-status.js` — the hub's status semantics in one place (RFC-0008): what is green, amber or
  red for sites, boxes, Close Listening health, alerts, Needs you, delivery, credit, spend and
  capacity. It returns data; `gen.sh` inlines it and the page draws from it. Tests:
  `test_status.js` (the module), `test_page.js` / `test_uptime.js` (the page on top of it).
- `status-job.js` — runs the same module on the mini every 5 minutes (launchd
  `com.homelab.hub-status`), writes `www/status.json` (served at `/status.json`), logs each
  snapshot to VictoriaLogs (`job:hub-status`), and records `hub_status_last_success_timestamp`
  (alert `hub-status-stale`).
- `briefing-job.js` — the morning briefing (RFC-0008 use case H1), at 07:00 (launchd
  `com.homelab.hub-briefing`): needs-you first, then the night (alert changes from Grafana's state
  history, containers started, new GlitchTip issues), numbers, all-green. Every number comes from
  code; the model (`assistant-cloud` through the mini's LiteLLM, key `~/hub-briefing-litellm.env`)
  writes only the two-sentence opening, and the briefing goes out without it if it fails. Writes
  `www/briefing/<date>.html` and `index.html` (the last 30 kept; `https://hub.tail6d0ed4.ts.net/briefing/`),
  pushes the headline to the phone through Home Assistant (`notify.mobile_app_iphone`, token
  `~/home-automation-secrets/ha-token`), records `hub_briefing_last_success_timestamp` (alert
  `hub-briefing-missing`). `node briefing-job.js --dry-run` builds the page without pushing.
- `hub-sources.js` — where both jobs read from (the mini's localhost services and token files).

Install the two jobs (system LaunchDaemons running as the operator, from this checkout, as the
mini-metrics jobs do):
```sh
for j in hub-status hub-briefing; do
  sudo cp com.homelab.$j.plist /Library/LaunchDaemons/ && sudo chown root:wheel /Library/LaunchDaemons/com.homelab.$j.plist
  sudo chmod 644 /Library/LaunchDaemons/com.homelab.$j.plist && sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.$j.plist
done
# undo: sudo launchctl bootout system/com.homelab.<job>; sudo rm /Library/LaunchDaemons/com.homelab.<job>.plist
```

## Not in git (mini-local, gitignored)
`www/index.html` (generated), `.env`. (`.htpasswd` and `.basic-auth-cred` are left over from the basic auth removed on 2026-10-24.)

## Deploy / refresh (run-in-place from the repo — no copy-out)
Runs from this repo checkout; `gen.sh` writes `www/index.html` next to itself
and the compose mounts it. `www/` is gitignored
(generated / secret, staged here on the mini).
```sh
# on the mini, in this dir (…/agentic-ai-homelab/infra/homelab-home)
./gen.sh                       # rebuild www/index.html
docker compose up -d           # (re)start nginx
```
Reachable at `https://hub.tail6d0ed4.ts.net` (HTTPS via Tailscale certificate node/Caddy).
The container binds loopback `:8888` internally; the public entry point is the dedicated node.

## Related

- Systems index: [`infra/README.md`](../README.md)
- Global docs: [Pillar 2 — Local AI infra](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/local-ai-infra.md)
