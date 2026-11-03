#!/usr/bin/env node
// Deterministic test of hub-status.js: each area's verdict from fixture VictoriaMetrics series and a
// fixture alert list, no page involved. Run: node infra/homelab-home/test_status.js (exit 0 = PASS)
'use strict';
const HS = require('./hub-status.js');

const NOW = 1788047143;
const vec = (value, labels = {}, ts = NOW) => ({ metric: labels, value: [ts, String(value)] });
const src = (fixtures, alerts = []) => ({
  now: NOW,
  q: async e => { for (const [needle, r] of fixtures) if (e.includes(needle)) return typeof r === 'function' ? r(e) : r; return []; },
  alerts: async () => { if (alerts instanceof Error) throw alerts; return alerts; },
});

let failed = 0;
const check = (name, cond, got) => { if (cond) console.log('ok   ' + name); else { failed++; console.error('FAIL ' + name + (got !== undefined ? ' (got ' + JSON.stringify(got) + ')' : '')); } };

(async () => {
  // sites
  const probes = (cur, d1) => [
    ['[24h:1m]', Object.entries(d1).map(([h, v]) => vec(v, { host: h }))],
    ['last_over_time(probe_success', Object.entries(cur).map(([h, v]) => vec(v, { host: h }))],
    ['mini_vm_egress_ok', [vec(1)]],
  ];
  let s = await HS.sites(src(probes({ a: 1, b: 1 }, { a: 1, b: 1 })));
  check('sites: all up and 24h >= 99.9% is up', s.state === 'up' && s.up === 2 && s.total === 2, s);
  s = await HS.sites(src(probes({ a: 1, b: 0 }, { a: 1, b: 1 })));
  check('sites: a host down now is down, named', s.state === 'down' && s.down.join() === 'b', s);
  s = await HS.sites(src(probes({ a: 1, b: 1 }, { a: 1, b: 0.995 })));
  check('sites: 24h under 99.9% is mid, lowest named', s.state === 'mid' && s.lowest.host === 'b', s);
  s = await HS.sites(src([...probes({ a: 0 }, { a: 1 }).slice(0, 2), ['mini_vm_egress_ok', [vec(0)]]]));
  check('sites: mini offline is stale, not down', s.state === 'stale' && s.offline, s);
  s = await HS.sites(src([]));
  check('sites: no probe data is stale', s.state === 'stale' && s.total === 0, s);

  // boxes
  const b = await HS.boxes(src([['mini_cpu_used_percent', [vec(5, {}, NOW - 30)]], ['DCGM_FI_DEV_GPU_TEMP', [vec(40, {}, NOW - 400)]], ['node_load1{instance="x3"}', [vec(1, {}, NOW - 60)]]]));
  check('boxes: 30 s old is up, 400 s old is stale, none is down', b.mini.state === 'up' && b.dgx.state === 'stale' && b.prod.state === 'down', b);
  check('boxes: the X3 reads its own collector', b.x3.state === 'up' && b.x3.ageSeconds === 60, b.x3);

  // podcast
  const ph = (tsAgo, agg, checks) => [
    ['prod_ops_health_last_run_timestamp', tsAgo == null ? [] : [vec(NOW - tsAgo)]],
    ['prod_ops_health_aggregate', agg == null ? [] : [vec(agg)]],
    ['prod_ops_health_check', Object.entries(checks).map(([c, v]) => vec(v, { check: c }))],
  ];
  let p = await HS.podcast(src(ph(3600, 1, { gateway: 1, o11y_logs: 0.5 })));
  check('podcast: fresh green is up; orange check is mid; missing expected check is null',
    p.state === 'up' && p.checks.o11y_logs === 'mid' && p.checks.o11y_traces === null && p.ageHours === 1, p);
  p = await HS.podcast(src(ph(27 * 3600, 1, { gateway: 1 })));
  check('podcast: older than 26 h is stale even when green', p.state === 'stale' && p.stale && p.checks.gateway === 'stale', p);
  p = await HS.podcast(src(ph(3600, 0, {})));
  check('podcast: aggregate 0 is down', p.state === 'down', p);

  // alerts
  const act = (name, sev, extra = {}) => ({ status: { state: 'active' }, labels: Object.assign({ alertname: name, severity: sev }, extra), annotations: { summary: name + ' summary' } });
  const a = await HS.alerts(src([], [act('disk-low', 'critical', { instance: 'mini' }), act('disk-low', 'critical', { instance: 'mini' }),
    act('slow', 'warning'), act('DatasourceNoData', 'critical'), { status: { state: 'suppressed' }, labels: { alertname: 'muted', severity: 'critical' } }]));
  check('alerts: critical deduped, warning kept, plumbing counted apart, inactive dropped',
    a.ok && a.critical.length === 1 && a.critical[0].instance === 'mini' && a.warning.length === 1 && a.plumbing === 1, a);
  const ae = await HS.alerts(src([], new Error('401')));
  check('alerts: a failing alertmanager is ok:false, not an empty all-clear', ae.ok === false, ae);

  // needs you
  let n = await HS.needsYou(src([['queue_depth{kind="bug"}', [vec(3)]], ['escalations_7d', [vec(2)]]]));
  check('needsYou: bug queue + escalations', n.total === 5, n);
  n = await HS.needsYou(src([]));
  check('needsYou: no data is null, not 0', n.total === null, n);

  // delivery
  let d = await HS.delivery(src([['count(up{job="delivery"})', [vec(3)]], ['sum(up{job="delivery"})', [vec(3)]]]));
  check('delivery: all workers up, nothing wrong is up', d.state === 'up' && d.reasons.length === 0, d);
  d = await HS.delivery(src([['count(up{job="delivery"})', [vec(3)]], ['sum(up{job="delivery"})', [vec(2)]]]));
  check('delivery: a worker down is down', d.state === 'down', d);
  d = await HS.delivery(src([['count(up{job="delivery"})', [vec(3)]], ['sum(up{job="delivery"})', [vec(3)]], ['dead_lettered"}[1h]', [vec(1)]]]));
  check('delivery: a dead letter in the last hour is mid, with the reason', d.state === 'mid' && /dead-lettered/.test(d.reasons[0]), d);
  d = await HS.delivery(src([]));
  check('delivery: no workers is stale', d.state === 'stale', d);

  // credit
  let c = await HS.credit(src([['openrouter_account_usd', [vec(4.24)]]]));
  check('credit: under $10 is low', c.low === true && c.leftUsd === 4.24, c);
  c = await HS.credit(src([]));
  check('credit: no data is null and not low', c.leftUsd === null && c.low === false, c);

  // all: one failing area does not hide the rest
  const all = await HS.all({ now: NOW, q: async e => { if (e.includes('delivery')) throw new Error('boom'); return []; }, alerts: async () => [] });
  check('all: a throwing area is reported as an error, the others still present', all.delivery.error === 'boom' && all.sites.state === 'stale' && all.takenAt, all.delivery);

  console.log(failed ? 'TEST_STATUS FAIL (' + failed + ')' : 'TEST_STATUS PASS');
  process.exit(failed ? 1 : 0);
})();
