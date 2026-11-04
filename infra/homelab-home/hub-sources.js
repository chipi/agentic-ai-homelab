// Where the mini's jobs (status-job.js, briefing-job.js) read from: the mini's localhost services and
// the token files that already live on it. Shared so both jobs read the same way.
//
// Env overrides: HUB_VM, HUB_VLOGS, HUB_GRAFANA, HUB_GLITCHTIP, HUB_LITELLM, HUB_HA, HUB_UMAMI,
// HUB_GRAFANA_TOKEN_FILE (variable GRAFANA_TOKEN), HUB_GLITCHTIP_TOKEN_FILE (GLITCHTIP_TOKEN),
// HUB_BRIEFING_KEY_FILE (LITELLM_API_KEY), HUB_HA_TOKEN_FILE (the whole file is the token),
// HUB_UMAMI_ENV_FILE (UMAMI_ADMIN_PASSWORD), HUB_GITHUB_TOKEN_FILE (GITHUB_TOKEN), HUB_FLEET_RESULTS, HUB_FLEET_QUEUE.
'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');

const H = os.homedir();
const E = process.env;
const URLS = {
  vm: E.HUB_VM || 'http://127.0.0.1:8428',
  vlogs: E.HUB_VLOGS || 'http://127.0.0.1:9428',
  grafana: E.HUB_GRAFANA || 'http://127.0.0.1:3000',
  glitchtip: E.HUB_GLITCHTIP || 'http://127.0.0.1:8090',
  litellm: E.HUB_LITELLM || 'http://127.0.0.1:4001',
  ha: E.HUB_HA || 'http://127.0.0.1:8123',
  umami: E.HUB_UMAMI || 'http://127.0.0.1:3001',
};
const FILES = {
  grafana: E.HUB_GRAFANA_TOKEN_FILE || path.join(H, 'signal-fleet/fleet-gateway.env'),
  glitchtip: E.HUB_GLITCHTIP_TOKEN_FILE || path.join(H, 'signal-fleet/fleet-gateway.env'),
  briefing: E.HUB_BRIEFING_KEY_FILE || path.join(H, 'hub-briefing-litellm.env'),
  ha: E.HUB_HA_TOKEN_FILE || path.join(H, 'home-automation-secrets/ha-token'),
  umami: E.HUB_UMAMI_ENV_FILE || path.join(H, 'umami/.env'),
  github: E.HUB_GITHUB_TOKEN_FILE || path.join(H, 'assistant-github-readonly.env'),
  fleetResults: E.HUB_FLEET_RESULTS || path.join(H, 'signal-fleet/results'),
  fleetQueue: E.HUB_FLEET_QUEUE || path.join(H, 'signal-fleet/queue'),
};

// The repos the triage fleet files into: signal-fleet/mvp/filing.py REPO_MAP, INSTANCE_REPO_MAP and
// OPS_REPO_DEFAULT. The assistant's GitHub token (Issues read) covers exactly these; a repo added there
// goes here and on the token, or it shows up in fleet.json's `unreadable`.
const FLEET_REPOS = ['chipi/agentic-ai-homelab', 'chipi/podcast_scraper', 'chipi/orrery', 'chipi/eval-harness', 'chipi/humancopilot.eu'];

// one variable from an env-style file, or the whole file when name is null; null if absent
function secret(file, name) {
  try {
    const txt = fs.readFileSync(file, 'utf8');
    if (!name) return txt.trim() || null;
    const line = txt.split('\n').find(l => l.startsWith(name + '='));
    return line ? line.slice(name.length + 1).trim().replace(/^["']|["']$/g, '') : null;
  } catch (e) { return null; }
}

async function getJson(url, opts = {}, timeoutMs = 30000) {
  const { onHeaders, ...init } = opts;
  const r = await fetch(url, Object.assign({ signal: AbortSignal.timeout(timeoutMs) }, init));
  if (!r.ok) throw new Error(url.split('?')[0] + ' -> HTTP ' + r.status);
  if (onHeaders) onHeaders(r.headers);
  return r.json();
}

// the source hub-status.js expects (the jobs' superset: annotations, logs and glitchtip need tokens or
// ports the page does not have)
function statusSource() {
  const tok = secret(FILES.grafana, 'GRAFANA_TOKEN');
  let umamiTok = null;
  return {
    now: Date.now() / 1000,
    q: async e => (await getJson(URLS.vm + '/api/v1/query?query=' + encodeURIComponent(e))).data.result,
    alerts: async () => {
      if (!tok) throw new Error('no GRAFANA_TOKEN in ' + FILES.grafana);
      return getJson(URLS.grafana + '/api/alertmanager/grafana/api/v2/alerts', { headers: { Authorization: 'Bearer ' + tok } });
    },
    annotations: async (fromMs, toMs) => {
      if (!tok) throw new Error('no GRAFANA_TOKEN in ' + FILES.grafana);
      return getJson(URLS.grafana + '/api/annotations?type=alert&limit=5000&from=' + fromMs + '&to=' + toMs, { headers: { Authorization: 'Bearer ' + tok } });
    },
    // a LogsQL query against VictoriaLogs; one parsed object per line
    logs: async query => {
      const r = await fetch(URLS.vlogs + '/select/logsql/query?limit=1000&query=' + encodeURIComponent(query), { signal: AbortSignal.timeout(30000) });
      if (!r.ok) throw new Error('VictoriaLogs query -> HTTP ' + r.status);
      return (await r.text()).split('\n').filter(Boolean).map(l => JSON.parse(l));
    },
    // the triage fleet's own files on the mini: the dispositions and filed ledgers, and its queue
    fleetFiles: async () => {
      const tsv = f => { const [h, ...rows] = fs.readFileSync(f, 'utf8').split('\n').filter(Boolean); const cols = h.split('\t');
        return rows.map(l => { const c = l.split('\t'), o = {}; cols.forEach((k, i) => { o[k] = c[i]; }); return o; }); };
      const queue = (fs.existsSync(FILES.fleetQueue) ? fs.readdirSync(FILES.fleetQueue) : []).filter(n => n.endsWith('.json')).map(n => {
        try { const d = JSON.parse(fs.readFileSync(path.join(FILES.fleetQueue, n), 'utf8'));
              return { kind: d.kind || n.split('-')[0], title: ((d.issue || {}).title) || ((d.signal || {}).alertname || '').slice(0, 140),
                       fingerprint: (d.signal || {}).fingerprint || '', queued_at: d.queued_at || '' }; } catch (e) { return null; } }).filter(Boolean);
      return { dispositions: tsv(path.join(FILES.fleetResults, 'dispositions.tsv')), filed: tsv(path.join(FILES.fleetResults, 'filed.tsv')), queue };
    },
    fleetRepos: FLEET_REPOS,
    github: async p => {
      const gh = secret(FILES.github, 'GITHUB_TOKEN');
      if (!gh) throw new Error('no GITHUB_TOKEN in ' + FILES.github);
      return getJson('https://api.github.com' + p, { headers: { Authorization: 'Bearer ' + gh, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'homelab-hub' } });
    },
    // Umami's API: one login per job run (self-hosted Umami has no API keys), the token kept in memory only
    umami: async p => {
      if (!umamiTok) {
        const pw = secret(FILES.umami, 'UMAMI_ADMIN_PASSWORD');
        if (!pw) throw new Error('no UMAMI_ADMIN_PASSWORD in ' + FILES.umami);
        umamiTok = getJson(URLS.umami + '/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: 'admin', password: pw }) }).then(r => r.token);
      }
      return getJson(URLS.umami + p, { headers: { Authorization: 'Bearer ' + await umamiTok } });
    },
    glitchtip: async p => {
      const gt = secret(FILES.glitchtip, 'GLITCHTIP_TOKEN');
      if (!gt) throw new Error('no GLITCHTIP_TOKEN in ' + FILES.glitchtip);
      return getJson(URLS.glitchtip + p, { headers: { Authorization: 'Bearer ' + gt } });
    },
  };
}

// one JSON line into VictoriaLogs (best effort: returns a short status string)
async function logLine(job, msg, fields) {
  try {
    const line = JSON.stringify(Object.assign({ _msg: msg, _time: new Date().toISOString(), job }, fields));
    const r = await fetch(URLS.vlogs + '/insert/jsonline?_stream_fields=job', { method: 'POST', body: line + '\n', signal: AbortSignal.timeout(15000) });
    return r.ok ? 'logged' : 'log HTTP ' + r.status;
  } catch (e) { return 'log failed: ' + e.message; }
}

// a gauge into VictoriaMetrics (Prometheus text import), e.g. a job's last success
async function pushGauge(name, value, labels = {}) {
  const l = Object.entries(labels).map(([k, v]) => k + '="' + String(v).replace(/"/g, '') + '"').join(',');
  const r = await fetch(URLS.vm + '/api/v1/import/prometheus', { method: 'POST', body: name + (l ? '{' + l + '}' : '') + ' ' + value + '\n', signal: AbortSignal.timeout(15000) });
  if (!r.ok) throw new Error('VictoriaMetrics import HTTP ' + r.status);
}

// write a file atomically, so a reader never sees half of it
function writeAtomic(file, body, mode = 0o644) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file + '.tmp', body, { mode });
  fs.renameSync(file + '.tmp', file);
}

module.exports = { URLS, FILES, secret, getJson, statusSource, logLine, pushGauge, writeAtomic };
