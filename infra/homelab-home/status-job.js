#!/usr/bin/env node
// The hub's status, written for everything that is not the page (RFC-0008, section 0): runs the same
// hub-status.js the page runs, against the mini's localhost services, and writes www/status.json
// (served by the hub at /status.json) and www/timeline.json, the last 48 h of events for incident
// write-ups (use case H7, served at /timeline.json) and www/analytics.json, the Umami sites' numbers for
// the assistant (served at /analytics.json). Each snapshot also goes to VictoriaLogs
// (job=hub-status), so any past hour can be checked against what the briefing said. Run every 5
// minutes by launchd (com.homelab.hub-status); one run, then exit. Sources and env overrides: hub-sources.js.
'use strict';
const path = require('path');
const HS = require('./hub-status.js');
const S = require('./hub-sources.js');

const OUT = process.env.HUB_OUT || path.join(__dirname, 'www/status.json');
const TIMELINE = path.join(path.dirname(OUT), 'timeline.json'), TIMELINE_DIR = path.join(path.dirname(OUT), 'timeline');
const TIMELINE_HOURS = 48;
const ANALYTICS = path.join(path.dirname(OUT), 'analytics.json');
const FLEET = path.join(path.dirname(OUT), 'fleet.json'), FLEET_DIR = path.join(path.dirname(OUT), 'fleet');

async function main() {
  const src = S.statusSource();
  const status = await HS.all(src);
  // the assistant's local / OpenRouter split (job only: it reads LiteLLM's database), in status.json for the
  // assistant and the briefing, and as gauges for the Spend tab (window = the tab's period)
  try { status.assistantSpend = await HS.assistantSpend(src); } catch (e) { status.assistantSpend = { error: String(e && e.message || e) }; }
  if (status.assistantSpend && status.assistantSpend.ok) {
    for (const [w, v] of Object.entries(status.assistantSpend.windows)) {
      for (const b of ['x3', 'openrouter']) {
        try { await S.pushGauge('hub_assistant_calls', v[b].calls, { backend: b, window: w });
              await S.pushGauge('hub_assistant_usd', v[b].usd, { backend: b, window: w }); } catch (e) { console.error('assistant gauges: ' + e.message); }
      }
    }
  }
  const body = JSON.stringify(status, null, 1);
  S.writeAtomic(OUT, body);
  const to = Math.round(src.now * 1000);
  const tl = await HS.timeline(src, to - TIMELINE_HOURS * 3600e3, to);
  tl.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  S.writeAtomic(TIMELINE, JSON.stringify(tl, null, 1));
  // the assistant reads one short list at a time (www/timeline/<kind>.json, last-night.json): copying from
  // the whole 30 KB timeline it changed times and took the wrong kind (2026-11-04, four runs)
  const head = { from: tl.from, to: tl.to, timezone: tl.timezone, missing: tl.missing };
  for (const [k, evs] of Object.entries(tl.byKind)) S.writeAtomic(path.join(TIMELINE_DIR, k + '.json'), JSON.stringify(Object.assign({ kind: k, count: evs.length }, head, { lines: evs.map(e => e.line) }), null, 1));
  S.writeAtomic(path.join(TIMELINE_DIR, 'last-night.json'), JSON.stringify(Object.assign({ kind: 'last-night', window: tl.lastNight.local, count: tl.lastNightLines.length }, head, { lines: tl.lastNightLines }), null, 1));
  let an; try { an = await HS.analytics(src); } catch (e) { an = { ok: false, reason: String(e && e.message || e) }; }
  S.writeAtomic(ANALYTICS, JSON.stringify(an, null, 1));
  let fq; try { fq = await HS.fleetQueue(src); } catch (e) { fq = { ok: false, reason: String(e && e.message || e) }; }
  S.writeAtomic(FLEET, JSON.stringify(fq, null, 1));
  // what the assistant reads (fleet.json is for scoring): one short list per question
  if (fq.ok) {
    const fh = { unreadable: fq.unreadable, repos: fq.repos };
    S.writeAtomic(path.join(FLEET_DIR, 'needs-you.json'), JSON.stringify(Object.assign({ list: 'needs-you', count: fq.needsYou,
      about: 'what the triage fleet wants from the operator: its escalations of the last 7 days and bug proposals; count is the number to give' }, fh, { lines: fq.needsYouLines }), null, 1));
    S.writeAtomic(path.join(FLEET_DIR, 'open-escalated.json'), JSON.stringify(Object.assign({ list: 'open-escalated', count: fq.openEscalatedCount,
      about: 'every escalated issue still open on GitHub, any age, newest first: the backlog' }, fh, { lines: fq.openEscalatedLines }), null, 1));
  }
  const logged = await S.logLine('hub-status', 'hub status snapshot', { snapshot: JSON.stringify(status) });
  const bad = Object.entries(status).filter(([, v]) => v && v.error).map(([k, v]) => k + ': ' + v.error);
  // the heartbeat the hub-status-stale alert reads (written even when an area failed: the file was)
  try { await S.pushGauge('hub_status_last_success_timestamp', Math.round(Date.now() / 1000)); } catch (e) { console.error('heartbeat: ' + e.message); }
  console.log(status.takenAt + ' wrote ' + OUT + ' (' + body.length + ' bytes), ' + logged
    + '; timeline ' + tl.count + ' events' + (tl.missing.length ? ' (missing: ' + tl.missing.join('; ') + ')' : '')
    + '; fleet ' + (fq.ok ? fq.needsYou + ' need you, ' + fq.openEscalatedCount + ' open escalated' + (fq.unreadable.length ? ' (unreadable: ' + fq.unreadable.join('; ') + ')' : '') : 'failed: ' + fq.reason)
    + '; analytics ' + (an.ok ? an.sites.length + ' sites' + (an.sites.some(x => x.error) ? ' (errors: ' + an.sites.filter(x => x.error).map(x => x.site).join(', ') + ')' : '') : 'failed: ' + an.reason)
    + (bad.length ? '; area errors: ' + bad.join('; ') : ''));
  process.exit(bad.length ? 1 : 0);
}

main().catch(e => { console.error('status-job failed: ' + (e && e.stack || e)); process.exit(2); });
