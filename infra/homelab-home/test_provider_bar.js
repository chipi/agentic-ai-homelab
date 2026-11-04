#!/usr/bin/env node
// Deterministic test of the home page's providers() status bar (infra/provider-status: GitHub,
// OpenRouter). No deps: extracts the function from gen.sh, runs it against a stub DOM and fixture
// provider_status_active / provider_status_component series, asserts the rendered HTML.
// Run: node infra/homelab-home/test_provider_bar.js   (exit 0 = PASS)
'use strict';
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, 'gen.sh'), 'utf8');
const m = src.match(/async function providers\(\)\{[\s\S]*?\n\}/);
if (!m) { console.error('FAIL: providers() not found in gen.sh'); process.exit(1); }

const el = { innerHTML: 'stale' };
const document = { getElementById: (id) => (id === 'provbar' ? el : null) };
let act = [], comp = [];
const q = async (expr) => (expr.includes('provider_status_active') ? act : expr.includes('provider_status_component') ? comp : []);
const providers = new Function('document', 'q', m[0] + '\nreturn providers;')(document, q);

let failed = 0;
const check = (name, cond) => { if (!cond) { failed++; console.error('FAIL: ' + name); } else console.log('ok   ' + name); };
const a = (labels) => ({ metric: Object.assign({ provider: 'github', kind: 'incident', relevance: 'direct', phase: 'ongoing',
  name: 'Incident with Actions', impact: 'minor', status: 'investigating', components: 'Actions', start: '2026-11-04T16:05:31.580Z',
  end: '', link: 'https://stspg.io/a' }, labels), value: [0, '1'] });
const c = (provider, name, status) => ({ metric: { provider, name, status }, value: [0, '1'] });

(async () => {
  act = []; comp = [];
  await providers();
  check('no series -> no bar', el.innerHTML === '');

  act = [a({ kind: 'maintenance', phase: 'upcoming', name: 'Packages migration', components: 'Packages', start: '2026-11-07T02:00:00.000Z', end: '2026-11-07T04:00:00.000Z', link: 'https://stspg.io/d' }),
         a({ relevance: 'other', name: 'Copilot slow', components: 'Copilot' }),
         a({ kind: 'maintenance', phase: 'ongoing', name: 'Git DB upgrade', components: 'Git Operations', link: 'https://stspg.io/c' }),
         a({ provider: 'openrouter', name: 'Elevated API errors', components: '', impact: '', status: 'Identified', start: '', link: 'https://status.openrouter.ai/i2' }),
         a({ provider: 'openrouter', kind: 'maintenance', phase: 'upcoming', relevance: 'other', name: 'Dashboard database', components: '', start: '', link: 'https://status.openrouter.ai/m2' }),
         a({})];
  comp = [c('github', 'Actions', 'degraded_performance'), c('github', 'Webhooks', 'partial_outage')];
  await providers();
  const parts = el.innerHTML.split('</a>').filter(Boolean);
  check('incidents on what we use first, red, each named by its provider',
    parts[0].includes('abar crit') && parts[1].includes('abar crit') && el.innerHTML.includes('>GitHub &middot; incident') && el.innerHTML.includes('>OpenRouter &middot; incident'));
  check('an OpenRouter incident has no components and no "since" when the feed gives none',
    parts.some(p => p.includes('Elevated API errors') && p.includes('(Identified)') && !p.includes('since')));
  check('maintenance in progress on ours: amber', parts.some(p => p.includes('Git DB upgrade') && p.includes('abar warn') && p.includes('in progress')));
  check('upcoming maintenance with a start: muted, start and end', parts.some(p => p.includes('Packages migration') && p.includes('abar plumb') && p.includes('starts 2026-11-07 02:00Z') && p.includes('until 2026-11-07 04:00Z')));
  check('announced maintenance without a start says announced', parts.some(p => p.includes('Dashboard database') && p.includes('announced') && p.includes('not on what we use')));
  check('a degraded component already named by an incident is not repeated', !parts.some(p => p.includes('a service we use') && p.includes('>Actions<')));
  check('a degraded component of ours with no incident: amber', parts.some(p => p.includes('abar warn') && p.includes('Webhooks') && p.includes('partial outage')));
  check('each bar carries its provider for the Notices count', (el.innerHTML.match(/data-provider="openrouter"/g) || []).length === 2);

  act = [a({ name: '<img src=x onerror=alert(1)>', link: 'https://stspg.io/x"><script>' })]; comp = [];
  await providers();
  check('escapes the name and the link', !el.innerHTML.includes('<img') && !el.innerHTML.includes('"><script>'));

  console.log(failed ? 'TEST_PROVIDER_BAR FAIL (' + failed + ')' : 'TEST_PROVIDER_BAR PASS');
  process.exit(failed ? 1 : 0);
})();
