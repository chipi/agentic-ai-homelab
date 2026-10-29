# cloudflare-edge

Cloudflare's view of our zones, and Cloudflare's own status, in VictoriaMetrics. Every public
host we run is proxied by Cloudflare. When Cloudflare cannot get a valid answer from our origin
it answers 520-526/530 itself, and those requests never reach the prod Caddy, so its logs can't
show them. This poller reads Cloudflare's analytics instead. It complements the outside-in
probes (`probe_success{job="site-probe"}`), which test one URL per host every minute from the
mini. This poller sees every visitor's request, from all of Cloudflare's PoPs.

`poll.py` runs every 5 minutes under launchd on the mini (`com.homelab.cloudflare-edge`, log
`/tmp/cloudflare-edge.log`). It only reads (stdlib only). It needs a read-only Cloudflare API
token in `~/.config/cloudflare/readonly.env` (mode 600, `CLOUDFLARE_API_TOKEN=`); the one there
is the `claude-mcp-readonly` token, all six zones. Run once by hand: `python3 poll.py --once`.

## What it publishes

| Metric | Meaning |
|---|---|
| `cloudflare_edge_requests{zone,host,class,window}` | requests over the last `5m` / `1h` / `24h` (ending 2 min ago) by class: `2xx`, `3xx`, `4xx`, `5xx_server` (500-519, our server answered an error), `5xx_unreachable` (520-526, 530: Cloudflare could not reach, handshake with or read our origin), `client_closed` (499, the client gave up first) |
| `cloudflare_edge_5xx{zone,host,status,window}` | the same per status code, for 499 and 5xx |
| `cloudflare_edge_pop_share{colo}` | share of our requests per Cloudflare PoP over 24h (top 20) |
| `cloudflare_security_events{zone,action,source}` | WAF / bot / rate-limit events over 24h |
| `cloudflare_status_indicator{indicator,description}` | cloudflarestatus.com's global indicator (it is almost never `none`: dozens of PoPs worldwide are always degraded) |
| `cloudflare_status_component{kind,name,status}` | a component that is **ours** and not operational |
| `cloudflare_status_incident{relevance,name,impact,status,components,link}` | every unresolved incident; `relevance="direct"` when it lists a component that is ours |
| `cloudflare_status_maintenance{name,status,start,end,components,link}` | maintenance on a component that is ours, in progress or starting within 24h |
| `cloudflare_poll_ok{part}`, `cloudflare_last_success_timestamp{part}` | `part` = `edge` (GraphQL) or `status` (status page) |

**Ours** (`ours.json`):
- the status-page services our zones use (`services`);
- the PoPs in `pops`;
- any PoP that carried at least `pop_share_min` (5%) of our requests over the last 24h.
  Visitors reach us through many PoPs, so this follows real traffic instead of a guess.

## Where it shows

- **Hub page:** the Uptime section at the top, under the Hetzner bar. Each endpoint's edge
  errors appear next to its probe result, and a relevant Cloudflare incident or maintenance
  appears as a bar.
- **Grafana:** Production Infra / Prod uptime, Cloudflare rows.
- **Alerts** (`rules.yaml`, group `cloudflare-edge`):
  - `cloudflare-edge-unreachable`: a host had at least 20 `5xx_unreachable` in the last hour
    and they were at least 5% of its requests;
  - `cloudflare-origin-errors-sustained`: at least 3 errors 520/522/525 across the prod server's hosts in each
    of two consecutive 5-minute windows (replayed over 7 days: it fired on the 2026-10-29 14:42Z incident and
    the 10-26 evals cut-over, nothing else). Its message carries prod's TCP retransmit rate against its
    1-hour median and the commands to run on the box; retransmits alone fire about daily, so they are
    context, not an alert;
  - `cloudflare-status-ours`: an unresolved Cloudflare incident lists a component that is ours;
  - `cloudflare-edge-poller-stale`: no successful edge read for 1h.

## Limits

- **Free plan only:** the per-request dataset (`httpRequestsAdaptive`) hides timing, PoP and
  Ray ID, so a single slow request can't be traced here. Grouped counts by minute, host,
  status, path and PoP do work.
- **Delay:** counts lag about a minute behind real time, so the windows end 2 minutes ago.
