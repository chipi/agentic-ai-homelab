#!/usr/bin/env node
// Deterministic tests of hub-project.js (the Projects tab): windows, comparison shifts, alignment,
// the card numbers (current vs comparison over the same stretch of time), retention, and a full
// render against stub sources. No deps. Run: node infra/homelab-home/test_project.js (exit 0 = PASS)
'use strict';
const assert = require('assert');
const P = require('./hub-project.js');
const { DAY, HOUR } = P;
let n = 0;
const t = (name, f) => Promise.resolve().then(f).then(() => { n++; console.log('ok', name); }, e => { console.error('FAIL', name, '\n', e); process.exit(1); });

// 2026-11-06 18:30Z
const NOW = Date.UTC(2026, 10, 6, 18, 30) / 1000, D0 = Date.UTC(2026, 10, 6) / 1000;

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

  // Stub sources that record what they were asked and answer from fixtures.
  function stubSrc(firstEvent) {
    const calls = { vmAt: [], vmRange: [], sql: [], vl: [] };
    return {
      calls, now: () => NOW,
      async vmAt(e, tt) { calls.vmAt.push([e, tt]); return tt === NOW ? 120 : 100; },
      async vmRange(e, s, en, st) { calls.vmRange.push([e, s, en, st]); const out = []; for (let x = s; x <= Math.min(en, NOW); x += st) out.push([x, 10]); return out; },
      async sql(q) {
        if (/min\(created_at\)/.test(q)) return [{ first: String(firstEvent || D0 - 400 * DAY) }];
        calls.sql.push(q);
        if (/group by 1/.test(q)) return [{ t: String(D0), visitors: '3' }, { t: String(D0 - 7 * DAY), visitors: '1' }];
        return [{ visitors_0: '5', visitors_1: '2' }];
      },
      async vl(q) {
        calls.vl.push(q);
        if (/run_timing/.test(q)) return [
          { run_id: 'a', started: '2026-11-06T00:00:30Z', last: '2026-11-06T04:00:30Z' },
          { run_id: 'b', started: '2026-10-30T00:00:30Z', last: '2026-10-30T02:00:30Z' },
          { run_id: 'hand', started: '2026-11-05T17:00:00Z', last: '2026-11-05T20:00:00Z' }];
        return [];
      },
    };
  }
  const usage = { title: 'Usage', src: 'umami', metrics: [{ id: 'visitors', label: 'Visitors', sql: 'count(distinct session_id) filter (where FILTER)', chart: true }] };
  const app = P.resolve({ id: 'x', umamiDomains: ['closelistening.app'], bands: [usage] },
    [['closelistening.app', 'cd384a3e-fd25-476e-affa-08985b73d4da'], ['other.app', 'a5a60c25-a555-4c2d-b096-c9814c21d25c'], ['closelistening.app', "x'; drop"]]);

  await t('resolve: only the app\'s Umami sites, and only real uuids', () => {
    assert.deepStrictEqual(app.umamiIds, ['cd384a3e-fd25-476e-affa-08985b73d4da']);
  });

  await t('umami band: card = this period so far vs the same stretch of the comparison; chart aligned', async () => {
    const src = stubSrc(), [r] = await P.band(src, app, usage, '7d', 'prev');
    assert.strictEqual(r.value, 5); assert.strictEqual(r.cmpValue, 2);
    const q = src.calls.sql[0], w = P.windowFor('7d', NOW);
    assert.ok(q.includes('created_at >= to_timestamp(' + w.start + ') and created_at < to_timestamp(' + NOW + ')'), 'current range ends now');
    assert.ok(q.includes('to_timestamp(' + (NOW - 7 * DAY) + ')'), 'comparison range ends at the same point a week earlier');
    assert.strictEqual(r.cur[6], 3); assert.strictEqual(r.cmp[6], 1);
  });

  await t('vm metric: cards are instant queries over the elapsed window, at now and at now - shift', async () => {
    const src = stubSrc(), b = { title: 'Delivery', src: 'vm', metrics: [{ id: 'r', label: 'Requests', expr: 'sum(increase(x[$W]))', chart: true }] };
    const [r] = await P.band(src, app, b, 'today', 'week');
    assert.deepStrictEqual(src.calls.vmAt.map(c => c[1]), [NOW, NOW - 7 * DAY]);
    assert.ok(src.calls.vmAt[0][0].includes('[' + (NOW - D0) + 's]'));
    assert.strictEqual(r.value, 120); assert.strictEqual(r.cmpValue, 100);
    assert.ok(r.cur.slice(19).every(x => x == null), 'future hours stay empty');
    assert.ok(src.calls.vmRange[0][0].includes('[3600s]'), 'chart buckets use the step as the window');
  });

  await t('jobs: nightly runs only (hand runs out), Today reads as 7 nights, mean per night', async () => {
    const src = stubSrc(), b = P.APPS.cl.bands.find(x => x.title === 'Jobs');
    const rs = await P.band(src, app, b, 'today', 'prev'), r = rs.find(x => x.m.id === 'nightly');
    assert.strictEqual(r.w.n, 7);
    assert.strictEqual(r.value, 4, 'the 11-06 nightly took 4 h; the 11-05 hand run is not a nightly');
    assert.strictEqual(r.cmpValue, 2, 'the 7 nights before: the 10-30 run, 2 h');
  });

  await t('retention: a comparison older than the source keeps is left out, not read as zero', async () => {
    const src = stubSrc(), b = P.APPS.cl.bands.find(x => x.title === 'Jobs');
    const r = (await P.band(src, app, b, '30d', 'prev')).find(x => x.m.id === 'processed');
    assert.strictEqual(r.cmpValue, null);
    assert.strictEqual(P.delta(r.value, r.cmpValue).text, 'no comparison');
  });

  await t('first event: comparison windows before the app\'s first Umami event are left out', async () => {
    const [r] = await P.band(stubSrc(D0 - 10 * DAY), app, usage, '7d', 'prev');
    assert.strictEqual(r.cmpValue, null, 'the 7 days before start 13 days ago, before the first event 10 days ago');
    assert.ok(r.cmp.every(x => x == null));
    const [r2] = await P.band(stubSrc(D0 - 20 * DAY), app, usage, '7d', 'prev');
    assert.strictEqual(r2.cmpValue, 2, 'a comparison after the first event stays');
  });

  await t('zero fill: a past bucket with no events is 0 for a count, empty for a mean, future stays empty', async () => {
    const [r] = await P.band(stubSrc(), app, usage, '7d', 'prev');
    assert.deepStrictEqual(r.cur, [0, 0, 0, 0, 0, 0, 3]);
    assert.deepStrictEqual(r.cmp, [0, 0, 0, 0, 0, 0, 1]);
    const b = P.APPS.cl.bands.find(x => x.title === 'Jobs');
    const nightly = (await P.band(stubSrc(), app, b, '7d', 'prev')).find(x => x.m.id === 'nightly');
    assert.strictEqual(nightly.cur[5], null, 'a night with no run has no run time');
    const [h] = await P.band(stubSrc(), app, usage, 'today', 'prev');
    assert.strictEqual(h.cur[18], 0); assert.strictEqual(h.cur[19], null, '19:00 has not started at 18:30');
  });

  await t('render: period and comparison links, one band per source, cards and charts', async () => {
    const el = { innerHTML: '', querySelector: () => null };
    await P.render(el, app, 'today', 'week', stubSrc());
    for (const s of ['#projects/x/7d/week', '#projects/x/today/avg', 'class=on>Same day last week', 'Visitors', 'class=pchart', 'same day last week'])
      assert.ok(el.innerHTML.includes(s), 'missing ' + s);
    const el2 = { innerHTML: '', querySelector: () => null };
    await P.render(el2, app, '7d', 'prev', stubSrc());
    assert.ok(!el2.innerHTML.includes('Same day last week'), '"same day last week" is offered for Today only');
  });

  await t('the Close Listening config: every band has metrics, every metric a label and a query', () => {
    for (const b of P.APPS.cl.bands) {
      assert.ok(b.metrics.length);
      for (const m of b.metrics) {
        assert.ok(m.label && m.id);
        assert.ok(m.sql || m.expr || (m.num && m.den) || m.rows, m.id + ' has no query');
        if (m.sql) assert.ok(m.sql.includes('FILTER'), m.id + ' must carry the FILTER placeholder');
        if (m.expr) assert.ok(m.expr.includes('$W'), m.id + ' must carry the $W window');
      }
    }
  });

  console.log('PASS', n, 'tests');
})();
