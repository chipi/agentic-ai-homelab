#!/bin/bash
# Write the generated page next to this script (run-in-place from the repo).
OUT="$(cd "$(dirname "$0")" && pwd)/www/index.html"
mkdir -p "$(dirname "$OUT")"
get(){ [ -f "$1" ] && grep -E "^$2=" "$1" | head -1 | cut -d= -f2- || echo "?"; }
REPO=~/agentic-ai-homelab/infra
GF_U=$(get "$REPO/observability/backend/.env" GRAFANA_ADMIN_USER); GF_P=$(get "$REPO/observability/backend/.env" GRAFANA_ADMIN_PASSWORD)
GT_U=$(get "$REPO/glitchtip/.env" DJANGO_SUPERUSER_EMAIL); GT_P=$(get "$REPO/glitchtip/.env" DJANGO_SUPERUSER_PASSWORD)
LF_U=$(get "$REPO/langfuse/.env" LANGFUSE_INIT_USER_EMAIL); LF_P=$(get "$REPO/langfuse/.env" LANGFUSE_INIT_USER_PASSWORD)
UM_U=admin; UM_P=$(get ~/umami/.env UMAMI_ADMIN_PASSWORD)
LL_K=$(get "$REPO/litellm/.env" LITELLM_MASTER_KEY)
# Grafana VIEWER service-account token (read-only) — powers the alert banner.
# Embedding follows the page's existing trust model (admin creds are already
# on it; the page itself is tailnet-only, no basic auth since 2026-10-24).
GF_VIEW=$(get ~/signal-fleet/fleet-gateway.env GRAFANA_TOKEN)
H=https://homelab.tail6d0ed4.ts.net   # legacy node (GlitchTip still fronted here until Level 3)
# Per-service caddy-tailscale nodes — each <name>.tail6d0ed4.ts.net with its own
# Tailscale cert (infra/reverse-proxy; ADR-0006).
TS=tail6d0ed4.ts.net
G=https://grafana.$TS
LF=https://langfuse.$TS; UM=https://umami.$TS; LL=https://litellm.$TS
VM=https://vm.$TS; VL=https://vlogs.$TS; VT=https://vtraces.$TS
DASH_MINI=$G/d/homelab-mini/homelab-e28094-mac-mini
DASH_GPU=$G/d/gpu-dcgm/gpu-e28094-dcgm
DASH_DGX=$G/d/dgx-services/dgx-e28094-services
# GPU dashboards have no host CPU/disk/IO/net panels; Node Exporter Full does, pinned to the DGX.
DASH_DGXHOST="$G/d/rYdddlPWk/node-exporter-full?var-job=integrations%2Funix&var-nodename=spark-2c14&var-node=dgx-llm-1"
DASH_CAD=$G/d/containers-cadvisor/containers-e28094-cadvisor
DASH_PROD=$G/d/prod-infra-host-overview/host-overview
DASH_PCON=$G/d/prod-infra-containers/containers
DASH_PEDGE=$G/d/prod-infra-edge-security/edge-security
DASH_OPER=$G/d/podcast-operator-overview/overview
DASH_PLAYER=$G/d/podcast-player-overview/overview
DASH_FLEET=$G/d/signal-fleet-disp
DASH_INBOX=$G/d/sf-inbox
DASH_BUGFIX=$G/d/bugfix-fleet-work
DASH_DELIVERY=$G/d/delivery-worker/delivery-worker
DASH_UPTIME=$G/d/prod-uptime
row(){ printf '<tr><td><a href="%s">%s</a></td><td><code>:%s</code></td><td><code>%s</code></td><td><code>%s</code></td></tr>\n' "$2" "$1" "$5" "$3" "$4"; }
dsvc(){ printf '<tr><td><a href="%s">%s</a></td><td><code>:%s</code></td><td class=muted>%s</td></tr>\n' "$4" "$1" "$2" "$3"; }
{
cat <<HDR
<!doctype html><html><head><meta charset=utf-8><title>homelab</title>
<meta name=viewport content="width=device-width, initial-scale=1">
<base target="_blank">
<style>body{font:15px/1.55 system-ui,sans-serif;margin:32px;background:#0d0d16;color:#e6e6ef}
h1{font-weight:600;margin:0 0 18px}h2{font-size:16px;font-weight:600;margin:0 0 8px}
h2 a{color:#dcdcf0;text-decoration:none}h2 a:hover{color:#7aa2ff}
.cols{display:flex;gap:34px;flex-wrap:wrap}.col{flex:1;min-width:340px}
table{border-collapse:collapse;width:100%}
th{text-align:left;color:#9a9ac2;font-size:12px;text-transform:uppercase;letter-spacing:.04em;border-bottom:2px solid #34344e;padding:7px 12px}
td{padding:8px 12px;border-bottom:1px solid #22223a}.muted{color:#8888aa}
a{color:#7aa2ff}td a{text-decoration:none;font-weight:500}td a:hover{text-decoration:underline}
code{background:#1a1a2b;padding:2px 7px;border-radius:4px;font-size:13px}
.sec{color:#8888aa;font-size:12.5px;margin-top:6px}
.sysrow{color:#c8c8e0;font-size:13.5px;margin:8px 0 12px}.sysrow b{color:#e6e6ef}
.charts{display:flex;gap:10px;margin:0 0 14px;flex-wrap:wrap}
a.card{box-sizing:border-box;background:#14141f;border:1px solid #26263a;border-radius:8px;padding:10px 12px;flex:1;min-width:110px;display:block;text-decoration:none;color:inherit}
a.card:hover{border-color:#3d3d63}
.card h3{margin:0 0 3px;font-size:10px;color:#9a9ac2;text-transform:uppercase;letter-spacing:.05em}
.cv{font-size:19px;font-weight:600;margin-bottom:2px}
.spark{width:100%;height:40px;display:block}.spark polyline{fill:none;stroke:#7aa2ff;stroke-width:2;vector-effect:non-scaling-stroke}
.health{display:flex;gap:14px;margin:0 0 12px;flex-wrap:wrap;font-size:13px}
a.svc{color:#c8c8e0;text-decoration:none}a.svc:hover{text-decoration:underline}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.up{background:#3fb950}.down{background:#f85149}.stale{background:#7a7a8c}.mid{background:#d29922}
.dock{color:#c8c8e0;font-size:13.5px;margin:2px 0 4px}.dock b{color:#e6e6ef}
#alertbar{margin:0 0 18px}
.abar{display:block;border-radius:8px;padding:10px 14px;margin:0 0 8px;font-size:13.5px;text-decoration:none;color:#e6e6ef}
.abar b{font-weight:600}
.abar.crit{background:#3d1114;border:1px solid #f85149}
.abar.warn{background:#3a2d0e;border:1px solid #d29922}
.abar.plumb{background:#16161f;border:1px solid #26263a;color:#8888aa}
.abar .hz{font-size:11px;text-transform:uppercase;letter-spacing:.05em;opacity:.8;margin-right:6px}
h3.sectitle,summary.sectitle{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#9a9ac2;font-weight:600;margin:16px 0 6px;border-bottom:1px solid #22223a;padding-bottom:4px}
table.ctbl td{padding:4px 10px;border-bottom:1px solid #1a1a2b;font-size:13px;vertical-align:middle}
table.ctbl td.u{color:#8888aa}table.ctbl code{font-size:12px}
.strip{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0 0 12px;font-size:13.5px}
.strip a{color:#c8c8e0;text-decoration:none;white-space:nowrap}.strip a:hover{color:#7aa2ff}.strip b{color:#e6e6ef}
.tabs{display:flex;gap:2px;margin:0 0 18px;border-bottom:1px solid #26263a}
.tabs a{padding:8px 14px;color:#9a9ac2;text-decoration:none;border-bottom:2px solid transparent;margin-bottom:-1px;font-weight:500}
.tabs a.on{color:#e6e6ef;border-bottom-color:#7aa2ff}.tabs a:hover{color:#e6e6ef}
section.tab{display:none}section.tab.on{display:block}
table.proj td{vertical-align:middle}table.proj td .s{font-size:12px;color:#8888aa}table.proj td svg{vertical-align:middle}
.subtabs{display:flex;gap:6px;margin:0 0 16px;flex-wrap:wrap}
.subtabs a{padding:5px 12px;border:1px solid #26263a;border-radius:16px;color:#9a9ac2;text-decoration:none;font-size:13.5px}
.subtabs a.on{color:#e6e6ef;border-color:#7aa2ff;background:#16182b}.subtabs a:hover{color:#e6e6ef}
.sub{display:none}.sub.on{display:block}
.svcs h4{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#9a9ac2;font-weight:600;margin:14px 0 6px}
.svcs .charts{margin-bottom:6px}.svcs a.card{min-width:150px}.svcs .cv{font-size:15px}
.svcs .ln{font-size:12px;color:#8888aa;line-height:1.45}
a.card.site h3{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
a.card.site .kv{display:grid;grid-template-columns:58px 1fr;gap:0 6px;font-size:12px;color:#8888aa;line-height:1.55}
a.card.site .kv b{color:#c8c8e0;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
a.card.site svg{display:block;width:100%;height:18px;margin-top:6px}
details.sect summary{cursor:pointer;list-style:none}details.sect summary::-webkit-details-marker{display:none}
details.sect summary::before{content:"\25B8  "}details.sect[open] summary::before{content:"\25BE  "}
#notices{margin:0 0 12px}#notices .abar.crit{display:none}
#notices summary{cursor:pointer;font-size:13.5px;color:#d29922;list-style:none}
#notices summary::-webkit-details-marker{display:none}
#notices summary::before{content:'\25B8  '}#notices[open] summary::before{content:'\25BE  '}
#notices[open] summary{margin-bottom:8px}
@media(max-width:640px){
  body{margin:14px}
  h1{font-size:20px;margin-bottom:14px}
  .cols{gap:18px}.col{min-width:0;flex-basis:100%}
  .charts{gap:8px}a.card{min-width:calc(50% - 4px);padding:9px 10px;overflow-wrap:anywhere}
  .cv{font-size:17px}.spark{height:34px}
  table{font-size:13px}th,td{padding:6px 8px}
  table.uptime th:nth-child(n+5),table.uptime td:nth-child(n+5){display:none}
  table.uptime td:first-child{overflow-wrap:anywhere}
  table.models th:nth-child(n+5),table.models td:nth-child(n+5){display:none}table.models th:nth-child(3),table.models td:nth-child(3){display:none}
  table.models td:first-child{overflow-wrap:anywhere}
  table.proj thead{display:none}table.proj tr{display:grid;grid-template-columns:1fr 1fr;gap:4px 10px;border:1px solid #26263a;border-radius:8px;padding:8px 10px;margin:0 0 8px;background:#14141f}
  table.proj td{border:none;padding:0}table.proj td:first-child{grid-column:1/-1;font-weight:600}
  table.proj td[data-l]::before{content:attr(data-l);display:block;font-size:10px;color:#9a9ac2;text-transform:uppercase;letter-spacing:.05em}
  .strip{gap:6px 12px;font-size:12.5px}
  .tabs a{padding:8px 9px;font-size:14px}
  .subtabs{flex-wrap:nowrap;gap:4px}
  .subtabs a{flex:1;text-align:center;white-space:nowrap;padding:5px 4px;font-size:12.5px}
  .subtabs .dot{width:7px;height:7px;margin-right:4px}
  code{word-break:break-all}
  .sysrow,.dock,.sec,.health{font-size:12.5px}
}</style></head><body>
<h1>homelab</h1>
<!-- Banners: critical ones are copied to #critbar and always shown; the rest fold into one
     line (#notices) so they never push the strip and tabs off a phone screen. The three bars
     are still filled by hetzner(), cloudflare() and alerts(); notices() only reads them. -->
<div id=critbar></div>
<!-- Always on top: one line per area. Each dot copies the state of that area's own dot in its
     tab (mirror() below), so there is one source of truth per signal. Green everywhere = done. -->
<div class=strip>
  <a href="#sites" target=_self><span class="dot stale" data-dot=up_agg></span>Sites</a>
  <a href="#overview" target=_self><span class="dot stale" data-dot=ph_agg></span>Podcast prod</a>
  <a href="#hosts/prod" target=_self><span class="dot stale" data-dot=st_prod></span>Prod box</a>
  <a href="#hosts/mini" target=_self><span class="dot stale" data-dot=st_mini></span>Mac mini</a>
  <a href="#hosts/dgx" target=_self><span class="dot stale" data-dot=st_dgx></span>DGX</a>
  <a href="#hosts/delivery" target=_self><span class="dot stale" data-dot=st_delivery></span>Delivery</a>
  <a href="#fleets" target=_self>Needs you <b data-text=f_inbox>&hellip;</b></a>
  <a href="#spend" target=_self>Credit left <b id=ov_credit_s>&hellip;</b></a>
</div>
<details id=notices hidden><summary id=nsum></summary>
<div id=hetznerbar></div>
<div id=cfbar></div>
<div id=alertbar></div>
</details>
<nav class=tabs>
  <a href="#overview" target=_self>Overview</a><a href="#sites" target=_self>Sites</a><a href="#hosts" target=_self>Hosts</a><a href="#fleets" target=_self>Fleets</a><a href="#spend" target=_self>Spend</a>
</nav>
<section class=tab id=t-overview>
<div class=charts style="max-width:1140px">
  <a class=card href="#sites" target=_self><h3>Sites up now</h3><div data-mirror=up_now>&hellip;</div></a>
  <a class=card href="#sites" target=_self><h3>Availability 24h</h3><div data-mirror=up_24h>&hellip;</div></a>
  <a class=card href="#fleets" target=_self><h3>Triage needs you</h3><div data-mirror=f_inbox>&hellip;</div></a>
  <a class=card href="#spend" target=_self><h3>OpenRouter this month</h3><div id=ov_month>&hellip;</div></a>
  <a class=card href="#spend" target=_self><h3>OpenRouter credit left</h3><div id=ov_credit>&hellip;</div></a>
  <a class=card href="#hosts/delivery" target=_self><h3>Delivery workers</h3><div data-mirror=dl_up>&hellip;</div></a>
</div>
<!-- Production apps — the operator's FIRST impression of app health, above the fleets and
     machine columns. Fed by each app's prod-ops-health run (podcast_scraper #1876) pushing
     prod_ops_health_* gauges into this VM; per-app template — clone the block and swap the
     app="..." label for the next production app. Traffic lights: 1 green / 0.5 orange
     (degraded, not customer-impacting) / 0 red; STALENESS IS A STATE — no run for >26h renders
     grey/stale, because a dead health check must never look healthy. -->
<h2>Projects</h2>
<table class="ctbl proj"><thead><tr><th>Project</th><th>Health</th><th>Sites</th><th>Requests 24h</th><th>Visitors 24h</th><th>Edge 5xx 24h</th><th>Edge 4xx 24h</th><th>LLM spend</th><th>LLM tokens</th></tr></thead><tbody id=projrows></tbody></table>
<p class=sec id=proj_llm_note></p>
<details class=sect><summary class=sectitle>Close Listening &middot; health checks</summary>
<div style="margin:0 0 22px" id=podcast_prod>
  <h2><span class="dot stale" id=ph_agg></span><a href="https://github.com/chipi/infra/actions/workflows/prod-ops-health.yml">Podcast &mdash; production &rarr;</a></h2>
  <div class=charts style="max-width:1140px">
    <a class=card href="https://github.com/chipi/infra/actions/workflows/prod-ops-health.yml"><h3>App health</h3><div id=ph_overall>&hellip;</div></a>
    <a class=card href="https://github.com/chipi/infra/actions/workflows/prod-ops-health.yml"><h3>LLM gateway</h3><div id=ph_gateway>&hellip;</div></a>
    <a class=card href="$VL"><h3>Logs flowing</h3><div id=ph_o11y_logs>&hellip;</div></a>
    <a class=card href="$DASH_PROD"><h3>Metrics flowing</h3><div id=ph_o11y_metrics>&hellip;</div></a>
    <a class=card href="$VT"><h3>Traces flowing</h3><div id=ph_o11y_traces>&hellip;</div></a>
    <a class=card href="https://glitchtip.tail6d0ed4.ts.net"><h3>Error tracking</h3><div id=ph_o11y_glitchtip>&hellip;</div></a>
    <a class=card href="https://github.com/chipi/infra/actions/workflows/prod-ops-health.yml"><h3>Last check</h3><div id=ph_age>&hellip;</div></a>
  </div>
</div>
</details>
</section>
<section class=tab id=t-sites>
<!-- Uptime: outside-in probes from the mini (job site-probe, every minute through Cloudflare)
     plus Cloudflare's own count of errors for every visitor (infra/cloudflare-edge). -->
<div style="margin:0 0 22px" id=uptime>
  <h2><span class="dot stale" id=up_agg></span><a href="$DASH_UPTIME">Uptime &mdash; prod endpoints &rarr;</a></h2>
  <div class=charts>
    <a class=card href="$DASH_UPTIME"><h3>Up now</h3><div id=up_now>&hellip;</div></a>
    <a class=card href="$DASH_UPTIME"><h3>Availability 24h</h3><div id=up_24h>&hellip;</div></a>
    <a class=card href="$DASH_UPTIME"><h3>Availability 7d</h3><div id=up_7d>&hellip;</div></a>
    <a class=card href="$DASH_UPTIME"><h3>Availability 30d</h3><div id=up_30d>&hellip;</div></a>
    <a class=card href="$DASH_UPTIME"><h3>Edge 5xx 1h</h3><div id=up_edge>&hellip;</div></a>
    <a class=card href="$DASH_UPTIME"><h3>Security blocks 24h</h3><div id=up_sec>&hellip;</div></a>
  </div>
  <div id=site_groups></div>
  <details class=sect><summary class=sectitle>All endpoints (table)</summary>
  <table class="ctbl uptime"><thead><tr><th>Endpoint</th><th>Now</th><th>24h</th><th>7d</th><th>30d</th><th title="Cloudflare: 5xx answered to all visitors, 24h">Edge 5xx 24h</th><th>Check</th></tr></thead><tbody id=uptbl></tbody></table>
  </details>
  <p class=sec>Checked from the mini (home internet) through Cloudflare every minute; minutes when the mini itself was offline are left out. Edge 5xx = Cloudflare's count for every visitor (520-530: it could not reach our origin).</p>
</div>
</section>
<section class=tab id=t-fleets>
<div style="margin:0 0 22px">
  <h2><span class="dot stale" id=fl_tdot></span><a href="$DASH_FLEET">Triage fleet &rarr;</a></h2>
  <div class=charts style="max-width:1140px">
    <a class=card href="$DASH_INBOX"><h3>Needs you</h3><div id=f_inbox>&hellip;</div><div id=fl_backlog class=muted style="font-size:12px"></div></a>
    <a class=card href="$DASH_FLEET"><h3>Decisions 24h</h3><div id=fl_dec>&hellip;</div></a>
    <a class=card href="$DASH_INBOX"><h3>Escalations 7d</h3><div id=fl_esc>&hellip;</div></a>
    <a class=card href="$DASH_FLEET"><h3>Spend this month</h3><div id=fl_spend>&hellip;</div></a>
    <a class=card href="$DASH_FLEET"><h3>Last cycle</h3><div id=fl_cycle>&hellip;</div></a>
    <a class=card href="$DASH_FLEET"><h3>Sources</h3><div id=fl_src>&hellip;</div></a>
  </div>
</div>
<div style="margin:0 0 22px">
  <h2><span class="dot stale" id=fl_bdot></span><a href="$DASH_BUGFIX">Bug-fix fleet &rarr;</a></h2>
  <div class=charts style="max-width:1140px">
    <a class=card href="$DASH_BUGFIX" style="min-width:100%"><h3>Pipeline</h3><div id=fl_pipe>&hellip;</div></a>
    <a class=card href="$DASH_BUGFIX"><h3>Shipped</h3><div id=fl_ship>&hellip;</div></a>
    <a class=card href="$DASH_BUGFIX"><h3>Stuck</h3><div id=fl_stuck>&hellip;</div></a>
    <a class=card href="https://github.com/search?q=owner%3Achipi+is%3Aissue+is%3Aopen+label%3A%22triage-fleet%2Factionable%22"><h3>Routable now</h3><div id=b_route>&hellip;</div></a>
  </div>
  <p class=sec>The bug-fix fleet reports no spend of its own; its model calls are in the Spend tab under the key it uses.</p>
</div>
</section>
<section class=tab id=t-spend>
  <nav class=subtabs id=sp_period>
    <a href="#spend/month" target=_self>This month</a><a href="#spend/30d" target=_self>Last 30 days</a><a href="#spend/7d" target=_self>Last 7 days</a><a href="#spend/yesterday" target=_self>Yesterday</a>
  </nav>
  <p class=sec id=sp_range style="margin:-8px 0 12px"></p>
  <h2>Totals</h2>
  <div class=charts style="max-width:1140px" id=sp_totals>&hellip;</div>
  <h2>By key</h2>
  <div class=charts style="max-width:1140px" id=sp_keys>&hellip;</div>
  <h2>By vendor</h2>
  <div class=charts style="max-width:1140px" id=sp_vendor>&hellip;</div>
  <h2>By model</h2>
  <table class="ctbl models"><thead><tr><th>Vendor</th><th>Model</th><th>Source</th><th>Spend</th><th>Tokens in / out</th><th>Requests</th><th>Keys</th><th>Served by</th></tr></thead><tbody id=sp_models></tbody></table>
  <details class=sect><summary class=sectitle>Local models by consumer (both gateways)</summary>
  <table class=ctbl><thead><tr><th>Gateway</th><th>Key</th><th>Model</th><th>Tokens in / out</th><th>Requests</th></tr></thead><tbody id=sp_consumers></tbody></table>
  </details>
  <p class=sec>Every number covers the same completed UTC days; only "Today so far" is live. Sources: OpenRouter (every key: prod, dev, evals, fleets; billed), vLLM on the DGX (its own token counters, all callers, $0), Ollama on the DGX, X3 and MacBook (its per-request log lines, $0; the lines carry no model or key). Fleet spend is part of OpenRouter, not extra.</p>
</section>
<section class=tab id=t-hosts>
<nav class=subtabs>
  <a href="#hosts/prod" target=_self><span class="dot stale" data-dot=st_prod></span>Prod box</a><a href="#hosts/mini" target=_self><span class="dot stale" data-dot=st_mini></span>Mac mini</a><a href="#hosts/dgx" target=_self><span class="dot stale" data-dot=st_dgx></span>DGX</a><a href="#hosts/delivery" target=_self><span class="dot stale" data-dot=st_delivery></span>Delivery</a>
</nav>
<div class=sub data-sub=delivery style="margin:0 0 22px">
  <h2><span class="dot stale" id=st_delivery></span><a href="$DASH_DELIVERY">Delivery &rarr;</a></h2>
  <div class=charts style="max-width:1140px">
    <a class=card href="$DASH_DELIVERY"><h3>Workers up</h3><div id=dl_up>&hellip;</div></a>
    <a class=card href="$DASH_DELIVERY"><h3>Sent 24h</h3><div id=dl_sent>&hellip;</div></a>
    <a class=card href="$DASH_DELIVERY"><h3>Bounce/complaint 1h</h3><div id=dl_bounce>&hellip;</div></a>
    <a class=card href="$DASH_DELIVERY"><h3>Dead-letters 24h</h3><div id=dl_dead>&hellip;</div></a>
    <a class=card href="$DASH_DELIVERY"><h3>Pending</h3><div id=dl_pending>&hellip;</div></a>
    <a class=card href="$DASH_DELIVERY"><h3>Cursor age</h3><div id=dl_cursor>&hellip;</div></a>
  </div>

</div>
<div class=cols>
<div class="col sub" data-sub=mini>
  <h2><span class="dot stale" id=st_mini></span><a href="$DASH_MINI">Mac mini &rarr;</a></h2>
  <div id=sysrow class=sysrow>&hellip;</div>
  <div class=charts>
    <a class=card href="$DASH_MINI"><h3>CPU</h3><div id=c_cpu>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>CPU temp</h3><div id=c_temp>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>Memory</h3><div id=c_mem>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>Disk</h3><div id=c_disk>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>Disk IO</h3><div id=c_io>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>Network</h3><div id=c_net>&hellip;</div></a>
  </div>
  <div id=svc_mini class=svcs></div>
  <details class=sect><summary class=sectitle>Containers</summary>
  <table class=ctbl><tbody id=mctr></tbody></table>
  </details>
  <div class=dock><a href="$DASH_CAD" style=color:inherit;text-decoration:none><span id=mdocker>&hellip;</span></a></div>
  <details class=sect><summary class=sectitle>Services &amp; credentials</summary>
  <table><thead><tr><th>Service</th><th>Port</th><th>User</th><th>Password</th></tr></thead><tbody>
HDR
row "Grafana"         "$G"            "$GF_U" "$GF_P" "3000"
row "GlitchTip"       "https://glitchtip.$TS" "$GT_U" "$GT_P" "8090"
row "Langfuse"        "$LF"           "$LF_U" "$LF_P" "4000"
row "Umami"           "$UM"           "$UM_U" "$UM_P" "3001"
row "LiteLLM"         "$LL/ui/"       "admin" "$LL_K" "4001"
row "VictoriaMetrics" "$VM/vmui"      "&mdash;" "tailnet" "8428"
row "VictoriaLogs"    "$VL"           "&mdash;" "tailnet" "9428"
row "VictoriaTraces"  "$VT"           "&mdash;" "tailnet" "10428"
row "Home Assistant"  "https://homeassistant.$TS" "own account" "&mdash;" "8123"
cat <<MID
  </tbody></table>
  </details>
</div>
<div class="col sub" data-sub=dgx>
  <h2><span class="dot stale" id=st_dgx></span><a href="$DASH_GPU">DGX &middot; dgx-llm-1 &rarr;</a></h2>
  <div id=dgxrow class=sysrow>&hellip;</div>
  <div class=charts>
    <a class=card href="$DASH_GPU"><h3>GPU temp</h3><div id=g_temp>&hellip;</div></a>
    <a class=card href="$DASH_GPU"><h3>GPU util</h3><div id=g_util>&hellip;</div></a>
    <a class=card href="$DASH_GPU"><h3>GPU power</h3><div id=g_pow>&hellip;</div></a>
    <a class=card href="$DASH_GPU"><h3>Mem temp</h3><div id=g_vram>&hellip;</div></a>
  </div>
  <div class=charts>
    <a class=card href="$DASH_DGXHOST"><h3>Host CPU</h3><div id=d_cpu>&hellip;</div></a>
    <a class=card href="$DASH_DGXHOST"><h3>Unified mem</h3><div id=d_mem>&hellip;</div></a>
    <a class=card href="$DASH_DGXHOST"><h3>Host disk</h3><div id=d_disk>&hellip;</div></a>
    <a class=card href="$DASH_DGXHOST"><h3>Disk IO</h3><div id=d_io>&hellip;</div></a>
    <a class=card href="$DASH_DGXHOST"><h3>Network</h3><div id=d_net>&hellip;</div></a>
  </div>
  <div id=svc_dgx class=svcs></div>
  <details class=sect><summary class=sectitle>Containers</summary>
  <table class=ctbl><tbody id=dgxctr></tbody></table>
  </details>
  <div class=dock><a href="$DASH_CAD" style=color:inherit;text-decoration:none><span id=ddocker>&hellip;</span></a></div>
  <details class=sect><summary class=sectitle>Services</summary>
  <table><thead><tr><th>Service</th><th>Port</th><th>Role</th></tr></thead><tbody>
MID
dsvc "ollama"         "11434" "LLM inference" "$DASH_DGX"
dsvc "speaches"       "8000"  "transcription" "$DASH_DGX"
dsvc "diarization"    "8001"  "speaker split" "$DASH_DGX"
dsvc "moss"           "8004"  "transcription" "$DASH_DGX"
dsvc "cadvisor"       "8080"  "containers"    "$DASH_CAD"
dsvc "dcgm"           "9400"  "GPU exporter"  "$DASH_GPU"
cat <<MID2
  </tbody></table>
  </details>
</div>
<div class="col sub" data-sub=prod>
  <h2><span class="dot stale" id=st_prod></span><a href="$DASH_PROD">Production &middot; prod-podcast &rarr;</a></h2>
  <div id=prodrow class=sysrow>&hellip;</div>
  <div class=charts>
    <a class=card href="$DASH_PROD"><h3>CPU</h3><div id=p_cpu>&hellip;</div></a>
    <a class=card href="$DASH_PROD"><h3>Memory</h3><div id=p_mem>&hellip;</div></a>
    <a class=card href="$DASH_PROD"><h3>Disk</h3><div id=p_disk>&hellip;</div></a>
    <a class=card href="$DASH_PROD"><h3>Disk IO</h3><div id=p_io>&hellip;</div></a>
    <a class=card href="$DASH_PROD"><h3>Network</h3><div id=p_net>&hellip;</div></a>
  </div>
  <div id=svc_prod class=svcs></div>
  <details class=sect><summary class=sectitle>Containers</summary>
  <table class=ctbl><tbody id=pctr></tbody></table>
  </details>
  <div class=dock><a href="$DASH_PCON" style=color:inherit;text-decoration:none><span id=pdocker>&hellip;</span></a></div>
  <details class=sect><summary class=sectitle>Services</summary>
  <table><thead><tr><th>Service</th><th>Board</th><th>Role</th></tr></thead><tbody>
MID2
dsvc "podcast operator" "ops" "operator API + viewer"  "$DASH_OPER"
dsvc "podcast player"   "app" "consumer player (public)" "$DASH_PLAYER"
dsvc "edge / security"  "443" "shared Caddy + fail2ban" "$DASH_PEDGE"
dsvc "containers"       "cA"  "cAdvisor"               "$DASH_PCON"
cat <<MID3
  </tbody></table>
  </details>
</div>
</div>
<p class=sec id=fresh></p>
</section>
MID3
UMAMI_SITES=$(/usr/local/bin/docker exec umami-db psql -U umami -d umami -At -F '|' \
  -c "select domain, website_id from website where deleted_at is null and domain <> 'localhost'" 2>/dev/null \
  | awk -F'|' 'NF==2{printf "%s[\"%s\",\"%s\"]", (n++?",":""), $1, $2}')
cat <<TOK
<script>const GTOK="$GF_VIEW";const UMAMI_SITES=[${UMAMI_SITES}];</script>
TOK
cat <<'SCRIPT'
<script>
const W=260,H=40,TS='tail6d0ed4.ts.net',G='https://grafana.'+TS;
// Service LINK targets = per-service caddy-tailscale nodes (real certs). The
// metric/alert FETCHES below stay same-origin (/vm/, /grafana/) — nginx proxies
// those to the backends; they must NOT become cross-origin (CORS).
const MINILINK={grafana:G,glitchtip:'https://glitchtip.'+TS,langfuse:'https://langfuse.'+TS,umami:'https://umami.'+TS,litellm:'https://litellm.'+TS+'/ui/',victoriametrics:'https://vm.'+TS+'/vmui',victorialogs:'https://vlogs.'+TS,victoriatraces:'https://vtraces.'+TS};
const DGXDASH=G+'/d/dgx-services/dgx-e28094-services';
async function q(query){try{const j=await(await fetch('/vm/api/v1/query?query='+encodeURIComponent(query))).json();return j.data.result;}catch(e){return[];}}
const g1=async m=>{const r=await q(m);return r.length?r[0].value:null;};
async function draw(id,qq,fmt,max){
  const e=Math.floor(Date.now()/1000),s=e-3600;
  let j;try{j=await(await fetch('/vm/api/v1/query_range?query='+encodeURIComponent(qq)+'&start='+s+'&end='+e+'&step=60')).json();}catch(x){return;}
  const vs=((j.data.result[0]||{}).values||[]).map(p=>+p[1]);const el=document.getElementById(id);if(!el)return;
  if(!vs.length){el.innerHTML='<div class=cv>&mdash;</div>';return;}
  const mx=max||Math.max.apply(0,vs)*1.15||1;
  const pts=vs.map((y,i)=>((i/(vs.length-1))*W).toFixed(1)+','+(H-(y/mx)*H).toFixed(1)).join(' ');
  el.innerHTML='<div class=cv>'+fmt(vs[vs.length-1])+'</div><svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio=none class=spark><polyline points="'+pts+'"/></svg>';
}
function fmtUp(s){s=+s;const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d?d+'d '+h+'h':(h?h+'h '+m+'m':m+'m');}
async function ctable(elId,box,cpuq,memq){
  const rows=await q('container_uptime_seconds{box=\"'+box+'\"}');
  const el=document.getElementById(elId);if(!el)return;
  const col={running:'#3fb950',restarting:'#d29922',created:'#d29922',paused:'#d29922',exited:'#f85149',dead:'#f85149'};
  if(!rows.length){el.innerHTML='<tr><td class=muted colspan='+(cpuq?6:4)+'>no data</td></tr>';return;}
  const cpuM={},memM={};
  if(cpuq){(await q(cpuq)).forEach(s=>cpuM[s.metric.name]=+s.value[1]);(await q(memq)).forEach(s=>memM[s.metric.name]=+s.value[1]);}
  el.innerHTML=rows.sort((a,b)=>{const A=(a.metric.app||'')+'/'+a.metric.name,B=(b.metric.app||'')+'/'+b.metric.name;return A<B?-1:1;}).map(s=>{const m=s.metric;let c,up;if(m.state=='running'){if(m.health=='unhealthy'){c='#d29922';up='unhealthy';}else if(m.health=='starting'){c='#d29922';up='starting';}else{c='#3fb950';up=fmtUp(s.value[1]);}}else if(m.state=='exited'){if(m.exit_code=='0'){c='#7a7a8c';up='done';}else{c='#f85149';up='exit '+m.exit_code;}}else{c=col[m.state]||'#7a7a8c';up=m.state;}var cv=cpuq?cpuM[m.name]:null,mv=cpuq?memM[m.name]:null,res=cpuq?('<td class=u>'+(cv!=null?cv.toFixed(0)+'%':'&mdash;')+'</td><td class=u>'+(mv!=null?(mv/1048576).toFixed(0)+' MB':'&mdash;')+'</td>'):'';return '<tr><td>'+m.name+'</td><td><span class=dot style=\"background:'+c+'\"></span></td><td class=u>'+up+'</td>'+res+'<td>'+(m.port?'<code>'+m.port+'</code>':'&mdash;')+'</td></tr>';}).join('');
}
async function mini(){
  draw('c_cpu','mini_cpu_used_percent',x=>x.toFixed(0)+'%',100);
  draw('c_temp','mini_cpu_temp_celsius',x=>x.toFixed(0)+'&deg;C',100);
  {const mt=await g1('mini_mem_total_bytes'),gb=mt?(+mt[1]/1073741824).toFixed(0):'?';
   draw('c_mem','mini_mem_used_percent',x=>x.toFixed(0)+'% <span class=muted>/ '+gb+' GB</span>',100);}
  {const pf=await g1('100*node_filesystem_avail_bytes{instance="homelab",mountpoint="/System/Volumes/Data"}/node_filesystem_size_bytes{instance="homelab",mountpoint="/System/Volumes/Data"}');
   draw('c_disk','mini_disk_free_bytes',x=>(x/1073741824).toFixed(0)+' GB'+(pf?' <span class=muted>'+(+pf[1]).toFixed(0)+'% free</span>':''));}
  draw('c_io','mini_disk_io_bytes_per_sec',x=>(x/1048576).toFixed(1)+' MB/s');
  draw('c_net','sum(rate(node_network_receive_bytes_total{instance=\"homelab\"}[2m]))+sum(rate(node_network_transmit_bytes_total{instance=\"homelab\"}[2m]))',x=>(x/1048576).toFixed(1)+' MB/s');
  const L=x=>x?(+x[1]).toFixed(2):'&mdash;';
  const l1=await g1('mini_load1'),l5=await g1('mini_load5'),l15=await g1('mini_load15'),sw=await g1('mini_swap_used_bytes'),up=await g1('mini_uptime_seconds');
  const sr=document.getElementById('sysrow');if(sr)sr.innerHTML='Load <b>'+L(l1)+' / '+L(l5)+' / '+L(l15)+'</b> &middot; Swap <b>'+(sw?((+sw[1])/1048576).toFixed(0)+' MB':'&mdash;')+'</b> &middot; Up <b>'+(up?fmtUp(up[1]):'&mdash;')+'</b>';
  const run=await g1('mini_docker_running'),tot=await g1('mini_docker_total'),rst=await g1('mini_docker_restarting'),unh=await g1('mini_docker_unhealthy');
  const md=document.getElementById('mdocker');if(md&&run)md.innerHTML='<b>'+run[1]+'/'+tot[1]+'</b> running'+(rst&&+rst[1]?' &middot; <span style=color:#f85149>'+rst[1]+' restarting</span>':'')+(unh&&+unh[1]?' &middot; <span style=color:#f85149>'+unh[1]+' unhealthy</span>':'');
  ctable('mctr','mini','mini_container_cpu_percent','mini_container_mem_bytes');
}
async function dgx(){
  draw('g_temp','DCGM_FI_DEV_GPU_TEMP',x=>x.toFixed(0)+'&deg;C');
  draw('g_util','DCGM_FI_DEV_GPU_UTIL',x=>x.toFixed(0)+'%',100);
  draw('g_pow','DCGM_FI_DEV_POWER_USAGE',x=>x.toFixed(0)+' W');
  draw('g_vram','DCGM_FI_DEV_MEMORY_TEMP',x=>x.toFixed(0)+'&deg;C');
  const D='{instance="dgx-llm-1"}';
  draw('d_cpu','100-avg(rate(node_cpu_seconds_total{instance="dgx-llm-1",mode="idle"}[5m]))*100',x=>x.toFixed(0)+'%',100);
  {const mt=await g1('node_memory_MemTotal_bytes'+D),gb=mt?(+mt[1]/1073741824).toFixed(0):'?';
   draw('d_mem','100-node_memory_MemAvailable_bytes'+D+'/node_memory_MemTotal_bytes'+D+'*100',x=>x.toFixed(0)+'% <span class=muted>/ '+gb+' GB</span>',100);}
  {const pu=await g1('100*(1-node_filesystem_avail_bytes{instance="dgx-llm-1",mountpoint="/"}/node_filesystem_size_bytes{instance="dgx-llm-1",mountpoint="/"})');
   draw('d_disk','node_filesystem_avail_bytes{instance="dgx-llm-1",mountpoint="/"}',x=>(x/1073741824).toFixed(0)+' GB'+(pu?' <span class=muted>'+(+pu[1]).toFixed(0)+'% used</span>':''));}
  draw('d_io','sum(rate(node_disk_read_bytes_total'+D+'[2m]))+sum(rate(node_disk_written_bytes_total'+D+'[2m]))',x=>(x/1048576).toFixed(2)+' MB/s');
  draw('d_net','sum(rate(node_network_receive_bytes_total'+D+'[2m]))+sum(rate(node_network_transmit_bytes_total'+D+'[2m]))',x=>(x/1048576).toFixed(2)+' MB/s');
  const clk=await g1('DCGM_FI_DEV_SM_CLOCK'),mbw=await g1('DCGM_FI_DEV_MEM_COPY_UTIL');
  const L=x=>x?(+x[1]).toFixed(2):'&mdash;';
  const l1=await g1('node_load1'+D),l5=await g1('node_load5'+D),l15=await g1('node_load15'+D),up=await g1('node_time_seconds'+D+'-node_boot_time_seconds'+D);
  const dr=document.getElementById('dgxrow');if(dr)dr.innerHTML='Clock <b>'+(clk?(+clk[1]).toFixed(0)+' MHz':'&mdash;')+'</b> &middot; Mem-BW <b>'+(mbw?(+mbw[1]).toFixed(0)+'%':'&mdash;')+'</b> &middot; Load <b>'+L(l1)+' / '+L(l5)+' / '+L(l15)+'</b> &middot; Up <b>'+(up?fmtUp(up[1]):'&mdash;')+'</b>';
  // container_last_seen counts every cgroup cadvisor sees (system slices too) and id="/" is the
  // whole host, so both read the inventory / named containers instead (62-77 "containers" vs 12).
  const dr1=await g1('count(container_uptime_seconds{box="dgx",state="running"})'),dt1=await g1('count(container_uptime_seconds{box="dgx"})');
  const mem=await g1('sum(container_memory_working_set_bytes{instance="dgx-llm-1",name!=""})');
  const dd=document.getElementById('ddocker');if(dd)dd.innerHTML='<b>'+(dr1?dr1[1]:'0')+'/'+(dt1?dt1[1]:'&mdash;')+'</b> running &middot; <b>'+(mem?(+mem[1]/1e9).toFixed(1)+' GB':'&mdash;')+'</b> in containers';
  ctable('dgxctr','dgx');
}
async function prod(){
  const P='{instance="prod-podcast"}';
  draw('p_cpu','100-avg(rate(node_cpu_seconds_total{instance="prod-podcast",mode="idle"}[5m]))*100',x=>x.toFixed(0)+'%',100);
  {const mt=await g1('node_memory_MemTotal_bytes'+P),gb=mt?(+mt[1]/1073741824).toFixed(0):'?';
   draw('p_mem','100-node_memory_MemAvailable_bytes'+P+'/node_memory_MemTotal_bytes'+P+'*100',x=>x.toFixed(0)+'% <span class=muted>/ '+gb+' GB</span>',100);}
  {const pu=await g1('100*(1-node_filesystem_avail_bytes{instance="prod-podcast",mountpoint="/"}/node_filesystem_size_bytes{instance="prod-podcast",mountpoint="/"})');
   draw('p_disk','node_filesystem_avail_bytes{instance="prod-podcast",mountpoint="/"}',x=>(x/1073741824).toFixed(0)+' GB'+(pu?' <span class=muted>'+(+pu[1]).toFixed(0)+'% used</span>':''));}
  draw('p_io','sum(rate(node_disk_read_bytes_total'+P+'[2m]))+sum(rate(node_disk_written_bytes_total'+P+'[2m]))',x=>(x/1048576).toFixed(2)+' MB/s');
  draw('p_net','sum(rate(node_network_receive_bytes_total'+P+'[2m]))+sum(rate(node_network_transmit_bytes_total'+P+'[2m]))',x=>(x/1048576).toFixed(2)+' MB/s');
  const L=x=>x?(+x[1]).toFixed(2):'&mdash;';
  const l1=await g1('node_load1'+P),l5=await g1('node_load5'+P),l15=await g1('node_load15'+P);
  const up=await g1('node_time_seconds'+P+'-node_boot_time_seconds'+P);
  const pr=document.getElementById('prodrow');if(pr)pr.innerHTML='Load <b>'+L(l1)+' / '+L(l5)+' / '+L(l15)+'</b> &middot; Up <b>'+(up?fmtUp(up[1]):'&mdash;')+'</b>';
  const pr1=await g1('count(container_uptime_seconds{box="prod",state="running"})'),pt1=await g1('count(container_uptime_seconds{box="prod"})');
  const pd=document.getElementById('pdocker');if(pd)pd.innerHTML='<b>'+(pr1?pr1[1]:'0')+'/'+(pt1?pt1[1]:'&mdash;')+'</b> running';
  ctable('pctr','prod');
}
async function fleet(){
  const N=x=>x?(+x[1]).toFixed(0):'&mdash;';
  // needs-you = actionable-now only (bug queue + escalations); config-enhancement
  // and cleanup drafts are Fleet-3 BACKLOG, not operator debt (2026-08-05)
  const qd=await g1('sum(last_over_time(signal_fleet_queue_depth{kind="bug"}[2h]))');
  const esc=await g1('sum(last_over_time(signal_fleet_escalations_7d[2h]))');
  const dec=await g1('sum(count_over_time(signal_fleet_disposition{disposition!="recurrence"}[24h]))');
  const sp=await g1('sum(last_over_time(fleetd_spend_day[2h]))');
  const d=new Date(),mS=Math.max(3600,Math.floor((d-new Date(d.getFullYear(),d.getMonth(),1))/1000));
  const dayS=Math.max(3600,Math.floor((d-new Date(d.getFullYear(),d.getMonth(),d.getDate()))/1000));
  const mo=await g1('sum(sum_over_time(signal_fleet_cost_usd['+mS+'s]))');
  const al=await g1('sum(sum_over_time(signal_fleet_cost_usd[180d]))'); // VM retention = 6mo
  const tkD=await g1('sum(sum_over_time(signal_fleet_tokens['+dayS+'s]))');
  const tkM=await g1('sum(sum_over_time(signal_fleet_tokens['+mS+'s]))');
  const tkA=await g1('sum(sum_over_time(signal_fleet_tokens[180d]))');
  const set=(id,html)=>{const e=document.getElementById(id);if(e)e.innerHTML=html;};
  const tot=(qd?+qd[1]:0)+(esc?+esc[1]:0);
  const cv=v=>'<div class=cv>'+v+'</div>';
  set('f_inbox',cv((qd||esc)?String(tot):'&mdash;'));
  set('f_esc',cv(N(esc)));set('f_dec',cv(N(dec)));
  const $=x=>x?'$'+(+x[1]).toFixed(2):'$0.00';
  const T=x=>{if(!x)return '0';const v=+x[1];return v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'k':v.toFixed(0);};
  const duo=(c,t)=>cv($(c))+'<div class=muted style="font-size:12px">'+T(t)+' tok</div>';
  // previous calendar month: a window of its length that ends at this month's start
  const pS=Math.floor((new Date(d.getFullYear(),d.getMonth(),1)-new Date(d.getFullYear(),d.getMonth()-1,1))/1000);
  const prevSum=m=>g1('sum(sum_over_time('+m+'['+pS+'s] offset '+mS+'s))');
  const last=(c,t)=>'<div class=muted style="font-size:12px">last month '+$(c)+' &middot; '+T(t)+' tok</div>';
  const moP=await prevSum('signal_fleet_cost_usd'),tkP=await prevSum('signal_fleet_tokens');
  set('f_spend',duo(sp,tkD));set('f_month',duo(mo,tkM)+last(moP,tkP));set('f_total',duo(al,tkA));
  // bug-fix fleet row — zeros until chains run; same accounting shape
  const bs=await g1('sum(count_over_time(bugfix_fleet_flow{state="shipped"}[7d]))');
  const bx=await g1('sum(count_over_time(bugfix_fleet_flow{state=~"stuck|needs-info"}[7d]))');
  const be=await g1('sum(count_over_time(bugfix_fleet_cost_usd[7d]))');
  const bmo=await g1('sum(sum_over_time(bugfix_fleet_cost_usd['+mS+'s]))');
  const bal=await g1('sum(sum_over_time(bugfix_fleet_cost_usd[180d]))');
  const btM=await g1('sum(sum_over_time(bugfix_fleet_tokens['+mS+'s]))');
  const btA=await g1('sum(sum_over_time(bugfix_fleet_tokens[180d]))');
  const N0=x=>x?(+x[1]).toFixed(0):'0'; // no series = no chains yet; the dashboard shows 0 too (or vector(0))
  set('b_ship',cv(N0(bs)));set('b_stuck',cv(N0(bx)));set('b_ep',cv(N0(be)));
  const bmoP=await prevSum('bugfix_fleet_cost_usd'),btP=await prevSum('bugfix_fleet_tokens');
  set('b_month',duo(bmo,btM)+last(bmoP,btP));set('b_total',duo(bal,btA));
  try{const r=await(await fetch('https://api.github.com/search/issues?q=owner%3Achipi+is%3Aissue+is%3Aopen+label%3A%22triage-fleet%2Factionable%22')).json();
    set('b_route',cv(typeof r.total_count==='number'?String(r.total_count):'&rarr;'));}
  catch(e){set('b_route',cv('&rarr;'));}
  // One card per OpenRouter key, every workspace (openrouter-spend.sh, provisioning key,
  // 10m cadence): big number = month-to-date as OpenRouter bills it; small = workspace and
  // lifetime total. Sorted by lifetime spend; the lifetime column sums to the account total.
  const ksel='max by (key, workspace) (last_over_time(openrouter_key_usd{window="WIN"}[2h]))';
  const kt=await q(ksel.replace('WIN','total')), km=await q(ksel.replace('WIN','month'));
  const mon={};for(const r of km)mon[r.metric.key+'|'+r.metric.workspace]=r.value;
  // Last month = the final month-to-date sample before the UTC month turned (OpenRouter's
  // month is UTC; the collector samples every 10m, so up to ~10m of the month's end is missed).
  // Per-key series start 2026-11-02; until they span a whole month, keys that had a vertical
  // series fall back to it. No history at all shows a dash, never a made-up 0.
  const u0=Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),1),uS=Math.max(60,Math.floor((d-u0)/1000));
  const upS=Math.floor((u0-Date.UTC(d.getUTCFullYear(),d.getUTCMonth()-1,1))/1000);
  const prevQ=sel=>q('max by (key, workspace, vertical) (last_over_time('+sel+'['+upS+'s] offset '+uS+'s))');
  const prv={};for(const r of await prevQ('openrouter_key_usd{window="month"}'))prv[r.metric.key+'|'+r.metric.workspace]=r.value;
  const vtk={gateway:'bugfleet-key',podcast:'podcast-scraper-prod',orrery:'orrery lab key',evals:'evals-harness'};
  const prvV={};for(const r of await prevQ('openrouter_vertical_usd{window="month"}'))if(vtk[r.metric.vertical])prvV[vtk[r.metric.vertical]]=r.value;
  const lastK=r=>{const k=r.metric.key+'|'+r.metric.workspace,v=prv[k]||prvV[r.metric.key];return v?$(v):'&mdash;';};
  const hx=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  kt.sort((a,b)=>b.value[1]-a.value[1]);
  set('v_keys', kt.length ? kt.map(r=>'<a class=card href="'+G+'/d/llm-gateway"><h3>'+hx(r.metric.key)+'</h3>'+
    cv($(mon[r.metric.key+'|'+r.metric.workspace])+' <span class=muted style="font-size:12px;font-weight:400">this month</span>')+
    '<div class=muted style="font-size:12px">last month '+lastK(r)+'</div>'+
    '<div class=muted style="font-size:12px">'+$(r.value)+' lifetime &middot; '+hx(r.metric.workspace)+'</div></a>').join('') : '<div class=muted>no key data</div>');
}
async function delivery(){
  const set=(id,html)=>{const e=document.getElementById(id);if(e)e.innerHTML=html;};
  const cv=v=>'<div class=cv>'+v+'</div>';
  const N=x=>x?(+x[1]).toFixed(0):'&mdash;';
  const up=await g1('sum(up{job="delivery"})'),tot=await g1('count(up{job="delivery"})');
  set('dl_up',cv((up?(+up[1]).toFixed(0):'0')+'/'+(tot?(+tot[1]).toFixed(0):'0')));
  set('dl_sent',cv(N(await g1('sum(increase(delivery_sent_total{status="delivered"}[24h]))'))));
  const br=await g1('sum(rate(delivery_sent_total{status=~"bounced|complaint"}[1h]))/clamp_min(sum(rate(delivery_sent_total{status=~"delivered|bounced|complaint"}[1h])),1)*100');
  set('dl_bounce',cv(br?(+br[1]).toFixed(1)+'%':'0%'));
  set('dl_dead',cv(N(await g1('sum(increase(delivery_sent_total{status="dead_lettered"}[24h]))'))));
  set('dl_pending',cv(N(await g1('sum(delivery_batch_pending)'))));
  const ca=await g1('max(delivery_events_cursor_age_seconds)');
  set('dl_cursor',cv(ca?fmtUp(ca[1]):'&mdash;'));
  // Lamp = the delivery alert rules (rules.yaml delivery-*): red when a worker is down; amber on
  // bounce/complaint >5%, a dead-letter in the last hour, the events cursor older than 1h, or
  // mail pending with nothing sent for 1h; grey when there are no workers to read.
  const n=x=>x?+x[1]:0, t=tot?+tot[1]:0;
  const dead1=await g1('sum(increase(delivery_sent_total{status="dead_lettered"}[1h]))');
  const sent1=await g1('sum(increase(delivery_sent_total{status="delivered"}[1h]))');
  const pend=await g1('sum(delivery_batch_pending)');
  const amber=n(br)>5||n(dead1)>0||n(ca)>3600||(n(pend)>0&&n(sent1)===0);
  const st=document.getElementById('st_delivery');
  if(st)st.className='dot '+(!t?'stale':(n(up)<t?'down':(amber?'mid':'up')));
}
async function hetzner(){
  // Hetzner status bulletins that touch us (infra/hetzner-status: correlated with prod's
  // datacenters in ours.json). hetzner_status_active is re-pushed every 10 min while a bulletin
  // is ongoing or starts within 7 days (direct/nearby) or is ongoing (service); empty = no bar.
  const el=document.getElementById('hetznerbar');if(!el)return;
  const rows=await q('last_over_time(hetzner_status_active{instance="homelab"}[15m])');
  if(!rows.length){el.innerHTML='';return;}
  const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const when=m=>{const s=m.start?new Date(m.start):null,e=m.end?new Date(m.end):null,f=d=>d.toISOString().slice(0,16).replace('T',' ')+'Z';
    return m.phase==='upcoming'?'starts '+(s?f(s):'?'):'ongoing'+(e?' until '+f(e):'')+(s?', since '+f(s):'');};
  const order={direct:0,nearby:1,service:2},cls={direct:'crit',nearby:'warn',service:'plumb'},
        what={direct:'our datacenter (prod-podcast, NBG1-DC3)',nearby:'near us (same city)',service:'a Hetzner service we use'};
  rows.sort((a,b)=>(order[a.metric.relevance]??9)-(order[b.metric.relevance]??9));
  el.innerHTML=rows.map(r=>{const m=r.metric;return '<a class="abar '+(cls[m.relevance]||'plumb')+'" href="'+esc(m.link)+'">'
    +'<span class=hz>Hetzner &middot; '+esc(m.kind)+' &middot; '+esc(what[m.relevance]||m.relevance)+'</span><b>'+esc(m.category)+'</b> &mdash; '+esc(m.title)+' <span style="opacity:.75">('+esc(when(m))+')</span></a>';}).join('');
}
async function cloudflare(){
  // Cloudflare status items that are ours (infra/cloudflare-edge/ours.json + PoPs carrying our
  // traffic): an incident listing one of our components is red, a degraded component of ours
  // amber, maintenance on a PoP of ours muted. Re-pushed every 5 min while true; empty = no bar.
  const el=document.getElementById('cfbar');if(!el)return;
  const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const f=s=>s?String(s).slice(0,16).replace('T',' ')+'Z':'';
  const inc=await q('last_over_time(cloudflare_status_incident{instance="homelab",relevance="direct"}[10m])');
  const comp=await q('last_over_time(cloudflare_status_component{instance="homelab"}[10m])');
  const mnt=await q('last_over_time(cloudflare_status_maintenance{instance="homelab"}[10m])');
  const bar=(cls,href,tag,body)=>'<a class="abar '+cls+'"'+(href?' href="'+esc(href)+'"':'')+'><span class=hz>Cloudflare &middot; '+tag+'</span>'+body+'</a>';
  el.innerHTML=inc.map(r=>{const m=r.metric;return bar('crit',m.link,'incident on what we use','<b>'+esc(m.name)+'</b> &mdash; '+esc(m.components)+' <span style="opacity:.75">('+esc(m.impact)+', '+esc(m.status)+')</span>');}).join('')
    +comp.map(r=>{const m=r.metric;return bar('warn','https://www.cloudflarestatus.com/',m.kind==='pop'?'a PoP carrying our traffic':'a service we use','<b>'+esc(m.name)+'</b> &mdash; '+esc(String(m.status).replace(/_/g,' ')));}).join('')
    +mnt.map(r=>{const m=r.metric;return bar(m.status==='in_progress'?'warn':'plumb',m.link,'maintenance','<b>'+esc(m.components)+'</b> &mdash; '+(m.status==='in_progress'?'in progress':'starts '+esc(f(m.start)))+(m.end?' until '+esc(f(m.end)):''));}).join('');
}
async function uptime(){
  // Outside-in availability per probed endpoint (job site-probe). The long windows are
  // subqueries over 1-minute steps, so they are refreshed every 5 minutes, not every 30s.
  const tb=document.getElementById('uptbl');if(!tb)return;
  const P='probe_success{job="site-probe",run_id=""}';
  const OK='(max by (host) ('+P+') and on () (last_over_time(mini_vm_egress_ok{instance="homelab",target="internet"}[5m]) == 1))';
  const byHost=async(query)=>{const m={};(await q(query)).forEach(r=>m[r.metric.host]=+r.value[1]);return m;};
  if(!uptime.c||Date.now()-uptime.t>300000){
    uptime.c={d1:await byHost('avg_over_time('+OK+'[24h:1m])'),d7:await byHost('avg_over_time('+OK+'[7d:1m])'),d30:await byHost('avg_over_time('+OK+'[30d:1m])')};
    uptime.t=Date.now();
  }
  const c=uptime.c;
  const cur=await byHost('max by (host) (last_over_time('+P+'[3m]))');
  const ms=await byHost('max by (host) (last_over_time(probe_duration_seconds{job="site-probe"}[3m]))');
  const E='{instance="homelab",class=~"5xx_unreachable|5xx_server",window="';
  const e24=await byHost('sum by (host) (last_over_time(cloudflare_edge_requests'+E+'24h"}[15m]))');
  const e1=await g1('sum(last_over_time(cloudflare_edge_requests'+E+'1h"}[15m]))');
  const sec=await g1('sum(last_over_time(cloudflare_security_events{instance="homelab"}[15m]))');
  const eg=await g1('last_over_time(mini_vm_egress_ok{instance="homelab",target="internet"}[5m])');
  const set=(id,h)=>{const el=document.getElementById(id);if(el)el.innerHTML=h;};
  const hosts=Object.keys(cur).sort();
  const col=v=>v==null?'':(v>=0.999?'':(v>=0.99?'color:#d29922':'color:#f85149'));
  const pct=v=>v==null||isNaN(v)?'&mdash;':(v>=0.99995?'100%':(v*100).toFixed(2)+'%');
  const avg=m=>{const v=hosts.map(h=>m[h]).filter(x=>x!=null);return v.length?v.reduce((a,b)=>a+b,0)/v.length:null;};
  const worst=m=>{let w=null;hosts.forEach(h=>{if(m[h]!=null&&(w==null||m[h]<m[w]))w=h;});return w;};
  const offline=eg&&+eg[1]===0;
  const down=hosts.filter(h=>cur[h]===0);
  const agg=document.getElementById('up_agg');
  if(agg)agg.className='dot '+(!hosts.length||offline?'stale':(down.length?'down':(hosts.some(h=>c.d1[h]!=null&&c.d1[h]<0.999)?'mid':'up')));
  set('up_now',!hosts.length?'<div class=cv>&mdash;</div>':'<div class=cv style="'+(down.length?'color:#f85149':'')+'">'+(hosts.length-down.length)+'/'+hosts.length+'</div><span class=muted>'+(offline?'mini offline: unknown':(down.length?'down: '+down.join(', '):'all answering'))+'</span>');
  for(const [id,k] of [['up_24h','d1'],['up_7d','d7'],['up_30d','d30']]){const a=avg(c[k]),w=worst(c[k]);
    set(id,'<div class=cv style="'+col(a)+'">'+pct(a)+'</div><span class=muted>'+(w&&c[k][w]<0.99995?'lowest: '+w+' '+pct(c[k][w]):'every endpoint')+'</span>');}
  set('up_edge','<div class=cv>'+(e1?(+e1[1]).toFixed(0):'&mdash;')+'</div><span class=muted>all hosts, Cloudflare</span>');
  set('up_sec','<div class=cv>'+(sec?(+sec[1]).toFixed(0):'&mdash;')+'</div><span class=muted>WAF / bots</span>');
  tb.innerHTML=hosts.length?hosts.map(h=>{const u=cur[h];return '<tr><td>'+h+'</td><td><span class=dot style="background:'+(offline?'#7a7a8c':(u?'#3fb950':'#f85149'))+'"></span></td>'
    +['d1','d7','d30'].map(k=>'<td class=u style="'+col(c[k][h])+'">'+pct(c[k][h])+'</td>').join('')
    +'<td class=u>'+(e24[h]!=null?e24[h].toFixed(0):'0')+'</td><td class=u>'+(ms[h]!=null?(ms[h]*1000).toFixed(0)+' ms':'&mdash;')+'</td></tr>';}).join('')
    :'<tr><td class=muted colspan=7>no probe data</td></tr>';
}
async function alerts(){
  // One consolidated notification surface: EVERYTHING alert-worthy is (or
  // becomes) a Grafana rule over VM/VLogs — disk, apps, security, delivery,
  // fleet substrate, LLM billing — so the banner renders ONE truth, not N
  // platform integrations. Plumbing states (DatasourceNoData/Error) are
  // wiring problems: shown muted, never as incidents.
  const el=document.getElementById('alertbar');if(!el)return;
  let list=[];
  try{list=await(await fetch('/grafana/api/alertmanager/grafana/api/v2/alerts',{headers:{Authorization:'Bearer '+GTOK}})).json();}catch(e){el.innerHTML='';return;}
  const PLUMB=new Set(['DatasourceNoData','DatasourceError','Watchdog']);
  const act=list.filter(a=>(a.status||{}).state==='active');
  const seen=new Set(),uniq=[];
  for(const a of act){const k=(a.labels||{}).alertname+'|'+((a.labels||{}).instance||'');if(!seen.has(k)){seen.add(k);uniq.push(a);}}
  const plumb=uniq.filter(a=>PLUMB.has((a.labels||{}).alertname));
  const crit=uniq.filter(a=>!PLUMB.has((a.labels||{}).alertname)&&(a.labels||{}).severity==='critical');
  const warn=uniq.filter(a=>!PLUMB.has((a.labels||{}).alertname)&&(a.labels||{}).severity!=='critical');
  const line=a=>{const l=a.labels||{},an=(a.annotations||{});let t=l.alertname;if(l.instance)t+=' · '+l.instance;const s=an.summary?' — '+an.summary.slice(0,110):'';return '<b>'+t+'</b>'+s+(l.meta==='true'?' <span style="opacity:.7">[substrate — yours alone]</span>':'');};
  let html='';
  if(crit.length)html+='<a class="abar crit" href="'+G+'/alerting/list">&#128308; '+crit.map(line).join('<br>')+'</a>';
  if(warn.length)html+='<a class="abar warn" href="'+G+'/alerting/list">&#9888;&#65039; '+warn.map(line).join('<br>')+'</a>';
  if(plumb.length)html+='<a class="abar plumb" href="'+G+'/alerting/list">'+plumb.length+' plumbing alert(s) (NoData/Error) — observability wiring, not incidents</a>';
  el.innerHTML=html;el.dataset.warn=warn.length;el.dataset.plumb=plumb.length;
}
async function fresh(){const now=Date.now()/1000,age=x=>x?Math.round(now-+x[0])+'s ago':'no data';const mc=await g1('mini_cpu_used_percent'),dg=await g1('DCGM_FI_DEV_GPU_TEMP'),pc=await g1('node_load1{instance="prod-podcast"}');const el=document.getElementById('fresh');if(el)el.innerHTML='collectors &middot; mini '+age(mc)+' &middot; dgx '+age(dg)+' &middot; prod '+age(pc);
  // box traffic lights: green = fresh samples (<3m), gray = lagging (VM's
  // instant lookback still returns it), red = gone (no sample in ~5m —
  // exactly how a dark box like the DGX presents)
  const dot=(id,v)=>{const e=document.getElementById(id);if(!e)return;let c='down';if(v){const a=now-+v[0];c=a<180?'up':'stale';}e.className='dot '+c;e.title=v?Math.round(now-+v[0])+'s since last sample':'no samples >5m — box dark?';};
  dot('st_mini',mc);dot('st_dgx',dg);dot('st_prod',pc);}
async function podcastHealth(){
  // prod-ops-health traffic lights (podcast_scraper #1876). Values: 1 green / 0.5 orange
  // (failed but not customer-impacting) / 0 red. STALENESS OVERRIDES GREEN: the pusher runs
  // daily at 06:00 UTC, so >26h without a sample means the health check itself is dead — render
  // grey "STALE", never a reassuring green from old data. last_over_time(28h) still finds the
  // sample; the timestamp metric carries when it was really taken.
  const A='{app="podcast"}';
  const ts=await g1('last_over_time(prod_ops_health_last_run_timestamp'+A+'[28h])');
  const agg=await g1('last_over_time(prod_ops_health_aggregate'+A+'[28h])');
  const now=Date.now()/1000, stale=!ts||now-(+ts[1])>26*3600;
  const cls=v=>stale?'stale':(+v===1?'up':(+v===0?'down':'mid'));
  const word=v=>stale?'STALE':(+v===1?'GREEN':(+v===0?'RED':'ORANGE'));
  const set=(id,html)=>{const e=document.getElementById(id);if(e)e.innerHTML=html;};
  const light=(id,v)=>set(id,'<div class=cv><span class="dot '+(v==null?'stale':cls(v[1]))+'"></span>'+(v==null?'&mdash;':word(v[1]))+'</div>');
  light('ph_overall',agg);
  const hd=document.getElementById('ph_agg');if(hd)hd.className='dot '+(agg==null?'stale':cls(agg[1]));
  const checks=await q('last_over_time(prod_ops_health_check'+A+'[28h])');
  // The pusher owns the check list — a check it adds that this page doesn't know yet must
  // still be VISIBLE, so grow a card for it (before "Last check") instead of dropping it.
  const grow=id=>{const row=document.querySelector('#podcast_prod .charts');const age=document.getElementById('ph_age');if(!row||!age)return;
    const a=document.createElement('a');a.className='card';a.href='https://github.com/chipi/infra/actions/workflows/prod-ops-health.yml';
    a.innerHTML='<h3></h3><div id="'+id+'">&hellip;</div>';a.querySelector('h3').textContent=id.slice(3).replace(/_/g,' ');
    row.insertBefore(a,age.closest('a.card'));};
  const seen=new Set();
  for(const r of checks){const id='ph_'+r.metric.check;seen.add(id);if(!document.getElementById(id))grow(id);light(id,r.value);}
  // checks the page expects but VM didn't return → grey dash, never a stuck ellipsis
  for(const c of ['gateway','o11y_logs','o11y_metrics','o11y_traces','o11y_glitchtip'])if(!seen.has('ph_'+c))light('ph_'+c,null);
  if(ts){const h=Math.floor((now-+ts[1])/3600);set('ph_age','<div class=cv>'+(h<1?'&lt;1':h)+'h ago</div>'+(stale?'<div class=muted style="font-size:12px">STALE &mdash; check not running</div>':''));}
  else set('ph_age','<div class=cv>&mdash;</div><div class=muted style="font-size:12px">no run in 28h</div>');
}
// ---- Service cards (Hosts tab): one card per key service, grouped. Each reads the shared
// container inventory (container_uptime_seconds{box}), memory/CPU (cadvisor on prod and the
// DGX, mini_container_* on the mini), outside probes for public hosts, and the per-host health
// checks. Lamp: red = a container not running, a probe failing now or a health check down;
// amber = 24h availability under 99.9%, memory over 90% of its limit, or unhealthy/starting;
// grey = no data, or (DGX) not expected in the current GPU mode.
const DGXMODE={prod:'prod-vllm :8003','research-vllm':'autoresearch vLLM :8003',code:'coder-next :9000',
  ollama:'Ollama :11434','research-ollama':'Ollama :11434',free:'nothing',
  'judging-a':'judge A :8003','judging-b':'judge B :8003','judging-qwen-next':'judge Qwen-Next :8003','judging-nemotron':'judge Nemotron :8003'};
const SVCS={
 prod:[
  ['Close Listening','Player app',['player-api-1'],['closelistening.app']],
  ['Close Listening','MCP',['player-mcp-1'],['mcp.closelistening.app']],
  ['Close Listening','Obs',['player-obs-1'],['obs.closelistening.app']],
  ['Close Listening','Operator',['operator-api-1','operator-viewer-1'],[]],
  ['Close Listening','Control plane',['compose-api-1','compose-viewer-1'],[]],
  ['Close Listening','Learning app',['player-learning-app-1'],[]],
  ['Close Listening','Background jobs',['player-board-summarizer-1','player-digest-scheduler-1'],[]],
  ['Orrery','Web',['orrery-web'],['www.orrerylearn.com']],
  ['Orrery','Lab API',['orrery-lab-api'],['lab-api.orrerylearn.com']],
  ['Orrery','MCP',['orrery-mcp'],['mcp.orrerylearn.com']],
  ['Evals','Evals',['evals-nginx','evals-inspector','evals-mcp'],['evals.humancopilot.eu']],
  ['Websites','Static sites',['websites-nginx'],['www.humancopilot.eu','www.markodragoljevic.com','airandspacehistory.com','www.devwhateverops.com']],
  ['Shared','LiteLLM (prod)',['litellm','litellm-postgres','litellm-spend-push'],[]],
  ['Shared','Observability',['alloy','cadvisor'],[]]],
 mini:[
  ['Observability','Grafana',['grafana'],[],'grafana'],
  ['Observability','VictoriaMetrics',['victoriametrics'],[],'victoriametrics'],
  ['Observability','VictoriaLogs',['victorialogs'],[],'victorialogs'],
  ['Observability','VictoriaTraces',['victoriatraces'],[],'victoriatraces'],
  ['Observability','GlitchTip',['glitchtip-web-1','glitchtip-worker-1','glitchtip-postgres-1','glitchtip-redis-1'],['telemetry.closelistening.app','telemetry.orrerylearn.com','telemetry.humancopilot.eu'],'glitchtip'],
  ['Observability','Langfuse',['langfuse-langfuse-web-1','langfuse-langfuse-worker-1','langfuse-clickhouse-1','langfuse-postgres-1','langfuse-redis-1','langfuse-minio-1'],[],'langfuse'],
  ['Observability','Umami',['umami','umami-db'],['analytics.closelistening.app','analytics.orrerylearn.com','analytics.humancopilot.eu','analytics.markodragoljevic.com','analytics.airandspacehistory.com'],'umami'],
  ['Observability','Alloy',['alloy-homelab'],[]],
  ['Gateway','LiteLLM (dev)',['litellm','litellm-postgres'],[],'litellm'],
  ['Apps','Delivery',['delivery-email','delivery-events','delivery-push'],[]],
  ['Apps','Evals docs + compare',['evals-docs','evals-compare'],[]],
  ['Apps','Edge (Caddy)',['caddy'],[]],
  ['Apps','Hub',['homelab-home'],[]],
  ['Home','Home automation',['home-assistant','mosquitto','unifi-poller'],[]]],
 dgx:[
  ['GPU','Main LLM',[],[],'MAIN'],
  ['GPU','Translate',['vllm-translate'],[],'translate',['prod','ollama']],
  ['Speech','Speaches',['faster-whisper'],[],'whisper'],
  ['Speech','Diarization',['pyannote'],[],'diarization'],
  ['Speech','MOSS',['moss'],[],'moss'],
  ['Apps','LibreChat',['librechat-api','librechat-mongodb','librechat-meilisearch'],[]],
  ['Collectors','Collectors',['alloy','cadvisor','dcgm-exporter'],[],'cadvisor']]};
const SVCLAMP={},SVCCTR={};
async function services(){
  const byName=async(qq,key='name')=>{const m={};(await q(qq)).forEach(r=>m[r.metric[key]]=r);return m;};
  const val=r=>r?+r.value[1]:null;
  const gb=b=>b==null?'?':(b<1e9?Math.round(b/1e6)+' MB':(b/1e9>=10?(b/1e9).toFixed(0):(b/1e9).toFixed(1))+' GB');
  const hx=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const probeNow=await byName('max by (host) (last_over_time(probe_success{job="site-probe",run_id=""}[3m]))','host');
  const probeMs=await byName('max by (host) (last_over_time(probe_duration_seconds{job="site-probe"}[3m]))','host');
  const d1=(uptime.c&&uptime.c.d1)||{};
  const mode0=(await q('last_over_time(dgx_gpu_mode[5m])'))[0];
  const dsu=await byName('last_over_time(dgx_service_up[2m])','service');
  const up=n=>dsu[n]?val(dsu[n])===1:null;
  let mode=mode0?mode0.metric.mode:null;
  if(mode==='free'&&up('ollama'))mode=up('translate')?'ollama':'research-ollama';
  const msu=await byName('last_over_time(service_up[2m])','service');
  for(const box of ['prod','mini','dgx']){
    const el=document.getElementById('svc_'+box);if(!el)continue;
    const inst={prod:'prod-podcast',dgx:'dgx-llm-1'}[box];
    const st=await byName('container_uptime_seconds{box="'+box+'"}');
    const mem=inst?await byName('max by (name) (container_memory_working_set_bytes{instance="'+inst+'",name!=""})'):await byName('mini_container_mem_bytes');
    const lim=inst?await byName('max by (name) (container_spec_memory_limit_bytes{instance="'+inst+'",name!=""})'):{};
    const cpu=inst?await byName('sum by (name) (rate(container_cpu_usage_seconds_total{instance="'+inst+'",name!=""}[5m]))*100'):await byName('mini_container_cpu_percent');
    const groups={};
    for(const g of new Set(SVCS[box].map(x=>x[0])))if(!SVCCTR[g]||SVCCTR[g].box===box)SVCCTR[g]={run:0,tot:0,box};
    for(const [g,name,ctrs,hosts,check,modes] of SVCS[box]){
      let title=name,lamp='up',lines=[],why=[];
      if(check==='MAIN'){
        const port=mode==='code'?'coder':(mode==='ollama'||mode==='research-ollama'?'ollama':'vllm8003');
        title='Main LLM';lines.push('mode <b>'+hx(mode||'?')+'</b> &middot; '+hx(DGXMODE[mode]||'?'));
        if(!mode)lamp='stale';else if(mode==='free')lamp='stale';else if(mode==='BROKEN-BOTH'){lamp='down';why.push('two LLMs');}
        else if(up(port)===false){lamp='down';why.push('port closed');}
        const mc={prod:'vllm-prod-vllm'}[mode];  // the other modes' container names are not mapped yet
        if(mc&&st[mc]){lines.push('mem '+gb(val(mem[mc]))+' &middot; cpu '+(val(cpu[mc])||0).toFixed(0)+'%');lines.push('up '+fmtUp(val(st[mc])));}
      }else{
        const off=modes&&mode&&!modes.includes(mode);
        const rows=ctrs.map(c=>st[c]);
        const running=rows.filter(r=>r&&r.metric.state==='running').length;
        const cc=SVCCTR[g]=SVCCTR[g]||{run:0,tot:0,box};if(cc.box===box){cc.run+=running;cc.tot+=ctrs.length;}
        if(ctrs.length){
          if(!rows.some(Boolean))lamp='stale';
          else if(running<ctrs.length&&!off){lamp='down';why.push(running+'/'+ctrs.length+' running');}
          if(rows.some(r=>r&&/unhealthy|starting/.test(r.metric.health||''))&&lamp==='up'){lamp='mid';why.push('health check');}
          const m=ctrs.reduce((a,c)=>a+(val(mem[c])||0),0),l=ctrs.map(c=>val(lim[c])).filter(x=>x&&x<1e15).reduce((a,b)=>a+b,0);
          const c=ctrs.reduce((a,c)=>a+(val(cpu[c])||0),0);
          if(m)lines.push('mem '+gb(m)+(l?' / '+gb(l):'')+' &middot; cpu '+c.toFixed(0)+'%');
          if(l&&m/l>0.9&&lamp==='up'){lamp='mid';why.push('memory over 90% of limit');}
          const upS=rows.filter(Boolean).map(r=>val(r)).filter(x=>x!=null);
          if(upS.length&&running)lines.push('up '+fmtUp(Math.min(...upS)));
        }
        if(check){const ok=box==='dgx'?up(check):(msu[check]?val(msu[check])===1:null);
          if(ok===false&&!off){lamp='down';why.push('health check failed');}}
        if(hosts.length){
          const dn=hosts.filter(h=>probeNow[h]&&val(probeNow[h])===0);
          const av=hosts.map(h=>d1[h]).filter(x=>x!=null),ms=hosts.map(h=>val(probeMs[h])).filter(x=>x!=null);
          const a=av.length?Math.min(...av):null;
          lines.push((hosts.length>1?hosts.length+' hosts &middot; ':'')+'24h '+(a==null?'&mdash;':(a>=0.99995?'100%':(a*100).toFixed(2)+'%'))+(ms.length?' &middot; '+Math.round(Math.max(...ms)*1000)+' ms':''));
          if(dn.length){lamp='down';why.push('down: '+dn.join(', '));}
          else if(a!=null&&a<0.999&&lamp==='up'){lamp='mid';why.push('24h under 99.9%');}
        }
        if(off){lamp='stale';why=['off in mode '+mode];}
      }
      (groups[g]=groups[g]||[]).push('<a class=card href="'+(box==='prod'?G+'/d/prod-infra-containers/containers':(box==='dgx'?DGXDASH:G))+'"><h3><span class="dot '+lamp+'"></span>'+hx(title)+'</h3>'+
        (why.length?'<div class=ln style="color:'+(lamp==='down'?'#f85149':(lamp==='mid'?'#d29922':'#8888aa'))+'">'+hx(why.join(' · '))+'</div>':'')+
        lines.map(x=>'<div class=ln>'+x+'</div>').join('')+'</a>');
    }
    for(const [g,c] of Object.entries(groups)){const ls=c.join('');SVCLAMP[g]=/dot down/.test(ls)?'down':(/dot mid/.test(ls)?'mid':(/dot up/.test(ls)?'up':'stale'));}
    const html=Object.entries(groups).map(([g,c])=>'<h4>'+hx(g)+'</h4><div class=charts>'+c.join('')+'</div>').join('');
    if(el.innerHTML!==html)el.innerHTML=html;
  }
}
// ---- Overview project blocks (Orrery, Evals, Websites), shaped like the Podcast block. No
// health run reports these apps, so a block is built from what is collected: outside probes of
// the project's public hosts, its prod containers (the Hosts service cards' lamps), Cloudflare's
// 24h request and 5xx counts for its hosts, and the app's own metrics where it exports any.
const PROJ=[
 {id:'cl',name:'Close Listening',group:'Close Listening',hosts:['closelistening.app','mcp.closelistening.app','obs.closelistening.app'],
  edge:'(www\\.)?closelistening\\.app|(mcp|obs)\\.closelistening\\.app',umami:['closelistening.app'],keys:['podcast-scraper-prod'],vllm:['NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4']},
 {id:'orrery',name:'Orrery',group:'Orrery',hosts:['www.orrerylearn.com','lab-api.orrerylearn.com','mcp.orrerylearn.com'],
  edge:'(www\\.)?orrerylearn\\.com|(lab-api|mcp)\\.orrerylearn\\.com',umami:['orrerylearn.com'],keys:['orrery lab key']},
 {id:'evals',name:'Evals',group:'Evals',hosts:['evals.humancopilot.eu'],edge:'evals\\.humancopilot\\.eu',umami:['evals.humancopilot.eu'],keys:['evals-harness'],ollama:true},
 {id:'web',name:'Websites',group:'Websites',hosts:['www.humancopilot.eu','www.markodragoljevic.com','airandspacehistory.com','www.devwhateverops.com'],
  edge:'(www\\.)?(humancopilot\\.eu|markodragoljevic\\.com|airandspacehistory\\.com|devwhateverops\\.com)',
  umami:['humancopilot.eu','markodragoljevic.com','airandspacehistory.com','devwhateverops.com'],keys:[]}];
// Umami visitors per site (24h distinct sessions, pageviews), through Grafana's umami-pg
// datasource with the hub's viewer token. Cached 10 minutes: the numbers move slowly.
function spark(d,lo,hi){if(!d||!d.some(x=>x!=null))return '';const xs=d.filter(x=>x!=null),w=56,h=16;
  const mn=lo!=null?Math.min(lo,...xs):0,mx=hi!=null?hi:Math.max(mn+1e-9,...xs,mn===0?1:mn);
  const pts=d.map((x,i)=>x==null?null:(i*(w-2)/(d.length-1)+1).toFixed(1)+','+(h-1-(x-mn)/(mx-mn||1)*(h-2)).toFixed(1)).filter(Boolean).join(' ');
  return ' <svg width='+w+' height='+h+' viewBox="0 0 '+w+' '+h+'" style="vertical-align:middle;margin-left:4px" aria-label="daily visitors, 14 days"><polyline points="'+pts+'" fill=none stroke=#7aa2ff stroke-width=1.5 vector-effect=non-scaling-stroke /></svg>';}
async function umami(){
  if(umami.c&&Date.now()-umami.t<600000)return umami.c;
  const sql="select website_id::text as id, count(distinct session_id) filter (where created_at > now() - interval '24 hours') as v24,"
    +" count(*) filter (where created_at > now() - interval '24 hours' and event_type = 1) as p24,"
    +" count(distinct session_id) as v7, count(*) filter (where event_type = 1) as p7"
    +" from website_event where created_at > now() - interval '7 days' group by 1";
  const out={};
  try{const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
      body:JSON.stringify({queries:[{refId:'A',datasource:{uid:'umami-pg'},rawSql:sql,format:'table'}],from:'now-7d',to:'now'})})).json();
    const f=r.results.A.frames[0],n=f.schema.fields.map(x=>x.name),v=f.data.values,col=k=>v[n.indexOf(k)];
    const byId={};col('id').forEach((id,i)=>byId[id]={v24:+col('v24')[i],p24:+col('p24')[i],v7:+col('v7')[i],p7:+col('p7')[i]});
    const dsql="select website_id::text as id, (now()::date - created_at::date) as ago, count(distinct session_id) as v"
      +" from website_event where created_at > now()::date - 13 group by 1, 2";
    const r2=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
      body:JSON.stringify({queries:[{refId:'B',datasource:{uid:'umami-pg'},rawSql:dsql,format:'table'}],from:'now-14d',to:'now'})})).json();
    const f2=r2.results.B.frames[0],n2=f2.schema.fields.map(x=>x.name),v2=f2.data.values,c2=k=>v2[n2.indexOf(k)];
    const days={};c2('id').forEach((id,i)=>{const a=+c2('ago')[i];if(a>=0&&a<14)(days[id]=days[id]||Array(14).fill(0))[13-a]+= +c2('v')[i];});
    for(const [dom,id] of UMAMI_SITES){const s=byId[id]||{v24:0,p24:0,v7:0,p7:0},k=dom.replace(/^www\./,''),o=out[k]=out[k]||{v24:0,p24:0,v7:0,p7:0,d:Array(14).fill(0)};
      for(const x of ['v24','p24','v7','p7'])o[x]+=s[x];
      (days[id]||[]).forEach((x,i)=>o.d[i]+=x);}
  }catch(e){return umami.c||null;}
  umami.c=out;umami.t=Date.now();return out;
}
// 14 daily points (oldest first) of an instant expression, via query_range at a 1-day step
// ending now. Cached 10 minutes per expression: these move slowly and the subqueries cost.
async function daily(expr){
  daily.c=daily.c||{};const c=daily.c[expr];if(c&&Date.now()-c.t<600000)return c.v;
  const e=Math.floor(Date.now()/1000),st=e-13*86400;let v=null;
  try{const j=await(await fetch('/vm/api/v1/query_range?query='+encodeURIComponent(expr)+'&start='+st+'&end='+e+'&step=86400')).json();
    const r=j.data.result[0];if(r){v=Array(14).fill(null);r.values.forEach(([t,x])=>{const i=Math.round((+t-st)/86400);if(i>=0&&i<14)v[i]=+x;});}}catch(x){}
  daily.c[expr]={t:Date.now(),v};return v;
}
// One row per project, the same columns for all: health (Close Listening: its daily health run;
// the others have none, so containers running + sites up + their service cards), sites, requests,
// visitors (Umami), edge 5xx, and LLM spend this month on the project's own OpenRouter key.
async function projects(){
  const el=document.getElementById('projrows');if(!el)return;
  const um=await umami(),d1=(uptime.c&&uptime.c.d1)||{};
  const now={},ms={};
  (await q('max by (host) (last_over_time(probe_success{job="site-probe",run_id=""}[3m]))')).forEach(r=>now[r.metric.host]=+r.value[1]);
  (await q('max by (host) (last_over_time(probe_duration_seconds{job="site-probe"}[3m]))')).forEach(r=>ms[r.metric.host]=+r.value[1]);
  // LLM spend and tokens over this month's COMPLETED UTC days (OpenRouter's activity has no partial
  // day, so spend uses the same days as tokens): OpenRouter per key, plus the project's local models
  // (prod-vllm's Qwen on the DGX for Close Listening; Ollama on all three machines for Evals, the only
  // Ollama user known). Translate on the DGX exports no token counter, so it is not in this.
  const rg=spendRange('month'),kU={},kT={};
  (await q('sum by (key) (last_over_time(openrouter_model_usd{window="month",key!=""}[2h]))')).forEach(r=>kU[r.metric.key]=+r.value[1]);
  (await q('sum by (key) (last_over_time(openrouter_model_tokens{window="month",key!=""}[2h]))')).forEach(r=>kT[r.metric.key]=+r.value[1]);
  const vT={};if(rg.R)(await q('sum by (model_name) (increase(vllm:prompt_tokens_total{instance="dgx-llm-1"}['+rg.R+'s] offset '+rg.O+'s)) + sum by (model_name) (increase(vllm:generation_tokens_total{instance="dgx-llm-1"}['+rg.R+'s] offset '+rg.O+'s))')).forEach(r=>vT[r.metric.model_name]=+r.value[1]);
  let olT=0;
  if(rg.R)try{const to=Date.now()-rg.O*1000,from=to-rg.R*1000;
    for(const ex of ['job:"ollama" "prompt eval time =" | extract_regexp "prompt eval time = +[0-9.]+ ms / +(?P<n>[0-9]+) tokens" | stats sum(n) as t',
                     'job:"ollama" "eval time =" -"prompt eval time" | extract_regexp "eval time = +[0-9.]+ ms / +(?P<n>[0-9]+) tokens" | stats sum(n) as t']){
      const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
        body:JSON.stringify({queries:[{refId:'O',datasource:{uid:'victorialogs'},expr:ex,queryType:'stats'}],from:String(from),to:String(to)})})).json();
      (r.results.O.frames||[]).forEach(f=>{const v=f.data.values[f.data.values.length-1];olT+= +(v[v.length-1]||0);});}}catch(e){olT=null;}
  const tk=v=>v>=1e9?(v/1e9).toFixed(1)+'B':v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'k':String(Math.round(v));
  const pct=v=>v==null?'&mdash;':(v>=0.99995?'100%':(v*100).toFixed(2)+'%');
  const vis=doms=>{if(!um)return null;const xs=doms.map(d=>um[d]).filter(Boolean);return xs.length?xs.reduce((a,b)=>({v24:a.v24+b.v24,p24:a.p24+b.p24,v7:a.v7+b.v7,p7:a.p7+b.p7,d:a.d.map((x,i)=>x+b.d[i])})):null;};
  // Close Listening health run
  const A='{app="podcast"}',ts=await g1('last_over_time(prod_ops_health_last_run_timestamp'+A+'[28h])'),agg=await g1('last_over_time(prod_ops_health_aggregate'+A+'[28h])');
  const chk=await q('last_over_time(prod_ops_health_check'+A+'[28h])'),nowS=Date.now()/1000,stale=!ts||nowS-(+ts[1])>26*3600;
  const bad=chk.filter(r=>+r.value[1]!==1).map(r=>r.metric.check.replace(/_/g,' '));
  let rows='';
  for(const p of PROJ){
    const E='{instance="homelab",window="24h",host=~`'+p.edge+'`';
    const req=await g1('sum(last_over_time(cloudflare_edge_requests'+E+'}[15m]))');
    const e5=await g1('sum(last_over_time(cloudflare_edge_requests'+E+',class=~"5xx_unreachable|5xx_server"}[15m]))');
    const e4=await g1('sum(last_over_time(cloudflare_edge_requests'+E+',class="4xx"}[15m]))');
    const sRq=await daily('sum(last_over_time(cloudflare_edge_requests'+E+'}[15m]))');
    const dn=p.hosts.filter(h=>now[h]===0),av=p.hosts.map(h=>d1[h]).filter(x=>x!=null),a=av.length?Math.min(...av):null;
    const cc=SVCCTR[p.group],sl=SVCLAMP[p.group]||'stale';
    let lamp,health;
    if(p.id==='cl'){
      lamp=agg==null?'stale':(stale?'stale':(+agg[1]===1?'up':(+agg[1]===0?'down':'mid')));
      const h=ts?Math.floor((nowS-+ts[1])/3600):null;
      health=stale?'health run stale':(bad.length?bad.join(', ')+' not green':(chk.length+'/'+chk.length+' checks'))+(h!=null?' &middot; '+(h<1?'&lt;1':h)+'h ago':'');
      if(dn.length||sl==='down')lamp='down';else if(lamp==='up'&&(sl==='mid'||(a!=null&&a<0.999)))lamp='mid';
    }else{
      lamp=dn.length||sl==='down'?'down':((a!=null&&a<0.999)||sl==='mid'?'mid':(sl==='stale'?'stale':'up'));
      health=(cc&&cc.tot?cc.run+'/'+cc.tot+' containers':'containers &mdash;')+(dn.length?' &middot; down: '+dn.join(', '):((a!=null&&a<0.999)?' &middot; 24h under 99.9%':''));
    }
    const vv=vis(p.umami),spend=p.keys.length?p.keys.reduce((x,k)=>x+(kU[k]||0),0):null;
    const orT=p.keys.reduce((x,k)=>x+(kT[k]||0),0),loT=(p.vllm||[]).reduce((x,m)=>x+(vT[m]||0),0)+(p.ollama&&olT?olT:0),allT=orT+loT;
    const worst=Math.max(0,...p.hosts.map(h=>ms[h]||0));
    rows+='<tr><td><span class="dot '+lamp+'"></span>'+p.name+'</td>'
      +'<td data-l=Health><span class=s>'+health+'</span></td>'
      +'<td data-l=Sites>'+(p.hosts.length-dn.length)+'/'+p.hosts.length+' &middot; '+pct(a)+'<div class=s>slowest '+Math.round(worst*1000)+' ms</div></td>'
      +'<td data-l="Requests 24h">'+(req?Math.round(+req[1]).toLocaleString():'&mdash;')+spark(sRq)+'</td>'
      +'<td data-l="Visitors 24h">'+(vv?vv.v24+spark(vv.d)+'<div class=s>'+vv.p24+' views &middot; 7d '+vv.v7+'</div>':'&mdash;')+'</td>'
      +'<td data-l="Edge 5xx 24h">'+(e5?Math.round(+e5[1]):(req?'0':'&mdash;'))+'</td>'
      +'<td data-l="Edge 4xx 24h">'+(e4?Math.round(+e4[1]).toLocaleString():(req?'0':'&mdash;'))+'</td>'
      +'<td data-l="LLM spend">'+(spend==null?'<span class=s>no key of its own</span>':'$'+spend.toFixed(2)+'<div class=s>'+p.keys.join(', ')+'</div>')+'</td>'
      +'<td data-l="LLM tokens">'+(allT?tk(allT)+'<div class=s>'+(orT?tk(orT)+' OpenRouter':'')+(orT&&loT?' &middot; ':'')+(loT?tk(loT)+' local':'')+'</div>':(p.keys.length||p.vllm||p.ollama?'0':'&mdash;'))+'</td></tr>';
  }
  if(el.innerHTML!==rows)el.innerHTML=rows;
  const nt=document.getElementById('proj_llm_note');if(nt)nt.innerHTML='LLM spend and tokens: this month, '+rg.label+'. Local tokens: prod-vllm (Close Listening), Ollama on the DGX, X3 and MacBook (Evals). Edge counts: Cloudflare, last 24h.';
}
// ---- Spend tab. One period for every number: completed UTC days only, because OpenRouter's
// activity API (spend per key/model/provider) has no partial day. month = this UTC month's
// completed days, 30d / 7d = that many completed days, yesterday = the last completed day.
// VM-based numbers (fleets, DGX tokens) use the same range: [R] offset <seconds since UTC midnight>.
function spendRange(p){
  const n=new Date(),mid=Date.UTC(n.getUTCFullYear(),n.getUTCMonth(),n.getUTCDate()),m0=Date.UTC(n.getUTCFullYear(),n.getUTCMonth(),1);
  const O=Math.max(1,Math.floor((n-mid)/1000)),days={month:Math.round((mid-m0)/86400000),'30d':30,'7d':7,yesterday:1}[p];
  const f=t=>new Date(t).toISOString().slice(0,10);
  return {R:days*86400,O,days,label:days?f(mid-days*86400000)+' to '+f(mid-86400000)+' (UTC, '+days+' day'+(days>1?'s':'')+')':'no completed day this month yet'};
}
async function spendModels(){
  const p=spendPeriod;
  // a slower call for an earlier period must not overwrite the period now selected
  const set=(id,h)=>{if(spendPeriod!==p)return;const e=document.getElementById(id);if(e&&e.innerHTML!==h)e.innerHTML=h;};
  const usd=x=>'$'+(x>=100?x.toFixed(0):x.toFixed(2));
  const tk=v=>v>=1e9?(v/1e9).toFixed(1)+'B':v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'k':String(Math.round(v));
  const hx=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const rg=spendRange(p),W='window="'+p+'"',L='[2h]';
  set('sp_range',rg.label);
  const one=async qq=>{const r=await q(qq);return r.length?+r[0].value[1]:0;};
  const vm=expr=>expr.replace(/\[R\]/g,'['+rg.R+'s] offset '+rg.O+'s');
  // ---- one row per (source, key, vendor, model, served by) ----
  const rows=[],get=(src,key,ven,model,by)=>{const k=[src,key,ven,model,by].join('|');let r=rows.find(x=>x.k===k);if(!r){r={k,src,key,ven,model,by,usd:0,i:0,o:0,req:0};rows.push(r);}return r;};
  const lbl=['key','vendor','model','provider'];
  const orq=async(name,extra)=>q('sum by (key, vendor, model, provider) (last_over_time('+name+'{'+W+',key!=""'+(extra?','+extra:'')+'}'+L+'))');
  (await orq('openrouter_model_usd')).forEach(r=>{const m=r.metric;get('OpenRouter',m.key,m.vendor,m.model.replace(/^[^/]+\//,''),m.provider).usd+= +r.value[1];});
  (await orq('openrouter_model_tokens','kind="prompt"')).forEach(r=>{const m=r.metric;get('OpenRouter',m.key,m.vendor,m.model.replace(/^[^/]+\//,''),m.provider).i+= +r.value[1];});
  (await orq('openrouter_model_tokens','kind="completion"')).forEach(r=>{const m=r.metric;get('OpenRouter',m.key,m.vendor,m.model.replace(/^[^/]+\//,''),m.provider).o+= +r.value[1];});
  (await orq('openrouter_model_requests')).forEach(r=>{const m=r.metric;get('OpenRouter',m.key,m.vendor,m.model.replace(/^[^/]+\//,''),m.provider).req+= +r.value[1];});
  // vLLM on the DGX: its own counters, every caller; vendor read from the model name
  const venOf=n=>{const l=n.toLowerCase();for(const v of ['qwen','gemma','llama','mistral','deepseek','nemotron','gpt-oss','phi'])if(l.includes(v))return v==='gpt-oss'?'openai':(v==='gemma'?'google':(v==='llama'?'meta-llama':(v==='nemotron'?'nvidia':(v==='phi'?'microsoft':(v==='mistral'?'mistralai':v)))));return 'unknown';};
  if(rg.R){
    const vq=async e=>{const m={};(await q(vm(e))).forEach(r=>m[r.metric.model_name]=+r.value[1]);return m;};
    const vi=await vq('sum by (model_name) (increase(vllm:prompt_tokens_total{instance="dgx-llm-1"}[R]))'),vo=await vq('sum by (model_name) (increase(vllm:generation_tokens_total{instance="dgx-llm-1"}[R]))'),
          vr=await vq('sum by (model_name) (increase(vllm:request_success_total{instance="dgx-llm-1"}[R]))');
    for(const n of new Set([...Object.keys(vi),...Object.keys(vo)])){if(!(vi[n]||vo[n]))continue;const r=get('vLLM','DGX vLLM (all callers)',venOf(n),n.split('/').pop(),'DGX');r.i+=vi[n]||0;r.o+=vo[n]||0;r.req+=vr[n]||0;}
  }
  // Ollama on the DGX, X3, MacBook: per-request log lines, no model or key in them
  if(rg.R)try{
    const to=Date.now()-rg.O*1000,from=to-rg.R*1000,names={'dgx-llm-1':'DGX','x3':'X3','macbook':'MacBook'};
    const vls=async expr=>{const m={};const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
        body:JSON.stringify({queries:[{refId:'O',datasource:{uid:'victorialogs'},expr,queryType:'stats'}],from:String(from),to:String(to)})})).json();
      (r.results.O.frames||[]).forEach(f=>{const fl=f.schema.fields[f.schema.fields.length-1],v=f.data.values[f.data.values.length-1];if(fl&&fl.labels)m[fl.labels.instance]=(m[fl.labels.instance]||0)+ +(v[v.length-1]||0);});return m;};
    const oi=await vls('job:"ollama" "prompt eval time =" | extract_regexp "prompt eval time = +[0-9.]+ ms / +(?P<n>[0-9]+) tokens" | stats by (instance) sum(n) as t');
    const oo=await vls('job:"ollama" "eval time =" -"prompt eval time" | extract_regexp "eval time = +[0-9.]+ ms / +(?P<n>[0-9]+) tokens" | stats by (instance) sum(n) as t');
    const oq=await vls('job:"ollama" "prompt eval time =" | stats by (instance) count() as t');
    for(const h of new Set([...Object.keys(oi),...Object.keys(oo)])){const r=get('Ollama','Ollama (no key)','unknown','Ollama models (not logged)',names[h]||h);r.i+=oi[h]||0;r.o+=oo[h]||0;r.req+=oq[h]||0;}
  }catch(e){}
  const sum=(xs,f)=>xs.reduce((a,x)=>a+x[f],0),src=n=>rows.filter(r=>r.src===n);
  // ---- Totals ----
  const today=await one('sum(last_over_time(openrouter_key_usd{window="day"}'+L+'))');
  const fl=rg.R?await one(vm('sum(sum_over_time(signal_fleet_cost_usd[R]))'))+await one(vm('sum(sum_over_time(bugfix_fleet_cost_usd[R]))')):0;
  const cr=await one('max(last_over_time(openrouter_account_usd{kind="credits"}'+L+')) - max(last_over_time(openrouter_account_usd{kind="usage"}'+L+'))');
  const t=n=>sum(src(n),'i')+sum(src(n),'o'),card=(ti,v,sub)=>'<a class=card><h3>'+ti+'</h3><div class=cv>'+v+'</div>'+(sub?'<span class=muted>'+sub+'</span>':'')+'</a>';
  const allT=t('OpenRouter')+t('vLLM')+t('Ollama');
  set('sp_totals',card('Spend (OpenRouter)',usd(sum(src('OpenRouter'),'usd')),Math.round(sum(src('OpenRouter'),'req')).toLocaleString()+' requests &middot; local $0')
    +card('Tokens, all sources',tk(allT),'OpenRouter '+tk(t('OpenRouter'))+' &middot; vLLM '+tk(t('vLLM'))+' &middot; Ollama '+tk(t('Ollama')))
    +card('Local tokens',tk(t('vLLM')+t('Ollama')),'vLLM '+tk(t('vLLM'))+' ('+Math.round(sum(src('vLLM'),'req'))+' req) &middot; Ollama '+tk(t('Ollama'))+' ('+Math.round(sum(src('Ollama'),'req'))+' req)')
    +card('of which fleets',usd(fl),'triage + bug-fix, part of OpenRouter')
    +card('Today so far (OpenRouter)',usd(today),'live, all keys')
    +card('OpenRouter credit left','<span style="'+(cr<10?'color:#f85149':'')+'">'+usd(cr)+'</span>','top up at openrouter.ai'));
  // ---- group helper ----
  const group=f=>{const g={};rows.forEach(r=>{const k=f(r);const x=g[k]=g[k]||{k,usd:0,i:0,o:0,req:0,src:new Set(),rows:[]};x.usd+=r.usd;x.i+=r.i;x.o+=r.o;x.req+=r.req;x.src.add(r.src);x.rows.push(r);});
    return Object.values(g).filter(x=>x.usd>=0.005||x.i+x.o>0).sort((a,b)=>b.usd-a.usd||(b.i+b.o)-(a.i+a.o));};
  const srcTag=x=>[...x.src].join(' + ');
  // ---- By key ----
  const life={};(await q('max by (key) (last_over_time(openrouter_key_usd{window="total"}'+L+'))')).forEach(r=>life[r.metric.key]=+r.value[1]);
  set('sp_keys',group(r=>r.key).map(x=>{const top={};x.rows.forEach(r=>top[r.model]=(top[r.model]||0)+r.usd+(r.i+r.o)*1e-9);
    const tops=Object.entries(top).sort((a,b)=>b[1]-a[1]).slice(0,2).map(e=>hx(e[0]));
    return '<a class="card site"><h3>'+hx(x.k)+'</h3><div class=cv>'+usd(x.usd)+'</div><div class=kv><span>Tokens</span><b>'+tk(x.i+x.o)+'</b><span>Top</span><b>'+(tops.join(', ')||'&mdash;')+'</b>'
      +'<span>Source</span><b>'+srcTag(x)+'</b>'+(life[x.k]!=null?'<span>Lifetime</span><b>'+usd(life[x.k])+'</b>':'')+'</div></a>';}).join('')||'<div class=muted>nothing in this period</div>');
  // ---- By vendor ----
  const vd={};(await q('last_over_time(openrouter_vendor_day_usd'+L+')')).forEach(r=>{(vd[r.metric.vendor]=vd[r.metric.vendor]||{})[r.metric.day]=+r.value[1];});
  const days=[...new Set(Object.values(vd).flatMap(o=>Object.keys(o)))].sort().slice(-14);
  set('sp_vendor',group(r=>r.ven).map(x=>'<a class=card><h3>'+hx(x.k)+'</h3><div class=cv>'+usd(x.usd)+(vd[x.k]?spark(days.map(d=>vd[x.k][d]||0)):'')+'</div><span class=muted>'+tk(x.i+x.o)+' tokens &middot; '+srcTag(x)+'</span></a>').join('')||'<div class=muted>nothing in this period</div>');
  // ---- By model: vendor and model in their own columns ----
  set('sp_models',group(r=>r.src+'|'+r.ven+'|'+r.model).map(x=>{const r0=x.rows[0],keys=[...new Set(x.rows.filter(r=>r.usd>0||r.i+r.o>0).map(r=>r.key))],by=[...new Set(x.rows.map(r=>r.by))];
    return '<tr><td>'+hx(r0.ven)+'</td><td>'+hx(r0.model)+'</td><td class=u>'+r0.src+'</td><td>'+(r0.src==='OpenRouter'?usd(x.usd):'$0')+'</td><td>'+tk(x.i)+' / '+tk(x.o)+'</td><td>'+Math.round(x.req).toLocaleString()+'</td><td class=u>'+hx(keys.join(', '))+'</td><td class=u>'+hx(by.join(', '))+'</td></tr>';}).join('')
    ||'<tr><td class=muted colspan=8>nothing in this period</td></tr>');
  // ---- local models by consumer (mini gateway log) ----
  try{
    const d0=new Date(Date.now()-rg.O*1000-rg.R*1000).toISOString().slice(0,10),d1=new Date(Date.now()-rg.O*1000).toISOString().slice(0,10);
    const sql="SELECT COALESCE(v.key_alias, LEFT(d.api_key,8)) AS k, d.model AS m, SUM(d.prompt_tokens) AS i, SUM(d.completion_tokens) AS o, SUM(d.api_requests) AS r"
      +" FROM \"LiteLLM_DailyUserSpend\" d LEFT JOIN \"LiteLLM_VerificationToken\" v ON v.token = d.api_key"
      +" WHERE d.date >= '"+d0+"' AND d.date < '"+d1+"' AND COALESCE(d.custom_llm_provider,'') <> 'openrouter' AND d.model NOT LIKE 'openrouter/%'"
      +" GROUP BY 1,2 HAVING SUM(d.prompt_tokens)+SUM(d.completion_tokens) > 0 ORDER BY 3 DESC";
    const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
      body:JSON.stringify({queries:[{refId:'L',datasource:{uid:'litellm-pg'},rawSql:sql,format:'table'}],from:'now-31d',to:'now'})})).json();
    const f=r.results.L.frames[0],n=f.schema.fields.map(x=>x.name),c=k=>f.data.values[n.indexOf(k)];
    // prod's gateway: per key x model series pushed by chipi/infra spend-to-vm.sh (box="prod")
    const pr={};for(const [kind,f] of [['prompt','i'],['completion','o']])(await q('sum by (key_alias, model) (last_over_time(litellm_model_tokens{box="prod",window="'+p+'",kind="'+kind+'",provider!="openrouter"}[2h]))')).forEach(r=>{const k=r.metric.key_alias+'|'+r.metric.model;(pr[k]=pr[k]||{i:0,o:0,r:0})[f]+= +r.value[1];});
    (await q('sum by (key_alias, model) (last_over_time(litellm_model_requests{box="prod",window="'+p+'",provider!="openrouter"}[2h]))')).forEach(r=>{const k=r.metric.key_alias+'|'+r.metric.model;(pr[k]=pr[k]||{i:0,o:0,r:0}).r+= +r.value[1];});
    const rowsC=Object.entries(pr).filter(([k,v])=>v.i+v.o>0).sort((a,b)=>(b[1].i+b[1].o)-(a[1].i+a[1].o)).map(([k,v])=>{const [ka,m]=k.split('|');return '<tr><td>prod</td><td>'+hx(ka)+'</td><td>'+hx(m.replace(/^hosted_vllm\//,''))+'</td><td>'+tk(v.i)+' / '+tk(v.o)+'</td><td>'+Math.round(v.r)+'</td></tr>';})
      .concat((c('k')||[]).map((k,i)=>'<tr><td>mini</td><td>'+hx(k)+'</td><td>'+hx(String(c('m')[i]).replace(/^hosted_vllm\//,''))+'</td><td>'+tk(+c('i')[i])+' / '+tk(+c('o')[i])+'</td><td>'+Math.round(+c('r')[i])+'</td></tr>'));
    set('sp_consumers',rowsC.length?rowsC.join(''):'<tr><td class=muted colspan=5>no local-model calls through either gateway in this period</td></tr>');
  }catch(e){set('sp_consumers','<tr><td class=muted colspan=5>gateway logs unavailable</td></tr>');}
}
// ---- Sites tab: one card per probed host, grouped by project, in the Overview card layout.
const SITEGROUPS=[['Close Listening',/closelistening\.app$/],['Orrery',/orrerylearn\.com$/],['Evals',/^evals\.humancopilot\.eu$/],
  ['Websites',/(humancopilot\.eu|markodragoljevic\.com|airandspacehistory\.com|devwhateverops\.com)$/]];
async function siteGroups(){
  const el=document.getElementById('site_groups');if(!el)return;
  const now={},ms={},rq={},er={};
  (await q('max by (host) (last_over_time(probe_success{job="site-probe",run_id=""}[3m]))')).forEach(r=>now[r.metric.host]=+r.value[1]);
  (await q('max by (host) (last_over_time(probe_duration_seconds{job="site-probe"}[3m]))')).forEach(r=>ms[r.metric.host]=+r.value[1]);
  const E='{instance="homelab",window="24h"';
  (await q('sum by (host) (last_over_time(cloudflare_edge_requests'+E+'}[15m]))')).forEach(r=>rq[r.metric.host]=+r.value[1]);
  (await q('sum by (host) (last_over_time(cloudflare_edge_requests'+E+',class=~"5xx_unreachable|5xx_server"}[15m]))')).forEach(r=>er[r.metric.host]=+r.value[1]);
  const um=await umami(),d1=(uptime.c&&uptime.c.d1)||{};
  const pct=v=>v==null?'&mdash;':(v>=0.99995?'100%':(v*100).toFixed(2)+'%');
  const site=h=>h.replace(/^www\./,''),both=(m,h)=>{const a=m[h],b=h.startsWith('www.')?m[site(h)]:m['www.'+h];return a==null&&b==null?null:(a||0)+(b||0);};
  const hosts=Object.keys(now).sort(),groups={};
  for(const h of hosts){const g=(SITEGROUPS.find(([n,re])=>re.test(h))||['Other'])[0];(groups[g]=groups[g]||[]).push(h);}
  const order=SITEGROUPS.map(x=>x[0]).concat(['Other']);
  const html=order.filter(g=>groups[g]).map(g=>'<h4 style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#9a9ac2;margin:14px 0 6px">'+g+'</h4><div class=charts style="max-width:1140px">'
    +groups[g].sort((a,b)=>(um&&um[site(b)]?1:0)-(um&&um[site(a)]?1:0)||a.localeCompare(b)).map(h=>{
      const k=site(h),u=um&&um[k],n=both(rq,h),e=both(er,h),v=d1[h],l=now[h]===0?'down':(v!=null&&v<0.999?'mid':(v==null?'stale':'up'));
      const row=(a,b)=>'<span>'+a+'</span><b>'+b+'</b>';
      return '<a class="card site" href="https://'+h+'" title="'+h+'"><h3><span class="dot '+l+'"></span>'+k+'</h3><div class=kv>'
        +row('Uptime',pct(v)+(ms[h]?' &middot; '+Math.round(ms[h]*1000)+' ms':''))
        +row('Requests',(n!=null?Math.round(n).toLocaleString():'&mdash;')+' &middot; '+(e?Math.round(e):(n!=null?0:'&mdash;'))+' 5xx')
        +row('Visitors',u?u.v24+' &middot; '+u.p24+' views':'&mdash;')+'</div>'
        +(u?spark(u.d).replace(' <svg width=56 height=16','<svg preserveAspectRatio="none"'):'<svg></svg>')+'</a>';}).join('')+'</div>').join('');
  if(el.innerHTML!==html)el.innerHTML=html;
}
// ---- Fleets tab. Triage: needs-you (bug queue + escalations, as before) with the backlog beside
// it, the decision mix, escalations, spend, the last fleetd cycle and the signal sources. Bug-fix:
// issues per stage from bugfix_fleet_issues{flow} (the previous cards read bugfix_fleet_flow and
// bugfix_fleet_cost_usd, which no collector writes, so they showed 0 while 7 issues existed).
async function fleetCards(){
  const set=(id,h)=>{const e=document.getElementById(id);if(e&&e.innerHTML!==h)e.innerHTML=h;};
  const cv=v=>'<div class=cv>'+v+'</div>',mut=t=>'<div class=muted style="font-size:12px">'+t+'</div>';
  const by=async(qq,k)=>{const m={};(await q(qq)).forEach(r=>m[r.metric[k]]=+r.value[1]);return m;};
  const one=async qq=>{const r=await q(qq);return r.length?+r[0].value[1]:null;};
  const usd=x=>'$'+(x||0).toFixed(2);
  // backlog beside needs-you
  const qd=await by('last_over_time(signal_fleet_queue_depth[2h])','kind'),old=await one('max(last_over_time(signal_fleet_queue_oldest_age_seconds[2h]))');
  const bl=Object.entries(qd).filter(([k,v])=>k!=='bug'&&v>0);
  set('fl_backlog',bl.length?'backlog '+bl.map(([k,v])=>v+' '+k).join(' &middot; ')+(old?' &middot; oldest '+fmtUp(old):''):'');
  // decisions: 24h count, 14-day line, 7-day mix
  const dec=await one('sum(count_over_time(signal_fleet_disposition{disposition!="recurrence"}[24h]))');
  const decD=await daily('sum(count_over_time(signal_fleet_disposition{disposition!="recurrence"}[1d]))');
  const mix=await by('sum by (disposition) (count_over_time(signal_fleet_disposition[7d]))','disposition');
  const col={file:'#7aa2ff',recurrence:'#8888aa',escalate:'#d29922',dismiss:'#3d3d63'},tot=Object.values(mix).reduce((a,b)=>a+b,0);
  const bar=tot?'<div style="display:flex;height:6px;border-radius:3px;overflow:hidden;margin:6px 0 4px">'+['file','recurrence','escalate','dismiss'].filter(k=>mix[k]).map(k=>'<span style="flex:'+mix[k]+';background:'+col[k]+'"></span>').join('')+'</div>'
    +mut(['file','recurrence','escalate','dismiss'].filter(k=>mix[k]).map(k=>'<span style="color:'+col[k]+'">&#9632;</span> '+mix[k]+' '+k).join(' &middot; ')+' (7d)'):'';
  set('fl_dec',cv((dec==null?'&mdash;':Math.round(dec))+spark(decD))+bar);
  const esc=await one('sum(last_over_time(signal_fleet_escalations_7d[2h]))'),escD=await daily('sum(count_over_time(signal_fleet_disposition{disposition="escalate"}[1d]))');
  set('fl_esc',cv((esc==null?'&mdash;':Math.round(esc))+spark(escD))+mut('line: escalations per day, 14 days'));
  // spend: this month vs last month, daily line, cost per decision this month
  const n=new Date(),mS=Math.max(3600,Math.floor((n-new Date(n.getFullYear(),n.getMonth(),1))/1000));
  const pS=Math.floor((new Date(n.getFullYear(),n.getMonth(),1)-new Date(n.getFullYear(),n.getMonth()-1,1))/1000);
  const mo=await one('sum(sum_over_time(signal_fleet_cost_usd['+mS+'s]))'),lm=await one('sum(sum_over_time(signal_fleet_cost_usd['+pS+'s] offset '+mS+'s))');
  const decM=await one('sum(count_over_time(signal_fleet_disposition['+mS+'s]))'),spD=await daily('sum(sum_over_time(signal_fleet_cost_usd[1d]))');
  set('fl_spend',cv(usd(mo)+spark(spD))+mut('last month '+usd(lm)+(decM?' &middot; $'+((mo||0)/decM).toFixed(4)+' per decision':'')));
  // last fleetd cycle
  const cy=(await q('last_over_time(fleetd_cycle[1d])'))[0],cs=await one('max(last_over_time(fleetd_cycle_seconds[1d]))'),ct=await one('max(tlast_over_time(fleetd_cycle[1d]))');
  const ok=cy&&cy.metric.outcome==='ok',age=ct?Date.now()/1000-ct:null;
  set('fl_cycle',cv(cy?'<span style="color:'+(ok?'#3fb950':'#f85149')+'">'+cy.metric.outcome+'</span>':'&mdash;')+mut((age!=null?fmtUp(age)+' ago':'no cycle in 24h')+(cs?' &middot; '+cs.toFixed(0)+' s':'')+(cy&&cy.metric.version?' &middot; '+cy.metric.version:'')));
  // sources
  const pr=await by('last_over_time(signal_fleet_probes[1d])','source'),gs=await by('last_over_time(signal_fleet_glitchtip_sync[1d])','kind');
  set('fl_src',cv(Object.keys(pr).length+' sources')+mut('watching '+Object.keys(pr).sort().join(', ')+(gs.mapped!=null?'<br>GlitchTip: '+Math.round(gs.mapped||0)+' mapped &middot; '+Math.round(gs.merged||0)+' merged &middot; '+Math.round(gs.resolved||0)+' resolved'+(gs.errors?' &middot; <span style=color:#f85149>'+Math.round(gs.errors)+' errors</span>':''):'')));
  const tdot=document.getElementById('fl_tdot');if(tdot)tdot.className='dot '+(!cy?'stale':(!ok?'down':(age!=null&&age>7200?'mid':'up')));
  // bug-fix pipeline
  const fl=await by('last_over_time(bugfix_fleet_issues[2h])','flow');
  const stages=['untriaged','triaging','fixing','in-review','changes-requested','approved','fixed','shipped'],sc={shipped:'#3fb950',stuck:'#f85149'};
  const all=stages.concat(['stuck']),total=all.reduce((a,k)=>a+(fl[k]||0),0);
  set('fl_pipe',Object.keys(fl).length?'<div style="display:flex;height:8px;border-radius:4px;overflow:hidden;margin:8px 0 6px;background:#1a1a2b">'+all.filter(k=>fl[k]).map(k=>'<span title="'+k+'" style="flex:'+fl[k]+';background:'+(sc[k]||'#7aa2ff')+';opacity:'+(sc[k]?1:0.45+0.07*stages.indexOf(k))+'"></span>').join('')+'</div>'
    +mut(stages.map(k=>'<span style="'+(fl[k]?'color:#c8c8e0':'')+'">'+k+' <b>'+(fl[k]||0)+'</b></span>').join(' &rarr; ')+(fl.stuck?' &middot; <span style="color:#f85149">stuck <b>'+fl.stuck+'</b></span>':'')+' &middot; '+total+' issues'):'<div class=muted>no data</div>');
  const shD=await daily('max(last_over_time(bugfix_fleet_issues{flow="shipped"}[1d]))'),stD=await daily('max(last_over_time(bugfix_fleet_issues{flow="stuck"}[1d]))');
  set('fl_ship',cv((fl.shipped||0)+spark(shD))+mut('issues shipped (line: 14 days)'));
  set('fl_stuck',cv('<span style="'+((fl.stuck||0)?'color:#f85149':'')+'">'+(fl.stuck||0)+'</span>'+spark(stD))+mut('need you to unblock'));
  const bdot=document.getElementById('fl_bdot');if(bdot)bdot.className='dot '+(!Object.keys(fl).length?'stale':((fl.stuck||0)?'mid':'up'));
}
// Tabs: the hash picks one (#overview default), so links and the back button work.
// Hosts has sub-tabs (#hosts/prod default, #hosts/mini, #hosts/dgx, #hosts/delivery).
const TABS=['overview','sites','hosts','fleets','spend'],SUBS=['prod','mini','dgx','delivery'];
function showTab(){const [h,sb]=location.hash.slice(1).split('/'),t=TABS.includes(h)?h:'overview',u=SUBS.includes(sb)?sb:'prod';
  document.querySelectorAll('section.tab').forEach(e=>e.classList.toggle('on',e.id==='t-'+t));
  document.querySelectorAll('.tabs a').forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#'+t));
  document.querySelectorAll('.sub').forEach(e=>e.classList.toggle('on',e.dataset.sub===u));
  document.querySelectorAll('#t-hosts .subtabs a').forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#hosts/'+u));
  const pv=['month','30d','7d','yesterday'].includes(sb)?sb:'30d';
  document.querySelectorAll('#sp_period a').forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#spend/'+pv));
  if(t==='spend'&&spendPeriod!==pv){spendPeriod=pv;spendModels();}}
let spendPeriod='30d';
addEventListener('hashchange',showTab);showTab();
// Overview cards and the strip copy what the tabs already show: one query per signal.
function mirror(){
  document.querySelectorAll('[data-mirror]').forEach(e=>{const s=document.getElementById(e.dataset.mirror);if(s&&e.innerHTML!==s.innerHTML)e.innerHTML=s.innerHTML;});
  document.querySelectorAll('[data-dot]').forEach(e=>{const s=document.getElementById(e.dataset.dot);if(s)e.className=s.className;});
  document.querySelectorAll('[data-text]').forEach(e=>{const s=document.getElementById(e.dataset.text);if(s)e.textContent=s.textContent.trim();});}
function notices(){
  const bars=['hetznerbar','cfbar','alertbar'].map(i=>document.getElementById(i));
  const crit=bars.flatMap(b=>[...b.querySelectorAll('.abar.crit')]).map(e=>e.outerHTML).join('');
  const cb=document.getElementById('critbar');if(cb.innerHTML!==crit)cb.innerHTML=crit;
  const n=(b,sel)=>b.querySelectorAll(sel).length,a=bars[2].dataset;
  const parts=[[+(a.warn||0),'alert'],[n(bars[0],'.abar:not(.crit)'),'Hetzner'],[n(bars[1],'.abar:not(.crit)'),'Cloudflare'],[+(a.plumb||0),'plumbing']]
    .filter(p=>p[0]).map(p=>p[0]+' '+p[1]+(p[1]==='alert'&&p[0]>1?'s':''));
  const det=document.getElementById('notices');det.hidden=!parts.length;
  const t=parts.length?'Notices: '+parts.join(' &middot; '):'';
  const sm=document.getElementById('nsum');if(sm.innerHTML!==t)sm.innerHTML=t;}
setInterval(()=>{mirror();notices();},2000);
async function overview(){
  const set=(id,h)=>{const e=document.getElementById(id);if(e)e.innerHTML=h;};
  const m=await g1('sum(max by (key, workspace) (last_over_time(openrouter_key_usd{window="month"}[2h])))');
  const c=await g1('max(last_over_time(openrouter_account_usd{kind="credits"}[2h])) - max(last_over_time(openrouter_account_usd{kind="usage"}[2h]))');
  const usd=x=>x?'$'+(+x[1]).toFixed(2):'&mdash;';
  set('ov_month','<div class=cv>'+usd(m)+'</div><div class=muted style="font-size:12px">all keys, UTC month</div>');
  const low=c&&+c[1]<10;
  set('ov_credit','<div class=cv'+(low?' style="color:#f85149"':'')+'>'+usd(c)+'</div><div class=muted style="font-size:12px">'+(low?'under $10: top up':'of credit bought')+'</div>');
  set('ov_credit_s',usd(c));}
function refresh(){overview();services().then(projects);spendModels();siteGroups();fleetCards();hetzner();cloudflare();uptime();alerts();podcastHealth();mini();dgx();prod();fleet();delivery();fresh();}
refresh();setInterval(refresh,30000);
</script>
SCRIPT
cat <<FTR
</body></html>
FTR
} > "$OUT"
chmod 600 "$OUT"
