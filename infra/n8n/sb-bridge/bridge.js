#!/usr/bin/env node
// The second brain's Slack bridge (RFC-0010 amendment A4): Slack Socket Mode in, one signed POST to n8n's webhook out. Node built-ins only
// (the global WebSocket and fetch, node:http, node:crypto): it runs in n8n's own image, no npm package, no build.
//
//   apps.connections.open (app-level token, xapp-) -> a wss URL -> connect -> `hello` -> envelopes. Every envelope is acked at once
//   ({envelope_id}). An events_api envelope whose event is an `app_mention` by a person (no bot_id; no subtype but `file_share`) is forwarded
//   to n8n: POST SB_HOOK_URL, body {channel, ts, thread_ts, user, text, event_id, bot, subtype}, headers X-SB-Timestamp (seconds) and
//   X-SB-Signature = sha256=HMAC-SHA256(secret, timestamp + "." + raw body), the header style of flotilla's hooks. Slack's retries (same
//   event_id) are forwarded once. n8n answers 200 at once and never answers a mention twice for one event_id, so the bridge retries a forward
//   that got no 2xx for up to FORWARD_BUDGET_MS (n8n down or being recreated) and never after one.
//
//   Connection: a failed or closed socket reconnects with backoff (1 s doubling to 30 s, jitter); only Slack's own `disconnect` with
//   reason refresh_requested reconnects at once. The backoff resets only after a socket stayed up STABLE_MS (a socket that gets `hello`
//   and is then closed, as too_many_websockets does, must not loop). A socket that does not open in CONNECT_TIMEOUT_MS is dropped.
//   Node's WebSocket does not expose Slack's ping frames, so a half-open socket cannot be seen from the frames; instead every REFRESH_MS
//   a new socket is opened (make before break: the old one is closed when the new one says `hello`), which bounds how long a dead one
//   can go unnoticed. When no socket has been open for UNHEALTHY_EXIT_MS the process exits 1, so the restart policy acts.
//   GET /healthz: 200 while a socket is open (after `hello`), else 503. One JSON log line per event: no message text, no token, no socket URL.
//
// Environment: SLACK_APP_TOKEN_FILE, SB_HOOK_SECRET_FILE, SB_HOOK_URL (required); SLACK_API_BASE (default https://slack.com), PORT (8080),
//   FORWARD_TIMEOUT_MS (10000), FORWARD_BUDGET_MS (120000), CONNECT_TIMEOUT_MS (15000), STABLE_MS (30000), REFRESH_MS (600000),
//   UNHEALTHY_EXIT_MS (300000).
'use strict';
const fs = require('node:fs');
const http = require('node:http');
const crypto = require('node:crypto');

const E = process.env;
const need = k => { if (!E[k]) { console.error(`STOP: set ${k}`); process.exit(2); } return E[k]; };
const readSecret = k => { const v = fs.readFileSync(need(k), 'utf8').trim(); if (!v) { console.error(`STOP: ${E[k]} is empty`); process.exit(2); } return v; };
const num = (k, d) => Number(E[k] || d);
const APP_TOKEN = readSecret('SLACK_APP_TOKEN_FILE');
const SECRET = readSecret('SB_HOOK_SECRET_FILE');
const HOOK = need('SB_HOOK_URL');
const API = (E.SLACK_API_BASE || 'https://slack.com').replace(/\/+$/, '');
const PORT = num('PORT', 8080);
const FORWARD_TIMEOUT = num('FORWARD_TIMEOUT_MS', 10000), FORWARD_BUDGET = num('FORWARD_BUDGET_MS', 120000);
const CONNECT_TIMEOUT = num('CONNECT_TIMEOUT_MS', 15000), STABLE = num('STABLE_MS', 30000), REFRESH = num('REFRESH_MS', 600000);
const UNHEALTHY_EXIT = num('UNHEALTHY_EXIT_MS', 300000);
const SEEN_MAX = 5000, SEEN_TTL_MS = 3600 * 1000;

const log = (msg, fields) => console.log(JSON.stringify(Object.assign({ t: new Date().toISOString(), msg }, fields)));

let cur = null, pending = null, attempt = 0, stopping = false, retryTimer = null, stableTimer = null, refreshTimer = null, lastUp = Date.now();
const isOpen = () => cur !== null;
const seen = new Map();   // event_id -> time first seen
const firstTime = id => {
  const now = Date.now();
  for (const [k, t] of seen) { if (now - t > SEEN_TTL_MS || seen.size > SEEN_MAX) seen.delete(k); else break; }   // Map keeps insertion order
  if (seen.has(id)) return false;
  seen.set(id, now);
  return true;
};

const sign = body => {
  const ts = String(Math.floor(Date.now() / 1000));
  return { ts, sig: 'sha256=' + crypto.createHmac('sha256', SECRET).update(ts + '.' + body).digest('hex') };
};

async function forward(ev, eventId, bot) {
  const body = JSON.stringify({ channel: ev.channel, ts: ev.ts, thread_ts: ev.thread_ts || null, user: ev.user, text: ev.text, event_id: eventId, bot: bot || null, subtype: ev.subtype || null });
  const t0 = Date.now();
  let status = 0, tries = 0;
  for (;;) {
    tries++;
    const { ts, sig } = sign(body);   // signed anew each try: the window is 5 minutes from the header
    try {
      const r = await fetch(HOOK, { method: 'POST', headers: { 'content-type': 'application/json', 'x-sb-timestamp': ts, 'x-sb-signature': sig },
        body, signal: AbortSignal.timeout(FORWARD_TIMEOUT) });
      status = r.status; await r.arrayBuffer().catch(() => {});
    } catch (e) { status = 0; }
    // any 2xx is done; a 400 or 401 is the webhook refusing this event (retrying never helps). No answer, a 5xx or a 404 (n8n down, being
    // recreated, or not yet serving the webhook) is tried again with backoff until the budget is spent.
    if ((status >= 200 && status < 300) || status === 400 || status === 401) break;
    const wait = Math.min(16000, 1000 * 2 ** (tries - 1));
    if (Date.now() - t0 + wait > FORWARD_BUDGET) break;
    await new Promise(r => setTimeout(r, wait));
  }
  log('mention', { channel: ev.channel, ts: ev.ts, thread_ts: ev.thread_ts || null, event_id: eventId, forwarded: status, tries });
  // the id was marked seen before the forward, so a mention whose budget ran out is not tried again by Slack's retry either: say so (ids only)
  if (!(status >= 200 && status < 300) && status !== 400 && status !== 401) log('forward gave up', { channel: ev.channel, ts: ev.ts, event_id: eventId, status, tries });
}

function onEnvelope(sock, raw) {
  let m; try { m = JSON.parse(raw); } catch (e) { log('bad frame'); return; }
  if (m.envelope_id) { try { sock.send(JSON.stringify({ envelope_id: m.envelope_id })); } catch (e) { /* the close handler reconnects */ } }
  if (m.type === 'hello') { adopt(sock, m); return; }
  if (m.type === 'disconnect') {
    log('disconnect', { reason: m.reason });
    if (m.reason === 'refresh_requested') { attempt = 0; retry(true); }   // Slack asked: a new socket at once; this one closes at the new one's hello
    else { try { sock.close(); } catch (e) { /* already closed */ } }
    return;
  }
  if (m.type !== 'events_api') return;
  const p = m.payload || {}, ev = p.event || {};
  if (ev.type !== 'app_mention' || ev.bot_id || (ev.subtype && ev.subtype !== 'file_share') || !ev.user || !ev.channel || !ev.ts || typeof ev.text !== 'string') {
    log('ignored', { event_type: String(ev.type || ''), channel: ev.channel || null, ts: ev.ts || null });
    return;
  }
  const eventId = String(p.event_id || '');
  if (!eventId) { log('ignored', { why: 'no event_id', ts: ev.ts }); return; }
  if (!firstTime(eventId)) { log('duplicate', { event_id: eventId, retry: m.retry_attempt || 0 }); return; }
  const bot = (Array.isArray(p.authorizations) && p.authorizations[0] && p.authorizations[0].user_id) || '';
  forward(ev, eventId, bot).catch(e => log('forward failed', { event_id: eventId, error: String(e && e.message).slice(0, 100) }));
}

// a socket that said hello becomes the current one; the one it replaces is closed after it (make before break)
function adopt(sock, hello) {
  if (sock !== pending && sock !== cur) return;
  const old = cur;
  cur = sock; if (pending === sock) pending = null;
  lastUp = Date.now();
  clearTimeout(sock.connectTimer);
  log('hello', { connections: hello.num_connections });
  clearTimeout(stableTimer); stableTimer = setTimeout(() => { attempt = 0; }, STABLE);   // the backoff resets only once a socket has stayed up
  clearTimeout(refreshTimer); refreshTimer = setTimeout(() => { log('refresh'); connect(); }, REFRESH);
  if (old && old !== sock) { old.replaced = true; try { old.close(); } catch (e) { /* already closed */ } }
}

async function connect() {
  if (pending || stopping) return;
  let url;
  try {
    const r = await fetch(API + '/api/apps.connections.open', { method: 'POST', headers: { authorization: 'Bearer ' + APP_TOKEN, 'content-type': 'application/x-www-form-urlencoded' },
      signal: AbortSignal.timeout(CONNECT_TIMEOUT) });
    const j = await r.json();
    if (!j.ok) throw new Error('slack: ' + String(j.error || 'no ok').slice(0, 60));
    url = j.url;
  } catch (e) { log('open failed', { error: String(e && e.message).slice(0, 100) }); retry(false); return; }   // also when a socket is open: a failed refresh is tried again
  const sock = new WebSocket(url);
  pending = sock;
  sock.connectTimer = setTimeout(() => {   // a socket through the proxy that never opens fires no close
    if (pending === sock) { log('connect timeout'); pending = null; try { sock.close(); } catch (e) { /* hung */ } retry(false); }
  }, CONNECT_TIMEOUT);
  sock.onmessage = ev => onEnvelope(sock, String(ev.data));
  sock.onerror = () => { /* onclose follows */ };
  sock.onclose = ev => {
    clearTimeout(sock.connectTimer);
    const wasCur = cur === sock, wasPending = pending === sock;
    if (wasPending) pending = null;
    if (wasCur) { cur = null; clearTimeout(stableTimer); }
    if (sock.replaced) return;
    log('closed', { code: ev.code });
    if (wasCur ? !pending : wasPending) retry(false);   // the current one died and none is coming, or a new one died before hello (a failed refresh included)
  };
}

function retry(immediate) {
  if (stopping || retryTimer) return;
  // zero wait only when Slack asked for a refresh; every other reconnect backs off, 1 s doubling to 30 s, with jitter
  const wait = immediate ? 0 : Math.min(30000, 1000 * 2 ** attempt) * (0.75 + Math.random() / 2);
  if (!immediate) attempt++;
  retryTimer = setTimeout(() => { retryTimer = null; connect(); }, wait);
}

setInterval(() => {
  if (isOpen()) { lastUp = Date.now(); return; }
  if (Date.now() - lastUp > UNHEALTHY_EXIT) { log('unhealthy, exiting', { for_ms: Date.now() - lastUp }); process.exit(1); }
}, 5000).unref();

http.createServer((req, res) => {
  const ok = req.url === '/healthz' && isOpen();
  res.writeHead(req.url === '/healthz' ? (ok ? 200 : 503) : 404, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ ok }));
}).listen(PORT, '0.0.0.0', () => log('listening', { port: PORT }));

for (const s of ['SIGTERM', 'SIGINT']) process.on(s, () => { stopping = true; for (const k of [cur, pending]) { try { k && k.close(); } catch (e) { /* closing */ } } setTimeout(() => process.exit(0), 200); });
connect();
