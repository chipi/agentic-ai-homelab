#!/usr/bin/env node
// Deterministic test of the home page's hetzner() bulletin bar (infra/hetzner-status).
// No deps: extracts the function from gen.sh, runs it against a stub DOM and fixture
// hetzner_status_active series, asserts the rendered HTML.
// Run: node infra/homelab-home/test_hetzner_bar.js   (exit 0 = PASS)
'use strict';
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, 'gen.sh'), 'utf8');
const m = src.match(/async function hetzner\(\)\{[\s\S]*?\n\}/);
if (!m) { console.error('FAIL: hetzner() not found in gen.sh'); process.exit(1); }

const el = { innerHTML: 'stale' };
const document = { getElementById: (id) => (id === 'hetznerbar' ? el : null) };
let rows = [];
const q = async () => rows;
const hetzner = new Function('document', 'q', m[0] + '\nreturn hetzner;')(document, q);

let failed = 0;
const check = (name, cond) => { if (!cond) { failed++; console.error('FAIL: ' + name); } else console.log('ok   ' + name); };
const s = (labels) => ({ metric: Object.assign({ relevance: 'direct', phase: 'upcoming', kind: 'maintenance',
  category: 'NBG1-DC3', title: 'UPS work', start: '2026-11-02T08:00:00+00:00', end: '',
  link: 'https://status.hetzner.com/incident/x' }, labels), value: [0, '1'] });

(async () => {
  rows = [];
  await hetzner();
  check('no series -> no bar', el.innerHTML === '');

  rows = [s({ relevance: 'service', phase: 'ongoing', category: 'Network', title: 'Core routers' }),
          s({ relevance: 'nearby', category: 'FSN1-DC22', title: 'UPS FSN1' }),
          s({})];
  await hetzner();
  const html = el.innerHTML;
  const iDirect = html.indexOf('NBG1-DC3'), iNearby = html.indexOf('FSN1-DC22'), iService = html.indexOf('Network');
  check('direct before nearby before service', iDirect >= 0 && iDirect < iNearby && iNearby < iService);
  check('direct is red (crit)', /class="abar crit"[^>]*>[^]*?NBG1-DC3/.test(html.split('</a>')[0]));
  check('nearby is amber (warn)', html.split('</a>')[1].includes('abar warn'));
  check('service is muted (plumb)', html.split('</a>')[2].includes('abar plumb'));
  check('upcoming shows its start', html.includes('starts 2026-11-02 08:00Z'));
  check('ongoing service says ongoing', html.split('</a>')[2].includes('ongoing'));
  check('links to the bulletin', html.includes('href="https://status.hetzner.com/incident/x"'));

  rows = [s({ title: '<img src=x onerror=alert(1)>', link: 'https://status.hetzner.com/x"><script>' })];
  await hetzner();
  check('title is escaped', !el.innerHTML.includes('<img') && el.innerHTML.includes('&lt;img'));
  check('link is escaped', !el.innerHTML.includes('"><script>'));

  if (failed) { console.error(failed + ' FAILED'); process.exit(1); }
  console.log('PASS');
})();
