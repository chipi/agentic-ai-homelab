#!/usr/bin/env node
// The hub's status, written for everything that is not the page (RFC-0008, section 0): runs the same
// hub-status.js the page runs, against the mini's localhost services, and writes www/status.json
// (served by the hub at /status.json). Each snapshot also goes to VictoriaLogs, so any past hour can
// be checked against what the briefing said. Run every 5 minutes by launchd; one run, then exit.
//
// Env: HUB_VM (default http://127.0.0.1:8428), HUB_VLOGS (http://127.0.0.1:9428),
// HUB_GRAFANA (http://127.0.0.1:3000), HUB_GRAFANA_TOKEN_FILE (~/signal-fleet/fleet-gateway.env,
// variable GRAFANA_TOKEN: the viewer token the page uses too), HUB_OUT (www/status.json next to this).
'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');
const HS = require('./hub-status.js');

const VM = process.env.HUB_VM || 'http://127.0.0.1:8428';
const VLOGS = process.env.HUB_VLOGS || 'http://127.0.0.1:9428';
const GRAFANA = process.env.HUB_GRAFANA || 'http://127.0.0.1:3000';
const TOKEN_FILE = process.env.HUB_GRAFANA_TOKEN_FILE || path.join(os.homedir(), 'signal-fleet/fleet-gateway.env');
const OUT = process.env.HUB_OUT || path.join(__dirname, 'www/status.json');

function token() {
  try {
    const line = fs.readFileSync(TOKEN_FILE, 'utf8').split('\n').find(l => l.startsWith('GRAFANA_TOKEN='));
    return line ? line.slice('GRAFANA_TOKEN='.length).trim().replace(/^["']|["']$/g, '') : null;
  } catch (e) { return null; }
}

async function main() {
  const tok = token();
  const src = {
    now: Date.now() / 1000,
    q: async e => {
      const r = await fetch(VM + '/api/v1/query?query=' + encodeURIComponent(e), { signal: AbortSignal.timeout(30000) });
      if (!r.ok) throw new Error('VictoriaMetrics ' + r.status);
      return (await r.json()).data.result;
    },
    alerts: async () => {
      if (!tok) throw new Error('no Grafana token in ' + TOKEN_FILE);
      const r = await fetch(GRAFANA + '/api/alertmanager/grafana/api/v2/alerts', { headers: { Authorization: 'Bearer ' + tok }, signal: AbortSignal.timeout(30000) });
      if (!r.ok) throw new Error('alertmanager ' + r.status);
      return r.json();
    },
  };
  const status = await HS.all(src);
  const body = JSON.stringify(status, null, 1);
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const tmp = OUT + '.tmp';
  fs.writeFileSync(tmp, body, { mode: 0o644 });
  fs.renameSync(tmp, OUT); // readers never see a half-written file

  // the snapshot, one log line, kept with the rest of the logs
  let logged = 'not logged';
  try {
    const line = JSON.stringify({ _msg: 'hub status snapshot', _time: status.takenAt, job: 'hub-status', snapshot: body });
    const r = await fetch(VLOGS + '/insert/jsonline?_stream_fields=job', { method: 'POST', body: line + '\n', signal: AbortSignal.timeout(15000) });
    logged = r.ok ? 'logged' : 'log HTTP ' + r.status;
  } catch (e) { logged = 'log failed: ' + e.message; }

  const bad = Object.entries(status).filter(([k, v]) => v && v.error).map(([k, v]) => k + ': ' + v.error);
  console.log(status.takenAt + ' wrote ' + OUT + ' (' + body.length + ' bytes), ' + logged + (bad.length ? '; area errors: ' + bad.join('; ') : ''));
  process.exit(bad.length ? 1 : 0);
}

main().catch(e => { console.error('status-job failed: ' + (e && e.stack || e)); process.exit(2); });
