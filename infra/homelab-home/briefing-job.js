#!/usr/bin/env node
// The morning briefing (RFC-0008, use case H1): what needs the operator today, then the night.
// Every number comes from code: the hub's status module (hub-status.js), Grafana's alert history, the
// container inventory, GlitchTip. The model writes only the two-sentence opening, from the same facts;
// if it fails, the briefing goes out without it. Run at 07:00 by launchd (com.homelab.hub-briefing);
// writes www/briefing/<date>.html and index.html (the last 30 kept), pushes the headline to the
// phone through Home Assistant's companion app, and records its last success in VictoriaMetrics.
//
// --dry-run: build and write the page, but no push, no metric. Env: HUB_BRIEFING_DIR, HUB_PUBLIC,
// HUB_BRIEFING_MODEL (assistant: the X3, failing over to OpenRouter), HUB_BRIEFING_NOTIFY (mobile_app_iphone); sources: hub-sources.js.
'use strict';
const fs = require('fs');
const path = require('path');
const HS = require('./hub-status.js');
const S = require('./hub-sources.js');

const DRY = process.argv.includes('--dry-run');
const DIR = process.env.HUB_BRIEFING_DIR || path.join(__dirname, 'www/briefing');
const PUBLIC = process.env.HUB_PUBLIC || 'https://hub.tail6d0ed4.ts.net';
const MODEL = process.env.HUB_BRIEFING_MODEL || 'assistant';
const NOTIFY = process.env.HUB_BRIEFING_NOTIFY || 'mobile_app_iphone';
const KEEP = 30;
const PLUMB = new Set(['DatasourceNoData', 'DatasourceError', 'Watchdog']);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const usd = v => v == null ? '—' : '$' + v.toFixed(2);
const hhmm = t => new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

// the window: since 19:00 the evening before; on Mondays since Friday 19:00 (local time)
function windowStart(now) {
  const d = new Date(now); d.setHours(19, 0, 0, 0); d.setDate(d.getDate() - (d.getDay() === 1 ? 3 : 1));
  return d;
}

// alerts that fired or resolved in the window (Grafana keeps state history as annotations)
async function alertChanges(from, to) {
  const tok = S.secret(S.FILES.grafana, 'GRAFANA_TOKEN');
  const list = await S.getJson(S.URLS.grafana + '/api/annotations?type=alert&limit=2000&from=' + from.getTime() + '&to=' + to.getTime(), { headers: { Authorization: 'Bearer ' + tok } });
  const out = [];
  for (const a of list) {
    const ns = a.newState || '', ps = a.prevState || '', name = a.alertName || '';
    if (!name || PLUMB.has(name)) continue;
    const fired = ns.startsWith('Alerting') && !ps.startsWith('Alerting');
    const resolved = ns.startsWith('Normal') && ps.startsWith('Alerting');
    if (!fired && !resolved) continue;
    const inst = (/instance=([^,}]+)/.exec(a.text || '') || [])[1] || null;
    out.push({ at: a.time, name, instance: inst, change: fired ? 'fired' : 'resolved' });
  }
  return out.sort((a, b) => a.at - b.at);
}

// one line per alert (name + instance): how often it fired and resolved, the span, and its state now
function groupAlerts(changes) {
  const g = {};
  for (const c of changes) {
    const k = c.name + '|' + (c.instance || '');
    const x = g[k] = g[k] || { name: c.name, instance: c.instance, fired: 0, resolved: 0, first: c.at, last: c.at, now: 'firing' };
    x[c.change]++; x.last = c.at; x.now = c.change === 'fired' ? 'firing' : 'resolved';
  }
  return Object.values(g).sort((a, b) => a.first - b.first);
}

// containers started in the window: deploys and restarts, from the shared inventory
async function restarts(from, now) {
  const w = Math.max(60, Math.round((now - from) / 1000));
  const r = await S.statusSource().q('container_uptime_seconds{state="running"} < ' + w);
  return r.map(x => ({ box: x.metric.box, name: x.metric.name, at: now.getTime() - (+x.value[1]) * 1000 }))
    .sort((a, b) => a.at - b.at);
}

// GlitchTip issues first seen in the window (the status module's definition, shared with status.json)
async function newErrors(from) {
  return HS.newIssues(S.statusSource(), from.getTime() / 1000);
}

// what needs the operator, most urgent first, at most 5 (decided here, in code)
function needsYou(st, errors) {
  const items = [];
  const al = st.alerts && st.alerts.ok ? st.alerts : { critical: [], warning: [] };
  al.critical.forEach(a => items.push({ rank: 0, text: 'Critical alert: ' + a.name + (a.instance ? ' (' + a.instance + ')' : ''), link: 'https://grafana.tail6d0ed4.ts.net/alerting/list' }));
  if (st.sites && st.sites.state === 'down') items.push({ rank: 1, text: 'Site down now: ' + st.sites.down.join(', '), link: PUBLIC + '/#sites' });
  for (const [box, b] of Object.entries(st.boxes || {})) if (b.state === 'down') items.push({ rank: 1, text: 'No data from ' + box + ' (collector silent)', link: PUBLIC + '/#hosts/' + box });
  if (st.podcast && ['down', 'mid'].includes(st.podcast.state)) items.push({ rank: 1, text: 'Close Listening health is ' + (st.podcast.state === 'down' ? 'red' : 'orange') + ': ' + Object.entries(st.podcast.checks).filter(([, s]) => s && s !== 'up').map(([c]) => c).join(', '), link: PUBLIC + '/#overview' });
  if (st.delivery && st.delivery.state === 'down') items.push({ rank: 1, text: 'Delivery: ' + st.delivery.workersUp + '/' + st.delivery.workers + ' workers up', link: PUBLIC + '/#hosts/delivery' });
  if (errors.length) items.push({ rank: 2, text: errors.length + ' new GlitchTip issue' + (errors.length > 1 ? 's' : '') + ': ' + errors.slice(0, 3).map(e => e.id).join(', '), link: errors[0].link });
  if (st.needsYou && st.needsYou.total) items.push({ rank: 3, text: 'Triage fleet: ' + st.needsYou.total + ' waiting for you', link: PUBLIC + '/#fleets' });
  if (st.credit && st.credit.low) items.push({ rank: 3, text: 'OpenRouter credit ' + usd(st.credit.leftUsd) + ', under $10: top up', link: 'https://openrouter.ai/settings/credits' });
  al.warning.filter(a => !/credit/i.test(a.name)).forEach(a => items.push({ rank: 4, text: 'Warning: ' + a.name + (a.instance ? ' (' + a.instance + ')' : ''), link: 'https://grafana.tail6d0ed4.ts.net/alerting/list' }));
  if (st.sites && st.sites.state === 'mid') st.sites.below999.forEach(h => items.push({ rank: 5, text: h.host + ' at ' + (h.avail24h * 100).toFixed(2) + '% over 24 h', link: PUBLIC + '/#sites' }));
  items.sort((a, b) => a.rank - b.rank);
  return { items: items.slice(0, 5), more: Math.max(0, items.length - 5) };
}

// Which deployment behind the alias wrote it, from LiteLLM's response headers: the X3's address in
// x-litellm-model-api-base is local; a fallback taken (x-litellm-attempted-fallbacks > 0) is OpenRouter.
const where = h => {
  const base = h.get('x-litellm-model-api-base') || '', fb = +(h.get('x-litellm-attempted-fallbacks') || 0);
  return base.includes('100.92.54.65') ? 'the X3, local' : (fb > 0 ? 'OpenRouter, failover' : null);
};

// the model's two sentences; null when it fails (the briefing does not depend on it)
async function opening(facts) {
  const key = S.secret(S.FILES.briefing, 'LITELLM_API_KEY');
  if (!key) return { text: null, why: 'no key in ' + S.FILES.briefing };
  try {
    let served = null;
    const d = await S.getJson(S.URLS.litellm + '/v1/chat/completions', {
      onHeaders: h => { served = where(h); },
      method: 'POST', headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json' },
      // named in Langfuse (LiteLLM passes these through), so its faithfulness evaluator can target them
      body: JSON.stringify({ model: MODEL, temperature: 0.2, max_tokens: 160,
        metadata: { trace_name: 'hub-briefing', generation_name: 'briefing-opening', tags: ['hub-briefing'] }, messages: [
        { role: 'system', content: 'You write the opening of a morning operations briefing for one person who runs a homelab and a few web products. Two sentences, plain English, no greeting, no lists. Use only the facts given; do not add or change any number, name or time. Overnight events are over: describe them in the past tense, and call something current only when the facts list it as current. Lead with what needs attention; if nothing does, say so.' },
        { role: 'user', content: JSON.stringify(facts) }] }),
    }, 60000);
    const text = ((d.choices || [])[0] || {}).message && d.choices[0].message.content;
    return { text: text ? text.trim() : null, model: (d.model || MODEL) + (served ? ' (' + served + ')' : ''), why: text ? null : 'empty reply' };
  } catch (e) { return { text: null, why: e.message }; }
}

const NA = '<p class=m>Not available this morning (see the note at the end).</p>';
function render(b) {
  const li = x => '<li>' + (x.link ? '<a href="' + esc(x.link) + '">' + esc(x.text) + '</a>' : esc(x.text)) + '</li>';
  const sect = (t, body) => '<h2>' + t + '</h2>' + body;
  const sp = b.status.spend || {}, cr = b.status.credit || {};
  return '<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Briefing ' + esc(b.date) + '</title>'
    + '<style>:root{color-scheme:dark}body{background:#0d0d14;color:#e6e6ef;font:15px/1.55 -apple-system,system-ui,sans-serif;margin:0 auto;max-width:760px;padding:16px}a{color:#7aa2ff}'
    + 'h1{font-size:22px;margin:4px 0}h2{font-size:13px;color:#9a9ac2;text-transform:uppercase;letter-spacing:.05em;margin:22px 0 6px}.m{color:#8888aa;font-size:13px}ul{padding-left:20px;margin:4px 0}'
    + '.open{background:#14141f;border:1px solid #26263a;border-radius:8px;padding:10px 12px;margin:12px 0}</style>'
    + '<p class=m><a href="' + esc(PUBLIC) + '/">hub</a> · window ' + esc(b.windowLabel) + ' · made ' + esc(hhmm(b.madeAt)) + '</p>'
    + '<h1>' + esc(b.headline) + '</h1>'
    + (b.opening.text ? '<div class=open>' + esc(b.opening.text) + '<div class=m>written by ' + esc(b.opening.model) + ' from the facts below</div></div>' : '')
    + sect('Needs you', b.needs.items.length ? '<ul>' + b.needs.items.map(li).join('') + '</ul>' + (b.needs.more ? '<p class=m>and ' + b.needs.more + ' more</p>' : '') : '<p>Nothing.</p>')
    + sect('Overnight', '<p class=m>Alerts</p>' + (b.alertGroups == null ? NA : (b.alertGroups.length ? '<ul>' + b.alertGroups.map(g => '<li>' + esc(g.name) + (g.instance ? ' (' + esc(g.instance) + ')' : '')
          + ' <span class=m>fired ' + g.fired + '&times;' + (g.resolved ? ', resolved ' + g.resolved + '&times;' : '') + ' · ' + esc(hhmm(g.first)) + (g.last !== g.first ? '–' + esc(hhmm(g.last)) : '') + ' · ' + (g.now === 'firing' ? '<b>still firing</b>' : 'resolved') + '</span></li>').join('') + '</ul>' : '<p>None fired or resolved.</p>'))
      + '<p class=m>Containers started (deploys, restarts)</p>' + (b.restarts == null ? NA : (b.restarts.length ? '<ul>' + b.restarts.map(r => '<li>' + esc(hhmm(r.at)) + ' ' + esc(r.box) + ' · ' + esc(r.name) + '</li>').join('') + '</ul>' : '<p>None.</p>'))
      + '<p class=m>New GlitchTip issues</p>' + (b.errors == null ? NA : (b.errors.length ? '<ul>' + b.errors.map(e => li({ text: e.id + ' · ' + e.title + ' (' + e.count + ')', link: e.link })).join('') + '</ul>' : '<p>None.</p>')))
    + sect('Numbers', '<ul><li>OpenRouter yesterday ' + usd(sp.yesterdayUsd) + ' (7-day average ' + usd(sp.avg7dUsd) + ')</li><li>OpenRouter this month ' + usd(sp.monthUsd) + '</li><li>Credit left ' + usd(cr.leftUsd) + '</li></ul>')
    + sect('All green', '<p>' + esc(b.green.join(' · ') || '—') + '</p>')
    + (b.missing.length ? '<p class=m>Not available this morning: ' + esc(b.missing.join('; ')) + '</p>' : '')
    + '</html>';
}

async function main() {
  const now = new Date(), from = windowStart(now);
  const missing = [];
  const status = await HS.all(S.statusSource());
  Object.entries(status).forEach(([k, v]) => { if (v && v.error) missing.push(k + ': ' + v.error); });
  // a source that fails is null (rendered "not available"), never an empty list (which reads "none")
  const safe = async (label, f) => { try { return await f(); } catch (e) { missing.push(label + ': ' + e.message); return null; } };
  const alertChangesL = await safe('alert history', () => alertChanges(from, now));
  const restartsL = await safe('container inventory', () => restarts(from, now));
  const errors = await safe('GlitchTip', () => newErrors(from));
  const needs = needsYou(status, errors || []);
  const green = [];
  if (status.sites && status.sites.state === 'up') green.push('sites ' + status.sites.up + '/' + status.sites.total);
  for (const [box, b] of Object.entries(status.boxes || {})) if (b.state === 'up') green.push(box);
  if (status.podcast && status.podcast.state === 'up') green.push('Close Listening');
  if (status.delivery && status.delivery.state === 'up') green.push('delivery');
  const n = needs.items.length + needs.more;
  const headline = n ? n + ' thing' + (n > 1 ? 's' : '') + ' need' + (n > 1 ? '' : 's') + ' you' : 'Nothing needs you';
  const windowLabel = from.toLocaleString('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit' }) + ' to ' + hhmm(now);
  const groups = alertChangesL && groupAlerts(alertChangesL);
  const facts = { headline, window: windowLabel, needsYou: needs.items.map(x => x.text),
    alerts: groups ? groups.map(g => g.name + ': fired ' + g.fired + ', resolved ' + g.resolved + ', ' + g.now + ' now') : 'not available',
    restarts: restartsL ? restartsL.length : 'not available', newErrors: errors ? errors.map(e => e.id + ' ' + e.title) : 'not available',
    spend: status.spend, creditLeftUsd: status.credit && status.credit.leftUsd, green };
  const op = await opening(facts);
  if (!op.text) missing.push('opening: ' + op.why);
  const date = now.toLocaleDateString('en-CA');
  const b = { date, madeAt: now.getTime(), windowLabel, headline, needs, alertChanges: alertChangesL, alertGroups: groups, restarts: restartsL, errors, green, status, opening: op, missing };
  const html = render(b);
  S.writeAtomic(path.join(DIR, date + '.html'), html);
  S.writeAtomic(path.join(DIR, date + '.json'), JSON.stringify(b, null, 1));
  // index: today's briefing, then links to the earlier ones; keep the last KEEP days
  const days = fs.readdirSync(DIR).filter(f => /^\d{4}-\d\d-\d\d\.html$/.test(f)).sort().reverse();
  days.slice(KEEP).forEach(f => { fs.unlinkSync(path.join(DIR, f)); try { fs.unlinkSync(path.join(DIR, f.replace('.html', '.json'))); } catch (e) {} });
  const prev = days.slice(1, KEEP).map(f => '<a href="' + f + '">' + f.slice(0, 10) + '</a>').join(' · ');
  S.writeAtomic(path.join(DIR, 'index.html'), html.replace('</html>', (prev ? '<h2>Earlier</h2><p class=m>' + prev + '</p>' : '') + '</html>'));

  let pushed = 'not pushed (dry run)';
  if (!DRY) {
    const tok = S.secret(S.FILES.ha, null);
    try {
      await S.getJson(S.URLS.ha + '/api/services/notify/' + NOTIFY, { method: 'POST', headers: { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'Briefing: ' + headline.toLowerCase(), message: needs.items.slice(0, 3).map(x => x.text).join('\n') || 'All green.', data: { url: PUBLIC + '/briefing/' } }) });
      pushed = 'pushed to ' + NOTIFY;
    } catch (e) { pushed = 'push failed: ' + e.message; missing.push('push: ' + e.message); }
    await S.pushGauge('hub_briefing_last_success_timestamp', Math.round(now.getTime() / 1000));
    await S.pushGauge('hub_briefing_needs_you', n);
  }
  const logged = DRY ? 'not logged (dry run)' : await S.logLine('hub-briefing', 'briefing ' + date, { headline, items: n, missing: missing.join('; ') });
  console.log(now.toISOString() + ' ' + headline + ' | ' + pushed + ' | ' + logged + (missing.length ? ' | missing: ' + missing.join('; ') : ''));
}

main().catch(e => { console.error('briefing-job failed: ' + (e && e.stack || e)); process.exit(2); });
