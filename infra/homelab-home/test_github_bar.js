#!/usr/bin/env node
// Deterministic test of the home page's github() status bar (infra/github-status).
// No deps: extracts the function from gen.sh, runs it against a stub DOM and fixture
// github_status_active / github_status_component series, asserts the rendered HTML.
// Run: node infra/homelab-home/test_github_bar.js   (exit 0 = PASS)
'use strict';
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, 'gen.sh'), 'utf8');
const m = src.match(/async function github\(\)\{[\s\S]*?\n\}/);
if (!m) { console.error('FAIL: github() not found in gen.sh'); process.exit(1); }

const el = { innerHTML: 'stale' };
const document = { getElementById: (id) => (id === 'ghbar' ? el : null) };
let act = [], comp = [];
const q = async (expr) => (expr.includes('github_status_active') ? act : expr.includes('github_status_component') ? comp : []);
const github = new Function('document', 'q', m[0] + '\nreturn github;')(document, q);

let failed = 0;
const check = (name, cond) => { if (!cond) { failed++; console.error('FAIL: ' + name); } else console.log('ok   ' + name); };
const a = (labels) => ({ metric: Object.assign({ kind: 'incident', relevance: 'direct', phase: 'ongoing', name: 'Incident with Actions',
  impact: 'minor', status: 'investigating', components: 'Actions', start: '2026-11-04T16:05:31.580Z', end: '',
  link: 'https://stspg.io/a' }, labels), value: [0, '1'] });
const c = (name, status) => ({ metric: { name, status }, value: [0, '1'] });

(async () => {
  act = []; comp = [];
  await github();
  check('no series -> no bar', el.innerHTML === '');

  act = [a({ kind: 'maintenance', phase: 'upcoming', name: 'Packages migration', components: 'Packages', start: '2026-11-07T02:00:00.000Z', end: '2026-11-07T04:00:00.000Z', link: 'https://stspg.io/d' }),
         a({ relevance: 'other', name: 'Copilot slow', components: 'Copilot' }),
         a({ kind: 'maintenance', phase: 'ongoing', name: 'Git DB upgrade', components: 'Git Operations', link: 'https://stspg.io/c' }),
         a({})];
  comp = [c('Actions', 'degraded_performance'), c('Webhooks', 'partial_outage')];
  await github();
  const parts = el.innerHTML.split('</a>').filter(Boolean);
  check('direct incident first, red', parts[0].includes('abar crit') && parts[0].includes('Incident with Actions'));
  check('maintenance in progress on ours: amber, second', parts[1].includes('abar warn') && parts[1].includes('in progress'));
  check('upcoming maintenance: muted, with its start and end', parts[2].includes('abar plumb') && parts[2].includes('starts 2026-11-07 02:00Z') && parts[2].includes('until 2026-11-07 04:00Z'));
  check('an incident on what we do not use: muted, said so', parts[3].includes('abar plumb') && parts[3].includes('not on what we use'));
  check('a degraded component already named by an incident is not repeated', !parts.slice(4).some(p => p.includes('>Actions<')));
  check('a degraded component of ours with no incident: amber', parts.slice(4).some(p => p.includes('abar warn') && p.includes('Webhooks') && p.includes('partial outage')));
  check('incidents link to their page', el.innerHTML.includes('href="https://stspg.io/a"'));

  act = [a({ name: '<img src=x onerror=alert(1)>', link: 'https://stspg.io/x"><script>' })]; comp = [];
  await github();
  check('escapes the name and the link', !el.innerHTML.includes('<img') && !el.innerHTML.includes('"><script>'));

  console.log(failed ? 'TEST_GITHUB_BAR FAIL (' + failed + ')' : 'TEST_GITHUB_BAR PASS');
  process.exit(failed ? 1 : 0);
})();
