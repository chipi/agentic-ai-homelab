#!/usr/bin/env node
// Deterministic tests of hub-project.js (the Projects tab): windows, comparison shifts, alignment,
// the card numbers (current vs comparison over the same stretch of time), what limits a comparison
// (retention, a metric's first event, the app's start), the audience filter, hourly gauges, nightly
// runs from container lifetimes, and a full render against stub sources. No deps.
// Run: node infra/homelab-home/test_project.js (exit 0 = PASS)
'use strict';
const assert = require('assert');
const P = require('./hub-project.js');
const { DAY, HOUR } = P;
let n = 0;
const t = (name, f) => Promise.resolve().then(f).then(() => { n++; console.log('ok', name); }, e => { console.error('FAIL', name, '\n', e); process.exit(1); });

// 2026-11-06 18:30Z
const NOW = Date.UTC(2026, 10, 6, 18, 30) / 1000, D0 = Date.UTC(2026, 10, 6) / 1000;
const OP = '00000000-0000-4000-8000-000000000001';   // a made-up operator id

// Stub sources that record what they were asked and answer from fixtures.
function stubSrc(opt) {
  opt = opt || {};
  const calls = { vmAt: [], vmRange: [], vmVec: [], sql: [], vl: [] };
  return {
    calls, now: () => NOW,
    async vmAt(e, tt) { calls.vmAt.push([e, tt]); return tt === NOW ? 120 : 100; },
    async vmRange(e, s, en, st) { calls.vmRange.push([e, s, en, st]); const out = []; for (let x = s; x <= Math.min(en, NOW); x += st) out.push([x, opt.rangeValue || 10]); return out; },
    async vmVec(e, tt) {
      calls.vmVec.push([e, tt]);
      // nightly containers: 11-06 00:00 4 h, the enrichment after it 04:00 0.1 h, a hand run 11-05 17:00 3 h,
      // 11-01 00:00 1 h with its enrichment at 01:21 (inside 00:00-02:00Z, like the real 11-01), 10-30 00:00 2 h
      const C = { a: [D0, 4], b: [D0 + 4 * HOUR, 0.1], hand: [D0 - DAY + 17 * HOUR, 3], n1: [D0 - 5 * DAY, 1], e1: [D0 - 5 * DAY + 81 * 60, 0.1], c: [D0 - 7 * DAY, 2] };
      if (/timestamp\(/.test(e)) return Object.entries(C).map(([k, [, h]]) => ({ metric: { name: k }, value: [tt, String(h * HOUR)] }));
      return Object.entries(C).map(([k, [s]]) => ({ metric: { name: k }, value: [tt, String(s)] }));
    },
    async sql(q) {
      calls.sql.push(q);
      if (/min\(created_at\)/.test(q)) return [{ visitors: String(opt.firstEvent || D0 - 400 * DAY) }];
      if (/group by 1/.test(q)) return [{ t: String(D0), visitors: '3' }, { t: String(D0 - 7 * DAY), visitors: '1' }];
      return [{ visitors_0: '5', visitors_1: '2' }];
    },
    async vl(q) { calls.vl.push(q); return []; },
  };
}
const usage = { title: 'Usage', metrics: [{ id: 'visitors', label: 'Visitors', agg: 'count(distinct session_id)', cond: 'true', chart: true }] };
const app = P.resolve({ id: 'x', umamiDomains: ['closelistening.app'], identifies: true, bands: [usage] },
  [['closelistening.app', 'cd384a3e-fd25-476e-affa-08985b73d4da'], ['other.app', 'a5a60c25-a555-4c2d-b096-c9814c21d25c'], ['closelistening.app', "x'; drop"]],
  [OP, "x') or true --"]);
const jobs = P.APPS.cl.bands.find(x => x.title === 'Jobs');

(async () => {
  await t('windows: today is the UTC day in hours, 7d/30d whole days ending today', () => {
    assert.deepStrictEqual(P.windowFor('today', NOW), { start: D0, end: D0 + DAY, step: HOUR, n: 24, len: DAY });
    assert.deepStrictEqual(P.windowFor('7d', NOW), { start: D0 - 6 * DAY, end: D0 + DAY, step: DAY, n: 7, len: 7 * DAY });
    assert.strictEqual(P.windowFor('30d', NOW).n, 30);
    assert.strictEqual(P.windowFor('today', NOW, true).step, DAY, 'a daily band never uses hours');
  });

  await t('shifts: previous, same day last week, average of earlier periods', () => {
    const w = P.windowFor('7d', NOW);
    assert.deepStrictEqual(P.shifts('7d', 'prev', w), [7 * DAY]);
    assert.deepStrictEqual(P.shifts('today', 'week', P.windowFor('today', NOW)), [7 * DAY]);
    assert.deepStrictEqual(P.shifts('today', 'avg', P.windowFor('today', NOW)), [1, 2, 3, 4, 5, 6, 7].map(k => k * DAY));
    assert.deepStrictEqual(P.shifts('7d', 'avg', w), [1, 2, 3, 4].map(k => k * 7 * DAY));
    assert.deepStrictEqual(P.shifts('30d', 'avg', P.windowFor('30d', NOW)), [1, 2, 3].map(k => k * 30 * DAY));
  });

  await t('align: bucket starts land in their slot, shifted points too, outside points dropped', () => {
    const w = P.windowFor('7d', NOW);
    assert.deepStrictEqual(P.align([[w.start, 2], [w.start + DAY + 5, 3], [w.start - DAY, 9]], w, 0), [2, 3, null, null, null, null, null]);
    assert.deepStrictEqual(P.align([[w.start - 7 * DAY, 4]], w, 7 * DAY), [4, null, null, null, null, null, null]);
    assert.deepStrictEqual(P.combine([[1, null, 3], [3, null, null]]), [2, null, 3]);
  });

  await t('delta: absolute difference, direction coloured by what is better', () => {
    assert.strictEqual(P.delta(5, 3).cls, 'good');
    assert.ok(P.delta(5, 3).text.includes('2 vs 3'));
    assert.strictEqual(P.delta(0.4, 0.2, 's', false).cls, 'bad', 'slower is bad');
    assert.strictEqual(P.delta(2, 2).cls, 'flat');
    assert.strictEqual(P.delta(2, null).text, 'no comparison');
    assert.strictEqual(P.fmt(0.039, 's'), '39 ms');
    assert.strictEqual(P.fmt(0, '%'), '0.00%');
  });

  await t('resolve: only the app\'s Umami sites, only real uuids; operator ids only for an app that identifies users', () => {
    assert.deepStrictEqual(app.umamiIds, ['cd384a3e-fd25-476e-affa-08985b73d4da']);
    assert.deepStrictEqual(app.operatorIds, [OP]);
    assert.deepStrictEqual(P.resolve(P.APPS.orrery, [], [OP]).operatorIds, [], 'Orrery has no user identity: no Beta switch');
    for (const a of Object.values(P.APPS)) assert.ok(!(a.operatorIds || []).length, a.id + ': no operator identity in the public config');
  });

  await t('umami: card = this period so far vs the same stretch of the comparison; chart aligned', async () => {
    const src = stubSrc(), [r] = await P.band(src, app, usage, '7d', 'prev', 'all');
    assert.strictEqual(r.value, 5); assert.strictEqual(r.cmpValue, 2);
    const q = src.calls.sql[0], w = P.windowFor('7d', NOW);
    assert.ok(q.includes('created_at >= to_timestamp(' + w.start + ') and created_at < to_timestamp(' + NOW + ')'), 'current range ends now');
    assert.ok(q.includes('to_timestamp(' + (NOW - 7 * DAY) + ')'), 'comparison range ends at the same point a week earlier');
    assert.ok(!q.includes('distinct_id'), 'Everyone: no session filter');
    assert.strictEqual(r.cur[6], 3); assert.strictEqual(r.cmp[6], 1);
  });

  await t('audience: Beta users leaves out the operator\'s sessions, only by a real uuid', async () => {
    const src = stubSrc();
    await P.band(src, app, usage, '7d', 'prev', 'beta');
    for (const q of src.calls.sql.filter(q => !/min\(created_at\)/.test(q)))
      assert.ok(q.includes("session_id not in (select session_id from session where distinct_id in ('" + OP + "'))"), 'filter in ' + q.slice(0, 60));
    assert.ok(!src.calls.sql.some(q => q.includes('or true')), 'a non-uuid operator id never reaches the SQL');
    const src2 = stubSrc(), withSite = Object.assign({}, app, { operatorSiteIds: ['a5a60c25-a555-4c2d-b096-c9814c21d25c'] });
    await P.band(src2, withSite, usage, '7d', 'prev', 'beta');
    assert.ok(src2.calls.sql.filter(q => !/min\(created_at\)/.test(q)).every(q => q.includes("website_id not in ('a5a60c25-a555-4c2d-b096-c9814c21d25c')")), 'the operator site is left out');
    const src3 = stubSrc();
    await P.band(src3, withSite, usage, '7d', 'prev', 'all');
    assert.ok(!src3.calls.sql.some(q => q.includes('website_id not in')), 'Everyone keeps the operator site');
  });

  await t('first event: comparison windows before a metric was first tracked are left out', async () => {
    const [r] = await P.band(stubSrc({ firstEvent: D0 - 10 * DAY }), app, usage, '7d', 'prev', 'all');
    assert.strictEqual(r.cmpValue, null, 'the 7 days before start 13 days ago, before the first event 10 days ago');
    assert.ok(r.cmp.every(x => x == null));
    const [r2] = await P.band(stubSrc({ firstEvent: D0 - 20 * DAY }), app, usage, '7d', 'prev', 'all');
    assert.strictEqual(r2.cmpValue, 2, 'a comparison after the first event stays');
  });

  await t('zero fill: a past bucket with no events is 0 for a count, empty for a mean, future stays empty', async () => {
    const [r] = await P.band(stubSrc(), app, usage, '7d', 'prev', 'all');
    assert.deepStrictEqual(r.cur, [0, 0, 0, 0, 0, 0, 3]);
    assert.deepStrictEqual(r.cmp, [0, 0, 0, 0, 0, 0, 1]);
    const nightly = (await P.band(stubSrc(), app, jobs, '7d', 'prev', 'all')).find(x => x.m.id === 'nightly');
    assert.strictEqual(nightly.cur[5], null, 'a night with no run has no run time');
    const [h] = await P.band(stubSrc(), app, usage, 'today', 'prev', 'all');
    assert.strictEqual(h.cur[18], 0); assert.strictEqual(h.cur[19], null, '19:00 has not started at 18:30');
  });

  await t('vm metric: cards are instant queries over the elapsed window, at now and at now - shift', async () => {
    const src = stubSrc(), b = { title: 'Delivery', metrics: [{ id: 'r', label: 'Requests', expr: 'sum(increase(x[$W]))', chart: true }] };
    const [r] = await P.band(src, app, b, 'today', 'week', 'all');
    assert.deepStrictEqual(src.calls.vmAt.map(c => c[1]), [NOW, NOW - 7 * DAY]);
    assert.ok(src.calls.vmAt[0][0].includes('[' + (NOW - D0) + 's]'));
    assert.strictEqual(r.value, 120); assert.strictEqual(r.cmpValue, 100);
    assert.ok(r.cur.slice(19).every(x => x == null), 'future hours stay empty');
    assert.ok(src.calls.vmRange[0][0].includes('[3600s]'), 'chart buckets use the step as the window');
  });

  await t('vm series: a comparison window the series only partly covers is left out', async () => {
    const src = stubSrc(), b = { title: 'Probes', metrics: [{ id: 'rt', label: 'Response time', unit: 's', expr: 'avg(avg_over_time(p[$W]))', chart: true }] };
    const late = D0 - 9 * DAY;   // the series starts inside the 7 days before (13..6 days ago)
    const vr = src.vmRange; src.vmRange = async (e, s, en, st) => (await vr(e, s, en, st)).filter(([x]) => x - DAY >= late);
    const [r] = await P.band(src, app, b, '7d', 'prev', 'all');
    assert.strictEqual(r.cmpValue, null);
    const [r2] = await P.band(stubSrc(), app, b, '7d', 'prev', 'all');
    assert.strictEqual(r2.cmpValue, 100, 'a fully covered comparison stays');
  });

  await t('hourly gauge: complete hours summed, the same hours in the comparison', async () => {
    const src = stubSrc({ rangeValue: 2 }), b = { title: 'Edge', metrics: [{ id: 'e', label: 'Edge', kind: 'hourly', expr: 'edge' }] };
    const [r] = await P.band(src, app, b, 'today', 'prev', 'all');
    assert.strictEqual(r.value, 18 * 2, '00:00-18:00 are complete at 18:30');
    assert.strictEqual(r.cmpValue, 18 * 2);
    assert.strictEqual(src.calls.vmRange[0][3], HOUR);
  });

  await t('hourly gauge: a comparison before the gauge\'s first sample is left out', async () => {
    const src = stubSrc({ rangeValue: 2 }), b = { title: 'Edge', metrics: [{ id: 'e', label: 'Edge', kind: 'hourly', expr: 'edge' }] };
    const late = D0 - 10 * DAY;  // the gauge starts in the middle of the 7 days before (13..6 days ago)
    const vr = src.vmRange; src.vmRange = async (e, s, en, st) => (await vr(e, s, en, st)).filter(([x]) => x - HOUR >= late);
    const [r] = await P.band(src, app, b, '7d', 'prev', 'all');
    assert.strictEqual(r.cmpValue, null);
    assert.ok(r.value > 0);
  });

  await t('jobs: the nightly is the first container of the day 00:00-02:00Z; hand runs and enrichment out', async () => {
    const rs = await P.band(stubSrc(), app, jobs, 'today', 'prev', 'all'), r = rs.find(x => x.m.id === 'nightly');
    assert.strictEqual(r.w.n, 7, 'Today reads as the last 7 nights');
    assert.strictEqual(r.value, 2.5, 'mean of the 11-06 nightly (4 h) and 11-01 (1 h); not the enrichments (04:00, 01:21) or the 11-05 17:00 hand run');
    assert.strictEqual(r.cmpValue, 2, 'the 7 nights before: the 10-30 run, 2 h');
  });

  await t('retention: a comparison older than the source keeps is left out, not read as zero', async () => {
    const r = (await P.band(stubSrc(), app, jobs, '30d', 'prev', 'all')).find(x => x.m.id === 'processed');
    assert.strictEqual(r.cmpValue, null);
    assert.strictEqual(P.delta(r.value, r.cmpValue).text, 'no comparison');
    const nightly = (await P.band(stubSrc(), app, jobs, '30d', 'prev', 'all')).find(x => x.m.id === 'nightly');
    assert.notStrictEqual(nightly.cmpValue, undefined, 'run time (6 months) keeps its 30-day comparison');
  });

  await t('render: period, comparison and audience links; cards and charts', async () => {
    const el = { innerHTML: '', querySelector: () => null };
    await P.render(el, app, 'today', 'week', stubSrc(), 'beta');
    for (const s of ['#projects/x/7d/prev/beta', '#projects/x/today/avg/beta', '#projects/x/today/week/all', 'class=on>Same day last week', 'class=on title="Usage without your own sessions">Beta users', 'Visitors', 'class=pchart', 'leaves out your own sessions'])
      assert.ok(el.innerHTML.includes(s), 'missing ' + s);
    const el2 = { innerHTML: '', querySelector: () => null };
    await P.render(el2, Object.assign({}, app, { operatorIds: [] }), '7d', 'prev', stubSrc(), 'beta');
    assert.ok(!el2.innerHTML.includes('Same day last week'), '"same day last week" is offered for Today only');
    assert.ok(!el2.innerHTML.includes('Beta users'), 'no audience switch for an app without an operator id');
  });

  await t('app p95: from the access log, background paths left out, card per range and chart per bucket', async () => {
    const src = stubSrc(), b = P.APPS.cl.bands.find(x => x.title === 'Delivery'), m = b.metrics.find(x => x.id === 'app_p95');
    src.vl = async q => {
      src.calls.vl.push(q);
      const [, a, b] = /_time:\[(\d+), (\d+)\]/.exec(q).map(Number);
      if (/by \(_time:1d\)/.test(q)) return [{ _time: new Date(a * 1000).toISOString(), p: '700' }].concat(b >= D0 ? [{ _time: new Date(D0 * 1000).toISOString(), p: '850' }] : []);
      return [{ p: b === NOW ? '900' : '450' }];
    };
    const [r] = await P.band(src, app, { title: 'D', metrics: [m] }, '7d', 'prev', 'all');
    assert.strictEqual(r.value, 0.9); assert.strictEqual(r.cmpValue, 0.45);
    assert.strictEqual(r.cur[6], 0.85);
    assert.ok(src.calls.vl.every(q => q.includes('filter -path:~"^(/internal/|/api/health|/metrics|/api/app/auth/status|/api/app/version)"')), 'background paths left out');
    assert.ok(src.calls.vl.some(q => q.includes('quantile(0.95, ms)')));
  });

  await t('every app: bands with metrics, each metric a label and a query in the right form', () => {
    for (const a of Object.values(P.APPS)) {
      assert.ok(a.bands.length && a.umamiDomains.length, a.id);
      for (const b of a.bands) {
        assert.ok(b.metrics.length, a.id + '/' + b.title);
        for (const m of b.metrics) {
          assert.ok(m.label && m.id, a.id + ' metric');
          assert.ok((m.agg && m.cond) || m.expr || (m.num && m.den) || m.rows || m.fetch, a.id + '/' + m.id + ' has no query');
          if (m.expr && m.kind !== 'hourly') assert.ok(m.expr.includes('$W'), a.id + '/' + m.id + ' must carry the $W window');
          if (m.kind === 'hourly') assert.ok(!m.expr.includes('$W') && m.expr.includes('window="1h"'), a.id + '/' + m.id + ' samples the 1 h gauge');
        }
        assert.strictEqual(new Set(b.metrics.map(m => m.id)).size, b.metrics.length, a.id + ': metric ids unique in a band');
      }
    }
  });

  console.log('PASS', n, 'tests');
})();
