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

  // errors: GlitchTip issues first seen in the last 24 h, newest first; the page (no source) gets ok:false
  const iso = sec => new Date(sec * 1000).toISOString();
  const issues = [
    { id: 3, shortId: 'NEW-2', title: 'b', count: '4', firstSeen: iso(NOW - 600), status: 'unresolved', project: { slug: 'p2' } },
    { id: 2, shortId: 'NEW-1', title: 'a', count: '1', firstSeen: iso(NOW - 86000), status: 'resolved', project: { slug: 'p1' } },
    { id: 1, shortId: 'OLD-1', title: 'z', count: '9', firstSeen: iso(NOW - 90000), status: 'unresolved', project: { slug: 'p1' } },
  ];
  let asked = '';
  const er = await HS.errors(Object.assign(src([]), { glitchtip: async p => { asked = p; return issues; } }));
  check('errors: open issues first seen in 24 h are listed, with project and count', er.ok && er.newCount === 1 &&
    er.new.map(x => x.id).join() === 'NEW-2' && er.new[0].project === 'p2' && er.new[0].count === 4, er);
  check('errors: new issues already resolved are counted, not listed', er.resolvedCount === 1 && !er.new.some(x => x.status === 'resolved'), er);
  check('isOpen: unresolved is open; resolved and ignored are not', HS.isOpen({ status: 'unresolved' }) && !HS.isOpen({ status: 'resolved' }) && !HS.isOpen({ status: 'ignored' }));
  check('errors: asks newest-first, all statuses, up to 100', asked.includes('sort=-first_seen') && asked.includes('limit=100') && asked.includes('query=&'), asked);
  const nosrc = await HS.errors(src([]));
  check('errors: without a GlitchTip source (the page) it says so, no throw', nosrc.ok === false && nosrc.reason, nosrc);
  const win = await HS.newIssues({ glitchtip: async () => issues }, NOW - 700);
  check('newIssues: the window is the caller\'s (the briefing\'s overnight)', win.map(x => x.id).join() === 'NEW-2', win);

  // alertChanges + timeline (H7): every event carries its source and a reference; a failing source is named
  const ms = sec => sec * 1000;
  const ann = [
    { id: 11, time: ms(NOW - 3000), alertName: 'Cloudflare origin', newState: 'Alerting', prevState: 'Pending', text: 'Cloudflare origin {alertname=Cloudflare origin, instance=prod, severity=critical} - q=1' },
    { id: 12, time: ms(NOW - 2000), alertName: 'Cloudflare origin', newState: 'Normal', prevState: 'Alerting', text: 'Cloudflare origin {alertname=Cloudflare origin, grafana_instance=x, instance=prod, severity=critical}' },
    { id: 13, time: ms(NOW - 2500), alertName: 'Scrape down', newState: 'Pending', prevState: 'Normal', text: '' },
    { id: 14, time: ms(NOW - 2400), alertName: 'DatasourceNoData', newState: 'Alerting', prevState: 'Normal', text: '' },
  ];
  const ch = await HS.alertChanges({ annotations: async () => ann }, 0, ms(NOW));
  check('alertChanges: fired and resolved only, plumbing and pending left out, oldest first', ch.map(c => c.change + c.annotationId).join() === 'fired11,resolved12', ch);
  check('alertChanges: instance and severity from the labels (not grafana_instance)', ch[1].instance === 'prod' && ch[1].severity === 'critical', ch[1]);
  const logsAsked = [];
  const tsrc = Object.assign(src([['container_uptime_seconds', [{ metric: { box: 'prod', name: 'caddy' }, value: [NOW, '1500'] }]]]), {
    annotations: async () => ann,
    logs: async qq => { logsAsked.push(qq); return [{ _time: iso(NOW - 2800), _msg: 'prod deploy success sha-1', event_type: 'deploy', status: 'success', app: 'podcast_scraper', env: 'prod' },
                                                 { _time: iso(NOW - 999999), _msg: 'too old', event_type: 'deploy' }]; },
    glitchtip: async () => issues,
  });
  const tl = await HS.timeline(tsrc, ms(NOW - 3600), ms(NOW));
  check('timeline: alerts, deploys, new errors and container starts, oldest first', tl.events.map(e => e.source).join() === 'alert,ops_event,alert,container,glitchtip', tl.events);
  check('timeline: every event has an ISO time, what and a ref', tl.events.every(e => /Z$/.test(e.at) && e.what && e.ref), tl.events);
  check('timeline: events outside the window are left out', !tl.events.some(e => /too old/.test(e.what)) && tl.count === tl.events.length, tl.events);
  check('timeline: the container start is now minus its uptime', tl.events.find(e => e.source === 'container').at === iso(NOW - 1500), tl.events);
  check('timeline: only failed CI runs are asked for', /event_type:ci_run status:failure/.test(logsAsked[0]) && /deploy OR backup OR drill OR drift/.test(logsAsked[0]), logsAsked);
  const prov = await HS.alertChanges({ annotations: async () => [{ id: 21, time: ms(NOW - 100), alertName: 'Cloudflare incident on a component we use', newState: 'Alerting', prevState: 'Pending',
    text: 'Cloudflare incident on a component we use {alertname=Cloudflare incident on a component we use, host=homelab, impact=minor, link=https://www.cloudflarestatus.com/incidents/x, name=Network Performance Issues in APJC, severity=warning, status=identified} - q=1' }] }, 0, ms(NOW));
  check('alertChanges: a provider incident keeps its name, stage, impact and page; alert names with ", " survive',
    prov[0].detail === 'Network Performance Issues in APJC, identified, impact minor' && prov[0].link === 'https://www.cloudflarestatus.com/incidents/x' && prov[0].host === 'homelab', prov[0]);
  const tlProv = await HS.timeline(Object.assign({}, tsrc, { annotations: async () => [{ id: 22, time: ms(NOW - 100), alertName: 'Cloudflare cannot reach the prod origin, sustained across hosts', newState: 'Alerting', prevState: 'Normal',
    text: 'x {alertname=Cloudflare cannot reach the prod origin, sustained across hosts, host=prod-podcast, instance=homelab, link=https://e.x/1, severity=warning}' }] }), ms(NOW - 3600), ms(NOW));
  const pe = tlProv.events.find(e => e.source === 'alert');
  check('timeline: an alert names its host before the collector instance, and its ref carries the annotation id and link',
    /on prod-podcast$/.test(pe.what) && pe.ref === 'Grafana annotation 22, https://e.x/1', pe);
  check('timeline: every event has a local time', tlProv.events.every(e => /^\w{3} \d{1,2} \w{3}, \d\d:\d\d$/.test(e.local)), tlProv.events.map(e => e.local));
  const tlBad = await HS.timeline(Object.assign({}, tsrc, { logs: async () => { throw new Error('vlogs down'); } }), ms(NOW - 3600), ms(NOW));
  check('timeline: a failing source is named in missing, the rest still there', tlBad.missing.length === 1 && /ops events.*vlogs down/.test(tlBad.missing[0]) && tlBad.events.some(e => e.source === 'alert'), tlBad.missing);

  // all: one failing area does not hide the rest
  const all = await HS.all({ now: NOW, q: async e => { if (e.includes('delivery')) throw new Error('boom'); return []; }, alerts: async () => [] });
  check('all: a throwing area is reported as an error, the others still present', all.delivery.error === 'boom' && all.sites.state === 'stale' && all.takenAt, all.delivery);

  console.log(failed ? 'TEST_STATUS FAIL (' + failed + ')' : 'TEST_STATUS PASS');
  process.exit(failed ? 1 : 0);
})();
