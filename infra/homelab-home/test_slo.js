#!/usr/bin/env node
// Deterministic test of hub-slo.js (service levels, RFC-0009): ratio, error budget, state, the daily
// line, a query with no data, the egress gate, the catalogue file, and the HTML the page draws from
// slo.json. Fixture VictoriaMetrics answers, no page, no network. Run: node infra/homelab-home/test_slo.js (exit 0 = PASS)
'use strict';
const fs = require('fs');
const path = require('path');
const SLO = require('./hub-slo.js');

const DAY = 86400, NOW = 1788047143;
const vec = v => [{ metric: {}, value: [NOW, String(v)] }];
const range = (vals, end = NOW) => [{ metric: {}, values: vals.map((v, i) => [end - (vals.length - 1 - i) * DAY, String(v)]) }];
// fixtures: [needle in the expanded query, answer]; an answer is an array, or a function of the query
const src = (fx, qr) => ({
  now: NOW,
  q: async e => { for (const [n, r] of fx) if (e.includes(n)) { if (r instanceof Error) throw r; return typeof r === 'function' ? r(e) : r; } return []; },
  qr: qr || (async (e, start, end) => { for (const [n, r] of fx) if (e.includes(n.split('[')[0])) { if (r instanceof Error) throw r; return range(Array(28).fill(0.999), end); } return []; }),
});
const E = (name, objective, extra) => Object.assign({ id: name.replace(/_/g, '-'), service: name, group: 'G', sli: 'availability', good_ratio: 'avg_over_time(' + name + '[window])', objective, link: '#x' }, extra);

let failed = 0;
const check = (name, cond, got) => { if (cond) console.log('ok   ' + name); else { failed++; console.error('FAIL ' + name + (got !== undefined ? ' (got ' + JSON.stringify(got) + ')' : '')); } };
const near = (a, b, eps = 1e-6) => a != null && Math.abs(a - b) < eps;

(async () => {
  // judge
  let j = SLO.judge(0.9993, 0.995);
  check('judge: well above the target is meeting, budget 86 % left', j.state === 'meeting' && near(j.left, 0.86), j);
  j = SLO.judge(0.996, 0.995);
  check('judge: budget 20 % left is at risk', j.state === 'at risk' && near(j.left, 0.2), j);
  j = SLO.judge(0.625, 0.5);
  check('judge: exactly 25 % left is meeting', j.state === 'meeting' && j.left === 0.25, j);
  j = SLO.judge(0.995, 0.995);
  check('judge: exactly on the target is at risk, not breached', j.state === 'at risk' && j.left === 0, j);
  j = SLO.judge(0.9703, 0.995);
  check('judge: under the target is breached, the plan\'s -494 %', j.state === 'breached' && Math.round(j.left * 100) === -494, j);
  j = SLO.judge(null, 0.995);
  check('judge: no ratio is stale, no budget', j.state === 'stale' && j.left === null, j);

  // a full run over fixtures: meeting, at risk, breached, no data, a failing query
  const cat = [E('m_meeting', 0.995), E('m_risk', 0.995), E('m_breached', 0.995), E('m_nodata', 0.995), E('m_nan', 0.995), E('m_boom', 0.995)];
  const fx = [
    ['mini_vm_egress_ok', vec(1)],
    ['m_meeting[28d', vec(0.9993)], ['m_meeting[7d', vec(0.9995)],
    ['m_risk[28d', vec(0.996)], ['m_risk[7d', vec(0.99)],
    ['m_breached[28d', vec(0.9703)], ['m_breached[7d', vec(0.97)],
    ['m_nan[28d', vec('NaN')],
    ['m_boom', new Error('VictoriaMetrics -> HTTP 503')],
  ];
  const out = await SLO.all(src(fx), cat);
  const by = Object.fromEntries(out.rows.map(r => [r.service, r]));
  check('all: meeting, at risk and breached from the same catalogue', by.m_meeting.state === 'meeting' && by.m_risk.state === 'at risk' && by.m_breached.state === 'breached',
    out.rows.map(r => r.service + ':' + r.state));
  check('all: ratio over 28 d and 7 d, 1 d from the last daily value', by.m_meeting.ratio['28d'] === 0.9993 && by.m_meeting.ratio['7d'] === 0.9995 && by.m_meeting.ratio['1d'] === 0.999, by.m_meeting.ratio);
  check('all: budget is 0.5 % of 28 d = 3 h 22 min; 86 % of it left', by.m_meeting.budgetSeconds === 12096 && SLO.dur(by.m_meeting.budgetSeconds) === '3 h 22 min'
    && Math.abs(by.m_meeting.leftSeconds - 10403) <= 1, by.m_meeting);
  check('all: a breached row shows the time it is over by', by.m_breached.leftSeconds < 0 && /^over by /.test(SLO.rowHtml(by.m_breached).match(/slo-left>([^<]*)</)[1]), by.m_breached.leftSeconds);
  check('all: a query with no data is stale, ratio null, never 100 %', by.m_nodata.state === 'stale' && by.m_nodata.ratio['28d'] === null && by.m_nodata.left === null && by.m_nodata.daily.every(x => x === null), by.m_nodata);
  check('all: NaN (0 / 0) is no data, not a number', by.m_nan.state === 'stale' && by.m_nan.ratio['28d'] === null, by.m_nan);
  check('all: a failing query leaves its row stale with the reason, the others stay', by.m_boom.state === 'stale' && by.m_boom.errors.length === 3 && /503/.test(by.m_boom.errors[0]) && by.m_meeting.state === 'meeting', by.m_boom.errors);
  check('all: summary counts every state', JSON.stringify(out.summary) === JSON.stringify({ total: 6, meeting: 1, atRisk: 1, breached: 1, stale: 3 }), out.summary);
  check('all: takenAt is the clock, window 28 days', out.takenAt === new Date(NOW * 1000).toISOString() && out.windowDays === 28, out.takenAt);

  // the daily line: 28 values, aligned to the end, a missing day stays a gap
  const late = await SLO.evaluate(src([['m_late[28d', vec(0.999)]], async (e, start, end) => range([0.9, 0.95, 1], end)), E('m_late', 0.995));
  check('daily: 28 values, the 3 returned sit at the end, the rest are gaps', late.daily.length === 28 && late.daily.slice(0, 25).every(x => x === null) && late.daily[25] === 0.9 && late.daily[27] === 1, late.daily);
  check('daily: a failing range query is a reported error, the ratios stay', (await SLO.evaluate({ now: NOW, q: async () => vec(0.999), qr: async () => { throw new Error('range boom'); } }, E('m_x', 0.995))).errors[0] === 'daily: range boom');
  const clamped = await SLO.evaluate(src([['m_over[28d', vec(1.0000002)]]), E('m_over', 0.995));
  check('ratio: counter-reset arithmetic above 1 is held at 1', clamped.ratio['28d'] === 1, clamped.ratio);

  // the egress gate
  const GATE = SLO.EGRESS;
  const probe = E('p', 0.995, { good_ratio: 'avg_over_time((max by (host) (probe_success{job="site-probe",run_id="",host="h"}) and on () (' + GATE + '))[window:1m])' });
  check('gate: a probe query with the gate passes the catalogue check', SLO.lint([probe]).length === 0, SLO.lint([probe]));
  const bare = E('p', 0.995, { good_ratio: 'avg_over_time(probe_success{job="site-probe",host="h"}[window])' });
  check('gate: a probe query without it is refused', SLO.lint([bare]).some(x => /egress gate/.test(x)), SLO.lint([bare]));
  const lat = E('p', 0.99, { sli: 'latency', good_ratio: 'avg_over_time((probe_duration_seconds{host="h"} < bool 2)[window:1m])' });
  check('gate: so is a probe latency query without it', SLO.lint([lat]).some(x => /egress gate/.test(x)));
  let refused = null; try { await SLO.all(src([]), [bare]); } catch (e) { refused = e.message; }
  check('gate: all() will not run an ungated probe catalogue', /egress gate/.test(refused || ''), refused);
  const hubStatus = fs.readFileSync(path.join(__dirname, 'hub-status.js'), 'utf8');
  check('gate: the same expression the Sites tab uses (hub-status.js PROBE_OK)', hubStatus.includes(GATE), GATE);
  check('gate: reported on the snapshot (mini online / offline / unknown)', (await SLO.all(src([['mini_vm_egress_ok', vec(1)]]), [E('a', 0.99)])).egressOk === true
    && (await SLO.all(src([['mini_vm_egress_ok', vec(0)]]), [E('a', 0.99)])).egressOk === false && (await SLO.all(src([]), [E('a', 0.99)])).egressOk === null);

  // the catalogue file
  const file = JSON.parse(fs.readFileSync(path.join(__dirname, 'slo-catalogue.json'), 'utf8'));
  check('catalogue: slo-catalogue.json passes the check (fields, objective, [window], gate, unique)', SLO.lint(file).length === 0, SLO.lint(file));
  check('catalogue: three groups, apps only cl / orrery / evals / web', new Set(file.map(e => e.group)).size === 3 && file.every(e => !e.app || ['cl', 'orrery', 'evals', 'web'].includes(e.app)), [...new Set(file.map(e => e.group))]);
  check('catalogue: links are a hub anchor or the tailnet Grafana', file.every(e => /^#|^https:\/\/grafana\.tail6d0ed4\.ts\.net\//.test(e.link)), file.filter(e => !/^#|^https:\/\/grafana\.tail6d0ed4\.ts\.net\//.test(e.link)).map(e => e.link));
  const apps = [...new Set(file.map(e => e.app).filter(Boolean))].sort();
  check('catalogue: every Projects page has rows', apps.join() === 'cl,evals,orrery,web', apps);
  check('lint: catches a missing placeholder, a bad objective and a duplicate', SLO.lint([E('d', 1.2, { good_ratio: 'up' }), E('d', 0.9)]).length === 3, SLO.lint([E('d', 1.2, { good_ratio: 'up' }), E('d', 0.9)]));
  check('lint: every row needs an id of lowercase letters, digits and dashes, unique in the catalogue', SLO.lint([E('a', 0.9, { id: undefined })]).length === 1 && SLO.lint([E('a', 0.9, { id: 'A b' })]).length === 1
    && SLO.lint([E('a', 0.9), E('b', 0.9, { id: 'a' })]).join().includes('listed twice') && SLO.lint([E('a', 0.9), E('b', 0.9)]).length === 0);
  check('catalogue: every row has an id, none shared', file.every(e => /^[a-z0-9][a-z0-9-]*$/.test(e.id)) && new Set(file.map(e => e.id)).size === file.length);
  check('evaluate: the row carries the catalogue id into slo.json', clamped.id === 'm-over');
  check('lint: an empty catalogue is refused', SLO.lint([]).length === 1 && SLO.lint(null).length === 1);

  // view: what the page decides from slo.json and the clock
  const mk = (service, group, state, left, extra) => Object.assign({ service, group, sli: 'availability', objective: 0.995, state, left, leftSeconds: left == null ? null : Math.round(left * 12096), budgetSeconds: 12096,
    ratio: { '28d': left == null ? null : 0.995 + left * 0.005, '7d': null, '1d': null }, daily: Array(28).fill(0.999), link: '#x', app: null }, extra || {});
  const doc = { takenAt: new Date(NOW * 1000).toISOString(), rows: [mk('ok', 'Sites', 'meeting', 0.9), mk('bad', 'Sites', 'breached', -4.9, { app: 'cl' }), mk('risk', 'Sites', 'at risk', 0.1, { app: 'cl' }), mk('none', 'Sites', 'stale', null), mk('p', 'Platform', 'meeting', 0.5)] };
  let v = SLO.view(doc, NOW + 60);
  check('view: fresh numbers keep their states; rows sort by budget left, no data last', v.groups[0].rows.map(r => r.service).join() === 'bad,risk,ok,none' && !v.stale && v.counts.breached === 1, v.groups[0].rows.map(r => r.service));
  check('view: groups keep the catalogue order', v.groups.map(g => g.group).join() === 'Sites,Platform');
  v = SLO.view(doc, NOW + 16 * 60);
  check('view: numbers older than 15 minutes turn every row stale (grey, never green)', v.stale && v.rows.every(r => r.state === 'stale') && v.counts.stale === 5 && v.counts.meeting === 0, v.counts);
  check('view: exactly 15 minutes old is still fresh', !SLO.view(doc, NOW + 900).stale);
  v = SLO.view(null, NOW);
  check('view: a missing slo.json is not ok and has no rows', !v.ok && v.stale && v.rows.length === 0);
  check('view: a document without rows is not ok', !SLO.view({ takenAt: doc.takenAt }, NOW).ok && !SLO.view({ rows: [], takenAt: 'nope' }, NOW).ok);

  // HTML
  const fresh = SLO.view(doc, NOW + 30), old = SLO.view(doc, NOW + 3600);
  let h = SLO.levelsHtml(fresh);
  check('tab: groups as headings, breached row first in its group', h.indexOf('>Sites<') > 0 && h.indexOf('>bad<') < h.indexOf('>risk<') && h.indexOf('>risk<') < h.indexOf('>ok<'), h.slice(0, 300));
  check('tab: summary counts and dots by state', /1 below target &middot; 1 at risk &middot; 2 meeting &middot; 1 stale/.test(h) && /dot down/.test(h) && /dot mid/.test(h) && /dot up/.test(h));
  check('tab: the three numbers and the budget in time', /97\.[0-9]{2}&nbsp;%/.test(h) && /99\.50&nbsp;%/.test(h) && /over by 16 h/.test(h) && /left of 3 h 22 min/.test(h), h.match(/slo-left>[^<]*</g));
  h = SLO.levelsHtml(old);
  check('tab: stale numbers render grey with a notice, no green dot, no red dot', /dot stale/.test(h) && !/dot up|dot down|dot mid/.test(h) && /60 minutes old/.test(h) && /spark grey/.test(h));
  check('tab: a missing slo.json says so, shows nothing green', /missing or unreadable/.test(SLO.levelsHtml(SLO.view(null, NOW))) && !/dot up/.test(SLO.levelsHtml(SLO.view(null, NOW))));
  check('tab: only 12 of 28 days of data is said so', /12 of 28 days have data/.test(SLO.rowHtml(mk('young', 'G', 'meeting', 0.9, { daily: [].concat(Array(16).fill(null), Array(12).fill(0.999)) }))) && !/days have data/.test(SLO.rowHtml(mk('full', 'G', 'meeting', 0.9))));
  check('tab: names are escaped', /&lt;b&gt;x&lt;\/b&gt;/.test(SLO.rowHtml(mk('<b>x</b>', 'G', 'meeting', 0.9))) && !/<b>x<\/b>/.test(SLO.rowHtml(mk('<b>x</b>', 'G', 'meeting', 0.9))));
  check('tab: a hub link stays in the tab, a Grafana link opens elsewhere', /href="#x" target=_self/.test(SLO.rowHtml(mk('a', 'G', 'meeting', 0.9))) && !/target=_self/.test(SLO.rowHtml(mk('a', 'G', 'meeting', 0.9, { link: 'https://grafana.tail6d0ed4.ts.net/d/x' }))));

  let c = SLO.cardHtml(fresh);
  check('card: "<meeting> of <all>", red when one is breached', />2 of 5</.test(c) && /color:#f85149/.test(c) && /1 breached/.test(c), c);
  c = SLO.cardHtml(SLO.view({ takenAt: doc.takenAt, rows: [mk('a', 'G', 'meeting', 0.9), mk('b', 'G', 'at risk', 0.1)] }, NOW));
  check('card: not red without a breach', />1 of 2</.test(c) && !/color:/.test(c), c);
  c = SLO.cardHtml(old);
  check('card: grey when the numbers are old, never red or green', /color:#7a7a8c/.test(c) && !/f85149/.test(c) && /numbers old/.test(c), c);
  check('card: no slo.json is a grey dash', /&mdash;/.test(SLO.cardHtml(SLO.view(null, NOW))) && /7a7a8c/.test(SLO.cardHtml(SLO.view(null, NOW))));

  h = SLO.bandHtml(fresh, 'cl');
  check('band: only that app\'s rows, closest to breaking first', /Service levels/.test(h) && h.indexOf('>bad<') > 0 && h.indexOf('>bad<') < h.indexOf('>risk<') && !/>ok</.test(h) && !/>p</.test(h), h);
  check('band: an app with no rows gets no band; so does a missing file', SLO.bandHtml(fresh, 'web') === '' && SLO.bandHtml(SLO.view(null, NOW), 'cl') === '');
  check('band: stale numbers are grey in the band too', /dot stale/.test(SLO.bandHtml(old, 'cl')) && !/dot down/.test(SLO.bandHtml(old, 'cl')));

  // sparkline and durations
  const s1 = SLO.spark({ objective: 0.99, daily: [0.999, 0.998, null, 0.97, 0.999, null, null, 1] });
  check('spark: a day with no data breaks the line; the target is drawn', (s1.match(/<polyline/g) || []).length === 2 && /<line /.test(s1) && /<circle/.test(s1), s1);
  check('spark: no data at all draws nothing', !/polyline|<line/.test(SLO.spark({ objective: 0.99, daily: Array(28).fill(null) })));
  check('dur: seconds, minutes, hours, days', SLO.dur(30) === '30 s' && SLO.dur(1500) === '25 min' && SLO.dur(11400) === '3 h 10 min' && SLO.dur(-12096) === '3 h 22 min' && SLO.dur(4 * 86400 + 5 * 3600) === '4 d 5 h');

  console.log(failed ? 'TEST_SLO FAIL (' + failed + ')' : 'TEST_SLO PASS');
  process.exit(failed ? 1 : 0);
})();
