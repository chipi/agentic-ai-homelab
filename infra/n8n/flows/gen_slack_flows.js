#!/usr/bin/env node
// Writes the two RFC-0014 case 1 Slack workflows (RFC-0010 amendment A3) as import files:
//   case1-slack-ask.json    Slack #ask (polled each minute) -> flotilla's `ask` hook (signed); imported INACTIVE: it starts polling when
//                           the operator publishes it (README "Case 1 Slack flows")
//   case1-slack-reply.json  /webhook/flotilla-reply (plumbing.reply: verified, idempotent) -> chat.postMessage in the question's thread
//   node gen_slack_flows.js [OUT_DIR] [--base URL]      --base (or SLACK_API_BASE) is for the throwaway proof only
// The Slack credential (type Slack API) is the operator's, made in the editor, so its id is not known here: the files carry the placeholder
// below and install-slack.sh puts the credential's real id (looked up by type) in its place.
'use strict';
const fs = require('fs'), path = require('path');
const args = process.argv.slice(2);
const bi = args.indexOf('--base');
const BASE = (bi >= 0 ? args.splice(bi, 2)[1] : process.env.SLACK_API_BASE || 'https://slack.com').replace(/\/+$/, '');
const OUT = args[0] || __dirname;

const CHANNEL = 'C0CM2K87SR1';           // Slack #ask: the questions are read here, and the one channel plumbing.reply's `general` maps to
const HOOK = 'http://flotillad:8488/hooks/ask';
const MAX_TEXT_IN = 2000, MAX_TEXT_OUT = 3000, PAGE = 50, MAX_PAGES = 10;

const SLACK_ID_PLACEHOLDER = '__SLACK_CRED_ID__';
const CRED = {
  slack: { slackApi: { id: SLACK_ID_PLACEHOLDER, name: 'Slack API (case 1)' } },
  ask: { crypto: { id: 'c1slackaskhook01', name: 'flotilla ask hook (HMAC)' } },
  reply: { crypto: { id: 'c1slackreplycb01', name: 'flotilla reply callback (HMAC)' } },
};
let x = 0;
const pos = () => [(x += 220), 0];
const code = (name, js, each) => ({ name, type: 'n8n-nodes-base.code', typeVersion: 2, position: pos(),
  parameters: Object.assign({ jsCode: js }, each ? { mode: 'runOnceForEachItem' } : {}) });
const hmac = (name, cred) => ({ name, type: 'n8n-nodes-base.crypto', typeVersion: 2, position: pos(), credentials: cred,
  parameters: { action: 'hmac', type: 'SHA256', value: '={{ $json.toSign }}', dataPropertyName: 'expected', encoding: 'hex' } });
const iff = (name, expr) => ({ name, type: 'n8n-nodes-base.if', typeVersion: 2.2, position: pos(), parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
    conditions: [{ id: 'c1', leftValue: expr, rightValue: '', operator: { type: 'boolean', operation: 'true', singleValue: true } }], combinator: 'and' },
  options: {} } });
const respond = name => ({ name, type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1.1, position: pos(), parameters: {
  respondWith: 'json', responseBody: '={{ JSON.stringify($json.response) }}', options: { responseCode: '={{ $json.code }}' } } });
const webhook = (name, p, id) => ({ name, type: 'n8n-nodes-base.webhook', typeVersion: 2, position: pos(), webhookId: id,
  parameters: { httpMethod: 'POST', path: p, responseMode: 'responseNode', options: { rawBody: true } } });
const wire = pairs => { const c = {}; for (const [from, to, out] of pairs) { const o = out || 0; c[from] = c[from] || { main: [] };
  while (c[from].main.length <= o) c[from].main.push([]); c[from].main[o].push({ node: to, type: 'main', index: 0 }); } return c; };
const wf = (id, name, nodes, conns, active) => [{ id, name, active: !!active, settings: { executionOrder: 'v1' },
  nodes: nodes.map((n, i) => Object.assign({ id: `${id}-${i}` }, n)), connections: wire(conns) }];

// a Slack ts is "seconds.micros" as text: compared as text, never as a float
const TS = `const cmp = (a, b) => { const [ai, af = ''] = String(a).split('.'), [bi, bf = ''] = String(b).split('.');
  const d = BigInt(ai || 0) - BigInt(bi || 0); return d !== 0n ? (d > 0n ? 1 : -1) : af.padEnd(9, '0').localeCompare(bf.padEnd(9, '0')); };`;

// ---- 1. Slack #ask -> the ask hook ---------------------------------------------------------------------
x = 0;
const ask = wf('case1slackask001', 'case 1: Slack #ask -> flotilla ask hook', [
  { name: 'Every minute', type: 'n8n-nodes-base.scheduleTrigger', typeVersion: 1.2, position: pos(),
    parameters: { rule: { interval: [{ field: 'minutes', minutesInterval: 1 }] } } },
  { name: 'Run now', type: 'n8n-nodes-base.manualTrigger', typeVersion: 1, position: pos(), parameters: {} },   // `n8n execute` and the editor start here
  code('State', `// the last message seen is kept in the workflow's static data. No state yet = the first run: it asks for the newest message only
const sd = $getWorkflowStaticData('global');
const skipped = sd.skipped || [];
sd.skipped = [];   // assigned, not deleted: the code runner passes back assignments only
return [{ json: { first: !sd.last, oldest: sd.last || '0', skipped } }];`),
  code('Report', `// a message flotilla refused for itself was moved past (Mark): say so here, once, so it shows as a failed run in n8n
const s = $input.first().json.skipped;
if (s.length) throw new Error('flotilla refused, and the flow moved past: ' + s.join('; '));
return $input.all();`),
  { name: 'History', type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position: pos(), credentials: CRED.slack,
    parameters: { method: 'GET', url: BASE + '/api/conversations.history', authentication: 'predefinedCredentialType', nodeCredentialType: 'slackApi',
      sendQuery: true, queryParameters: { parameters: [
        { name: 'channel', value: CHANNEL },
        { name: 'oldest', value: '={{ $json.oldest }}' },
        { name: 'limit', value: `={{ $json.first ? 1 : ${PAGE} }}` }] },
      options: { response: { response: { neverError: true } }, pagination: { pagination: {
        // history comes newest first: when has_more, the older messages are on the next page, so all pages are read before any is acted on
        paginationMode: 'updateAParameterInEachRequest',
        parameters: { parameters: [{ type: 'qs', name: 'cursor', value: '={{ $response.body.response_metadata.next_cursor }}' }] },
        paginationCompleteWhen: 'other',
        completeExpression: `={{ $response.body.ok !== true || $response.body.has_more !== true || !$response.body.response_metadata || !$response.body.response_metadata.next_cursor || $('State').first().json.first }}`,
        limitPagesFetched: true, maxRequests: MAX_PAGES } } } } },
  code('Pick', `${TS}
// Slack's answer: check it, then keep top-level human messages, oldest first. Nothing is advanced unless every page came.
const sd = $getWorkflowStaticData('global');
const pages = $input.all().map(i => i.json);
if (!pages.length) throw new Error('Slack conversations.history: no answer');
for (const p of pages) if (p.ok !== true) throw new Error('Slack conversations.history: ' + String(p.error || 'no ok in the answer').slice(0, 200));
const msgs = pages.flatMap(p => p.messages || []).filter(m => m && /^\\d+\\.\\d+$/.test(String(m.ts)));
if (!sd.last) {  // the first run: remember the newest message (or now) and post nothing: no backfill of old history
  const t = msgs.map(m => m.ts).sort(cmp).pop();
  sd.last = t || (Date.now() / 1000).toFixed(6);
  return [];
}
if (pages[pages.length - 1].has_more === true) throw new Error('Slack conversations.history: more than ' + ${PAGE * MAX_PAGES} + ' messages since ' + sd.last + '; nothing advanced');
const fresh = msgs.filter(m => cmp(m.ts, sd.last) > 0);
const seen = new Set();
const humans = fresh.filter(m => !m.subtype && !m.bot_id && m.user && typeof m.text === 'string' && m.text.trim()
  && (!m.thread_ts || m.thread_ts === m.ts) && !seen.has(m.ts) && seen.add(m.ts))
  .sort((a, b) => cmp(a.ts, b.ts));
const newest = fresh.map(m => m.ts).sort(cmp).pop();
if (!humans.length) { if (newest) sd.last = newest; return []; }
return humans.map(m => ({ json: { ts: m.ts, user: String(m.user), text: m.text, newest } }));`),
  { name: 'One at a time', type: 'n8n-nodes-base.splitInBatches', typeVersion: 3, position: pos(), parameters: { batchSize: 1, options: {} } },
  code('Build', `// flotilla's ask hook body {thread, user, text}; the delivery id is the channel and the message's ts, so a re-post is a replay
const text = Array.from(String($json.text)).slice(0, ${MAX_TEXT_IN}).join('');
const delivery = 'slack-${CHANNEL}-' + $json.ts;
const body = JSON.stringify({ thread: $json.ts, user: $json.user, text });
const ts = String(Math.floor(Date.now() / 1000));
return { json: { thread: $json.ts, delivery, ts, body, toSign: ts + '.' + delivery + '.' + body } };`, true),
  hmac('Sign', CRED.ask),
  { name: 'Send', type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position: pos(), parameters: {
      method: 'POST', url: HOOK, sendHeaders: true,
      headerParameters: { parameters: [
        { name: 'X-Flotilla-Timestamp', value: '={{ $json.ts }}' },
        { name: 'X-Flotilla-Delivery', value: '={{ $json.delivery }}' },
        { name: 'X-Flotilla-Signature', value: '=sha256={{ $json.expected }}' }] },
      sendBody: true, contentType: 'raw', rawContentType: 'application/json', body: '={{ $json.body }}',
      options: { response: { response: { fullResponse: true, neverError: true, responseFormat: 'text' } } } } },
  code('Mark', `${TS}
// 202: a question case opened; 200: a replay of this message. Either way the message is done and the stored ts moves past it.
// 400, 413 and 422 are flotilla refusing this message itself (a field too long, a body too big): retrying never helps, so it is
// moved past and reported by the next run's Report node. Anything else (5xx, 401, 429, a network error) fails the run right here: the stored
// ts stays before this message and the next minute sends it again.
const sd = $getWorkflowStaticData('global');
const r = $json, f = $('Build').item.json;
if (r.statusCode === 202 || r.statusCode === 200) { if (cmp(f.thread, sd.last) > 0) sd.last = f.thread; return { json: { thread: f.thread, status: r.statusCode } }; }
if ([400, 413, 422].includes(r.statusCode)) {
  sd.skipped = (sd.skipped || []).concat(f.thread + ' (' + r.statusCode + ': ' + String(r.body ?? r.data).slice(0, 120) + ')');
  if (cmp(f.thread, sd.last) > 0) sd.last = f.thread; return { json: { thread: f.thread, status: r.statusCode } };
}
throw new Error('flotilla ask hook answered ' + r.statusCode + ' for ' + f.delivery + ': ' + String(r.body ?? r.data).slice(0, 300) + '; it is sent again next run');`, true),
  code('Done', `${TS}
// every message sent: the ts moves past the ignored ones after the last (bots, thread replies)
const sd = $getWorkflowStaticData('global');
const newest = $('Pick').first().json.newest;
if (newest && cmp(newest, sd.last) > 0) sd.last = newest;
return [{ json: { last: sd.last } }];`),
], [['Every minute', 'State'], ['Run now', 'State'], ['State', 'Report'], ['Report', 'History'], ['History', 'Pick'], ['Pick', 'One at a time'],
    ['One at a time', 'Done', 0], ['One at a time', 'Build', 1], ['Build', 'Sign'], ['Sign', 'Send'], ['Send', 'Mark'], ['Mark', 'One at a time']], false);

// ---- 2. flotilla's plumbing.reply -> chat.postMessage ------------------------------------------------------
x = 0;
const rp = wf('case1slackreply1', 'case 1: flotilla reply -> Slack thread', [
  webhook('Webhook', 'flotilla-reply', '3e8a6d14-9b27-4c05-8f1e-6a4d2c9b7e03'),
  code('Verify', `// flotilla's plumbing.call: HMAC-SHA256(secret, timestamp + "." + delivery + "." + raw body), 5-minute window
let raw = '';
try { raw = (await this.helpers.getBinaryDataBuffer(0, 'data')).toString('utf8'); } catch (e) { raw = ''; }
const h = $input.first().json.headers || {};
const ts = String(h['x-flotilla-timestamp'] || ''), delivery = String(h['x-flotilla-delivery'] || ''), sig = String(h['x-flotilla-signature'] || '');
const fresh = /^\\d+$/.test(ts) && Math.abs(Math.floor(Date.now() / 1000) - Number(ts)) <= 300;
return [{ json: { ts, delivery, sig, raw, fresh, okDelivery: /^[A-Za-z0-9._:-]{1,128}$/.test(delivery), toSign: ts + '.' + delivery + '.' + raw } }];`),
  hmac('Sign', CRED.reply),
  code('Check', `const v = $input.first().json;
const fail = (code, error) => [{ json: { valid: false, code, response: { error } } }];
if (!v.raw) return fail(400, 'no body');
if (!v.okDelivery) return fail(400, 'bad delivery id');
if (!v.fresh) return fail(401, 'stale or missing timestamp');
if (v.sig !== 'sha256=' + v.expected) return fail(401, 'bad signature');
let b; try { b = JSON.parse(v.raw); } catch (e) { return fail(400, 'body is not JSON'); }
if (b.action !== 'plumbing.reply') return fail(400, 'this webhook takes plumbing.reply only');
if (b.mode !== 'send' && b.mode !== 'status') return fail(400, 'mode must be send or status');
const p = b.params || {};
if (b.mode === 'send') {
  if (p.channel !== 'general') return fail(400, 'params.channel: general only');
  if (typeof p.thread !== 'string' || !/^[0-9]{1,20}\\.[0-9]{1,10}$/.test(p.thread)) return fail(400, 'params.thread: a Slack message ts');
  if (typeof p.text !== 'string' || !p.text.trim() || Array.from(p.text).length > ${MAX_TEXT_OUT}) return fail(400, 'params.text: 1 to ${MAX_TEXT_OUT} characters');
}
return [{ json: { valid: true, mode: b.mode, delivery: v.delivery, thread: String(p.thread || ''), text: String(p.text || '') } }];`),
  iff('Valid?', '={{ $json.valid }}'),
  respond('Refuse'),
  code('Decide', `// the reply is kept by its delivery id in this workflow's static data once Slack took it: a re-send finds it and posts nothing
const c = $input.first().json, sd = $getWorkflowStaticData('global');
const done = (sd.sent || {})[c.delivery];
if (c.mode === 'status') return [{ json: { post: false, code: 200, response: done ? { done: true, ref: done.ref } : { done: false } } }];
if (done) return [{ json: { post: false, code: 200, response: { ref: done.ref } } }];
return [{ json: { post: true, delivery: c.delivery, request: { channel: '${CHANNEL}', thread_ts: c.thread, text: c.text, unfurl_links: false, unfurl_media: false } } }];`),
  iff('Post?', '={{ $json.post }}'),
  respond('Answer'),
  { name: 'Post', type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position: pos(), credentials: CRED.slack, parameters: {
      method: 'POST', url: BASE + '/api/chat.postMessage', authentication: 'predefinedCredentialType', nodeCredentialType: 'slackApi',
      sendBody: true, specifyBody: 'json', jsonBody: '={{ JSON.stringify($json.request) }}',
      options: { response: { response: { neverError: true } } } } },
  code('Made', `const r = $input.first().json, d = $('Decide').first().json;
if (r.ok !== true || !r.ts) return [{ json: { code: 502, response: { error: 'Slack did not take the reply: ' + String(r.error || JSON.stringify(r)).slice(0, 200) } } }];
const sd = $getWorkflowStaticData('global');
const ref = ('Slack #ask thread ' + d.request.thread_ts + ', reply ' + r.ts).slice(0, 200);
sd.sent = sd.sent || {};
sd.sent[d.delivery] = { ref, at: Date.now() };
// the newest 1000 are kept (a delivery is re-sent within minutes, not months); assigned whole, as the code runner passes back assignments only
const keep = Object.entries(sd.sent).sort((a, b) => b[1].at - a[1].at).slice(0, 1000);
sd.sent = Object.fromEntries(keep);
return [{ json: { code: 200, response: { ref } } }];`),
  respond('Answer made'),
], [['Webhook', 'Verify'], ['Verify', 'Sign'], ['Sign', 'Check'], ['Check', 'Valid?'], ['Valid?', 'Decide', 0], ['Valid?', 'Refuse', 1],
    ['Decide', 'Post?'], ['Post?', 'Post', 0], ['Post?', 'Answer', 1], ['Post', 'Made'], ['Made', 'Answer made']], true);

for (const [f, w] of [['case1-slack-ask.json', ask], ['case1-slack-reply.json', rp]]) {
  fs.writeFileSync(path.join(OUT, f), JSON.stringify(w, null, 1) + '\n');
  console.log('wrote', f, w[0].nodes.length, 'nodes');
}
