#!/usr/bin/env node
// Writes the two RFC-0014 case 1 read servers (RFC-0010 amendment A2) as import files:
//   case1-mcp-docs.json   MCP server `docs`:  tools search {query}, read {id}   (the documents folder and the decisions doc)
//   case1-mcp-tasks.json  MCP server `tasks`: tool list {}                      (the follow-ups task list)
// Each file holds the server workflow (an MCP Server Trigger and its tool nodes, Call n8n Workflow Tool) and one sub-workflow per
// tool, which the tool node calls by id (the node takes its argument names from $fromAI only when it calls a workflow by id).
// Every Google call is an HTTP Request node on the one read-only credential.
//   node gen_mcp_flows.js [OUT_DIR] [--base URL]      --base (or GOOGLE_API_BASE) is for the throwaway proof only
// The read-only Google credential is made by the operator's sign-in in the editor, so its id is not known here: the files carry
// the placeholder below and install-mcp.sh puts the credential's real id (looked up by name and type) in its place.
'use strict';
const fs = require('fs'), path = require('path');
const args = process.argv.slice(2);
const bi = args.indexOf('--base');
const BASE = (bi >= 0 ? args.splice(bi, 2)[1] : process.env.GOOGLE_API_BASE || 'https://www.googleapis.com').replace(/\/+$/, '');
const OUT = args[0] || __dirname;

// ---- what the servers read: the case 3 constants (gen_flows.js), the operator's to change ---------------------------
const FOLDER = '19-16sCI6H6egNTbB1G6RJx6cdVdJnq5Q';              // Drive folder "homelab n8n meeting notes": docs.search and docs.read
const DOC = '1uzHJ3t00ZdVsUlyLHQdYLo05z-Ugd5FnRLU8V4BW0os';       // Google Doc "homelab n8n decisions": readable too
const LIST = 'ai1ER3E5cXFzZWRCUnNTZQ';                           // Tasks list "homelab n8n follow-ups": tasks.list
// ---- limits ---------------------------------------------------------------------------------------------------------
const MAX_QUERY = 200, MAX_HITS = 10, MAX_READ = 60000, MAX_TASKS = 100, MAX_NOTES = 300;

const GOOGLE_ID_PLACEHOLDER = '__GOOGLE_RO_CRED_ID__';
const CRED = {
  google: { googleOAuth2Api: { id: GOOGLE_ID_PLACEHOLDER, name: 'Google read-only (case 1)' } },
  docsToken: { httpBearerAuth: { id: 'c1mcpdocstoken01', name: 'case 1 docs MCP (bearer)' } },
  tasksToken: { httpBearerAuth: { id: 'c1mcptaskstoken1', name: 'case 1 tasks MCP (bearer)' } },
};
const PATHS = { docs: 'case1-docs', tasks: 'case1-tasks' };   // served at {WEBHOOK_URL}mcp/<path>

let x = 0;
const pos = () => [(x += 220), 0];
const code = (name, js) => ({ name, type: 'n8n-nodes-base.code', typeVersion: 2, position: pos(), parameters: { jsCode: js } });
const http = (name, url, query, extra) => ({ name, type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position: pos(), credentials: CRED.google,
  parameters: Object.assign({ method: 'GET', url, authentication: 'predefinedCredentialType', nodeCredentialType: 'googleOAuth2Api',
    sendQuery: true, queryParameters: { parameters: Object.entries(query).map(([name, value]) => ({ name, value })) },
    options: { response: { response: { neverError: true } } } }, extra || {}) });
const iff = (name, expr) => ({ name, type: 'n8n-nodes-base.if', typeVersion: 2.2, position: pos(), parameters: {
  conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
    conditions: [{ id: 'c1', leftValue: expr, rightValue: '', operator: { type: 'boolean', operation: 'true', singleValue: true } }], combinator: 'and' },
  options: {} } });
const stop = (name, expr) => ({ name, type: 'n8n-nodes-base.stopAndError', typeVersion: 1, position: pos(), parameters: { errorMessage: expr } });
const wire = pairs => { const c = {}; for (const [from, to, out] of pairs) { const o = out || 0; c[from] = c[from] || { main: [] };
  while (c[from].main.length <= o) c[from].main.push([]); c[from].main[o].push({ node: to, type: 'main', index: 0 }); } return c; };
// a read's saved execution would hold the document text in n8n's database: successes are saved without their data (RFC-0014 section 4.8)
const wf = (id, name, nodes, connections, active) => ({ id, name, active: !!active, settings: { executionOrder: 'v1', saveDataSuccessExecution: 'none' },
  nodes: nodes.map((n, i) => Object.assign({ id: `${id}-${i}` }, n)), connections });

// A tool's sub-workflow: an Execute Workflow trigger takes the one argument the model gave, then the fixed steps.
const sub = (id, name, steps, conns) => {
  x = 0;
  return wf(id, name, [{ name: 'In', type: 'n8n-nodes-base.executeWorkflowTrigger', typeVersion: 1.1, position: pos(), parameters: { inputSource: 'passthrough' } }]
    .concat(steps(x)), wire(conns), false);
};

// The tool node the MCP trigger lists. The model supplies `arg` only: everything else is fixed in the sub-workflow.
const tool = (name, description, subId, arg, argDescription, position) => ({ name, type: '@n8n/n8n-nodes-langchain.toolWorkflow', typeVersion: 2.2, position,
  parameters: Object.assign({ description, source: 'database', workflowId: { __rl: true, value: subId, mode: 'id' } },
    arg ? { workflowInputs: { mappingMode: 'defineBelow', matchingColumns: [], attemptToConvertTypes: false, convertFieldsToString: false,
      value: { [arg]: `={{ $fromAI('${arg}', ${JSON.stringify(argDescription)}, 'string') }}` },
      schema: [{ id: arg, displayName: arg, required: true, defaultMatch: false, display: true, canBeUsedToMatch: false, type: 'string' }] } }
      : { workflowInputs: { mappingMode: 'defineBelow', value: {}, matchingColumns: [], schema: [], attemptToConvertTypes: false, convertFieldsToString: false } }) });

const server = (id, name, urlPath, cred, instructions, tools, webhookId) => {
  const trig = { name: 'MCP Server Trigger', type: '@n8n/n8n-nodes-langchain.mcpTrigger', typeVersion: 2, position: [0, 0], webhookId, credentials: cred,
    parameters: { path: urlPath, authentication: 'bearerAuth', instructions } };
  const nodes = [trig].concat(tools.map((t, i) => Object.assign(t, { position: [-220, 160 * (i + 1) - 80 * tools.length] })));
  const conns = {};
  for (const t of tools) conns[t.name] = { ai_tool: [[{ node: trig.name, type: 'ai_tool', index: 0 }]] };
  return wf(id, name, nodes, conns, true);
};

// ---- docs.search ------------------------------------------------------------------------------------------------------
const SEARCH = sub('case1mcpdsearch01', 'case 1 docs.search (sub-workflow of the docs MCP server)', () => [
  code('Query', `// the model's words go into a Drive query: cut, control characters out, and \\ and ' escaped, so they stay a string literal
const raw = String($input.first().json.query ?? '').replace(/[\\u0000-\\u001f\\u007f]+/g, ' ').trim().slice(0, ${MAX_QUERY});
if (!raw) return [{ json: { ok: false, error: 'search needs a non-empty query' } }];
const esc = raw.replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'");
return [{ json: { ok: true, query: raw, q: "'${FOLDER}' in parents and fullText contains '" + esc + "' and trashed = false" } }];`),
  iff('Valid?', '={{ $json.ok }}'),
  stop('Refuse', "={{ 'docs.search: ' + $json.error }}"),
  http('Folder files', `${BASE}/drive/v3/files`, { q: '={{ $json.q }}', fields: 'files(id,name,modifiedTime,webViewLink)', pageSize: String(MAX_HITS),
    supportsAllDrives: 'true' }),
  http('Decisions doc', `${BASE}/drive/v3/files/${DOC}`, { fields: 'id,name,modifiedTime,webViewLink,trashed', supportsAllDrives: 'true' }),
  http('Decisions text', `${BASE}/drive/v3/files/${DOC}/export`, { mimeType: 'text/plain' }, { options: { response: { response: { neverError: true, responseFormat: 'text', outputPropertyName: 'data' } } } }),
  code('Format', `// the folder's hits, then the decisions doc when every word of the query is in its name or text (Drive cannot filter by id)
const q = $('Query').first().json, folder = $('Folder files').first().json, doc = $('Decisions doc').first().json, text = String($input.first().json.data ?? '');
if (!Array.isArray(folder.files)) throw new Error('docs.search: Drive did not answer the search: ' + JSON.stringify(folder.error || folder).slice(0, 200));
const hits = folder.files.map(f => ({ id: f.id, name: f.name, modified: f.modifiedTime, webViewLink: f.webViewLink }));
const terms = q.query.toLowerCase().split(/\\s+/).filter(Boolean), hay = ((doc.name || '') + '\\n' + text).toLowerCase();
if (doc.id === '${DOC}' && !doc.trashed && terms.every(t => hay.includes(t)) && !hits.some(h => h.id === doc.id))
  hits.push({ id: doc.id, name: doc.name, modified: doc.modifiedTime, webViewLink: doc.webViewLink });
if (!hits.length) return [{ json: { matches: 0, query: q.query, note: 'no document in the documents folder or the decisions doc matches' } }];
return hits.slice(0, ${MAX_HITS}).map(h => ({ json: h }));`),
], [['In', 'Query'], ['Query', 'Valid?'], ['Valid?', 'Folder files', 0], ['Valid?', 'Refuse', 1], ['Folder files', 'Decisions doc'], ['Decisions doc', 'Decisions text'], ['Decisions text', 'Format']]);

// ---- docs.read --------------------------------------------------------------------------------------------------------
const READ = sub('case1mcpdread00001', 'case 1 docs.read (sub-workflow of the docs MCP server)', () => [
  code('Check id', `// a Drive id only: it goes into a URL path
const id = String($input.first().json.id ?? '').trim();
return [{ json: { ok: /^[A-Za-z0-9_-]{1,128}$/.test(id), id, error: 'read needs a document id as the search returned it' } }];`),
  iff('Id ok?', '={{ $json.ok }}'),
  stop('Refuse id', "={{ 'docs.read: ' + $json.error }}"),
  http('Meta', `=${BASE}/drive/v3/files/{{ $json.id }}`, { fields: 'id,name,parents,webViewLink,mimeType,modifiedTime,trashed', supportsAllDrives: 'true' }),
  code('Gate', `// the one rule that matters: a file is read only when it is in the documents folder, or is the decisions doc
const m = $input.first().json;
const refuse = why => [{ json: { ok: false, error: 'docs.read: ' + why } }];
if (!m.id) return refuse('no document with that id, or it cannot be read');
if (!(m.id === '${DOC}' || (Array.isArray(m.parents) && m.parents.includes('${FOLDER}')))) return refuse('refused: that document is not in the documents folder');
if (m.trashed) return refuse('that document is in the trash');
const doc = m.mimeType === 'application/vnd.google-apps.document';
if (!doc && m.mimeType !== 'text/plain' && m.mimeType !== 'text/markdown') return refuse('only Google Docs, .txt and .md files can be read (this is ' + m.mimeType + ')');
return [{ json: { ok: true, id: m.id, title: m.name, webViewLink: m.webViewLink, modified: m.modifiedTime,
  url: '${BASE}/drive/v3/files/' + m.id + (doc ? '/export' : ''), qs: doc ? { mimeType: 'text/plain' } : { alt: 'media' } } }];`),
  iff('Allowed?', '={{ $json.ok }}'),
  stop('Refuse', "={{ $json.error }}"),
  { name: 'Text', type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position: pos(), credentials: CRED.google, parameters: {
      method: 'GET', url: '={{ $json.url }}', authentication: 'predefinedCredentialType', nodeCredentialType: 'googleOAuth2Api',
      sendQuery: true, specifyQuery: 'json', jsonQuery: '={{ JSON.stringify($json.qs) }}',
      options: { response: { response: { neverError: false, responseFormat: 'text', outputPropertyName: 'data' } } } } },
  code('Answer', `const r = $input.first().json, g = $('Gate').first().json;  // a Drive error here fails the call: the HTTP node throws on non-2xx
const full = String(r.data ?? ''), cut = full.length > ${MAX_READ};
return [{ json: { title: g.title, webViewLink: g.webViewLink, id: g.id, modified: g.modified, truncated: cut,
  text: cut ? full.slice(0, ${MAX_READ}) + '\\n[cut: the document goes on for ' + (full.length - ${MAX_READ}) + ' more characters]' : full } }];`),
], [['In', 'Check id'], ['Check id', 'Id ok?'], ['Id ok?', 'Meta', 0], ['Id ok?', 'Refuse id', 1], ['Meta', 'Gate'], ['Gate', 'Allowed?'],
    ['Allowed?', 'Text', 0], ['Allowed?', 'Refuse', 1], ['Text', 'Answer']]);

// ---- tasks.list -------------------------------------------------------------------------------------------------------
const LISTFLOW = sub('case1mcptlist0001', 'case 1 tasks.list (sub-workflow of the tasks MCP server)', () => [
  http('Open tasks', `${BASE}/tasks/v1/lists/${LIST}/tasks`, { showCompleted: 'false', showHidden: 'false', maxResults: String(MAX_TASKS) }),
  code('Format', `const r = $input.first().json;
if (r.error || (r.items !== undefined && !Array.isArray(r.items))) throw new Error('tasks.list: Google Tasks did not answer: ' + JSON.stringify(r.error || r).slice(0, 200));
const items = r.items || [];
if (!items.length) return [{ json: { open: 0, note: 'no open tasks' } }];
return items.map(t => ({ json: { title: t.title || '(no title)', due: t.due ? String(t.due).slice(0, 10) : null,
  notes: t.notes ? (t.notes.length > ${MAX_NOTES} ? t.notes.slice(0, ${MAX_NOTES}) + '...' : t.notes) : null, ref: t.webViewLink || t.id, id: t.id } }));`),
], [['In', 'Open tasks'], ['Open tasks', 'Format']]);

// ---- the two servers --------------------------------------------------------------------------------------------------
const DOCS = [
  server('case1mcpdocs0001', 'case 1: docs read server (MCP)', PATHS.docs, CRED.docsToken,
    'Read-only access to the company documents: meeting notes in one folder and the decisions doc. search finds documents by words; read returns one document\'s text. Every document has a link: quote it as it is given.',
    [tool('search', 'Search the company documents (meeting notes and the decisions doc) for words. Returns up to ' + MAX_HITS + ' documents, each with its id, name, modified time and link (webViewLink). Use the id with read.', SEARCH.id, 'query', 'The words to look for, for example a topic, a name or a decision'),
     tool('read', 'Read one document by the id that search returned. Returns its title, link (webViewLink) and text (cut at ' + MAX_READ + ' characters). Refuses any document outside the meeting notes folder and the decisions doc.', READ.id, 'id', 'The document id exactly as search returned it')],
    'a1c70d51-2b3e-4f86-9d04-6e1b7c9a0f11'),
  SEARCH, READ];
const TASKS = [
  server('case1mcptasks001', 'case 1: tasks read server (MCP)', PATHS.tasks, CRED.tasksToken,
    'Read-only access to the open follow-up tasks. list returns every open task: title, due date, notes and a link or id.',
    [tool('list', 'List the open follow-up tasks: title, due date (YYYY-MM-DD), notes (cut) and ref (a link to the task when Google gives one, else its id). Takes no arguments.', LISTFLOW.id, null, null)],
    'b2d81e62-3c4f-4097-8e15-7f2c8dab1022'),
  LISTFLOW];

for (const [f, w] of [['case1-mcp-docs.json', DOCS], ['case1-mcp-tasks.json', TASKS]]) {
  fs.writeFileSync(path.join(OUT, f), JSON.stringify(w, null, 1) + '\n');
  console.log('wrote', f, w.length, "workflows,", w.reduce((n, o) => n + o.nodes.length, 0), 'nodes, base', BASE);
}
