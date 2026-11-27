#!/usr/bin/env node
// hub-engines.js: the Docker disk tables from fixture VictoriaMetrics vectors. Run: node test_engines.js
'use strict';
const E = require('./hub-engines.js');
let fail = 0;
const check = (name, ok, got) => { console.log((ok ? 'ok   ' : 'FAIL ') + name.replace(/##\[/g, '## [')); if (!ok) { fail++; console.log('     got:', JSON.stringify(got)); } };
const NOW = 1795780000;
const v = (metric, val) => ({ metric, value: [NOW, String(val)] });
const x3 = (t, b) => v({ box: 'x3', engine: 'dev', type: t }, b);
const vec = {
  bytes: [x3('images', 156.9e9), x3('build_cache', 219.7e9), x3('volumes', 15.62e9), x3('containers', 21.06e9)],
  reclaim: [x3('images', 94.55e9), x3('build_cache', 42.66e9), x3('volumes', 14.01e9), x3('containers', 21.01e9)],
  count: [x3('images', 274)],
  measured: [v({ box: 'x3', engine: 'dev' }, NOW - 1800)],
  pruned: [v({ job: 'docker-prune' }, NOW - 86400), v({ job: 'dev-engine-prune', box: 'x3', engine: 'dev' }, NOW - 3600)],
  freed: [v({ box: 'x3', engine: 'dev' }, 120.31e9)],
};
const m = E.model(vec, 'x3', NOW);
check('model: one engine, totals of the four types', m.length === 1 && Math.round(m[0].total / 1e9) === 413 && Math.round(m[0].reclaim / 1e9) === 172, m);
check('model: the x3 dev engine is pruned by dev-engine-prune, an hour ago, not late', m[0].prune && m[0].prune.job === 'dev-engine-prune' && m[0].prune.age === 3600 && !m[0].prune.late, m[0].prune);
const r = E.rows(m);
check('rows: the engine line, measured 30 min ago', /<b>dev<\/b> engine &middot; 413 GB <span class=muted>measured 30 min ago/.test(r), r);
check('rows: build cache size and reclaimable', /Build cache<\/td><td>220 GB<\/td><td class=u>42.7 GB reclaimable/.test(r), r);
check('rows: the prune line with what it freed', /Prune \(dev-engine-prune\): 1 h ago, freed 120 GB/.test(r), r);
check('summary: total, reclaimable, no lateness', E.summary(m) === 'Docker disk &middot; <b>413 GB</b> &middot; 172 GB reclaimable', E.summary(m));

// the DGX: no prune job; a reading 5 h old is marked old
const dg = E.model({ bytes: [v({ box: 'dgx', engine: 'default', type: 'images' }, 145.6e9)], measured: [v({ box: 'dgx', engine: 'default' }, NOW - 5 * 3600)] }, 'dgx', NOW);
const dr = E.rows(dg);
check('dgx: no prune job for its engine', dg[0].prune === null && /No prune job for this engine/.test(dr), dr);
check('dgx: a 5 h old reading is marked old', /measured 5 h ago<\/span> <span style=color:#d29922>\(old\)/.test(dr), dr);

// the mini: prod pruned 9 days ago is late, and the summary says so; dev has no prune job
const mi = E.model({ bytes: [v({ box: 'mini', engine: 'prod', type: 'images' }, 25.8e9), v({ box: 'mini', engine: 'dev', type: 'images' }, 3e9)], pruned: [v({ job: 'docker-prune' }, NOW - 9 * 86400)] }, 'mini', NOW);
check('mini: two engines, dev first', mi.map(e => e.engine).join() === 'dev,prod', mi);
check('mini: prod pruned 9 days ago is late', mi[1].prune.late && /9 days ago, late/.test(E.rows(mi)), E.rows(mi));
check('mini: the summary flags the late prune', /prune late/.test(E.summary(mi)), E.summary(mi));
check('a prune job with no run recorded says so', /no run recorded/.test(E.rows(E.model({ bytes: [x3('images', 1e9)] }, 'x3', NOW))));
check('no data at all', /no data/.test(E.rows([])) && /no data/.test(E.summary([])));
check('names are escaped', /&lt;x&gt;/.test(E.rows(E.model({ bytes: [v({ box: 'b', engine: '<x>', type: 'images' }, 1)] }, 'b', NOW))));
console.log(fail ? 'TEST_ENGINES FAIL (' + fail + ')' : 'TEST_ENGINES PASS');
process.exit(fail ? 1 : 0);
