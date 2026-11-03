#!/usr/bin/env node
// The hub's status, written for everything that is not the page (RFC-0008, section 0): runs the same
// hub-status.js the page runs, against the mini's localhost services, and writes www/status.json
// (served by the hub at /status.json). Each snapshot also goes to VictoriaLogs (job=hub-status), so
// any past hour can be checked against what the briefing said. Run every 5 minutes by launchd
// (com.homelab.hub-status); one run, then exit. Sources and env overrides: hub-sources.js.
'use strict';
const path = require('path');
const HS = require('./hub-status.js');
const S = require('./hub-sources.js');

const OUT = process.env.HUB_OUT || path.join(__dirname, 'www/status.json');

async function main() {
  const status = await HS.all(S.statusSource());
  const body = JSON.stringify(status, null, 1);
  S.writeAtomic(OUT, body);
  const logged = await S.logLine('hub-status', 'hub status snapshot', { snapshot: JSON.stringify(status) });
  const bad = Object.entries(status).filter(([, v]) => v && v.error).map(([k, v]) => k + ': ' + v.error);
  // the heartbeat the hub-status-stale alert reads (written even when an area failed: the file was)
  try { await S.pushGauge('hub_status_last_success_timestamp', Math.round(Date.now() / 1000)); } catch (e) { console.error('heartbeat: ' + e.message); }
  console.log(status.takenAt + ' wrote ' + OUT + ' (' + body.length + ' bytes), ' + logged + (bad.length ? '; area errors: ' + bad.join('; ') : ''));
  process.exit(bad.length ? 1 : 0);
}

main().catch(e => { console.error('status-job failed: ' + (e && e.stack || e)); process.exit(2); });
