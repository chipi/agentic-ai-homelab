#!/usr/bin/env node
// The second brain's Slack bridge (RFC-0010 amendment A4): Slack Socket Mode in, one signed POST to n8n's webhook out. Node built-ins only
// (the global WebSocket and fetch, node:http, node:crypto): it runs in n8n's own image, no npm package, no build.
//
//   apps.connections.open (app-level token, xapp-) -> a wss URL -> connect -> `hello` -> envelopes. Every envelope is acked at once
//   ({envelope_id}). An events_api envelope whose event is an `app_mention` by a person (no bot_id, no subtype) is forwarded to n8n:
//   POST SB_HOOK_URL, body {channel, ts, thread_ts, user, text, event_id, bot}, headers X-SB-Timestamp (seconds) and
//   X-SB-Signature = sha256=HMAC-SHA256(secret, timestamp + "." + raw body), the header style of flotilla's hooks. Slack's retries
//   (same event_id) are forwarded once. A `disconnect` (or a closed socket) reconnects: at once on Slack's own request, else with backoff.
//   GET /healthz: 200 while the socket is open (after `hello`), else 503. One JSON log line per event: no message text, no token, no socket URL.
//
// Environment: SLACK_APP_TOKEN_FILE, SB_HOOK_SECRET_FILE, SB_HOOK_URL (required); SLACK_API_BASE (default https://slack.com), PORT (8080),
//   FORWARD_TIMEOUT_MS (10000), FORWARD_TRIES (4).
'use strict';
const fs = require('node:fs');
const http = require('node:http');
const crypto = require('node:crypto');

const E = process.env;
const need = k => { if (!E[k]) { console.error(`STOP: set ${k}`); process.exit(2); } return E[k]; };
const readSecret = k => { const v = fs.readFileSync(need(k), 'utf8').trim(); if (!v) { console.error(`STOP: ${E[k]} is empty`); process.exit(2); } return v; };
const APP_TOKEN = readSecret('SLACK_APP_TOKEN_FILE');
const SECRET = readSecret('SB_HOOK_SECRET_FILE');
const HOOK = need('SB_HOOK_URL');
const API = (E.SLACK_API_BASE || 'https://slack.com').replace(/\/+$/, '');
const PORT = Number(E.PORT || 8080);
const FORWARD_TIMEOUT = Number(E.FORWARD_TIMEOUT_MS || 10000), FORWARD_TRIES = Number(E.FORWARD_TRIES || 4);
const SEEN_MAX = 5000, SEEN_TTL_MS = 3600 * 1000;

const log = (msg, fields) => console.log(JSON.stringify(Object.assign({ t: new Date().toISOString(), msg }, fields)));

let ws = null, open = false, attempt = 0, stopping = false;
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
  const body = JSON.stringify({ channel: ev.channel, ts: ev.ts, thread_ts: ev.thread_ts || null, user: ev.user, text: ev.text, event_id: eventId, bot: bot || null });
  let status = 0;
  for (let i = 1; i <= FORWARD_TRIES; i++) {
    const { ts, sig } = sign(body);   // signed anew each try: the window is 5 minutes from the header
    try {
      const r = await fetch(HOOK, { method: 'POST', headers: { 'content-type': 'application/json', 'x-sb-timestamp': ts, 'x-sb-signature': sig },
        body, signal: AbortSignal.timeout(FORWARD_TIMEOUT) });
      status = r.status; await r.arrayBuffer().catch(() => {});
    } catch (e) { status = 0; }
    // 2xx is taken; a 4xx is the webhook refusing this event (retrying never helps); anything else (n8n down or restarting) is tried again
    if (status >= 200 && status < 500) break;
    if (i < FORWARD_TRIES) await new Promise(r => setTimeout(r, 1000 * 2 ** (i - 1)));
  }
  log('mention', { channel: ev.channel, ts: ev.ts, thread_ts: ev.thread_ts || null, event_id: eventId, forwarded: status });
}

function onEnvelope(raw) {
  let m; try { m = JSON.parse(raw); } catch (e) { log('bad frame'); return; }
  if (m.envelope_id) { try { ws.send(JSON.stringify({ envelope_id: m.envelope_id })); } catch (e) { /* the close handler reconnects */ } }
  if (m.type === 'hello') { open = true; attempt = 0; log('hello', { connections: m.num_connections }); return; }
  if (m.type === 'disconnect') { log('disconnect', { reason: m.reason }); try { ws.close(); } catch (e) { /* already closed */ } return; }
  if (m.type !== 'events_api') return;
  const p = m.payload || {}, ev = p.event || {};
  if (ev.type !== 'app_mention' || ev.bot_id || ev.subtype || !ev.user || !ev.channel || !ev.ts || typeof ev.text !== 'string') {
    log('ignored', { event_type: String(ev.type || ''), channel: ev.channel || null, ts: ev.ts || null });
    return;
  }
  const eventId = String(p.event_id || '');
  if (!eventId) { log('ignored', { why: 'no event_id', ts: ev.ts }); return; }
  if (!firstTime(eventId)) { log('duplicate', { event_id: eventId, retry: m.retry_attempt || 0 }); return; }
  const bot = (Array.isArray(p.authorizations) && p.authorizations[0] && p.authorizations[0].user_id) || '';
  forward(ev, eventId, bot).catch(e => log('forward failed', { event_id: eventId, error: String(e && e.message).slice(0, 100) }));
}

async function connect() {
  let url;
  try {
    const r = await fetch(API + '/api/apps.connections.open', { method: 'POST', headers: { authorization: 'Bearer ' + APP_TOKEN, 'content-type': 'application/x-www-form-urlencoded' },
      signal: AbortSignal.timeout(15000) });
    const j = await r.json();
    if (!j.ok) throw new Error('slack: ' + String(j.error || 'no ok').slice(0, 60));
    url = j.url;
  } catch (e) { log('open failed', { error: String(e && e.message).slice(0, 100) }); return retry(); }
  const sock = new WebSocket(url);
  ws = sock;
  sock.onmessage = ev => { if (sock === ws) onEnvelope(String(ev.data)); };
  sock.onerror = () => { /* onclose follows */ };
  sock.onclose = ev => { if (sock !== ws) return; open = false; log('closed', { code: ev.code }); retry(); };
}

let retryTimer = null;
function retry() {
  if (stopping || retryTimer) return;
  // a close right after `hello` + `disconnect` (Slack asked) comes back at once; failures back off, 1s doubling to 30s, with jitter
  const wait = attempt === 0 ? 0 : Math.min(30000, 1000 * 2 ** (attempt - 1)) * (0.75 + Math.random() / 2);
  attempt++;
  retryTimer = setTimeout(() => { retryTimer = null; connect(); }, wait);
}

http.createServer((req, res) => {
  const ok = req.url === '/healthz' && open;
  res.writeHead(req.url === '/healthz' ? (open ? 200 : 503) : 404, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ ok }));
}).listen(PORT, '0.0.0.0', () => log('listening', { port: PORT }));

for (const s of ['SIGTERM', 'SIGINT']) process.on(s, () => { stopping = true; try { ws && ws.close(); } catch (e) { /* closing */ } setTimeout(() => process.exit(0), 200); });
connect();
