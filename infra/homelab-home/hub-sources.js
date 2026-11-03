// Where the mini's jobs (status-job.js, briefing-job.js) read from: the mini's localhost services and
// the token files that already live on it. Shared so both jobs read the same way.
//
// Env overrides: HUB_VM, HUB_VLOGS, HUB_GRAFANA, HUB_GLITCHTIP, HUB_LITELLM, HUB_HA,
// HUB_GRAFANA_TOKEN_FILE (variable GRAFANA_TOKEN), HUB_GLITCHTIP_TOKEN_FILE (GLITCHTIP_TOKEN),
// HUB_BRIEFING_KEY_FILE (LITELLM_API_KEY), HUB_HA_TOKEN_FILE (the whole file is the token).
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
};
const FILES = {
  grafana: E.HUB_GRAFANA_TOKEN_FILE || path.join(H, 'signal-fleet/fleet-gateway.env'),
  glitchtip: E.HUB_GLITCHTIP_TOKEN_FILE || path.join(H, 'signal-fleet/fleet-gateway.env'),
  briefing: E.HUB_BRIEFING_KEY_FILE || path.join(H, 'hub-briefing-litellm.env'),
  ha: E.HUB_HA_TOKEN_FILE || path.join(H, 'home-automation-secrets/ha-token'),
};

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

// the source hub-status.js expects
function statusSource() {
  const tok = secret(FILES.grafana, 'GRAFANA_TOKEN');
  return {
    now: Date.now() / 1000,
    q: async e => (await getJson(URLS.vm + '/api/v1/query?query=' + encodeURIComponent(e))).data.result,
    alerts: async () => {
      if (!tok) throw new Error('no GRAFANA_TOKEN in ' + FILES.grafana);
      return getJson(URLS.grafana + '/api/alertmanager/grafana/api/v2/alerts', { headers: { Authorization: 'Bearer ' + tok } });
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
