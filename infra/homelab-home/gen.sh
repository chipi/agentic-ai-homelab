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
a.card{box-sizing:border-box;background:#14141f;border:1px solid #26263a;border-radius:8px;padding:10px 12px;flex:0 1 200px;min-width:110px;overflow-wrap:anywhere;display:block;text-decoration:none;color:inherit}
a.card:hover{border-color:#3d3d63}
.card h3{margin:0 0 3px;font-size:10px;color:#9a9ac2;text-transform:uppercase;letter-spacing:.05em}
.cv{font-size:19px;font-weight:600;margin-bottom:2px;display:flex;align-items:center;gap:6px;white-space:nowrap;min-height:26px}.subkv{display:grid;grid-template-columns:auto 1fr;gap:1px 12px;font-size:12px;line-height:1.55;margin-top:4px}.subkv span{color:#8888aa}.subkv b{color:#b8b8d0;font-weight:500;text-align:right;font-variant-numeric:tabular-nums}a.card[data-msrc]{cursor:pointer}.cv .tr{order:-1}.cv .sl{order:9;margin-left:auto;flex:none}a.card.site .cv svg.sl{display:block;width:56px;height:16px;margin-top:0}
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
a.card.site{flex:0 1 250px;min-width:230px;max-width:250px}
a.card.site h3{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
a.card.site .kv{display:grid;grid-template-columns:58px 1fr;gap:0 6px;font-size:12px;color:#8888aa;line-height:1.55}
a.card.site .kv b{color:#c8c8e0;font-weight:500;overflow-wrap:anywhere}
a.card.site svg{display:block;width:100%;height:18px;margin-top:6px}
details.sect summary{cursor:pointer;list-style:none}details.sect summary::-webkit-details-marker{display:none}
details.sect summary::before{content:"\25B8  "}details.sect[open] summary::before{content:"\25BE  "}
#notices{margin:0 0 12px}#notices .abar.crit{display:none}
#notices summary{cursor:pointer;font-size:13.5px;color:#d29922;list-style:none}
#notices summary::-webkit-details-marker{display:none}
#notices summary::before{content:'\25B8  '}#notices[open] summary::before{content:'\25BE  '}
#notices[open] summary{margin-bottom:8px}
table.models td{white-space:nowrap}table.models th,table.models td{padding-left:7px;padding-right:7px}table.models td.ven img{margin-right:6px}
.mstats{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,170px));gap:8px;margin:0 0 18px}.mstats div{background:#14141f;border:1px solid #26263a;border-radius:8px;padding:9px 11px}.mstats span{display:block;font-size:11px;color:#8888aa;text-transform:uppercase;letter-spacing:.04em}.mstats b{display:block;font-size:18px;font-weight:600;color:#e6e6ef;margin-top:2px}.mstats i{display:block;font-style:normal;font-size:11px;color:#8888aa}
@media(max-width:640px){
  body{margin:14px}
  h1{font-size:20px;margin-bottom:14px}
  .cols{gap:18px}.col{min-width:0;flex-basis:100%}
  .charts{gap:8px}a.card{flex:0 0 calc(50% - 4px);min-width:calc(50% - 4px);padding:9px 10px;overflow-wrap:anywhere}
  .cv{font-size:17px}.spark{height:34px}.cv{gap:4px}.cv .sl,a.card.site .cv svg.sl{width:40px}.cv .tr{font-size:10px!important;margin:0!important}.cv>span.muted{min-width:0;overflow:hidden;text-overflow:ellipsis}
  table{font-size:13px}th,td{padding:6px 8px}
  table.uptime th:nth-child(n+5),table.uptime td:nth-child(n+5){display:none}
  table.uptime td:first-child{overflow-wrap:anywhere}
  table.models th:nth-child(n+6),table.models td:nth-child(n+6){display:none}table.models .vn{display:none}table.models td.mod{white-space:normal;overflow-wrap:anywhere}table.models td.ven img{margin-right:0}table.models td span[title]{display:none}table.mtbl th:nth-child(5),table.mtbl td:nth-child(5),table.mtbl th:nth-child(7),table.mtbl td:nth-child(7){display:none}
  a.card.site{min-width:calc(50% - 4px);flex:1 1 calc(50% - 4px);max-width:none}
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
<div class=charts>
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
  <div class=charts>
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
  <div class=charts>
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
  <div class=charts>
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
    <a href="#spend/month" data-p=month target=_self>This month</a><a href="#spend/30d" data-p=30d target=_self>Last 30 days</a><a href="#spend/7d" data-p=7d target=_self>Last 7 days</a><a href="#spend/yesterday" data-p=yesterday target=_self>Yesterday</a>
  </nav>
  <p class=sec id=sp_range style="margin:-8px 0 12px"></p>
  <div id=sp_main>
  <h2>Totals</h2>
  <div class=charts id=sp_totals>&hellip;</div>
  <h2>By caller</h2>
  <div class=charts id=sp_callers>&hellip;</div>
  <p class=sec id=sp_callers_note></p>
  <h2>By key (OpenRouter billing)</h2>
  <div class=charts id=sp_keys>&hellip;</div>
  <h2>By vendor</h2>
  <div class=charts id=sp_vendor>&hellip;</div>
  <h2>By model</h2>
  <div id=sp_mfilter style="display:flex;gap:8px;flex-wrap:wrap;margin:0 0 8px;font-size:13px">
    <span class=subtabs style="margin:0" id=sp_msrc><a data-v="" class=on>All</a><a data-v=OpenRouter>OpenRouter</a><a data-v=vLLM>vLLM</a><a data-v=Ollama>Ollama</a><a data-v=Speech>Speech</a></span>
    <select id=sp_mw style="background:#14141f;color:#c8c8e0;border:1px solid #26263a;border-radius:6px;padding:4px 8px"><option value="">Open + proprietary</option><option value=open>Open weights</option><option value=proprietary>Proprietary</option><option value="?">Not known</option></select>
    <select id=sp_ma style="background:#14141f;color:#c8c8e0;border:1px solid #26263a;border-radius:6px;padding:4px 8px"><option value="">Any architecture</option><option value=moe>MoE</option><option value=dense>Dense</option><option value=none>Not published</option></select>
    <select id=sp_mven style="background:#14141f;color:#c8c8e0;border:1px solid #26263a;border-radius:6px;padding:4px 8px"><option value="">All vendors</option></select>
    <input id=sp_mq placeholder="Filter models" style="background:#14141f;color:#e6e6ef;border:1px solid #26263a;border-radius:6px;padding:4px 8px;min-width:140px">
  </div>
  <table class="ctbl models"><thead><tr><th data-k=ven>Vendor</th><th data-k=m>Model</th><th>14 days</th><th data-k=u>Spend</th><th data-k=t>Tokens</th><th data-k=i>In / out</th><th data-k=r>Requests</th><th data-k=src>Source</th><th data-k=w>Weights</th><th data-k=p title="Total parameters; for MoE also the active ones per token">Size</th><th data-k=a title="Dense: every parameter works on every token. MoE (mixture of experts): a router picks a few experts per token">Architecture</th><th data-k=c title="Context length in tokens">Context</th><th data-k=mem title="Weights only, to load the model at 4-bit / 8-bit; an MoE needs its total size. The KV cache for long context comes on top">Memory 4 / 8-bit</th></tr></thead><tbody id=sp_models></tbody>
  <tfoot><tr id=sp_mtotal style="font-weight:600;border-top:2px solid #34344e"></tr></tfoot></table>
  <details class=sect><summary class=sectitle>Local models by consumer (both gateways)</summary>
  <table class=ctbl><thead><tr><th>Gateway</th><th>Key</th><th>Model</th><th>Tokens in / out</th><th>Requests</th></tr></thead><tbody id=sp_consumers></tbody></table>
  </details>
  <p class=sec>Every number covers the same completed UTC days; only "Today so far" is live. Sources: OpenRouter (every key: prod, dev, evals, fleets; billed), vLLM on the DGX (its own token counters, all callers, $0), Ollama on the DGX, X3 and MacBook (its per-request log lines, $0; the lines carry no model or key). Fleet spend is part of OpenRouter, not extra.</p>
  </div>
  <div id=sp_model style="display:none"></div>
</section>
<section class=tab id=t-hosts>
<nav class=subtabs>
  <a href="#hosts/prod" target=_self><span class="dot stale" data-dot=st_prod></span>Prod box</a><a href="#hosts/mini" target=_self><span class="dot stale" data-dot=st_mini></span>Mac mini</a><a href="#hosts/dgx" target=_self><span class="dot stale" data-dot=st_dgx></span>DGX</a><a href="#hosts/delivery" target=_self><span class="dot stale" data-dot=st_delivery></span>Delivery</a>
</nav>
<div class=sub data-sub=delivery style="margin:0 0 22px">
  <h2><span class="dot stale" id=st_delivery></span><a href="$DASH_DELIVERY">Delivery &rarr;</a></h2>
  <div class=charts>
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
  return ' <svg width='+w+' height='+h+' viewBox="0 0 '+w+' '+h+'" class=sl style="vertical-align:middle" aria-label="daily values, 14 days"><polyline points="'+pts+'" fill=none stroke=#7aa2ff stroke-width=1.5 vector-effect=non-scaling-stroke /></svg>';}
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
  const rg=spendRange('month'),kU={},kT={};const cl=await gatewayCallers('month');
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
    const mine=cl.filter(x=>x.proj===p.name),vv=vis(p.umami),spend=mine.length?mine.reduce((a,x)=>a+x.usd,0):null;
    const orT=mine.reduce((a,x)=>a+x.tOR,0),loT=mine.reduce((a,x)=>a+x.tLoc,0)+(p.ollama&&olT?olT:0),allT=orT+loT;
    const worst=Math.max(0,...p.hosts.map(h=>ms[h]||0));
    rows+='<tr><td><span class="dot '+lamp+'"></span>'+ico(PROJECT_SITE[p.name])+p.name+'</td>'
      +'<td data-l=Health><span class=s>'+health+'</span></td>'
      +'<td data-l=Sites>'+(p.hosts.length-dn.length)+'/'+p.hosts.length+' &middot; '+pct(a)+'<div class=s>slowest '+Math.round(worst*1000)+' ms</div></td>'
      +'<td data-l="Requests 24h">'+(req?Math.round(+req[1]).toLocaleString():'&mdash;')+spark(sRq)+'</td>'
      +'<td data-l="Visitors 24h">'+(vv?vv.v24+spark(vv.d)+'<div class=s>'+vv.p24+' views &middot; 7d '+vv.v7+'</div>':'&mdash;')+'</td>'
      +'<td data-l="Edge 5xx 24h">'+(e5?Math.round(+e5[1]):(req?'0':'&mdash;'))+'</td>'
      +'<td data-l="Edge 4xx 24h">'+(e4?Math.round(+e4[1]).toLocaleString():(req?'0':'&mdash;'))+'</td>'
      +'<td data-l="LLM spend">'+(spend==null?'<span class=s>no LLM calls</span>':'$'+spend.toFixed(2)+'<div class=s>'+mine.map(x=>x.key+' ('+x.gw+')').join(', ')+'</div>')+'</td>'
      +'<td data-l="LLM tokens">'+(allT?tk(allT)+'<div class=s>'+(orT?tk(orT)+' OpenRouter':'')+(orT&&loT?' &middot; ':'')+(loT?tk(loT)+' local':'')+'</div>':(p.keys.length||p.vllm||p.ollama?'0':'&mdash;'))+'</td></tr>';
  }
  if(el.innerHTML!==rows)el.innerHTML=rows;
  const nt=document.getElementById('proj_llm_note');if(nt)nt.innerHTML='LLM spend and tokens: this month, '+rg.label+', by the caller (the gateway key that made the call, mini and prod LiteLLM; dollars are LiteLLM&#39;s estimate), not the OpenRouter key that paid. Evals also gets Ollama on the DGX, X3 and MacBook. Edge counts: Cloudflare, last 24h.';
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
// ---- trend arrow: the last 7 days against the 7 before; nothing when either week has no data
// (a short history must not look like a jump). Neutral colour: up is not good or bad by itself.
function trend(d){if(!d||d.length<14)return '';const a=d.slice(-7),b=d.slice(-14,-7);
  if(!a.some(x=>x!=null)||!b.some(x=>x!=null))return '';const sa=a.reduce((p,x)=>p+(x||0),0),sb=b.reduce((p,x)=>p+(x||0),0);
  if(!sb&&!sa)return '';const ch=sb?(sa-sb)/sb:1,t='last 7 days vs the 7 before: '+(sb?(ch>=0?'+':'')+(ch*100).toFixed(0)+'%':'from 0');
  const ar=Math.abs(ch)<0.1?'&#8594;':(ch>0?'&#9650;':'&#9660;'),txt=!sb?' new':(Math.abs(ch)<0.1?'':(ch>10?'&gt;10&times;':Math.abs(ch*100).toFixed(0)+'%'));
  return '<span class=tr title="'+t+'" style="color:#9a9ac2;font-size:11px;font-weight:500;margin:0 2px;vertical-align:middle;white-space:nowrap">'+ar+txt+'</span>';}
const sparkT=(d,lo,hi)=>spark(d,lo,hi)+trend(d);
// 14 completed UTC days (oldest first) from gauges that carry a day="YYYY-MM-DD" label
function dayArr(byDay){const out=[],n=new Date(),mid=Date.UTC(n.getUTCFullYear(),n.getUTCMonth(),n.getUTCDate());
  for(let i=14;i>=1;i--){const d=new Date(mid-i*86400000).toISOString().slice(0,10);out.push(byDay[d]!=null?byDay[d]:null);}return out;}
async function dayGauge(metric,by){const m={};(await q('last_over_time('+metric+'[2h])')).forEach(r=>{const k=by?r.metric[by]:'_';(m[k]=m[k]||{})[r.metric.day]=(m[k][r.metric.day]||0)+ +r.value[1];});
  const o={};for(const k in m)o[k]=dayArr(m[k]);return o;}
// logos: the site's own icon through DuckDuckGo's icon service; gone quietly if it fails
const VENDOR_SITE={anthropic:'anthropic.com',openai:'openai.com',google:'deepmind.google',deepseek:'deepseek.com',qwen:'qwen.ai','meta-llama':'llama.com',
  mistralai:'mistral.ai',moonshotai:'moonshot.ai',pyannote:'pyannote.ai','z-ai':'z.ai',nvidia:'nvidia.com',microsoft:'microsoft.com','x-ai':'x.ai',cohere:'cohere.com'};
const PROJECT_SITE={'Close Listening':'closelistening.app','Orrery':'orrerylearn.com','Evals':'humancopilot.eu','Websites':'humancopilot.eu','Fleets':'github.com'};
const ico=dom=>dom?'<img src="https://icons.duckduckgo.com/ip3/'+dom+'.ico" width=14 height=14 alt="" loading=lazy style="vertical-align:-2px;margin-right:5px;border-radius:3px" onerror="this.remove()">':'';
// Open weights or proprietary: an official weights repo on Hugging Face = open (checked 2026-11-03
// against the HF API per family); none = proprietary; local models are open by definition (their
// weights are on our disks); "?" where the API-served model may not be the published one.
const OPEN_RE=/^(deepseek\/|moonshotai\/kimi-k3$|z-ai\/glm-|mistralai\/(mistral-large-(2512|4)|mistral-medium-3-5|mistral-small|ministral|mixtral)|qwen\/qwen3(\.[56])?-\d|google\/gemma|openai\/gpt-oss|meta-llama\/|nvidia\/|microsoft\/phi)/;
const PROP_RE=/^(anthropic\/|openai\/|google\/gemini|qwen\/qwen[\d.]*-(max|plus)|mistralai\/mistral-medium-3\.1|moonshotai\/kimi-k3\.1|x-ai\/)/;
function weights(full,src){if(src!=='OpenRouter')return 'open';if(OPEN_RE.test(full))return 'open';if(PROP_RE.test(full))return 'proprietary';return '?';}
// where a click on a model goes: open models to their Hugging Face organisation, proprietary ones to
// OpenRouter's model page (vendors do not all have a page per model); vendors to their own site
const HF_ORG={deepseek:'deepseek-ai',moonshotai:'moonshotai','z-ai':'zai-org',mistralai:'mistralai',qwen:'Qwen',google:'google',openai:'openai','meta-llama':'meta-llama',nvidia:'nvidia',microsoft:'microsoft'};
function modelUrl(full,src,model){if(src==='vLLM'||src==='Speech')return 'https://huggingface.co/'+full;if(src==='Ollama')return 'https://ollama.com/library';
  const [v,m]=[full.split('/')[0],full.split('/').slice(1).join('/')];
  return weights(full,src)==='open'&&HF_ORG[v]?'https://huggingface.co/'+HF_ORG[v]+'?search_models='+encodeURIComponent(m):'https://openrouter.ai/'+full;}
// Ollama's token lines are in VictoriaLogs from 2026-10-30; earlier days are unknown, not zero
const OLLAMA_LOGS_FROM=Date.UTC(2026,9,30);
// Open models' size and shape, fetched from Hugging Face 2026-11-03: p = total parameters (billions,
// safetensors count), a = active per token (from the name: A3B, A17B...), arch/e = dense or MoE with
// experts (config.json), ctx = context length. approx = stored as packed int weights, so the count
// is not confirmed. Proprietary models publish none of this. Add a model here when it shows up.
const MODEL_FACTS={"deepseek/deepseek-v4-pro":{"p":1598.8,"arch":"MoE","e":"384 experts, 6 per token","ctx":1048576,"src":"HF parameter count (packed int weights: not confirmed); HF config.json","approx":1},"deepseek/deepseek-v4-flash":{"p":290.9,"arch":"MoE","e":"256 experts, 6 per token","ctx":1048576,"src":"HF parameter count (packed int weights: not confirmed); HF config.json","approx":1},"deepseek/deepseek-v4.1-flash":{"p":763.2,"arch":"MoE","e":"384 experts, 6 per token","ctx":1048576,"src":"HF parameter count (packed int weights: not confirmed); HF config.json","approx":1},"moonshotai/kimi-k3":{"p":2779.9,"arch":"MoE","e":"896 experts, 16 per token","ctx":1048576,"src":"HF parameter count (packed int weights: not confirmed); HF config.json","approx":1},"z-ai/glm-4.5-air":{"p":110.5,"arch":"MoE","e":"128 experts, 8 per token","ctx":131072,"src":"HF parameter count; HF config.json"},"z-ai/glm-4.6":{"p":356.8,"arch":"MoE","e":"160 experts, 8 per token","ctx":202752,"src":"HF parameter count; HF config.json"},"z-ai/glm-5":{"p":753.9,"arch":"MoE","e":"256 experts, 8 per token","ctx":202752,"src":"HF parameter count; HF config.json"},"z-ai/glm-5.3-flash":{"p":321.3,"arch":"MoE","e":"288 experts, 8 per token","ctx":1048576,"src":"HF parameter count; HF config.json"},"mistralai/mistral-large-2512":{"arch":"MoE","e":"128 experts, 4 per token","ctx":294912,"p":675,"src":"HF config.json; model name"},"mistralai/mistral-large-4-0":{"arch":"MoE","e":"128 experts, 4 per token","ctx":1048576,"p":1000,"a":52,"src":"HF config.json; model name"},"mistralai/mistral-medium-3-5":{"p":127.7,"arch":"dense","ctx":262144,"src":"HF parameter count; HF config.json"},"mistralai/mistral-small-3.2-24b-instruct":{"p":24.0,"arch":"dense","ctx":131072,"src":"HF parameter count; HF config.json"},"qwen/qwen3-30b-a3b-instruct-2507":{"p":30.5,"arch":"MoE","e":"128 experts, 8 per token","ctx":262144,"a":3.0,"src":"HF parameter count; HF config.json"},"qwen/qwen3.5-122b-a10b":{"p":125.1,"arch":"MoE","e":"256 experts, 8 per token","ctx":262144,"a":10.0,"src":"HF parameter count; HF config.json"},"qwen/qwen3.5-397b-a17b":{"p":403.4,"arch":"MoE","e":"512 experts, 10 per token","ctx":262144,"a":17.0,"src":"HF parameter count; HF config.json"},"qwen/qwen3.6-35b-a3b":{"p":36.0,"arch":"MoE","e":"256 experts, 8 per token","ctx":262144,"a":3.0,"src":"HF parameter count; HF config.json"},"google/gemma-3-27b-it":{"p":27.4,"arch":"dense","src":"HF parameter count; model name"},"google/gemma-4-26b-a4b-it":{"p":25.8,"arch":"MoE","e":"128 experts","ctx":262144,"a":4.0,"src":"HF parameter count; HF config.json"},"google/gemma-4-31b-it":{"p":31.3,"arch":"dense","ctx":262144,"src":"HF parameter count; HF config.json"},"openai/gpt-oss-120b":{"p":116.8,"arch":"MoE","e":"128 experts, 4 per token","ctx":131072,"src":"HF parameter count; HF config.json"},"meta-llama/llama-3.3-70b-instruct":{"p":70.6,"arch":"dense","src":"HF parameter count; model name"},"meta-llama/llama-4-scout":{"p":108.6,"a":17,"arch":"MoE","e":"16 experts","src":"HF parameter count; model name"},"meta-llama/llama-4-maverick":{"p":401.6,"a":17,"arch":"MoE","e":"128 experts","src":"HF parameter count; model name"},"NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4":{"p":30.5,"arch":"MoE","e":"128 experts, 8 per token","ctx":262144,"a":3.0,"src":"HF parameter count; HF config.json"}};
// The DGX's other models. whisper: the served CTranslate2 conversion has no parameter count on HF; its
// upstream openai/whisper-large-v3-turbo has 808.9M (32 encoder, 4 decoder layers). translategemma's
// config is gated; it is Gemma 3 based (dense). pyannote publishes no count: a pipeline of models.
Object.assign(MODEL_FACTS,{'google/translategemma-12b-it':{p:12.2,arch:'dense',src:'HF parameter count; Gemma 3 family (config gated)'},
  'deepdml/faster-whisper-large-v3-turbo-ct2':{p:0.81,arch:'encoder-decoder',e:'32 encoder + 4 decoder layers',src:'HF openai/whisper-large-v3-turbo (served as a CTranslate2 int8 conversion)'},
  'OpenMOSS-Team/MOSS-Transcribe-Diarize':{p:0.91,arch:'audio LM',ctx:131072,src:'HF parameter count; HF config.json'},
  'pyannote/speaker-diarization-community-1':{arch:'pipeline',e:'segmentation + speaker embedding + PLDA clustering',src:'HF model card files'}});
// which container serves which DGX model (port for the reader)
// whisper prints a clip's length as mm:ss.sss, or hh:mm:ss.sss from an hour up; both read as seconds
const WHISPER_AUDIO='container:"faster-whisper" "Processing audio with duration" | extract_regexp "duration (?:(?P<h>[0-9]+):)?(?P<m>[0-9]+):(?P<s>[0-9.]+)$" | format if (h:"") "0" as h | math h*3600 + m*60 + s as sec';
const DGX_CT={'NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4':['vllm-prod-vllm',8003],'google/translategemma-12b-it':['vllm-translate',8005],
  'deepdml/faster-whisper-large-v3-turbo-ct2':['faster-whisper',8000],'pyannote/speaker-diarization-community-1':['pyannote',8001],'OpenMOSS-Team/MOSS-Transcribe-Diarize':['moss',8004]};
const mfact=full=>MODEL_FACTS[String(full).replace(/:.*$/,'')]||null;
// weights-only memory: 4-bit ~0.56 B/param (scales add ~12%), 8-bit ~1.05; an MoE loads every expert,
// so it needs memory for its total size, not its active size. KV cache for the context comes on top.
const memGB=p=>[Math.ceil(p*0.56),Math.ceil(p*1.05)];
const gb=v=>v>=1000?(v/1000).toFixed(1)+' TB':v+' GB';
function factCells(F){const hx=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const td=(v,t)=>'<td class=u style="white-space:nowrap"'+(t?' title="'+hx(t)+'"':'')+'>'+v+'</td>';
  if(!F)return td('&mdash;')+td('&mdash;')+td('&mdash;')+td('&mdash;');
  const ap=F.approx?'~':'',src=F.src+(F.approx?'. Packed weights: size not confirmed':''),m=F.p?memGB(F.p):null;
  const sz=p=>p>=1000?(p/1000).toFixed(1)+'T':(p>=100?Math.round(p):p)+'B',ex=/(\d+) experts(?:, (\d+) per token)?/.exec(F.e||'');
  return td(F.p?ap+sz(F.p)+(F.a?' <span class=muted style="font-size:11px">'+F.a+'B active</span>':''):'&mdash;',src)
    +td(F.arch==='MoE'?'MoE'+(ex?' '+ex[1]+(ex[2]?'&times;'+ex[2]:''):''):(F.arch||'&mdash;'),(F.e?F.arch+': '+F.e+'. ':'')+src)
    +td(F.ctx?(F.ctx>=1e6?Math.round(F.ctx/1048576)+'M':Math.round(F.ctx/1024)+'k'):'&mdash;')
    +td(m?ap+gb(m[0])+' / '+gb(m[1]):'&mdash;',src);}
// a long list in a narrow cell: the first two, then "+N", the whole list on hover
function short(l,n=2){const hx=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  return '<td class=u title="'+hx(l.join(', '))+'">'+hx(l.slice(0,n).join(', '))+(l.length>n?' <span class=muted>+'+(l.length-n)+'</span>':'')+'</td>';}
// ---- Who called: the gateway key (LiteLLM, mini and prod), not the OpenRouter key that paid.
// OpenRouter only knows the paying key, and keys were shared (eval-harness's aliases used the
// podcast key until 2026-10-30), so per-project spend comes from the gateways' own logs: the mini's
// "LiteLLM_DailyUserSpend" (litellm-pg datasource) and prod's litellm_model_* (box="prod", pushed by
// chipi/infra spend-to-vm.sh). Gateway dollars are LiteLLM's own price estimate, not OpenRouter's
// bill. OpenRouter keys no gateway uses are "direct". Same completed UTC days as everything else.
const CALLERPROJ=[[/^eval-harness$/,'Evals'],[/^fleet-/,'Fleets'],[/^(proj-podcast|podcast-)/,'Close Listening'],[/^proj-orrery/,'Orrery']];
const DIRECTKEYS=['pi-key','photo-key','opencode-key','Default key'];
async function gatewayCallers(p){
  gatewayCallers.c=gatewayCallers.c||{};const c=gatewayCallers.c[p];if(c&&Date.now()-c.t<300000)return c.v;
  const rg=spendRange(p),out=[];if(!rg.R){gatewayCallers.c[p]={t:Date.now(),v:out};return out;}
  const get=(gw,key)=>{let r=out.find(x=>x.gw===gw&&x.key===key);if(!r){r={gw,key,usd:0,tOR:0,tLoc:0,req:0,proj:(CALLERPROJ.find(([re])=>re.test(key))||[0,'Other'])[1]};out.push(r);}return r;};
  try{
    const d0=new Date(Date.now()-rg.O*1000-rg.R*1000).toISOString().slice(0,10),d1=new Date(Date.now()-rg.O*1000).toISOString().slice(0,10);
    const sql="SELECT COALESCE(v.key_alias, '(no alias)') AS k, CASE WHEN d.custom_llm_provider='openrouter' OR d.model LIKE 'openrouter/%' THEN 'or' ELSE 'loc' END AS s,"
      +" SUM(d.spend) AS u, SUM(d.prompt_tokens)+SUM(d.completion_tokens) AS t, SUM(d.api_requests) AS r"
      +" FROM \"LiteLLM_DailyUserSpend\" d LEFT JOIN \"LiteLLM_VerificationToken\" v ON v.token = d.api_key"
      +" WHERE d.date >= '"+d0+"' AND d.date < '"+d1+"' GROUP BY 1,2";
    const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
      body:JSON.stringify({queries:[{refId:'G',datasource:{uid:'litellm-pg'},rawSql:sql,format:'table'}],from:'now-31d',to:'now'})})).json();
    const f=r.results.G.frames[0],n=f.schema.fields.map(x=>x.name),col=k=>f.data.values[n.indexOf(k)]||[];
    col('k').forEach((k,i)=>{const x=get('mini',k);x.usd+= +col('u')[i];x.req+= +col('r')[i];if(col('s')[i]==='or')x.tOR+= +col('t')[i];else x.tLoc+= +col('t')[i];});
  }catch(e){}
  const W='window="'+p+'"',by=async e=>q('sum by (key_alias, provider) (last_over_time('+e+'{box="prod",'+W+'}[2h]))');
  (await by('litellm_model_usd')).forEach(r=>{get('prod',r.metric.key_alias).usd+= +r.value[1];});
  (await by('litellm_model_tokens')).forEach(r=>{const x=get('prod',r.metric.key_alias);if(r.metric.provider==='openrouter')x.tOR+= +r.value[1];else x.tLoc+= +r.value[1];});
  (await by('litellm_model_requests')).forEach(r=>{get('prod',r.metric.key_alias).req+= +r.value[1];});
  const v=out.filter(x=>x.usd>=0.0005||x.tOR+x.tLoc>0);
  gatewayCallers.c[p]={t:Date.now(),v};return v;
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
  const rows=[],get=(src,key,ven,model,by,full)=>{const k=[src,key,ven,model,by].join('|');let r=rows.find(x=>x.k===k);if(!r){r={k,src,key,ven,model,by,full:full||model,usd:0,i:0,o:0,req:0};rows.push(r);}return r;};
  const lbl=['key','vendor','model','provider'];
  const orq=async(name,extra)=>q('sum by (key, vendor, model, provider) (last_over_time('+name+'{'+W+',key!=""'+(extra?','+extra:'')+'}'+L+'))');
  (await orq('openrouter_model_usd')).forEach(r=>{const m=r.metric;get('OpenRouter',m.key,m.vendor,m.model.replace(/^[^/]+\//,''),m.provider,m.model).usd+= +r.value[1];});
  (await orq('openrouter_model_tokens','kind="prompt"')).forEach(r=>{const m=r.metric;get('OpenRouter',m.key,m.vendor,m.model.replace(/^[^/]+\//,''),m.provider,m.model).i+= +r.value[1];});
  (await orq('openrouter_model_tokens','kind="completion"')).forEach(r=>{const m=r.metric;get('OpenRouter',m.key,m.vendor,m.model.replace(/^[^/]+\//,''),m.provider,m.model).o+= +r.value[1];});
  (await orq('openrouter_model_requests')).forEach(r=>{const m=r.metric;get('OpenRouter',m.key,m.vendor,m.model.replace(/^[^/]+\//,''),m.provider,m.model).req+= +r.value[1];});
  // vLLM on the DGX: its own counters, every caller; vendor read from the model name
  const venOf=n=>{const l=n.toLowerCase();for(const v of ['qwen','gemma','llama','mistral','deepseek','nemotron','gpt-oss','phi'])if(l.includes(v))return v==='gpt-oss'?'openai':(v==='gemma'?'google':(v==='llama'?'meta-llama':(v==='nemotron'?'nvidia':(v==='phi'?'microsoft':(v==='mistral'?'mistralai':v)))));return 'unknown';};
  if(rg.R){
    const vq=async e=>{const m={};(await q(vm(e))).forEach(r=>m[r.metric.model_name]=+r.value[1]);return m;};
    const vi=await vq('sum by (model_name) (increase(vllm:prompt_tokens_total{instance="dgx-llm-1"}[R]))'),vo=await vq('sum by (model_name) (increase(vllm:generation_tokens_total{instance="dgx-llm-1"}[R]))'),
          vr=await vq('sum by (model_name) (increase(vllm:request_success_total{instance="dgx-llm-1"}[R]))');
    for(const n of new Set([...Object.keys(vi),...Object.keys(vo)])){if(!(vi[n]||vo[n]))continue;const r=get('vLLM','DGX vLLM (all callers)',venOf(n),n.split('/').pop(),'DGX',n);r.i+=vi[n]||0;r.o+=vo[n]||0;r.req+=vr[n]||0;}
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
  // Speech on the DGX: pyannote and moss count their own requests (/metrics); faster-whisper has no
  // /metrics, so its access and "Processing audio with duration" log lines give requests and audio.
  if(rg.R)try{
    const n1=async e=>{const r=await q(vm(e));return r.length?+r[0].value[1]:0;};
    const to=Date.now()-rg.O*1000,from=to-rg.R*1000;
    const ls=async expr=>{const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
        body:JSON.stringify({queries:[{refId:'W',datasource:{uid:'victorialogs'},expr,queryType:'stats'}],from:String(from),to:String(to)})})).json();
      const o={};((r.results.W||{}).frames||[]).forEach(f=>{const l=f.schema.fields[1].labels||{},v=f.data.values[1];o[l.__name__]=+v[v.length-1]||0;});return o;};
    const [dz,ms,wq,wa]=await Promise.all([n1('sum(increase(http_requests_total{job="pyannote-app",handler="/v1/diarize"}[R]))'),
      n1('sum(increase(http_requests_total{job="moss-app",handler="/v1/transcribe"}[R]))'),
      ls('container:"faster-whisper" "POST /v1/audio/transcriptions" | stats count() as n'),
      ls(WHISPER_AUDIO+' | stats sum(sec) as sec')]);
    const sp=(ven,full,req,audio)=>{if(!req)return;const r=get('Speech','DGX speech (all callers)',ven,full.split('/').pop(),'DGX',full);r.req+=req;r.audio=(r.audio||0)+(audio||0);};
    sp('openai','deepdml/faster-whisper-large-v3-turbo-ct2',wq.n,wa.sec||0);
    sp('pyannote','pyannote/speaker-diarization-community-1',dz);sp('openmoss','OpenMOSS-Team/MOSS-Transcribe-Diarize',ms);
  }catch(e){}
  const sum=(xs,f)=>xs.reduce((a,x)=>a+(x[f]||0),0),src=n=>rows.filter(r=>r.src===n);
  // ---- Totals ----
  const today=await one('sum(last_over_time(openrouter_key_usd{window="day"}'+L+'))');
  const fl=rg.R?await one(vm('sum(sum_over_time(signal_fleet_cost_usd[R]))'))+await one(vm('sum(sum_over_time(bugfix_fleet_cost_usd[R]))')):0;
  const cr=await one('max(last_over_time(openrouter_account_usd{kind="credits"}'+L+')) - max(last_over_time(openrouter_account_usd{kind="usage"}'+L+'))');
  const t=n=>sum(src(n),'i')+sum(src(n),'o'),card=(ti,v,sub,ms)=>'<a class=card'+(ms!=null?' data-msrc="'+ms+'"':'')+'><h3>'+ti+'</h3><div class=cv>'+v+'</div>'
    +(Array.isArray(sub)?'<div class=subkv>'+sub.filter(Boolean).map(([l,x])=>'<span>'+l+'</span><b>'+x+'</b>').join('')+'</div>':(sub?'<span class=muted>'+sub+'</span>':''))+'</a>';
  const allT=t('OpenRouter')+t('vLLM')+t('Ollama');
  // 14-day daily lines: OpenRouter spend (account, from the vendor-day gauges), vLLM tokens, Ollama tokens
  const vdd={};(await q('last_over_time(openrouter_vendor_day_usd'+L+')')).forEach(r=>vdd[r.metric.day]=(vdd[r.metric.day]||0)+ +r.value[1]);
  const orLine=dayArr(vdd);
  const vtk=(await dayGauge('openrouter_vendor_day_tokens'))._||null,kDay=await dayGauge('openrouter_key_day_usd','key'),kTok=await dayGauge('openrouter_key_day_tokens','key');
  const mDay=await dayGauge('openrouter_model_day_usd','model');
  const vLine=await daily('sum(increase(vllm:prompt_tokens_total{instance="dgx-llm-1"}[1d])) + sum(increase(vllm:generation_tokens_total{instance="dgx-llm-1"}[1d]))');
  let oLine=null;try{const e=Date.now(),st=e-14*86400000;
    const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
      body:JSON.stringify({queries:[{refId:'D',datasource:{uid:'victorialogs'},expr:'job:"ollama" "eval time =" | extract_regexp "eval time = +[0-9.]+ ms / +(?P<n>[0-9]+) tokens" | stats sum(n) as t',queryType:'statsRange',step:'1d'}],from:String(st),to:String(e)})})).json();
    const f=(r.results.D.frames||[])[0];if(f){const ts=f.data.values[0],vs=f.data.values[f.data.values.length-1];oLine=Array(14).fill(0);ts.forEach((t0,i)=>{const k=Math.floor((+t0-st)/86400000);if(k>=0&&k<14)oLine[k]+= +vs[i]||0;});
      oLine=oLine.map((v,k)=>st+(k+1)*86400000<=OLLAMA_LOGS_FROM?null:v);}}catch(x){}
  const add=(...ls)=>{const ok=ls.filter(Boolean);return ok.length?ok[0].map((_,i)=>ok.some(l=>l[i]!=null)?ok.reduce((p,l)=>p+(l[i]||0),0):null):null;};
  const spR=n=>src('Speech').find(r=>r.model.startsWith(n))||{},orU=sum(src('OpenRouter'),'usd');
  set('sp_totals',card('All tokens',tk(allT)+sparkT(add(vtk,vLine,oLine)),[['OpenRouter',tk(t('OpenRouter'))],['vLLM',tk(t('vLLM'))],['Ollama',tk(t('Ollama'))]],'')
    +card('Local tokens',tk(t('vLLM')+t('Ollama'))+sparkT(add(vLine,oLine)),[['vLLM',tk(t('vLLM'))],['Ollama',tk(t('Ollama'))],['Cost','$0']],'vLLM')
    +(sum(src('Speech'),'req')?card('Speech requests',Math.round(sum(src('Speech'),'req')).toLocaleString(),
      [['Whisper',Math.round(spR('faster-whisper').req||0).toLocaleString()],['Audio',Math.round((spR('faster-whisper').audio||0)/3600).toLocaleString()+' h'],
       ['Diarization',Math.round(spR('speaker-diarization').req||0).toLocaleString()],spR('MOSS').req?['MOSS',Math.round(spR('MOSS').req).toLocaleString()]:null],'Speech'):'')
    +card('OpenRouter spend',usd(orU)+sparkT(orLine),[['Requests',Math.round(sum(src('OpenRouter'),'req')).toLocaleString()],['Today (live)',usd(today)]],'OpenRouter')
    +card('OpenRouter fleets',usd(fl),[['Share',orU?(fl/orU*100).toFixed(1)+'%':'&mdash;'],['Fleets','triage + bug-fix']])
    +card('OpenRouter credit left','<span style="'+(cr<10?'color:#f85149':'')+'">'+usd(cr)+'</span>',[['Top up','openrouter.ai']]));
  // ---- By caller ----
  const cl=await gatewayCallers(p),dKeys={};
  // mini callers' daily tokens over 14 days, one query (prod's gateway pushes period totals only)
  const cLine={};try{const st=new Date(Date.now()-14*86400000).toISOString().slice(0,10);
    const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
      body:JSON.stringify({queries:[{refId:'C',datasource:{uid:'litellm-pg'},rawSql:"SELECT COALESCE(v.key_alias,'(no alias)') AS k, d.date AS dt, SUM(d.prompt_tokens)+SUM(d.completion_tokens) AS t FROM \"LiteLLM_DailyUserSpend\" d LEFT JOIN \"LiteLLM_VerificationToken\" v ON v.token = d.api_key WHERE d.date >= '"+st+"' GROUP BY 1,2",format:'table'}],from:'now-15d',to:'now'})})).json();
    const f=r.results.C.frames[0],n=f.schema.fields.map(x=>x.name),c=k=>f.data.values[n.indexOf(k)]||[],base=Date.now()-14*86400000;
    c('k').forEach((k,i)=>{const di=Math.floor((Date.parse(String(c('dt')[i]).slice(0,10))-base)/86400000)+1;if(di>=0&&di<14)(cLine[k]=cLine[k]||Array(14).fill(0))[di]+= +c('t')[i];});}catch(x){}
  rows.filter(r=>r.src==='OpenRouter'&&DIRECTKEYS.includes(r.key)).forEach(r=>{const x=dKeys[r.key]=dKeys[r.key]||{usd:0,t:0};x.usd+=r.usd;x.t+=r.i+r.o;});
  const orBill=sum(src('OpenRouter'),'usd'),gwOR=cl.reduce((a,x)=>a+x.usd,0),dir=Object.values(dKeys).reduce((a,x)=>a+x.usd,0);
  // local-only (vLLM / Ollama) costs nothing: its big number is tokens, not $0
  const big=(u,t)=>u>=0.005||!t?usd(u):tk(t)+' <span class=muted style="font-size:12px;font-weight:400">tokens</span>';
  const ccard=(t,b,tok,sub)=>'<a class="card site"><h3>'+t+'</h3><div class=cv>'+b+'</div><div class=kv>'+tok+'</div>'+(sub?'<span class=muted style="font-size:12px">'+sub+'</span>':'')+'</a>';
  set('sp_callers',cl.sort((a,b)=>b.usd-a.usd||(b.tOR+b.tLoc)-(a.tOR+a.tLoc)).map(x=>ccard(hx(x.key),big(x.usd,x.tOR+x.tLoc)+(x.gw==='mini'&&cLine[x.key]?sparkT(cLine[x.key]):''),'<span>Project</span><b>'+x.proj+'</b><span>Tokens</span><b>'+tk(x.tOR+x.tLoc)+(x.tLoc?' ('+tk(x.tLoc)+' local)':'')+'</b><span>Via</span><b>'+x.gw+' gateway &middot; '+Math.round(x.req).toLocaleString()+' req</b>')).join('')
    +Object.entries(dKeys).filter(([k,x])=>x.usd>=0.005).map(([k,x])=>ccard(hx(k),usd(x.usd),'<span>Project</span><b>Other</b><span>Tokens</span><b>'+tk(x.t)+'</b><span>Via</span><b>direct to OpenRouter</b>')).join('')
    +(t('Ollama')?ccard('Ollama (no gateway)',big(0,t('Ollama'))+sparkT(oLine),'<span>Project</span><b>Evals</b><span>Requests</span><b>'+Math.round(sum(src('Ollama'),'req')).toLocaleString()+'</b><span>Via</span><b>straight to Ollama</b>'):'')
    +(t('vLLM')?ccard('vLLM (all callers)',big(0,t('vLLM'))+sparkT(vLine),'<span>Requests</span><b>'+Math.round(sum(src('vLLM'),'req')).toLocaleString()+'</b><span>Note</span><b>gateway callers above are part of it</b>'):''));
  const gap=orBill-gwOR-dir;
  set('sp_callers_note','Gateway callers: '+usd(gwOR)+' (LiteLLM&#39;s own price estimate) + direct keys '+usd(dir)+' = '+usd(gwOR+dir)+' against OpenRouter&#39;s bill of '+usd(orBill)
    +' ('+(gap>=0?'+':'')+usd(gap).replace('$','$')+' difference: pricing estimates, and calls by keys no gateway logs).');
  // ---- group helper ----
  const group=f=>{const g={};rows.forEach(r=>{const k=f(r);const x=g[k]=g[k]||{k,usd:0,i:0,o:0,req:0,src:new Set(),rows:[]};x.usd+=r.usd;x.i+=r.i;x.o+=r.o;x.req+=r.req;x.audio=(x.audio||0)+(r.audio||0);x.src.add(r.src);x.rows.push(r);});
    return Object.values(g).filter(x=>x.usd>=0.005||x.i+x.o>0||x.req>0).sort((a,b)=>b.usd-a.usd||(b.i+b.o)-(a.i+a.o));};
  const srcTag=x=>[...x.src].join(' + ');
  // ---- By key ----
  const life={};(await q('max by (key) (last_over_time(openrouter_key_usd{window="total"}'+L+'))')).forEach(r=>life[r.metric.key]=+r.value[1]);
  set('sp_keys',group(r=>r.key).map(x=>{const top={};x.rows.forEach(r=>top[r.model]=(top[r.model]||0)+r.usd+(r.i+r.o)*1e-9);
    const tops=Object.entries(top).sort((a,b)=>b[1]-a[1]).slice(0,2).map(e=>hx(e[0]));
    const kl=x.src.has('OpenRouter')?kDay[x.k]:(x.src.has('vLLM')?vLine:oLine);
    return '<a class="card site"><h3>'+hx(x.k)+'</h3><div class=cv>'+(x.src.has('OpenRouter')?usd(x.usd):(x.src.has('Speech')?Math.round(x.req).toLocaleString()+' <span class=muted style="font-size:12px;font-weight:400">requests</span>':big(0,x.i+x.o)))+sparkT(kl)+'</div><div class=kv><span>Tokens</span><b>'+tk(x.i+x.o)+'</b><span>Top</span><b>'+(tops.join(', ')||'&mdash;')+'</b>'
      +'<span>Source</span><b>'+srcTag(x)+'</b>'+(life[x.k]!=null?'<span>Lifetime</span><b>'+usd(life[x.k])+'</b>':'')+'</div></a>';}).join('')||'<div class=muted>nothing in this period</div>');
  // ---- By vendor ----
  const vd={};(await q('last_over_time(openrouter_vendor_day_usd'+L+')')).forEach(r=>{(vd[r.metric.vendor]=vd[r.metric.vendor]||{})[r.metric.day]=+r.value[1];});
  const days=[...new Set(Object.values(vd).flatMap(o=>Object.keys(o)))].sort().slice(-14);
  set('sp_vendor',group(r=>r.ven).map(x=>'<a class=card href="https://'+(VENDOR_SITE[x.k]||'openrouter.ai')+'"><h3>'+ico(VENDOR_SITE[x.k])+hx(x.k)+'</h3><div class=cv>'+(x.src.has('OpenRouter')?usd(x.usd):big(0,x.i+x.o))+(vd[x.k]?sparkT(dayArr(vd[x.k])):'')+'</div><span class=muted>'+tk(x.i+x.o)+' tokens &middot; '+srcTag(x)+'</span></a>').join('')||'<div class=muted>nothing in this period</div>');
  // ---- By model: vendor and model in their own columns ----
  const mg=group(r=>r.src+'|'+r.ven+'|'+r.model);
  const mTok=await dayGauge('openrouter_model_day_tokens','model');
  const MM={};
  set('sp_models',mg.map(x=>{const r0=x.rows[0],id=x.k;
    const w=weights(r0.full,r0.src),F=mfact(r0.full),line=r0.src==='OpenRouter'?mDay[r0.full]:(r0.src==='vLLM'?vLine:(r0.src==='Ollama'?oLine:null));
    MM[id]={x,r0,w,F,line,tline:r0.src==='OpenRouter'?mTok[r0.full]:line};
    return '<tr data-src="'+r0.src+'" data-ven="'+hx(r0.ven)+'" data-m="'+hx(r0.model.toLowerCase())+'" data-w="'+w+'" data-u="'+x.usd+'" data-t="'+(x.i+x.o)+'" data-i="'+x.i+'" data-o="'+x.o+'" data-r="'+x.req+'" data-p="'+(F&&F.p||'')+'" data-mem="'+(F&&F.p||'')+'" data-c="'+(F&&F.ctx||'')+'" data-a="'+(F&&F.arch?F.arch.toLowerCase():'none')+'">'
      +'<td class=ven><a href="https://'+(VENDOR_SITE[r0.ven]||'openrouter.ai')+'" title="'+hx(r0.ven)+'">'+ico(VENDOR_SITE[r0.ven])+'<span class=vn>'+hx(r0.ven)+'</span></a></td>'
      +'<td class=mod><a href="#spend/'+p+'/m/'+encodeURIComponent(id)+'" target=_self>'+hx(r0.model)+'</a></td><td>'+sparkT(line)+'</td>'
      +'<td>'+(r0.src==='OpenRouter'?usd(x.usd):'$0')+'</td><td>'+(r0.src==='Speech'?(x.audio?Math.round(x.audio/3600)+' h audio':'&mdash;'):tk(x.i+x.o))+'</td><td>'+(r0.src==='Speech'?'&mdash;':tk(x.i)+' / '+tk(x.o))+'</td><td>'+Math.round(x.req).toLocaleString()+'</td>'
      +'<td class=u>'+r0.src+'</td><td class=u style="color:'+(w==='open'?'#3fb950':(w==='proprietary'?'#c8c8e0':'#d29922'))+'">'+w+'</td>'+factCells(F)+'</tr>';}).join('')
    ||'<tr><td class=muted colspan=13>nothing in this period</td></tr>');
  if(spendPeriod===p){MODELS=MM;MODELS_P=p;MODELS_LABEL=rg.label;modelPage();}
  const sel=document.getElementById('sp_mven'),vens=[...new Set(mg.map(x=>x.rows[0].ven))].sort(),cur=sel?sel.value:'';
  if(sel){const h='<option value="">All vendors</option>'+vens.map(v=>'<option'+(v===cur?' selected':'')+'>'+hx(v)+'</option>').join('');if(sel.innerHTML!==h)sel.innerHTML=h;}
  modelFilter();
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
  const html=order.filter(g=>groups[g]).map(g=>'<h4 style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#9a9ac2;margin:14px 0 6px">'+g+'</h4><div class=charts>'
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
// By model filters (source, vendor, text) and the totals row that follows them; client-side only.
let modelSrc='';
function modelFilter(){
  const ven=(document.getElementById('sp_mven')||{}).value||'',txt=((document.getElementById('sp_mq')||{}).value||'').toLowerCase(),wt=(document.getElementById('sp_mw')||{}).value||'',ar=(document.getElementById('sp_ma')||{}).value||'';
  let u=0,i=0,o=0,r=0,n=0;
  document.querySelectorAll('#sp_models tr[data-src]').forEach(tr=>{const d=tr.dataset,show=(!modelSrc||d.src===modelSrc)&&(!ven||d.ven===ven)&&(!wt||d.w===wt)&&(!ar||d.a===ar)&&(!txt||d.m.includes(txt));
    tr.style.display=show?'':'none';if(show){u+= +d.u;i+= +d.i;o+= +d.o;r+= +d.r;n++;}});
  const tk=v=>v>=1e9?(v/1e9).toFixed(1)+'B':v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'k':String(Math.round(v));
  const f=document.getElementById('sp_mtotal');if(f)f.innerHTML='<td>Total</td><td>'+n+' models</td><td></td><td>$'+u.toFixed(2)+'</td><td>'+tk(i+o)+'</td><td>'+tk(i)+' / '+tk(o)+'</td><td>'+Math.round(r).toLocaleString()+'</td><td></td><td></td><td></td><td></td><td></td><td></td>';
  modelSort();
}
// column sorting: click a header; numbers sort high first, text A-Z; a second click reverses
let mSortK='u',mSortDir=-1;
const M_NUM=['u','t','i','r','p','c','mem'];
function modelSort(){const tb=document.getElementById('sp_models');if(!tb)return;const num=M_NUM.includes(mSortK);
  [...tb.querySelectorAll('tr[data-src]')].sort((a,b)=>{const x=a.dataset[mSortK]||'',y=b.dataset[mSortK]||'';const ex=x===''||x==='none',ey=y===''||y==='none';
    if(ex!==ey)return ex?1:-1;return (num?(+x-+y):x.localeCompare(y))*mSortDir;}).forEach(tr=>tb.appendChild(tr));
  document.querySelectorAll('table.models th[data-k]').forEach(th=>{th.style.cursor='pointer';const t=th.textContent.replace(/ [\u25B2\u25BC]$/,'');th.textContent=t+(th.dataset.k===mSortK?(mSortDir<0?' \u25BC':' \u25B2'):'');});}
document.querySelector('table.models thead')?.addEventListener('click',e=>{const th=e.target.closest('th[data-k]');if(!th)return;
  const k=th.dataset.k;if(k===mSortK)mSortDir=-mSortDir;else{mSortK=k;mSortDir=M_NUM.includes(k)?-1:1;}modelSort();});
document.getElementById('sp_mw')?.addEventListener('change',modelFilter);
document.getElementById('sp_ma')?.addEventListener('change',modelFilter);
document.getElementById('sp_totals')?.addEventListener('click',e=>{const c=e.target.closest('a.card[data-msrc]');if(!c)return;
  const a=document.querySelector('#sp_msrc a[data-v="'+c.dataset.msrc+'"]');if(a)a.click();document.getElementById('sp_mfilter')?.scrollIntoView({behavior:'smooth',block:'start'});});
document.getElementById('sp_msrc')?.addEventListener('click',e=>{const a=e.target.closest('a');if(!a)return;modelSrc=a.dataset.v;
  document.querySelectorAll('#sp_msrc a').forEach(x=>x.classList.toggle('on',x===a));modelFilter();});
document.getElementById('sp_mven')?.addEventListener('change',modelFilter);
document.getElementById('sp_mq')?.addEventListener('input',modelFilter);
// Tabs: the hash picks one (#overview default), so links and the back button work.
// Hosts has sub-tabs (#hosts/prod default, #hosts/mini, #hosts/dgx, #hosts/delivery).
const TABS=['overview','sites','hosts','fleets','spend'],SUBS=['prod','mini','dgx','delivery'];
function showTab(){const [h,sb,mk,...mr]=location.hash.slice(1).split('/'),t=TABS.includes(h)?h:'overview',u=SUBS.includes(sb)?sb:'prod';
  MODEL_ID=t==='spend'&&mk==='m'?decodeURIComponent(mr.join('/')):'';
  document.querySelectorAll('section.tab').forEach(e=>e.classList.toggle('on',e.id==='t-'+t));
  document.querySelectorAll('.tabs a').forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#'+t));
  document.querySelectorAll('.sub').forEach(e=>e.classList.toggle('on',e.dataset.sub===u));
  document.querySelectorAll('#t-hosts .subtabs a').forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#hosts/'+u));
  const pv=['month','30d','7d','yesterday'].includes(sb)?sb:'30d';
  document.querySelectorAll('#sp_period a').forEach(a=>{a.classList.toggle('on',a.dataset.p===pv);a.setAttribute('href','#spend/'+a.dataset.p+(MODEL_ID?'/m/'+encodeURIComponent(MODEL_ID):''));});
  if(t==='spend'&&spendPeriod!==pv){spendPeriod=pv;spendModels();}
  if(t==='spend')modelPage();}
let spendPeriod='30d',MODEL_ID='',MODELS=null,MODELS_P='',MODELS_LABEL='';
// One model's page: what the model is (facts table) and how we use it (the period's rows for it, split
// by key and by provider), from the same rows the By model table is built from.
function modelPage(){const main=document.getElementById('sp_main'),pg=document.getElementById('sp_model');if(!main||!pg)return;
  main.style.display=MODEL_ID?'none':'';pg.style.display=MODEL_ID?'':'none';if(!MODEL_ID)return;
  const hx=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const usd=x=>'$'+(x>=100?x.toFixed(0):x.toFixed(2));
  const tk=v=>v>=1e9?(v/1e9).toFixed(1)+'B':v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'k':String(Math.round(v));
  const [src,ven,model]=MODEL_ID.split('|'),back='<p><a href="#spend/'+spendPeriod+'" target=_self>&larr; All models</a></p>';
  if(!MODELS||MODELS_P!==spendPeriod){pg.innerHTML=back+'<h2>'+hx(model||'')+'</h2><p class=muted>loading&hellip;</p>';return;}
  const M=MODELS[MODEL_ID];
  if(!M){pg.innerHTML=back+'<h2>'+ico(VENDOR_SITE[ven])+hx(ven||'')+' / '+hx(model||'')+'</h2><p class=muted>No use of this model in '+hx(MODELS_LABEL)+'. Pick another period above.</p>';return;}
  const {x,r0,w,F,line,tline}=M,paid=r0.src==='OpenRouter',T=x.i+x.o;
  const stat=(k,v,sub)=>'<div><span>'+k+'</span><b>'+v+'</b>'+(sub?'<i>'+sub+'</i>':'')+'</div>';
  const kv=(k,v)=>'<tr><td class=muted style="width:180px">'+k+'</td><td>'+v+'</td></tr>';
  const sz=p=>p>=1000?(p/1000).toFixed(2)+' T':p+' B',m=F&&F.p?memGB(F.p):null,ap=F&&F.approx?'~':'';
  const split=f=>{const g={};x.rows.forEach(r=>{const k=f(r),y=g[k]=g[k]||{k,usd:0,i:0,o:0,req:0};y.usd+=r.usd;y.i+=r.i;y.o+=r.o;y.req+=r.req;});
    return Object.values(g).filter(y=>y.usd>0||y.i+y.o>0).sort((a,b)=>b.usd-a.usd||(b.i+b.o)-(a.i+a.o));};
  const tbl=(h,l)=>'<table class="ctbl mtbl"><thead><tr><th>'+h+'</th><th>Spend</th><th>Share</th><th>Tokens</th><th>In / out</th><th>Requests</th><th>$ / 1M tokens</th></tr></thead><tbody>'
    +l.map(y=>'<tr><td>'+hx(y.k)+'</td><td>'+(paid?usd(y.usd):'$0')+'</td><td>'+(paid&&x.usd?Math.round(y.usd/x.usd*100):(T?Math.round((y.i+y.o)/T*100):0))+'%</td><td>'+tk(y.i+y.o)+'</td><td>'+tk(y.i)+' / '+tk(y.o)+'</td><td>'+Math.round(y.req).toLocaleString()+'</td><td>'+(paid&&y.i+y.o?usd(y.usd/(y.i+y.o)*1e6):'&mdash;')+'</td></tr>').join('')+'</tbody></table>';
  const links=['<a href="https://'+(VENDOR_SITE[r0.ven]||'openrouter.ai')+'">'+hx(r0.ven)+' website</a>','<a href="'+modelUrl(r0.full,r0.src,r0.model)+'">'+(w==='open'?'weights on Hugging Face':(r0.src==='OpenRouter'?'OpenRouter model page':'model page'))+'</a>'];
  if(paid&&w==='open')links.push('<a href="https://openrouter.ai/'+hx(r0.full)+'">OpenRouter model page</a>');
  pg.innerHTML=back
    +'<h2 style="font-size:20px;text-transform:none;letter-spacing:0">'+ico(VENDOR_SITE[r0.ven])+hx(r0.ven)+' / '+hx(r0.model)+'</h2>'
    +'<p class=sec>'+hx(r0.full)+' &middot; '+r0.src+' &middot; <span style="color:'+(w==='open'?'#3fb950':(w==='proprietary'?'#c8c8e0':'#d29922'))+'">'+(w==='open'?'open weights':(w==='proprietary'?'proprietary':'weights not known'))+'</span> &middot; '+links.join(' &middot; ')+'</p>'
    +'<h2>Our use &middot; '+hx(MODELS_LABEL)+'</h2><div class=mstats>'
    +stat('Spend',paid?usd(x.usd):'$0',paid?'':'local, no cost')+stat('Tokens',tk(T),tk(x.i)+' in / '+tk(x.o)+' out')+stat('Requests',Math.round(x.req).toLocaleString())
    +stat('$ per 1M tokens',paid&&T?usd(x.usd/T*1e6):'&mdash;')+stat('Tokens per request',x.req?tk(T/x.req):'&mdash;',x.req?tk(x.i/x.req)+' in / '+tk(x.o/x.req)+' out':'')
    +stat('Cost per request',paid&&x.req?'$'+(x.usd/x.req).toFixed(4):'&mdash;')+'</div>'
    +'<div class=charts>'
    +(paid?'<a class="card site"><h3>Spend, 14 days</h3><div class=cv>'+usd((line||[]).reduce((a,b)=>a+(b||0),0))+sparkT(line)+'</div></a>':'')
    +'<a class="card site"><h3>Tokens, 14 days</h3><div class=cv>'+tk((tline||[]).reduce((a,b)=>a+(b||0),0))+sparkT(tline)+'</div>'+(r0.src!=='OpenRouter'?'<span class=muted style="font-size:12px">all '+r0.src+' models together</span>':'')+'</a></div>'
    +(r0.src==='vLLM'||r0.src==='Ollama'||r0.src==='Speech'?'<div id=sp_rt><h2>How it runs</h2><p class=muted>loading&hellip;</p></div>':'')
    +'<h2>By key</h2>'+tbl('Key',split(r=>r.key))
    +'<h2>'+(paid?'Served by (OpenRouter provider)':'Served by')+'</h2>'+tbl('Provider',split(r=>r.by))
    +'<h2>The model</h2><table class=ctbl><tbody>'
    +kv('Weights',w==='open'?'open (published on Hugging Face)':(w==='proprietary'?'proprietary: size and architecture not published':'not known'))
    +(F?kv('Parameters',F.p?ap+sz(F.p)+' total'+(F.a?', '+F.a+' B active per token':''):'&mdash;')
      +kv('Architecture',F.arch&&F.arch!=='MoE'&&F.arch!=='dense'?hx(F.arch)+(F.e?': '+hx(F.e):''):F.arch==='MoE'?'Mixture of experts (MoE)'+(F.e?': '+hx(F.e):'')+'. A router sends each token to a few experts, so it computes like a smaller model but must hold all of it in memory.':(F.arch==='dense'?'Dense: every parameter works on every token.':'&mdash;'))
      +kv('Context',F.ctx?F.ctx.toLocaleString()+' tokens':'&mdash;')
      +kv('Memory to load the weights',m?ap+gb(m[0])+' at 4-bit &middot; '+ap+gb(m[1])+' at 8-bit &middot; '+ap+gb(Math.ceil(F.p*2))+' at 16-bit (BF16); the KV cache for the context comes on top':'&mdash;')
      +kv('Source',hx(F.src)+', checked 2026-11-03'+(F.approx?'. Stored as packed integer weights, so the count is not confirmed':''))
     :(w==='open'?kv('Size','not in the facts table yet'):''))
    +'</tbody></table>';
  if(r0.src==='vLLM'||r0.src==='Ollama'||r0.src==='Speech')runtime(r0,MODEL_ID,spendPeriod);}
// ---- How a local model runs, over the selected period (same completed UTC days as everything else).
// vLLM: its own /metrics (latency histograms, KV and prefix cache, queue) and DCGM for the GPU.
// Ollama: no metrics endpoint; its llama.cpp timing lines in VictoriaLogs, per machine, no model name.
async function runtime(r0,id,per){
  const box=()=>MODEL_ID===id&&spendPeriod===per?document.getElementById('sp_rt'):null;
  const rg=spendRange(per);if(!rg.R){const b=box();if(b)b.innerHTML='<h2>How it runs</h2><p class=muted>no completed day in this period yet</p>';return;}
  const end=Math.floor(Date.now()/1000)-rg.O,start=end-rg.R,step=rg.R>=6*86400?86400:(rg.R>=2*86400?21600:3600),n=Math.round(rg.R/step);
  const W='['+rg.R+'s] offset '+rg.O+'s',SQ='['+rg.R+'s:5m] offset '+rg.O+'s';
  const one=async e=>{const r=await q(e);return r.length&&isFinite(+r[0].value[1])?+r[0].value[1]:null;};
  const line=async e=>{try{const j=await(await fetch('/vm/api/v1/query_range?query='+encodeURIComponent(e)+'&start='+(start+step)+'&end='+end+'&step='+step)).json();
    const r=j.data.result[0];if(!r)return null;const v=Array(n).fill(null);r.values.forEach(([t,x])=>{const i=Math.round((+t-start)/step)-1;if(i>=0&&i<n&&isFinite(+x))v[i]=+x;});return v;}catch(x){return null;}};
  const hx=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const tk=v=>v>=1e9?(v/1e9).toFixed(1)+'B':v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(1)+'k':String(Math.round(v));
  const sec=v=>v==null?'&mdash;':(v<1?Math.round(v*1000)+' ms':v.toFixed(v<10?2:1)+' s'),pc=v=>v==null?'&mdash;':(v>0&&v<0.01?'&lt;1%':Math.round(v*100)+'%'),nm=(v,d)=>v==null?'&mdash;':(+v).toFixed(d||0);
  const per_='per '+(step===86400?'day':(step===21600?'6 hours':'hour'));
  const crd=(t,v,l,sub)=>'<a class="card site"><h3>'+t+'</h3><div class=cv>'+v+(l?sparkT(l.length>=14?l:l):'')+'</div>'+(sub?'<span class=muted style="font-size:12px">'+sub+'</span>':'')+'</a>';
  const grp=(t,cards)=>'<h3 style="margin:14px 0 6px;font-size:13px;color:#9a9ac2;text-transform:uppercase;letter-spacing:.05em">'+t+'</h3><div class=charts>'+cards.join('')+'</div>';
  if(r0.src==='vLLM'){
    const [CT,PORT]=DGX_CT[r0.full]||['?','?'];
    const F='{instance="dgx-llm-1",model_name="'+r0.full+'"}',G='{instance="dgx-llm-1"}',busy='and on() sum(vllm:num_requests_running'+F+') > 0';
    const hq=(qq,m,w)=>'histogram_quantile('+qq+', sum by (le) (increase(vllm:'+m+'_bucket'+F+(w||W)+')))';
    const ratio=(a,b,w)=>'sum(increase(vllm:'+a+F+(w||W)+')) / sum(increase(vllm:'+b+F+(w||W)+'))';
    const S='['+step+'s]';
    const [req,len,ttft50,ttft95,itl50,e2e50,e2e95,q95,pre95,pin,pin95,gout,hit,cachedsh,preempt,kvmax,kv95,wait,waitmax,run,tps,gpu,pw,pwmax,temp,kwh,toks,mem,cfg]=await Promise.all([
      one('sum(increase(vllm:request_success_total'+F+W+'))'),one('sum(increase(vllm:request_success_total{instance="dgx-llm-1",model_name="'+r0.full+'",finished_reason="length"}'+W+'))'),
      one(hq(0.5,'time_to_first_token_seconds')),one(hq(0.95,'time_to_first_token_seconds')),one(hq(0.5,'inter_token_latency_seconds')),
      one(hq(0.5,'e2e_request_latency_seconds')),one(hq(0.95,'e2e_request_latency_seconds')),one(hq(0.95,'request_queue_time_seconds')),one(hq(0.95,'request_prefill_time_seconds')),
      one(ratio('request_prompt_tokens_sum','request_prompt_tokens_count')),one(hq(0.95,'request_prompt_tokens')),one(ratio('request_generation_tokens_sum','request_generation_tokens_count')),
      one(ratio('prefix_cache_hits_total','prefix_cache_queries_total')),one(ratio('prompt_tokens_cached_total','prompt_tokens_total')),one('sum(increase(vllm:num_preemptions_total'+F+W+'))'),
      one('max_over_time(max(vllm:kv_cache_usage_perc'+F+')'+SQ+')'),one('quantile_over_time(0.95, (max(vllm:kv_cache_usage_perc'+F+') '+busy+')'+SQ+')'),
      one('sum_over_time((sum(vllm:num_requests_waiting'+F+') > bool 0)'+SQ+') / count_over_time((sum(vllm:num_requests_running'+F+') > 0)'+SQ+')'),one('max_over_time(sum(vllm:num_requests_waiting'+F+')'+SQ+')'),
      one('max_over_time(sum(vllm:num_requests_running'+F+')'+SQ+')'),one('quantile_over_time(0.5, (sum(rate(vllm:generation_tokens_total'+F+'[5m])) > 1)'+SQ+')'),
      one('avg_over_time((avg(DCGM_FI_DEV_GPU_UTIL'+G+') '+busy+')'+SQ+')'),one('avg_over_time((avg(DCGM_FI_DEV_POWER_USAGE'+G+') '+busy+')'+SQ+')'),
      one('max_over_time(max(DCGM_FI_DEV_POWER_USAGE'+G+')'+SQ+')'),one('max_over_time(max(DCGM_FI_DEV_GPU_TEMP'+G+')'+SQ+')'),
      one('sum(increase(DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION'+G+W+')) / 3.6e9'),
      one('sum(increase(vllm:prompt_tokens_total'+F+W+')) + sum(increase(vllm:generation_tokens_total'+F+W+'))'),
      one('sum(dgx_gpu_process_memory_bytes{instance="dgx-llm-1",container="'+CT+'"})'),q('vllm:cache_config_info{instance="dgx-llm-1",job="'+(CT==='vllm-translate'?'vllm-translate':'vllm-autoresearch')+'"}')]);
    const [lReq,lTtft,lE2e,lTps,lKv,lGpu,lPw,lHit]=await Promise.all([
      line('sum(increase(vllm:request_success_total'+F+S+'))'),line(hq(0.95,'time_to_first_token_seconds',S)),line(hq(0.95,'e2e_request_latency_seconds',S)),
      line('quantile_over_time(0.5, (sum(rate(vllm:generation_tokens_total'+F+'[5m])) > 1)['+step+'s:5m])'),line('max_over_time(max(vllm:kv_cache_usage_perc'+F+')['+step+'s:5m])'),
      line('avg_over_time((avg(DCGM_FI_DEV_GPU_UTIL'+G+') '+busy+')['+step+'s:5m])'),line('avg_over_time(avg(DCGM_FI_DEV_POWER_USAGE'+G+')['+step+'s:5m])'),
      line(ratio('prefix_cache_hits_total','prefix_cache_queries_total',S))]);
    const c=(cfg[0]||{}).metric||{},kvTok=c.num_gpu_blocks&&c.block_size?+c.num_gpu_blocks*+c.block_size:null;
    const b=box();if(!b)return;
    if(!req){b.innerHTML='<h2>How it runs</h2><p class=muted>no requests to this model in '+hx(rg.label)+'</p>';return;}
    // what the numbers point at: each line states its rule and the measured values it rests on
    const notes=[];
    if(kvmax!=null&&kvmax>=0.9)notes.push('The KV cache filled to '+pc(kvmax)+' at its peak'+(preempt?' and '+nm(preempt)+' request'+(preempt>1?'s were':' was')+' preempted (recomputed)':'')+', while its 95th percentile when busy was '+pc(kv95)+'. The cache is '+(c.kv_cache_memory_bytes?(c.kv_cache_memory_bytes/2**30).toFixed(1)+' GiB':'?')+(kvTok?' ('+tk(kvTok)+' tokens)':'')+' at gpu_memory_utilization '+hx(c.gpu_memory_utilization||'?')+'. Peaks come from long prompts (95th percentile '+tk(pin95||0)+' tokens) running together: more KV memory, or a lower max_num_seqs / max context for this caller, removes the preemptions.');
    if(cachedsh!=null)notes.push(pc(cachedsh)+' of prompt tokens were served from the prefix cache (block hit rate '+pc(hit)+'). Prompts that start with the same text (system prompt, instructions, shared context) and put the varying part last raise this, and cut prefill (95th percentile '+sec(pre95)+').');
    if(len)notes.push(nm(len)+' request'+(len>1?'s':'')+' ('+(len/req*100).toFixed(1)+'%) stopped at max_tokens, so their answers are cut off; the caller sets the limit.');
    if(wait!=null)notes.push(wait<0.02?'Requests almost never queued (a wait in '+pc(wait)+' of busy 5-minute windows, at most '+nm(waitmax)+' waiting; up to '+nm(run)+' ran at once): capacity is not the limit.':'Requests waited in '+pc(wait)+' of busy 5-minute windows (at most '+nm(waitmax)+' waiting): at those times the server is the bottleneck.');
    if(e2e95!=null&&itl50)notes.push('One stream decodes at about '+Math.round(1/itl50)+' tokens/s (inter-token '+sec(itl50)+'), so end-to-end time is mostly output length: 95th percentile '+sec(e2e95)+' for '+tk(gout||0)+' output tokens on average.');
    b.innerHTML='<h2>How it runs &middot; vLLM on the DGX</h2><p class=sec>'+hx(rg.label)+'; lines '+per_+'. Container '+CT+', port '+PORT+'. GPU figures are the whole GPU (DCGM), shared with the other DGX services.</p>'
      +grp('Traffic',[crd('Requests',Math.round(req).toLocaleString(),lReq,len?nm(len)+' cut at max_tokens':'none cut at max_tokens'),
        crd('Prompt / request',tk(pin||0),null,'95th percentile '+tk(pin95||0)),crd('Output / request',tk(gout||0),null,'mean'),crd('Most at once',nm(run),null,'running; '+nm(waitmax)+' waiting at most')])
      +grp('Latency',[crd('First token, p95',sec(ttft95),lTtft,'median '+sec(ttft50)),crd('End to end, p95',sec(e2e95),lE2e,'median '+sec(e2e50)),
        crd('Per token',sec(itl50),null,'median inter-token = '+(itl50?Math.round(1/itl50):'?')+' tokens/s per stream'),crd('Queue, p95',sec(q95),null,'prefill p95 '+sec(pre95))])
      +grp('Throughput and caches',[crd('Output tokens/s',nm(tps),lTps,'median while generating'),crd('Prefix cache hits',pc(hit),lHit,pc(cachedsh)+' of prompt tokens cached'),
        crd('KV cache peak',pc(kvmax),lKv,'p95 when busy '+pc(kv95)+' &middot; '+nm(preempt)+' preemptions'),crd('KV cache size',c.kv_cache_memory_bytes?(c.kv_cache_memory_bytes/2**30).toFixed(1)+' GiB':'&mdash;',null,(kvTok?tk(kvTok)+' tokens &middot; ':'')+hx(c.cache_dtype||'')+(c.enable_prefix_caching==='True'?' &middot; prefix caching on':''))])
      +grp('GPU (NVIDIA GB10, whole GPU)',[crd('GPU busy while serving',gpu==null?'&mdash;':Math.round(gpu)+'%',lGpu,'average utilisation while requests run'),
        crd('Power',pw==null?'&mdash;':Math.round(pw)+' W',lPw,'while serving; peak '+(pwmax==null?'?':Math.round(pwmax))+' W, max '+(temp==null?'?':Math.round(temp))+' &deg;C'),
        crd('Energy',kwh==null?'&mdash;':kwh.toFixed(1)+' kWh',null,kwh&&toks?'whole GPU; '+(kwh*1000/(toks/1e6)).toFixed(0)+' Wh per 1M tokens of this model, upper bound':'whole GPU'),
        crd('GPU memory',mem?(mem/1e9).toFixed(1)+' GB':'&mdash;',null,CT+' now (weights + KV cache)')])
      +(notes.length?'<h3 style="margin:14px 0 6px;font-size:13px;color:#9a9ac2;text-transform:uppercase;letter-spacing:.05em">What the numbers point at</h3><ul style="max-width:900px;line-height:1.55;color:#c8c8e0;font-size:13px;padding-left:18px">'+notes.map(x=>'<li>'+x+'</li>').join('')+'</ul>':'');
    return;}
  if(r0.src==='Speech'){
    const [CT,PORT]=DGX_CT[r0.full]||['?','?'],JOB={pyannote:['pyannote-app','/v1/diarize'],moss:['moss-app','/v1/transcribe']}[CT];
    const S='['+step+'s]',N='{instance="dgx-llm-1",name="'+CT+'"}';
    const common=[one('sum(dgx_gpu_process_memory_bytes{instance="dgx-llm-1",container="'+CT+'"})'),one('max_over_time(max(container_memory_working_set_bytes'+N+')'+SQ+')'),
      one('sum(rate(container_cpu_usage_seconds_total'+N+W+'))'),line('max_over_time(max(container_memory_working_set_bytes'+N+')['+step+'s:5m])')];
    let cards,head;
    if(JOB){const H='{job="'+JOB[0]+'",handler="'+JOB[1]+'"}',hq=(qq,w)=>'histogram_quantile('+qq+', sum by (le) (increase(http_request_duration_seconds_bucket'+H+(w||W)+')))';
      const mean=w=>'sum(increase(http_request_duration_seconds_sum'+H+w+')) / sum(increase(http_request_duration_seconds_count'+H+w+'))';
      const [req,err,avg,busy,lReq,lAvg,gm,cm,cpu,lMem]=await Promise.all([one('sum(increase(http_requests_total'+H+W+'))'),one('sum(increase(http_requests_total{job="'+JOB[0]+'",handler="'+JOB[1]+'",status=~"5.."}'+W+'))'),
        one(mean(W)),one('sum(increase(http_request_duration_seconds_sum'+H+W+'))'),line('sum(increase(http_requests_total'+H+S+'))'),line(mean(S)),...common]);
      head='its own /metrics (requests and their duration, per endpoint '+JOB[1]+')';
      cards=grp('Traffic and latency',[crd('Requests',Math.round(req||0).toLocaleString(),lReq,(err?nm(err)+' failed (5xx)':'none failed')),crd('Time per request',sec(avg),lAvg,'mean, the whole file end to end; '+(busy?(busy/3600).toFixed(1)+' h busy in the period':''))])
        +grp('Resources',[crd('GPU memory',gm?(gm/1e9).toFixed(1)+' GB':'&mdash;',null,CT+' now'),crd('Container memory',cm?(cm/1e9).toFixed(1)+' GB':'&mdash;',lMem,'peak in the period (RAM)'),
          crd('CPU',cpu==null?'&mdash;':(cpu).toFixed(2)+' cores',null,'average over the period')])
        +'<p class=muted style="font-size:12px;max-width:900px">Audio hours and the real-time factor need the length of the audio each request carried; '+hx(CT)+' does not report it yet.</p>';}
    else{// whisper: log lines
      const lq2=async(expr,type)=>{try{const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
          body:JSON.stringify({queries:[{refId:'A',datasource:{uid:'victorialogs'},expr,queryType:type||'stats',step:step+'s'}],from:String(start*1000),to:String(end*1000)})})).json();
        const o={};((r.results.A||{}).frames||[]).forEach(f=>{const l=f.schema.fields[1].labels||{},vs=f.data.values;o[l.__name__]=type==='statsRange'?{t:vs[0],v:vs[1]}:+vs[1][vs[1].length-1];});return o;}catch(x){return {};}};
      const AU=WHISPER_AUDIO;
      const [a,rq,rl,al,err,gm,cm,cpu,lMem]=await Promise.all([lq2(AU+' | stats count() as n, sum(sec) as sec, quantile(0.5, sec) as p50, quantile(0.95, sec) as p95'),
        lq2('container:"faster-whisper" "POST /v1/audio/transcriptions" | stats count() as n'),lq2('container:"faster-whisper" "POST /v1/audio/transcriptions" | stats count() as n','statsRange'),
        lq2(AU+' | stats sum(sec) as sec','statsRange'),lq2('container:"faster-whisper" "POST /v1/audio/transcriptions" -"200 OK" | stats count() as n'),...common]);
      const toLine=o=>{if(!o)return null;const v=Array(n).fill(null);o.t.forEach((t,i)=>{const k=Math.floor((t/1000-start)/step);if(k>=0&&k<n)v[k]=+o.v[i];});return v;};
      // real-time factor: processing wall time / audio length. Start = "Processing audio with duration",
      // end = the next "is idle" (logged when no request is left running); overlapping requests count as
      // one busy stretch for their audio together.
      let rtf=null,rtfLine=null,longMed=null,shortMed=null,busyS=0;
      try{const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
          body:JSON.stringify({queries:[{refId:'A',datasource:{uid:'victorialogs'},expr:'container:"faster-whisper" ("Processing audio with duration" or "is idle") | extract_regexp "duration (?P<d>[0-9:.]+)$" | fields _time, d',queryType:'instant',maxLines:100000}],from:String(start*1000),to:String(end*1000)})})).json();
        const f=((r.results.A||{}).frames||[])[0];
        if(f){const fi=k=>f.schema.fields.findIndex(x=>x.name===k),T=f.data.values[fi('Time')],Lb=f.data.values[fi('labels')];
          const ev=T.map((t,i)=>({t:+t,d:(Lb[i]||{}).d})).sort((a,b)=>a.t-b.t),toS=d=>d.split(':').reduce((a,x)=>a*60+ +x,0);
          const bs=Array(n).fill(0),as=Array(n).fill(0),one=[],shortR=[];let open=[],audio=0;
          for(const e of ev){if(e.d){open.push({t:e.t,a:toS(e.d)});continue;}if(!open.length)continue;
            const w=(e.t-open[0].t)/1000,a=open.reduce((p,x)=>p+x.a,0),k=Math.floor((open[0].t/1000-start)/step);
            if(w>=0&&a>0){busyS+=w;audio+=a;if(k>=0&&k<n){bs[k]+=w;as[k]+=a;}if(open.length===1)(a>=60?one:shortR).push(w/a);}open=[];}
          const med=l=>{if(!l.length)return null;const x=[...l].sort((p,q)=>p-q);return x[Math.floor(x.length/2)];};
          if(audio){rtf=busyS/audio;rtfLine=bs.map((b,i)=>as[i]?b/as[i]:null);longMed=med(one);shortMed=med(shortR);}}}catch(x){}
      const xr=v=>v==null?'&mdash;':v.toFixed(3)+' <span class=muted style="font-size:12px;font-weight:400">('+Math.round(1/v)+'&times; real time)</span>';
      const mm=v=>v==null?'&mdash;':(v>=3600?(v/3600).toFixed(1)+' h':(v>=60?Math.round(v/60)+' min':Math.round(v)+' s'));
      head='its log lines (faster-whisper serves no /metrics): each request and the length of its audio';
      cards=grp('Traffic',[crd('Requests',Math.round(rq.n||0).toLocaleString(),toLine(rl.n),(err.n?nm(err.n)+' not 200 OK':'all 200 OK')),
          crd('Audio transcribed',mm(a.sec),toLine(al.sec),'median clip '+mm(a.p50)+', 95th percentile '+mm(a.p95))])
        +grp('Speed',[crd('Real-time factor',xr(rtf),rtfLine,'processing time / audio length, all requests; '+(busyS/3600).toFixed(1)+' h busy'),
          crd('Clips of 1 min or more',xr(longMed),null,'median per clip'),crd('Clips under 1 min',xr(shortMed),null,'median per clip: fixed overhead per request dominates')])
        +grp('Resources',[crd('GPU memory',gm?(gm/1e9).toFixed(1)+' GB':'&mdash;',null,CT+' now'),crd('Container memory',cm?(cm/1e9).toFixed(1)+' GB':'&mdash;',lMem,'peak in the period (RAM)'),
          crd('CPU',cpu==null?'&mdash;':(cpu).toFixed(2)+' cores',null,'average over the period')]);}
    const b=box();if(!b)return;
    b.innerHTML='<h2>How it runs &middot; '+hx(CT)+' on the DGX</h2><p class=sec>'+hx(rg.label)+'; lines '+per_+'. Port '+PORT+'. From '+head+', cAdvisor (container) and the GPU process list.</p>'+cards;
    return;}
  // Ollama: three per-machine stats queries over the period's log lines
  const lq=async(expr,type)=>{try{const r=await(await fetch('/grafana/api/ds/query',{method:'POST',headers:{Authorization:'Bearer '+GTOK,'Content-Type':'application/json'},
      body:JSON.stringify({queries:[{refId:'A',datasource:{uid:'victorialogs'},expr,queryType:type||'stats',step:step+'s'}],from:String(start*1000),to:String(end*1000)})})).json();
    const o={};((r.results.A||{}).frames||[]).forEach(f=>{const l=f.schema.fields[1].labels||{},vs=f.data.values;(o[l.instance]=o[l.instance]||{})[l.__name__]=type==='statsRange'?{t:vs[0],v:vs[1]}:+vs[1][vs[1].length-1];});return o;}catch(x){return {};}};
  const TL=p=>'job:"ollama" '+p+' | extract_regexp "= +(?P<ms>[0-9.]+) ms / +(?P<n>[0-9]+) tokens( \\\\( *[0-9.]+ ms per token, +(?P<tps>[0-9.]+) tokens per second)?"';
  const [gen,pro,tot,rng]=await Promise.all([
    lq(TL('"eval time =" -"prompt eval time"')+' | stats by (instance) count() as req, quantile(0.5, tps) as tps50, avg(n) as outn'),
    lq(TL('"prompt eval time ="')+' | stats by (instance) quantile(0.5, tps) as ptps50, avg(n) as inn'),
    lq(TL('"total time ="')+' | stats by (instance) quantile(0.5, ms) as t50, quantile(0.95, ms) as t95'),
    lq(TL('"eval time =" -"prompt eval time"')+' | stats by (instance) quantile(0.5, tps) as tps50','statsRange')]);
  const b=box();if(!b)return;const ins=Object.keys(gen).sort();
  if(!ins.length){b.innerHTML='<h2>How it runs</h2><p class=muted>no Ollama requests in '+hx(rg.label)+'</p>';return;}
  const toLine=o=>{if(!o)return null;const v=Array(n).fill(null);o.t.forEach((t,i)=>{const k=Math.floor((t/1000-start)/step);if(k>=0&&k<n)v[k]=+o.v[i];});return v;};
  const NAME={'dgx-llm-1':'DGX','x3':'X3 (omarchy)','macbook':'MacBook'};
  b.innerHTML='<h2>How it runs &middot; Ollama</h2><p class=sec>'+hx(rg.label)+'; per machine, from Ollama&rsquo;s own timing lines (they name no model, so this is every model on that machine). Lines: median output speed '+per_+'.</p>'
    +grp('By machine',ins.map(i=>{const g=gen[i]||{},p=pro[i]||{},t=tot[i]||{};
      return crd(hx(NAME[i]||i),nm(g.tps50,1)+' <span class=muted style="font-size:12px;font-weight:400">tokens/s out</span>',toLine((rng[i]||{}).tps50),
        Math.round(g.req||0).toLocaleString()+' requests &middot; prompt '+nm(p.ptps50,0)+' tokens/s &middot; '+tk(p.inn||0)+' in / '+tk(g.outn||0)+' out per request &middot; total '+sec((t.t50||0)/1000)+' median, '+sec((t.t95||0)/1000)+' p95');}));
}
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
