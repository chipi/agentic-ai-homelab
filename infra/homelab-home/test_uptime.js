#!/usr/bin/env node
// Deterministic test of the home page's uptime() section and cloudflare() bar.
// No deps: extracts both functions from gen.sh, runs them against a stub DOM and fixture
// VictoriaMetrics series, asserts the rendered HTML.
// Run: node infra/homelab-home/test_uptime.js   (exit 0 = PASS)
'use strict';
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, 'gen.sh'), 'utf8');
const grab = (name) => {
  const m = src.match(new RegExp('async function ' + name + '\\(\\)\\{[\\s\\S]*?\\n\\}'));
  if (!m) { console.error('FAIL: ' + name + '() not found in gen.sh'); process.exit(1); }
  return m[0];
};

const els = {};
const document = { getElementById: (id) => (els[id] = els[id] || { innerHTML: '', className: '' }) };
let fixture = {};
let queries = [];
const q = async (query) => {
  queries.push(query);
  for (const [k, v] of Object.entries(fixture)) if (query.includes(k)) return typeof v === 'function' ? v(query) : v;
  return [];
};
const g1 = async (m) => { const r = await q(m); return r.length ? r[0].value : null; };
const fns = new Function('document', 'q', 'g1', grab('cloudflare') + '\n' + grab('uptime') + '\nreturn {cloudflare, uptime};')(document, q, g1);

let failed = 0;
const check = (name, cond) => { if (!cond) { failed++; console.error('FAIL: ' + name); } else console.log('ok   ' + name); };
const s = (host, v) => ({ metric: { host }, value: [0, String(v)] });
const one = (v) => [{ metric: {}, value: [0, String(v)] }];

function base() {
  return {
    'avg_over_time(': (query) => query.includes('[24h:1m]') ? [s('a.example', 1), s('b.example', 0.995)]
      : query.includes('[7d:1m]') ? [s('a.example', 1), s('b.example', 0.9999)] : [s('a.example', 0.98), s('b.example', 1)],
    'last_over_time(probe_success': [s('a.example', 1), s('b.example', 1)],
    'probe_duration_seconds': [s('a.example', 0.123), s('b.example', 0.4)],
    'window="24h"': [s('b.example', 7)],
    'window="1h"': one(3),
    'cloudflare_security_events': one(42),
    'last_over_time(mini_vm_egress_ok': one(1),
  };
}

(async () => {
  fixture = base();
  await fns.uptime();
  check('all up -> 2/2', els.up_now.innerHTML.includes('2/2') && els.up_now.innerHTML.includes('all answering'));
  check('24h below 99.9% on one host -> amber dot', els.up_agg.className === 'dot mid');
  check('table shows 99.50% for b 24h, amber', /b\.example[\s\S]*?color:#d29922">99\.50%/.test(els.uptbl.innerHTML));
  check('30d 98% for a is red', /a\.example[\s\S]*?color:#f85149">98\.00%/.test(els.uptbl.innerHTML));
  check('edge 5xx per host from Cloudflare (b=7, a=0)', /b\.example(?:(?!<\/tr>)[\s\S])*?<td class=u>7<\/td>/.test(els.uptbl.innerHTML)
    && /a\.example(?:(?!<\/tr>)[\s\S])*?<td class=u>0<\/td>/.test(els.uptbl.innerHTML));
  check('response time in ms', els.uptbl.innerHTML.includes('123 ms'));
  check('lowest host named in 24h card', els.up_24h.innerHTML.includes('lowest: b.example 99.50%'));
  check('edge 1h and security cards', els.up_edge.innerHTML.includes('>3<') && els.up_sec.innerHTML.includes('>42<'));

  queries = [];
  fixture = base();
  fixture['last_over_time(probe_success'] = [s('a.example', 1), s('b.example', 0)];
  await fns.uptime();
  check('long windows cached between 30s refreshes', !queries.some((x) => x.includes('[30d:1m]')));
  check('one down -> red dot, named', els.up_agg.className === 'dot down' && els.up_now.innerHTML.includes('down: b.example'));

  fixture = base();
  fixture['last_over_time(mini_vm_egress_ok'] = one(0);
  fixture['last_over_time(probe_success'] = [s('a.example', 0), s('b.example', 0)];
  await fns.uptime();
  check('mini offline -> grey, not down', els.up_agg.className === 'dot stale' && els.up_now.innerHTML.includes('mini offline'));

  fixture = {};
  await fns.uptime();
  check('no data -> grey and a no-data row', els.up_agg.className === 'dot stale' && els.uptbl.innerHTML.includes('no probe data'));

  fixture = {};
  await fns.cloudflare();
  check('nothing ours -> no Cloudflare bar', els.cfbar.innerHTML === '');

  fixture = {
    'cloudflare_status_incident': [{ metric: { name: 'CDN errors <img src=x>', components: 'CDN/Cache', impact: 'major', status: 'investigating', link: 'https://stspg.io/x' }, value: [0, '1'] }],
    'cloudflare_status_component': [{ metric: { kind: 'pop', name: 'Paris, France - (CDG)', status: 'partial_outage' }, value: [0, '1'] }],
    'cloudflare_status_maintenance': [{ metric: { name: 'FRA', components: 'Frankfurt, Germany - (FRA)', status: 'scheduled', start: '2026-10-30T09:00:00.000Z', end: '2026-10-30T14:00:00.000Z', link: 'https://stspg.io/m' }, value: [0, '1'] }],
  };
  await fns.cloudflare();
  const parts = els.cfbar.innerHTML.split('</a>');
  check('incident first, red', parts[0].includes('abar crit') && parts[0].includes('CDN/Cache'));
  check('incident name escaped', !els.cfbar.innerHTML.includes('<img') && els.cfbar.innerHTML.includes('&lt;img'));
  check('PoP component amber', parts[1].includes('abar warn') && parts[1].includes('partial outage'));
  check('scheduled maintenance muted with start', parts[2].includes('abar plumb') && parts[2].includes('starts 2026-10-30 09:00Z'));

  if (failed) { console.error(failed + ' FAILED'); process.exit(1); }
  console.log('PASS');
})();
