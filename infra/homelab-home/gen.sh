#!/bin/bash
OUT=~/homelab-home/www/index.html
get(){ [ -f "$1" ] && grep -E "^$2=" "$1" | head -1 | cut -d= -f2- || echo "?"; }
REPO=~/agentic-ai-homelab/infra
GF_U=$(get "$REPO/observability/backend/.env" GRAFANA_ADMIN_USER); GF_P=$(get "$REPO/observability/backend/.env" GRAFANA_ADMIN_PASSWORD)
GT_U=$(get "$REPO/glitchtip/.env" DJANGO_SUPERUSER_EMAIL); GT_P=$(get "$REPO/glitchtip/.env" DJANGO_SUPERUSER_PASSWORD)
LF_U=$(get "$REPO/langfuse/.env" LANGFUSE_INIT_USER_EMAIL); LF_P=$(get "$REPO/langfuse/.env" LANGFUSE_INIT_USER_PASSWORD)
UM_U=admin; UM_P=$(get ~/umami/.env UMAMI_ADMIN_PASSWORD)
G=http://homelab:3000
DASH_MINI=$G/d/homelab-mini/homelab-e28094-mac-mini
DASH_GPU=$G/d/gpu-dcgm/gpu-e28094-dcgm
DASH_DGX=$G/d/dgx-services/dgx-e28094-services
DASH_CAD=$G/d/containers-cadvisor/containers-e28094-cadvisor
row(){ printf '<tr><td><a href="%s">%s</a></td><td><code>:%s</code></td><td><code>%s</code></td><td><code>%s</code></td></tr>\n' "$2" "$1" "$5" "$3" "$4"; }
dsvc(){ printf '<tr><td><a href="%s">%s</a></td><td><code>:%s</code></td><td class=muted>%s</td></tr>\n' "$4" "$1" "$2" "$3"; }
{
cat <<HDR
<!doctype html><html><head><meta charset=utf-8><title>homelab</title>
<style>body{font:15px/1.55 system-ui,sans-serif;margin:32px;background:#0d0d16;color:#e6e6ef}
h1{font-weight:600;margin:0 0 18px}h2{font-size:16px;font-weight:600;margin:0 0 8px}
h2 a{color:#dcdcf0;text-decoration:none}h2 a:hover{color:#7aa2ff}
.cols{display:flex;gap:34px;flex-wrap:wrap}.col{flex:1;min-width:400px}
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
.dock{color:#c8c8e0;font-size:13.5px;margin:2px 0 4px}.dock b{color:#e6e6ef}</style></head><body>
<h1>homelab</h1>
<div class=cols>
<div class=col>
  <h2><a href="$DASH_MINI">Mac mini &rarr;</a></h2>
  <div id=sysrow class=sysrow>&hellip;</div>
  <div class=charts>
    <a class=card href="$DASH_MINI"><h3>CPU</h3><div id=c_cpu>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>Memory</h3><div id=c_mem>&hellip;</div></a>
    <a class=card href="$DASH_MINI"><h3>Disk free</h3><div id=c_disk>&hellip;</div></a>
  </div>
  <div id=health class=health></div>
  <div class=dock>&#128051; <a href="$DASH_CAD" style=color:inherit;text-decoration:none><span id=mdocker>&hellip;</span></a></div>
  <div class=sec id=mtop></div>
  <table><thead><tr><th>Service</th><th>Port</th><th>User</th><th>Password</th></tr></thead><tbody>
HDR
row "Grafana"   "$G"                  "$GF_U" "$GF_P" "3000"
row "GlitchTip" "http://homelab:8090" "$GT_U" "$GT_P" "8090"
row "Langfuse"  "http://homelab:4000" "$LF_U" "$LF_P" "4000"
row "Umami"     "http://homelab:3001" "$UM_U" "$UM_P" "3001"
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
  </div>
  <div id=dgxhealth class=health></div>
  <div class=dock>&#128051; <a href="$DASH_CAD" style=color:inherit;text-decoration:none><span id=ddocker>&hellip;</span></a></div>
  <table><thead><tr><th>Service</th><th>Port</th><th>Role</th></tr></thead><tbody>
MID
dsvc "ollama"         "11434" "LLM inference" "$DASH_DGX"
dsvc "speaches"       "8000"  "transcription" "$DASH_DGX"
dsvc "diarization"    "8001"  "speaker split" "$DASH_DGX"
dsvc "openai-whisper" "8002"  "transcription" "$DASH_DGX"
dsvc "moss"           "8004"  "transcription" "$DASH_DGX"
dsvc "cadvisor"       "8080"  "containers"    "$DASH_CAD"
dsvc "dcgm"           "9400"  "GPU exporter"  "$DASH_GPU"
cat <<MID2
  </tbody></table>
  <p class=sec>Host CPU/mem/disk unavailable (node-exporter :9100 down on DGX).</p>
</div>
</div>
<p class=sec id=fresh></p>
MID2
cat <<'SCRIPT'
<script>
const W=260,H=40,G='http://homelab:3000';
const MINILINK={grafana:G,glitchtip:'http://homelab:8090',langfuse:'http://homelab:4000',umami:'http://homelab:3001',victoriametrics:'http://homelab:8428/vmui'};
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
async function mini(){
  draw('c_cpu','mini_cpu_used_percent',x=>x.toFixed(0)+'%',100);
  draw('c_mem','mini_mem_used_percent',x=>x.toFixed(0)+'%',100);
  draw('c_disk','mini_disk_free_bytes',x=>(x/1073741824).toFixed(0)+' GB');
  const L=x=>x?(+x[1]).toFixed(2):'&mdash;';
  const l1=await g1('mini_load1'),l5=await g1('mini_load5'),l15=await g1('mini_load15'),sw=await g1('mini_swap_used_bytes'),up=await g1('mini_uptime_seconds');
  const sr=document.getElementById('sysrow');if(sr)sr.innerHTML='Load <b>'+L(l1)+' / '+L(l5)+' / '+L(l15)+'</b> &middot; Swap <b>'+(sw?((+sw[1])/1048576).toFixed(0)+' MB':'&mdash;')+'</b> &middot; Up <b>'+(up?fmtUp(up[1]):'&mdash;')+'</b>';
  badges('health','service_up',['grafana','glitchtip','langfuse','umami','victoriametrics'],n=>MINILINK[n]||G);
  const run=await g1('mini_docker_running'),tot=await g1('mini_docker_total'),rst=await g1('mini_docker_restarting'),unh=await g1('mini_docker_unhealthy');
  const md=document.getElementById('mdocker');if(md&&run)md.innerHTML='<b>'+run[1]+'/'+tot[1]+'</b> running'+(rst&&+rst[1]?' &middot; <span style=color:#f85149>'+rst[1]+' restarting</span>':'')+(unh&&+unh[1]?' &middot; <span style=color:#f85149>'+unh[1]+' unhealthy</span>':'');
  const top=await q('topk(3,mini_container_mem_bytes)');const mt=document.getElementById('mtop');
  if(mt)mt.innerHTML='top: '+top.sort((a,b)=>b.value[1]-a.value[1]).map(s=>s.metric.name+' <span class=muted>'+(s.value[1]/1048576).toFixed(0)+'MB</span>').join(' &middot; ');
}
async function dgx(){
  draw('g_temp','DCGM_FI_DEV_GPU_TEMP',x=>x.toFixed(0)+'&deg;C');
  draw('g_util','DCGM_FI_DEV_GPU_UTIL',x=>x.toFixed(0)+'%',100);
  draw('g_pow','DCGM_FI_DEV_POWER_USAGE',x=>x.toFixed(0)+' W');
  const clk=await g1('DCGM_FI_DEV_SM_CLOCK'),mbw=await g1('DCGM_FI_DEV_MEM_COPY_UTIL');
  const dr=document.getElementById('dgxrow');if(dr)dr.innerHTML='Clock <b>'+(clk?(+clk[1]).toFixed(0)+' MHz':'&mdash;')+'</b> &middot; Mem-BW <b>'+(mbw?(+mbw[1]).toFixed(0)+'%':'&mdash;')+'</b>';
  badges('dgxhealth','dgx_service_up',['ollama','whisper','diarization','openai-whisper','moss','cadvisor','dcgm'],n=>DGXDASH);
  const cc=await g1('count(container_last_seen{host=\"dgx\"})'),mem=await g1('sum(container_memory_usage_bytes{host=\"dgx\",id=\"/\"})');
  const dd=document.getElementById('ddocker');if(dd)dd.innerHTML='<b>'+(cc?cc[1]:'&mdash;')+'</b> containers &middot; <b>'+(mem?(+mem[1]/1e9).toFixed(1)+' GB':'&mdash;')+'</b>';
}
async function fresh(){const now=Date.now()/1000,age=x=>x?Math.round(now-+x[0])+'s ago':'no data';const mc=await g1('mini_cpu_used_percent'),dg=await g1('DCGM_FI_DEV_GPU_TEMP');const el=document.getElementById('fresh');if(el)el.innerHTML='collectors &middot; mini '+age(mc)+' &middot; dgx '+age(dg);}
function refresh(){mini();dgx();fresh();}
refresh();setInterval(refresh,30000);
</script>
SCRIPT
cat <<FTR
</body></html>
FTR
} > "$OUT"
chmod 600 "$OUT"
