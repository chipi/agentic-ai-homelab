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
H=https://homelab.tail6d0ed4.ts.net; G=$H/grafana
DASH_MINI=$G/d/homelab-mini/homelab-e28094-mac-mini
DASH_GPU=$G/d/gpu-dcgm/gpu-e28094-dcgm
DASH_DGX=$G/d/dgx-services/dgx-e28094-services
DASH_CAD=$G/d/containers-cadvisor/containers-e28094-cadvisor
DASH_PROD=$G/d/prod-infra-host-overview/host-overview
DASH_PCON=$G/d/prod-infra-containers/containers
DASH_PEDGE=$G/d/prod-infra-edge-security/edge-security
DASH_OPER=$G/d/podcast-operator-overview/overview
DASH_PLAYER=$G/d/podcast-player-overview/overview
DASH_FLEET=$G/d/signal-fleet-disp
DASH_INBOX=$G/d/sf-inbox
DASH_BUGFIX=$G/d/bugfix-fleet-work
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
a.card{background:#14141f;border:1px solid #26263a;border-radius:8px;padding:10px 12px;flex:1;min-width:110px;display:block;text-decoration:none;color:inherit}
a.card:hover{border-color:#3d3d63}
.card h3{margin:0 0 3px;font-size:10px;color:#9a9ac2;text-transform:uppercase;letter-spacing:.05em}
.cv{font-size:19px;font-weight:600;margin-bottom:2px}
.spark{width:100%;height:40px;display:block}.spark polyline{fill:none;stroke:#7aa2ff;stroke-width:2;vector-effect:non-scaling-stroke}
.health{display:flex;gap:14px;margin:0 0 12px;flex-wrap:wrap;font-size:13px}
a.svc{color:#c8c8e0;text-decoration:none}a.svc:hover{text-decoration:underline}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.up{background:#3fb950}.down{background:#f85149}.stale{background:#7a7a8c}
.dock{color:#c8c8e0;font-size:13.5px;margin:2px 0 4px}.dock b{color:#e6e6ef}
h3.sectitle{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#9a9ac2;font-weight:600;margin:16px 0 6px;border-bottom:1px solid #22223a;padding-bottom:4px}
table.ctbl td{padding:4px 10px;border-bottom:1px solid #1a1a2b;font-size:13px;vertical-align:middle}
table.ctbl td.u{color:#8888aa}table.ctbl code{font-size:12px}
@media(max-width:640px){
  body{margin:14px}
  h1{font-size:20px;margin-bottom:14px}
  .cols{gap:18px}.col{min-width:0;flex-basis:100%}
  .charts{gap:8px}a.card{min-width:calc(50% - 4px);padding:9px 10px}
  .cv{font-size:17px}.spark{height:34px}
  table{font-size:13px}th,td{padding:6px 8px}
  code{word-break:break-all}
  .sysrow,.dock,.sec,.health{font-size:12.5px}
}</style></head><body>
<h1>homelab</h1>
<div style="margin:0 0 22px">
  <h2><a href="$DASH_FLEET">Triage fleet &rarr;</a></h2>
  <div class=charts style="max-width:1140px">
    <a class=card href="$DASH_INBOX"><h3>Needs you</h3><div id=f_inbox>&hellip;</div></a>
    <a class=card href="$DASH_INBOX"><h3>Escalations 7d</h3><div id=f_esc>&hellip;</div></a>
    <a class=card href="$DASH_FLEET"><h3>Decisions 24h</h3><div id=f_dec>&hellip;</div></a>
    <a class=card href="$DASH_FLEET"><h3>Spend today</h3><div id=f_spend>&hellip;</div></a>
    <a class=card href="$DASH_FLEET"><h3>Spend this month</h3><div id=f_month>&hellip;</div></a>
    <a class=card href="$DASH_FLEET"><h3>Spend total</h3><div id=f_total>&hellip;</div></a>
  </div>
</div>
<div style="margin:0 0 22px">
  <h2><a href="$DASH_BUGFIX">Bug-fix fleet &rarr;</a></h2>
  <div class=charts style="max-width:1140px">
    <a class=card href="$DASH_BUGFIX"><h3>Chains shipped 7d</h3><div id=b_ship>&hellip;</div></a>
    <a class=card href="$DASH_BUGFIX"><h3>Stuck / needs-info 7d</h3><div id=b_stuck>&hellip;</div></a>
    <a class=card href="$DASH_BUGFIX"><h3>Fix episodes 7d</h3><div id=b_ep>&hellip;</div></a>
    <a class=card href="$DASH_BUGFIX"><h3>Spend this month</h3><div id=b_month>&hellip;</div></a>
    <a class=card href="$DASH_BUGFIX"><h3>Spend total</h3><div id=b_total>&hellip;</div></a>
    <a class=card href="https://github.com/search?q=owner%3Achipi+is%3Aissue+is%3Aopen+label%3A%22triage-fleet%2Factionable%22"><h3>Routable now</h3><div id=b_route>&hellip;</div></a>
  </div>
</div>
<div class=cols>
<div class=col>
  <h2><a href="$DASH_MINI">Mac mini &rarr;</a></h2>
  <div id=sysrow class=sysrow>&hellip;</div>
  <div class=charts>
    <a class=card href="$DASH_MINI"><h3>CPU</h3><div id=c_cpu>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>CPU temp</h3><div id=c_temp>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>Memory</h3><div id=c_mem>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>Disk</h3><div id=c_disk>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>Disk IO</h3><div id=c_io>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>Network</h3><div id=c_net>&hellip;</div></a>
  </div>
  <div id=health class=health></div>
  <h3 class=sectitle>Containers</h3>
  <div class=dock>&#128051; <a href="$DASH_CAD" style=color:inherit;text-decoration:none><span id=mdocker>&hellip;</span></a></div>
  <table class=ctbl><tbody id=mctr></tbody></table>
  <h3 class=sectitle>Services &amp; credentials</h3>
  <table><thead><tr><th>Service</th><th>Port</th><th>User</th><th>Password</th></tr></thead><tbody>
HDR
row "Grafana"         "$G"            "$GF_U" "$GF_P" "3000"
row "GlitchTip"       "$H/glitchtip"  "$GT_U" "$GT_P" "8090"
row "Langfuse"        "$H:8443"       "$LF_U" "$LF_P" "4000"
row "Umami"           "$H:8444"       "$UM_U" "$UM_P" "3001"
row "LiteLLM"         "$H:10000/ui/"  "admin" "$LL_K" "4001"
row "VictoriaMetrics" "$H/vm/vmui"    "&mdash;" "tailnet" "8428"
row "VictoriaLogs"    "$H/vlogs"      "&mdash;" "tailnet" "9428"
row "VictoriaTraces"  "$H/vtraces"    "&mdash;" "tailnet" "10428"
cat <<MID
  </tbody></table>
</div>
<div class=col>
  <h2><a href="$DASH_GPU">DGX &middot; dgx-llm-1 &rarr;</a></h2>
  <div id=dgxrow class=sysrow>&hellip;</div>
  <div class=charts>
    <a class=card href="$DASH_GPU"><h3>GPU temp</h3><div id=g_temp>&hellip;</div></a>
    <a class=card href="$DASH_GPU"><h3>GPU util</h3><div id=g_util>&hellip;</div></a>
    <a class=card href="$DASH_GPU"><h3>GPU power</h3><div id=g_pow>&hellip;</div></a>
    <a class=card href="$DASH_GPU"><h3>Mem temp</h3><div id=g_vram>&hellip;</div></a>
  </div>
  <div class=charts>
    <a class=card href="$DASH_GPU"><h3>Host CPU</h3><div id=d_cpu>&hellip;</div></a>
    <a class=card href="$DASH_GPU"><h3>Unified mem</h3><div id=d_mem>&hellip;</div></a>
    <a class=card href="$DASH_GPU"><h3>Host disk</h3><div id=d_disk>&hellip;</div></a>
    <a class=card href="$DASH_GPU"><h3>Disk IO</h3><div id=d_io>&hellip;</div></a>
    <a class=card href="$DASH_GPU"><h3>Network</h3><div id=d_net>&hellip;</div></a>
  </div>
  <div id=dgxhealth class=health></div>
  <h3 class=sectitle>Containers</h3>
  <div class=dock>&#128051; <a href="$DASH_CAD" style=color:inherit;text-decoration:none><span id=ddocker>&hellip;</span></a></div>
  <table class=ctbl><tbody id=dgxctr></tbody></table>
  <h3 class=sectitle>Services</h3>
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
</div>
<div class=col>
  <h2><a href="$DASH_PROD">Production &middot; prod-podcast &rarr;</a></h2>
  <div id=prodrow class=sysrow>&hellip;</div>
  <div class=charts>
    <a class=card href="$DASH_PROD"><h3>CPU</h3><div id=p_cpu>&hellip;</div></a>
    <a class=card href="$DASH_PROD"><h3>Memory</h3><div id=p_mem>&hellip;</div></a>
    <a class=card href="$DASH_PROD"><h3>Disk</h3><div id=p_disk>&hellip;</div></a>
    <a class=card href="$DASH_PROD"><h3>Disk IO</h3><div id=p_io>&hellip;</div></a>
    <a class=card href="$DASH_PROD"><h3>Network</h3><div id=p_net>&hellip;</div></a>
  </div>
  <h3 class=sectitle>Containers</h3>
  <div class=dock>&#128051; <a href="$DASH_PCON" style=color:inherit;text-decoration:none><span id=pdocker>&hellip;</span></a></div>
  <table class=ctbl><tbody id=pctr></tbody></table>
  <h3 class=sectitle>Services</h3>
  <table><thead><tr><th>Service</th><th>Board</th><th>Role</th></tr></thead><tbody>
MID2
dsvc "podcast operator" "ops" "operator API + viewer"  "$DASH_OPER"
dsvc "podcast player"   "app" "consumer player (public)" "$DASH_PLAYER"
dsvc "edge / security"  "443" "shared Caddy + fail2ban" "$DASH_PEDGE"
dsvc "containers"       "cA"  "cAdvisor"               "$DASH_PCON"
cat <<MID3
  </tbody></table>
</div>
</div>
<p class=sec id=fresh></p>
MID3
cat <<'SCRIPT'
<script>
const W=260,H=40,B='https://homelab.tail6d0ed4.ts.net',G=B+'/grafana';
const MINILINK={grafana:G,glitchtip:B+'/glitchtip',langfuse:B+':8443',umami:B+':8444',litellm:B+':10000/ui',victoriametrics:B+'/vm/vmui',victorialogs:B+'/vlogs',victoriatraces:B+'/vtraces'};
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
async function badges(elId,metric,order,linkFor){
  const hs=await q(metric),map={},now=Date.now()/1000;hs.forEach(s=>map[s.metric.service]=s.value);
  const el=document.getElementById(elId);if(!el)return;
  el.innerHTML=order.map(n=>{let c='stale';const v=map[n];if(v){const a=now-+v[0];c=a>120?'stale':(+v[1]?'up':'down');}return '<a class=svc href="'+linkFor(n)+'"><span class="dot '+c+'"></span>'+n+'</a>';}).join('');
}
async function ctable(elId,box){
  const rows=await q('container_uptime_seconds{box=\"'+box+'\"}');
  const el=document.getElementById(elId);if(!el)return;
  const col={running:'#3fb950',restarting:'#d29922',created:'#d29922',paused:'#d29922',exited:'#f85149',dead:'#f85149'};
  if(!rows.length){el.innerHTML='<tr><td class=muted colspan=4>no data</td></tr>';return;}
  el.innerHTML=rows.sort((a,b)=>{const A=(a.metric.app||'')+'/'+a.metric.name,B=(b.metric.app||'')+'/'+b.metric.name;return A<B?-1:1;}).map(s=>{const m=s.metric,c=col[m.state]||'#7a7a8c',up=m.state=='running'?fmtUp(s.value[1]):m.state;return '<tr><td>'+m.name+'</td><td><span class=dot style=\"background:'+c+'\"></span></td><td class=u>'+up+'</td><td>'+(m.port?'<code>'+m.port+'</code>':'&mdash;')+'</td></tr>';}).join('');
}
async function mini(){
  draw('c_cpu','mini_cpu_used_percent',x=>x.toFixed(0)+'%',100);
  draw('c_temp','mini_cpu_temp_celsius',x=>x.toFixed(0)+'&deg;C',100);
  {const mt=await g1('mini_mem_total_bytes'),gb=mt?(+mt[1]/1073741824).toFixed(0):'?';
   draw('c_mem','mini_mem_used_percent',x=>x.toFixed(0)+'% <span class=muted>/ '+gb+' GB</span>',100);}
  draw('c_disk','mini_disk_free_bytes',x=>(x/1073741824).toFixed(0)+' GB');
  draw('c_io','mini_disk_io_bytes_per_sec',x=>(x/1048576).toFixed(1)+' MB/s');
  draw('c_net','sum(rate(node_network_receive_bytes_total{instance=\"homelab\"}[2m]))+sum(rate(node_network_transmit_bytes_total{instance=\"homelab\"}[2m]))',x=>(x/1048576).toFixed(1)+' MB/s');
  const L=x=>x?(+x[1]).toFixed(2):'&mdash;';
  const l1=await g1('mini_load1'),l5=await g1('mini_load5'),l15=await g1('mini_load15'),sw=await g1('mini_swap_used_bytes'),up=await g1('mini_uptime_seconds');
  const sr=document.getElementById('sysrow');if(sr)sr.innerHTML='Load <b>'+L(l1)+' / '+L(l5)+' / '+L(l15)+'</b> &middot; Swap <b>'+(sw?((+sw[1])/1048576).toFixed(0)+' MB':'&mdash;')+'</b> &middot; Up <b>'+(up?fmtUp(up[1]):'&mdash;')+'</b>';
  badges('health','service_up',['grafana','glitchtip','langfuse','umami','litellm','victoriametrics','victorialogs','victoriatraces'],n=>MINILINK[n]||G);
  const run=await g1('mini_docker_running'),tot=await g1('mini_docker_total'),rst=await g1('mini_docker_restarting'),unh=await g1('mini_docker_unhealthy');
  const md=document.getElementById('mdocker');if(md&&run)md.innerHTML='<b>'+run[1]+'/'+tot[1]+'</b> running'+(rst&&+rst[1]?' &middot; <span style=color:#f85149>'+rst[1]+' restarting</span>':'')+(unh&&+unh[1]?' &middot; <span style=color:#f85149>'+unh[1]+' unhealthy</span>':'');
  ctable('mctr','mini');
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
  draw('d_disk','node_filesystem_avail_bytes{instance="dgx-llm-1",mountpoint="/"}',x=>(x/1073741824).toFixed(0)+' GB');
  draw('d_io','sum(rate(node_disk_read_bytes_total'+D+'[2m]))+sum(rate(node_disk_written_bytes_total'+D+'[2m]))',x=>(x/1048576).toFixed(2)+' MB/s');
  draw('d_net','sum(rate(node_network_receive_bytes_total'+D+'[2m]))+sum(rate(node_network_transmit_bytes_total'+D+'[2m]))',x=>(x/1048576).toFixed(2)+' MB/s');
  const clk=await g1('DCGM_FI_DEV_SM_CLOCK'),mbw=await g1('DCGM_FI_DEV_MEM_COPY_UTIL');
  const L=x=>x?(+x[1]).toFixed(2):'&mdash;';
  const l1=await g1('node_load1'+D),l5=await g1('node_load5'+D),l15=await g1('node_load15'+D),up=await g1('node_time_seconds'+D+'-node_boot_time_seconds'+D);
  const dr=document.getElementById('dgxrow');if(dr)dr.innerHTML='Clock <b>'+(clk?(+clk[1]).toFixed(0)+' MHz':'&mdash;')+'</b> &middot; Mem-BW <b>'+(mbw?(+mbw[1]).toFixed(0)+'%':'&mdash;')+'</b> &middot; Load <b>'+L(l1)+' / '+L(l5)+' / '+L(l15)+'</b> &middot; Up <b>'+(up?fmtUp(up[1]):'&mdash;')+'</b>';
  badges('dgxhealth','dgx_service_up',['ollama','whisper','diarization','moss','cadvisor','dcgm'],n=>DGXDASH);
  const cc=await g1('count(container_last_seen{instance=\"dgx-llm-1\"})'),mem=await g1('sum(container_memory_usage_bytes{instance=\"dgx-llm-1\",id=\"/\"})');
  const dd=document.getElementById('ddocker');if(dd)dd.innerHTML='<b>'+(cc?cc[1]:'&mdash;')+'</b> containers &middot; <b>'+(mem?(+mem[1]/1e9).toFixed(1)+' GB':'&mdash;')+'</b>';
  ctable('dgxctr','dgx');
}
async function prod(){
  const P='{instance="prod-podcast"}';
  draw('p_cpu','100-avg(rate(node_cpu_seconds_total{instance="prod-podcast",mode="idle"}[5m]))*100',x=>x.toFixed(0)+'%',100);
  {const mt=await g1('node_memory_MemTotal_bytes'+P),gb=mt?(+mt[1]/1073741824).toFixed(0):'?';
   draw('p_mem','100-node_memory_MemAvailable_bytes'+P+'/node_memory_MemTotal_bytes'+P+'*100',x=>x.toFixed(0)+'% <span class=muted>/ '+gb+' GB</span>',100);}
  draw('p_disk','node_filesystem_avail_bytes{instance="prod-podcast",mountpoint="/"}',x=>(x/1073741824).toFixed(0)+' GB');
  draw('p_io','sum(rate(node_disk_read_bytes_total'+P+'[2m]))+sum(rate(node_disk_written_bytes_total'+P+'[2m]))',x=>(x/1048576).toFixed(2)+' MB/s');
  draw('p_net','sum(rate(node_network_receive_bytes_total'+P+'[2m]))+sum(rate(node_network_transmit_bytes_total'+P+'[2m]))',x=>(x/1048576).toFixed(2)+' MB/s');
  const L=x=>x?(+x[1]).toFixed(2):'&mdash;';
  const l1=await g1('node_load1'+P),l5=await g1('node_load5'+P),l15=await g1('node_load15'+P);
  const up=await g1('node_time_seconds'+P+'-node_boot_time_seconds'+P);
  const pr=document.getElementById('prodrow');if(pr)pr.innerHTML='Load <b>'+L(l1)+' / '+L(l5)+' / '+L(l15)+'</b> &middot; Up <b>'+(up?fmtUp(up[1]):'&mdash;')+'</b>';
  const cc=await g1('count(container_last_seen'+P+')');
  const pd=document.getElementById('pdocker');if(pd)pd.innerHTML='<b>'+(cc?cc[1]:'&mdash;')+'</b> containers';
  ctable('pctr','prod');
}
async function fleet(){
  const N=x=>x?(+x[1]).toFixed(0):'&mdash;';
  const qd=await g1('sum(last_over_time(signal_fleet_queue_depth[2h]))');
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
  set('f_spend',duo(sp,tkD));set('f_month',duo(mo,tkM));set('f_total',duo(al,tkA));
  // bug-fix fleet row — zeros until chains run; same accounting shape
  const bs=await g1('sum(count_over_time(bugfix_fleet_flow{state="shipped"}[7d]))');
  const bx=await g1('sum(count_over_time(bugfix_fleet_flow{state=~"stuck|needs-info"}[7d]))');
  const be=await g1('sum(count_over_time(bugfix_fleet_cost_usd[7d]))');
  const bmo=await g1('sum(sum_over_time(bugfix_fleet_cost_usd['+mS+'s]))');
  const bal=await g1('sum(sum_over_time(bugfix_fleet_cost_usd[180d]))');
  const btM=await g1('sum(sum_over_time(bugfix_fleet_tokens['+mS+'s]))');
  const btA=await g1('sum(sum_over_time(bugfix_fleet_tokens[180d]))');
  set('b_ship',cv(N(bs)));set('b_stuck',cv(N(bx)));set('b_ep',cv(N(be)));
  set('b_month',duo(bmo,btM));set('b_total',duo(bal,btA));
  try{const r=await(await fetch('https://api.github.com/search/issues?q=owner%3Achipi+is%3Aissue+is%3Aopen+label%3A%22triage-fleet%2Factionable%22')).json();
    set('b_route',cv(typeof r.total_count==='number'?String(r.total_count):'&rarr;'));}
  catch(e){set('b_route',cv('&rarr;'));}
}
async function fresh(){const now=Date.now()/1000,age=x=>x?Math.round(now-+x[0])+'s ago':'no data';const mc=await g1('mini_cpu_used_percent'),dg=await g1('DCGM_FI_DEV_GPU_TEMP'),pc=await g1('node_load1{instance="prod-podcast"}');const el=document.getElementById('fresh');if(el)el.innerHTML='collectors &middot; mini '+age(mc)+' &middot; dgx '+age(dg)+' &middot; prod '+age(pc);}
function refresh(){mini();dgx();prod();fleet();fresh();}
refresh();setInterval(refresh,30000);
</script>
SCRIPT
cat <<FTR
</body></html>
FTR
} > "$OUT"
chmod 600 "$OUT"
