#!/usr/bin/env node
// Writes the three RFC-0014 case 3 n8n workflows (RFC-0010 amendment A1) as import files:
//   case3-meeting.json        Drive folder -> flotilla's `meeting` hook (signed)
//   case3-create-tasks.json   /webhook/flotilla-create-tasks  (plumbing.create_tasks, verified, idempotent)
//   case3-post-decisions.json /webhook/flotilla-post-decisions (plumbing.post_decisions, verified, idempotent)
'use strict';
const fs = require('fs'), path = require('path');
const OUT = process.argv[2] || __dirname;
const FOLDER = '19-16sCI6H6egNTbB1G6RJx6cdVdJnq5Q', DOC = '1uzHJ3t00ZdVsUlyLHQdYLo05z-Ugd5FnRLU8V4BW0os', LIST = 'ai1ER3E5cXFzZWRCUnNTZQ';
const CRED = {
  drive: { googleDriveOAuth2Api: { id: 'hnWVwuND8WJ56zgN', name: 'Google Drive account' } },
  docs: { googleDocsOAuth2Api: { id: '5AFJ3cb7tOlHOJj3', name: 'Google Docs account' } },
  tasks: { googleTasksOAuth2Api: { id: 't7nA9h2E8Af6s8jm', name: 'Google Tasks account' } },
  meeting: { crypto: { id: 'c3meetingsecret1', name: 'flotilla meeting hook (HMAC)' } },
  createTasks: { crypto: { id: 'c3createtasks001', name: 'flotilla create_tasks callback (HMAC)' } },
  postDecisions: { crypto: { id: 'c3postdecision01', name: 'flotilla post_decisions callback (HMAC)' } },
};
let x = 0;
const pos = () => [(x += 220), 0];
const code = (name, js, each) => ({ name, type: 'n8n-nodes-base.code', typeVersion: 2, position: pos(),
  parameters: Object.assign({ jsCode: js }, each ? { mode: 'runOnceForEachItem' } : {}) });
const hmac = (name, cred) => ({ name, type: 'n8n-nodes-base.crypto', typeVersion: 2, position: pos(), credentials: cred,
  parameters: { action: 'hmac', type: 'SHA256', value: '={{ $json.toSign }}', dataPropertyName: 'expected', encoding: 'hex' } });
const http = (name, cred, credType, method, url, extra) => ({ name, type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position: pos(), credentials: cred,
  parameters: Object.assign({ method, url, authentication: 'predefinedCredentialType', nodeCredentialType: credType,
    options: { response: { response: { neverError: true } } } }, extra || {}) });
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

// ---- shared: verify flotilla's signed callback ------------------------------------------------------
const VERIFY = `// flotilla's plumbing.call: HMAC-SHA256(secret, timestamp + "." + delivery + "." + raw body), 5-minute window
let raw = '';
try { raw = (await this.helpers.getBinaryDataBuffer(0, 'data')).toString('utf8'); } catch (e) { raw = ''; }
const h = $input.first().json.headers || {};
const ts = String(h['x-flotilla-timestamp'] || ''), delivery = String(h['x-flotilla-delivery'] || ''), sig = String(h['x-flotilla-signature'] || '');
const fresh = /^\\d+$/.test(ts) && Math.abs(Math.floor(Date.now() / 1000) - Number(ts)) <= 300;
return [{ json: { ts, delivery, sig, raw, fresh, okDelivery: /^[A-Za-z0-9._:-]{1,128}$/.test(delivery), toSign: ts + '.' + delivery + '.' + raw } }];`;
const checkHead = action => `const v = $input.first().json;
const fail = (code, error) => [{ json: { valid: false, code, response: { error } } }];
if (!v.raw) return fail(400, 'no body');
if (!v.okDelivery) return fail(400, 'bad delivery id');
if (!v.fresh) return fail(401, 'stale or missing timestamp');
if (v.sig !== 'sha256=' + v.expected) return fail(401, 'bad signature');
let b; try { b = JSON.parse(v.raw); } catch (e) { return fail(400, 'body is not JSON'); }
if (b.action !== '${action}') return fail(400, 'this webhook takes ${action} only');
if (b.mode !== 'send' && b.mode !== 'status') return fail(400, 'mode must be send or status');
const p = b.params || {};`;

// ---- 1. create_tasks -------------------------------------------------------------------------------
x = 0;
const ct = wf('case3createtasks', 'case 3: flotilla create_tasks -> Google Tasks', [
  webhook('Webhook', 'flotilla-create-tasks', '7d4e1c52-3a0b-4f61-9b7e-0c3a5b1e2d01'),
  code('Verify', VERIFY),
  hmac('Sign', CRED.createTasks),
  code('Check', checkHead('plumbing.create_tasks') + `
let items = [];
if (b.mode === 'send') {
  items = Array.isArray(p.items) ? p.items : [];
  if (items.length < 1 || items.length > 20) return fail(400, 'params.items: 1 to 20 follow-ups');
  for (const it of items) if (!it || typeof it.what !== 'string' || !it.what.trim() || typeof it.who !== 'string' || !/^\\d{4}-\\d{2}-\\d{2}$/.test(String(it.by)))
    return fail(400, 'each item needs who, what and by (YYYY-MM-DD)');
}
return [{ json: { valid: true, mode: b.mode, delivery: v.delivery, case_id: String(b.case_id || ''), items } }];`),
  iff('Valid?', '={{ $json.valid }}'),
  respond('Refuse'),
  http('Existing', CRED.tasks, 'googleTasksOAuth2Api', 'GET', `https://www.googleapis.com/tasks/v1/lists/${LIST}/tasks?showCompleted=true&showHidden=true&maxResults=100`),
  code('Decide', `// a re-send of a delivery already made makes nothing twice: the delivery id is in each task's notes
const c = $('Check').first().json, mark = 'flotilla delivery: ' + c.delivery;
const mine = ($input.first().json.items || []).filter(t => String(t.notes || '').includes(mark));
const ref = ('Google Tasks list "homelab n8n follow-ups": ' + mine.length + ' task(s), e.g. ' + (mine[0] && mine[0].id)).slice(0, 200);
if (c.mode === 'status') return [{ json: { create: false, code: 200, response: mine.length ? { done: true, ref } : { done: false } } }];
if (mine.length) return [{ json: { create: false, code: 200, response: { ref } } }];
return c.items.map(it => ({ json: { create: true, title: it.what.trim().slice(0, 1024), due: it.by + 'T00:00:00.000Z',
  notes: ('who: ' + it.who + '\\n' + mark + '\\ncase: ' + c.case_id).slice(0, 8000) } }));`),
  iff('Create?', '={{ $json.create }}'),
  respond('Answer'),
  http('Create task', CRED.tasks, 'googleTasksOAuth2Api', 'POST', `https://www.googleapis.com/tasks/v1/lists/${LIST}/tasks`,
    { sendBody: true, specifyBody: 'json', jsonBody: '={{ JSON.stringify({ title: $json.title, due: $json.due, notes: $json.notes }) }}' }),
  code('Made', `const ids = $input.all().map(i => i.json.id);
if (!ids.length || ids.some(id => !id)) return [{ json: { code: 502, response: { error: 'Google Tasks did not create every task: ' + JSON.stringify($input.all().map(i => i.json.error || null)).slice(0, 300) } } }];
return [{ json: { code: 200, response: { ref: ('Google Tasks list "homelab n8n follow-ups": ' + ids.length + ' task(s), e.g. ' + ids[0]).slice(0, 200) } } }];`),
  respond('Answer made'),
], [['Webhook', 'Verify'], ['Verify', 'Sign'], ['Sign', 'Check'], ['Check', 'Valid?'], ['Valid?', 'Existing', 0], ['Valid?', 'Refuse', 1],
    ['Existing', 'Decide'], ['Decide', 'Create?'], ['Create?', 'Create task', 0], ['Create?', 'Answer', 1], ['Create task', 'Made'], ['Made', 'Answer made']], true);

// ---- 2. post_decisions -----------------------------------------------------------------------------
x = 0;
const pd = wf('case3postdecisio', 'case 3: flotilla post_decisions -> Google Doc', [
  webhook('Webhook', 'flotilla-post-decisions', '5b9f0a17-6c2d-4e38-a4f1-2d8c7e6b3a02'),
  code('Verify', VERIFY),
  hmac('Sign', CRED.postDecisions),
  code('Check', checkHead('plumbing.post_decisions') + `
if (p.page !== undefined && p.page !== 'decisions') return fail(400, 'params.page: decisions only');
if (b.mode === 'send' && (typeof p.text !== 'string' || !p.text.trim() || p.text.length > 8000)) return fail(400, 'params.text: 1 to 8000 characters');
return [{ json: { valid: true, mode: b.mode, delivery: v.delivery, case_id: String(b.case_id || ''), text: String(p.text || '') } }];`),
  iff('Valid?', '={{ $json.valid }}'),
  respond('Refuse'),
  http('Doc', CRED.docs, 'googleDocsOAuth2Api', 'GET', `https://docs.googleapis.com/v1/documents/${DOC}`),
  code('Decide', `// the delivery id is written with the decisions: a re-send finds it and appends nothing
const c = $('Check').first().json, d = $input.first().json, mark = 'flotilla delivery: ' + c.delivery;
const ref = 'Google Doc "homelab n8n decisions" (${DOC})';
if (!d.body) return [{ json: { post: false, code: 502, response: { error: 'could not read the decisions doc' } } }];
const text = (d.body.content || []).flatMap(e => (e.paragraph && e.paragraph.elements) || []).map(e => (e.textRun && e.textRun.content) || '').join('');
const has = text.includes(mark);
if (c.mode === 'status') return [{ json: { post: false, code: 200, response: has ? { done: true, ref } : { done: false } } }];
if (has) return [{ json: { post: false, code: 200, response: { ref } } }];
const line = '\\n' + c.text.trim() + '\\n' + mark + ' · case ' + c.case_id + ' · ' + new Date().toISOString().slice(0, 10) + '\\n';
return [{ json: { post: true, ref, request: { requests: [{ insertText: { endOfSegmentLocation: { segmentId: '' }, text: line } }] } } }];`),
  iff('Post?', '={{ $json.post }}'),
  respond('Answer'),
  http('Append', CRED.docs, 'googleDocsOAuth2Api', 'POST', `https://docs.googleapis.com/v1/documents/${DOC}:batchUpdate`,
    { sendBody: true, specifyBody: 'json', jsonBody: '={{ JSON.stringify($json.request) }}' }),
  code('Made', `const r = $input.first().json, ref = $('Decide').first().json.ref;
if (!r.documentId) return [{ json: { code: 502, response: { error: 'Google Docs did not append: ' + JSON.stringify(r.error || r).slice(0, 300) } } }];
return [{ json: { code: 200, response: { ref } } }];`),
  respond('Answer made'),
], [['Webhook', 'Verify'], ['Verify', 'Sign'], ['Sign', 'Check'], ['Check', 'Valid?'], ['Valid?', 'Doc', 0], ['Valid?', 'Refuse', 1],
    ['Doc', 'Decide'], ['Decide', 'Post?'], ['Post?', 'Append', 0], ['Post?', 'Answer', 1], ['Append', 'Made'], ['Made', 'Answer made']], true);

// ---- 3. Drive folder -> meeting hook ---------------------------------------------------------------
x = 0;
const trig = (name, event) => ({ name, type: 'n8n-nodes-base.googleDriveTrigger', typeVersion: 1, position: pos(), credentials: CRED.drive,
  parameters: { pollTimes: { item: [{ mode: 'everyMinute' }] }, triggerOn: 'specificFolder',
    folderToWatch: { __rl: true, value: FOLDER, mode: 'id' }, event, options: {} } });
const mt = wf('case3meetinghook', 'case 3: Drive meeting notes -> flotilla meeting hook', [
  trig('New file', 'fileCreated'),
  trig('Changed file', 'fileUpdated'),
  code('Pick', `// text-like files only: a Google Doc (exported as plain text), .txt, .md
const ok = ['application/vnd.google-apps.document', 'text/plain', 'text/markdown'];
return $input.all().filter(i => ok.includes(i.json.mimeType))
  .map(i => ({ json: { id: i.json.id, name: String(i.json.name || 'meeting-notes'), mimeType: i.json.mimeType, modifiedTime: i.json.modifiedTime || i.json.createdTime || '' } }));`),
  http('Text', CRED.drive, 'googleDriveOAuth2Api', 'GET',
    "={{ $json.mimeType === 'application/vnd.google-apps.document' ? 'https://www.googleapis.com/drive/v3/files/' + $json.id + '/export?mimeType=text/plain' : 'https://www.googleapis.com/drive/v3/files/' + $json.id + '?alt=media' }}",
    { options: { response: { response: { neverError: false, responseFormat: 'text', outputPropertyName: 'data' } } } }),
  code('Build', `// flotilla's meeting hook body {file, date?, text}; the delivery id is the file's id and version, so a
// re-send of the same version opens nothing and an edited file is a new delivery
const f = $('Pick').item.json, text = String($json.data || '');
const file = f.name.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 120) || 'meeting-notes';
const m = f.name.match(/(\\d{4}-\\d{2}-\\d{2})/);
const delivery = (f.id + ':' + (f.modifiedTime || 'v')).replace(/[^A-Za-z0-9._:-]/g, '-').slice(0, 128);
const body = JSON.stringify(m ? { file, date: m[1], text } : { file, text });
const size = new TextEncoder().encode(body).length;
if (size > 200000) throw new Error('notes too large for the meeting hook: ' + size + ' bytes (about 200 KB at most)');
const ts = String(Math.floor(Date.now() / 1000));
return { json: { file, ts, delivery, body, toSign: ts + '.' + delivery + '.' + body } };`, true),
  hmac('Sign', CRED.meeting),
  { name: 'Send', type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position: pos(), parameters: {
      method: 'POST', url: 'http://flotillad:8488/hooks/meeting', sendHeaders: true,
      headerParameters: { parameters: [
        { name: 'X-Flotilla-Timestamp', value: '={{ $json.ts }}' },
        { name: 'X-Flotilla-Delivery', value: '={{ $json.delivery }}' },
        { name: 'X-Flotilla-Signature', value: '=sha256={{ $json.expected }}' }] },
      sendBody: true, contentType: 'raw', rawContentType: 'application/json', body: '={{ $json.body }}',
      options: { response: { response: { fullResponse: true, neverError: true, responseFormat: 'text' } } } } },
  code('Check', `// 202: a case opened; 200: a replay of this version. Anything else fails the run, so it shows in n8n.
const r = $json, f = $('Build').item.json;
if (r.statusCode !== 202 && r.statusCode !== 200) throw new Error('flotilla meeting hook answered ' + r.statusCode + ' for ' + f.file + ': ' + String(r.body).slice(0, 300));
return { json: { file: f.file, delivery: f.delivery, status: r.statusCode, body: String(r.body).slice(0, 300) } };`, true),
], [['New file', 'Pick'], ['Changed file', 'Pick'], ['Pick', 'Text'], ['Text', 'Build'], ['Build', 'Sign'], ['Sign', 'Send'], ['Send', 'Check']], false);

for (const [f, w] of [['case3-create-tasks.json', ct], ['case3-post-decisions.json', pd], ['case3-meeting.json', mt]]) {
  fs.writeFileSync(path.join(OUT, f), JSON.stringify(w, null, 1) + '\n');
  console.log('wrote', f, w[0].nodes.length, 'nodes');
}
