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
  let n = await HS.needsYou(src([['queue_depth{service="triage-fleet",kind="bug"}', [vec(3)]], ['escalations_7d{service="triage-fleet"}', [vec(2)]]]));
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
  const flat = t => Object.values(t.byKind).flat();
  // a line is '<local> — <what> — <ref>'; what may itself hold ' — ' ("DR drill — exercise"), a ref never does
  const SEP = ' — ', LOC = e => e.line.slice(0, e.line.indexOf(SEP)), REF = e => e.line.slice(e.line.lastIndexOf(SEP) + 3), WHAT = e => e.line.slice(e.line.indexOf(SEP) + 3, e.line.lastIndexOf(SEP));
  const tl = await HS.timeline(tsrc, ms(NOW - 3600), ms(NOW));
  check('timeline: grouped by kind, each kind oldest first, every kind present', Object.keys(tl.byKind).join() === 'alert,deploy,backup,drill,drift,ci_failure,error,container_start' &&
    tl.byKind.alert.map(REF).join() === 'Grafana annotation 11,Grafana annotation 12' && tl.byKind.deploy.length === 1 && tl.byKind.error.length === 1 && tl.byKind.container_start.length === 1 && tl.byKind.backup.length === 0, tl.byKind);
  check('timeline: counts per kind match the lists', Object.entries(tl.counts).every(([k, n]) => tl.byKind[k].length === n) && tl.count === flat(tl).length, tl.counts);
  check('timeline: every event is one line with a time, what and a ref, and no UTC at', flat(tl).every(e => !('at' in e) && LOC(e) && WHAT(e) && REF(e) && e.line.split(SEP).length >= 3), flat(tl));
  check('timeline: events outside the window are left out', !flat(tl).some(e => /too old/.test(WHAT(e))), flat(tl));
  check('timeline: the container start is now minus its uptime', LOC(tl.byKind.container_start[0]) === new Date((NOW - 1500) * 1000).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), tl.byKind.container_start);
  check('timeline: only failed CI runs are asked for', /event_type:ci_run status:failure/.test(logsAsked[0]) && /deploy OR backup OR drill OR drift/.test(logsAsked[0]), logsAsked);
  const prov = await HS.alertChanges({ annotations: async () => [{ id: 21, time: ms(NOW - 100), alertName: 'Cloudflare incident on a component we use', newState: 'Alerting', prevState: 'Pending',
    text: 'Cloudflare incident on a component we use {alertname=Cloudflare incident on a component we use, host=homelab, impact=minor, link=https://www.cloudflarestatus.com/incidents/x, name=Network Performance Issues in APJC, severity=warning, status=identified} - q=1' }] }, 0, ms(NOW));
  check('alertChanges: a provider incident keeps its name, stage, impact and page; alert names with ", " survive',
    prov[0].detail === 'Network Performance Issues in APJC, identified, impact minor' && prov[0].link === 'https://www.cloudflarestatus.com/incidents/x' && prov[0].host === 'homelab', prov[0]);
  const tlProv = await HS.timeline(Object.assign({}, tsrc, { annotations: async () => [{ id: 22, time: ms(NOW - 100), alertName: 'Cloudflare cannot reach the prod origin, sustained across hosts', newState: 'Alerting', prevState: 'Normal',
    text: 'x {alertname=Cloudflare cannot reach the prod origin, sustained across hosts, host=prod-podcast, instance=homelab, link=https://e.x/1, severity=warning}' }] }), ms(NOW - 3600), ms(NOW));
  const pe = tlProv.byKind.alert[0];
  check('timeline: an alert names its host before the collector instance, and its ref carries the annotation id and link',
    /on prod-podcast$/.test(WHAT(pe)) && REF(pe) === 'Grafana annotation 22, https://e.x/1', pe);
  check('timeline: every event has a local time', flat(tlProv).every(e => /^\w{3} \d{1,2} \w{3}, \d\d:\d\d$/.test(LOC(e))), flat(tlProv).map(LOC));
  const tlBad = await HS.timeline(Object.assign({}, tsrc, { logs: async () => { throw new Error('vlogs down'); } }), ms(NOW - 3600), ms(NOW));
  check('timeline: a failing source is named in missing, the rest still there', tlBad.missing.length === 1 && /ops events.*vlogs down/.test(tlBad.missing[0]) && tlBad.byKind.alert.length === 2, tlBad.missing);

  // last night: 19:00 to 07:00 local, the night that ended at the latest 07:00 (built in local time, so any TZ works)
  const L = (d, h, m = 0) => new Date(2026, 10, d, h, m).getTime();
  const nightSrc = at => ({ now: at / 1000, q: async () => [], logs: async () => [{ _time: new Date(L(3, 22)).toISOString(), _msg: 'night deploy', event_type: 'deploy', status: 'success' }], glitchtip: async () => [],
    annotations: async () => [[L(3, 18, 59), 31], [L(3, 19, 0), 32], [L(4, 6, 59), 33], [L(4, 7, 0), 34]].map(([t, id]) => ({ id, time: t, alertName: 'a', newState: 'Alerting', prevState: 'Normal', text: '' })) });
  let tn = await HS.timeline(nightSrc(L(4, 11)), L(2, 11), L(4, 11));
  check('timeline: at 11:00 last night is yesterday 19:00 to today 07:00, its events flagged',
    tn.lastNight.from === new Date(L(3, 19)).toISOString() && tn.lastNight.to === new Date(L(4, 7)).toISOString() &&
    tn.byKind.alert.filter(e => e.lastNight).map(REF).join() === 'Grafana annotation 32,Grafana annotation 33', tn);
  check('timeline: lastNightLines hold every kind of the night in time order', tn.lastNightLines.map(l => l.slice(l.lastIndexOf(' — ') + 3).replace(/ _time .*/, '')).join() === 'Grafana annotation 32,VictoriaLogs ops_event deploy,Grafana annotation 33', tn.lastNightLines);
  check('timeline: a line holds one clock time, its own (an ISO time in a ref was copied as the time, 2026-11-04)', tn.lastNightLines.every(l => (l.match(/\b\d\d:\d\d\b/g) || []).length === 1) && /_time \d+ \(unix\)$/.test(tn.lastNightLines[1]), tn.lastNightLines);
  tn = await HS.timeline(nightSrc(L(4, 6)), L(2, 6), L(4, 6));
  check('timeline: at 06:00 the night still running is not "last night"; the one before is', tn.lastNight.to === new Date(L(3, 7)).toISOString() && !tn.byKind.alert.some(e => e.lastNight), tn.lastNight);
  check('timeline: lastNight has its local label', /^\w{3} \d{1,2} \w{3}, 19:00 to \w{3} \d{1,2} \w{3}, 07:00$/.test(tn.lastNight.local), tn.lastNight.local);

  // analytics (Umami): local-day periods, dev sites left out, one failing site reported, not dropped
  const asked2 = [];
  const usrc = { now: L(4, 11) / 1000, umami: async p => { asked2.push(p);
    if (p.startsWith('/api/websites?')) return { data: [{ id: 'a', name: 'site A', domain: 'a.eu' }, { id: 'b', name: 'site B', domain: 'b.com' }, { id: 'd', name: 'A (dev)', domain: 'localhost' }] };
    if (p.startsWith('/api/websites/b/')) throw new Error('boom');
    if (p.includes('/stats?')) return { visitors: 5, pageviews: 9, visits: 6, bounces: 3 };
    if (p.includes('/active')) return { visitors: 1 };
    if (p.includes('type=referrer')) return [{ x: '', y: 4 }, { x: 'google.com', y: 2 }];
    return [{ x: '/', y: 7 }];
  } };
  const an = await HS.analytics(usrc);
  check('analytics: dev (localhost) sites left out, a failing site reported with its error', an.ok && an.sites.map(x => x.site).join() === 'site A,site B' && an.sites[1].error === 'boom', an.sites);
  check('analytics: today, yesterday, 7 days and the 7 before, with bounce %', an.sites[0].today.visitors === 5 && an.sites[0].yesterday.pageviews === 9 && an.sites[0].last7d.bouncePct === 50 && an.sites[0].previous7d, an.sites[0]);
  check('analytics: today starts at local midnight, yesterday is the local day before', asked2.some(p => p.includes('/a/stats?startAt=' + L(4, 0) + '&endAt=' + L(4, 11))) && asked2.some(p => p.includes('/a/stats?startAt=' + L(3, 0) + '&endAt=' + L(4, 0))), asked2.filter(p => p.includes('/a/stats')));
  check('analytics: direct traffic is not listed as a referrer; pages, countries, events, active kept', an.sites[0].top7d.referrers.map(r => r.name).join() === 'google.com' && an.sites[0].top7d.pages[0].name === '/' && an.sites[0].activeNow === 1 && /^\w{3} \d{1,2} \w{3}, 00:00 to now$/.test(an.periods.today), an.sites[0]);
  check('analytics: without an Umami source (the page) it says so', (await HS.analytics({ now: NOW })).ok === false);
  let inFlight = 0, maxInFlight = 0;
  await HS.analytics({ now: usrc.now, umami: async p => { inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
    await new Promise(r => setTimeout(r, 1)); try { return await usrc.umami(p); } finally { inFlight--; } } });
  check('analytics: one Umami request at a time (a burst of ~60 preceded the 2026-11-04 forward break)', maxInFlight === 1, maxInFlight);

  // fleetQueue (H6): the fleet's published inbox (fleet_inbox/v1), plus the open escalated backlog from GitHub.
  // Which escalations count (7 days, open issue, unreadable kept) is the fleet's: signal-fleet/mvp/test_units.py.
  const issueOf = (n, state, title, extra) => Object.assign({ repo: 'chipi/a', number: n, url: 'https://github.com/chipi/a/issues/' + n, state, title }, extra);
  const inboxDoc = { schema: 'fleet_inbox/v1', fleet: 'triage', generated_at: iso(NOW - 120), needs_you: 4,
    escalations_7d: [  // not in time order: the Hub sorts
      { ts: iso(NOW - 300), alertname: 'never filed', reason: 'r', fingerprint: 'grafana:zz', issue: null },
      { ts: iso(NOW - 3600), alertname: 'boom', reason: 'gate: no corroboration', fingerprint: 'glitchtip:X-1', issue: issueOf(9, 'open', 'boom issue') },
      { ts: iso(NOW - 100), alertname: 'unreadable one', reason: 'r', fingerprint: 'glitchtip:X-5', issue: issueOf(12, null, null, { error: 'HTTP 502' }) }],
    bug_queue: [{ title: 'a bug', fingerprint: 'glitchtip:Y-1', queued_at: iso(NOW - 100) }], queue_depth: { bug: 1, cleanup: 1 } };
  const fsrc = { now: NOW, fleetRepos: ['chipi/a', 'chipi/b'],
    fleetInbox: async () => inboxDoc,
    github: async p => {
      if (p.startsWith('/repos/chipi/a/issues?')) return [{ number: 9, title: 'boom issue', html_url: 'https://github.com/chipi/a/issues/9', created_at: iso(NOW - 2 * 86400) },
                                                       { number: 3, title: 'a PR', pull_request: {}, html_url: 'x', created_at: iso(NOW) }];
      if (p.startsWith('/repos/chipi/b/')) throw new Error('HTTP 404');
      throw new Error('unexpected ' + p);
    } };
  const fq = await HS.fleetQueue(fsrc);
  check('fleetQueue: the fleet\'s escalations in time order, plus its bug-queue proposals; the count is the fleet\'s',
    fq.ok && fq.escalations7d.map(e => e.signal).join() === 'boom,never filed,unreadable one' && fq.bugQueue.map(b => b.title).join() === 'a bug' && fq.needsYou === 4 && fq.needsYou === inboxDoc.needs_you, fq);
  check('fleetQueue: an issue the fleet could not read keeps state null and its error', fq.escalations7d[2].issue.state === null && fq.escalations7d[2].issue.error === 'HTTP 502', fq.escalations7d);
  check('fleetQueue: an escalation carries its filed issue, with state and title',
    fq.escalations7d[0].issue.number === 9 && fq.escalations7d[0].issue.url === 'https://github.com/chipi/a/issues/9' && fq.escalations7d[0].issue.state === 'open' && fq.escalations7d[0].issue.title === 'boom issue', fq.escalations7d[0]);
  check('fleetQueue: an escalation the fleet never filed has issue null, not a guess', fq.escalations7d[1].issue === null, fq.escalations7d[1]);
  check('fleetQueue: open escalated backlog without pull requests; a refused repo named in unreadable',
    fq.openEscalated.map(i => i.number).join() === '9' && fq.openEscalated[0].ageDays === 2 && fq.unreadable.length === 1 && /chipi\/b: HTTP 404/.test(fq.unreadable[0]), fq);
  check('fleetQueue: a fresh inbox is not stale and says when it was made', fq.stale === false && fq.generatedAt === inboxDoc.generated_at, fq);
  const old = await HS.fleetQueue(Object.assign({}, fsrc, { fleetInbox: async () => Object.assign({}, inboxDoc, { generated_at: iso(NOW - 3700) }) }));
  check('fleetQueue: an inbox older than an hour is still shown, marked stale', old.ok && old.stale === true && old.needsYou === 4, old);
  const noTime = await HS.fleetQueue(Object.assign({}, fsrc, { fleetInbox: async () => Object.assign({}, inboxDoc, { generated_at: 'garbage' }) }));
  check('fleetQueue: an inbox with no readable time is stale, not fresh', noTime.stale === true, noTime);
  const wrong = await HS.fleetQueue(Object.assign({}, fsrc, { fleetInbox: async () => Object.assign({}, inboxDoc, { schema: 'fleet_inbox/v2' }) }));
  check('fleetQueue: another schema version is refused with the reason, not misread', wrong.ok === false && /fleet_inbox\/v2/.test(wrong.reason), wrong);
  const missing = await HS.fleetQueue(Object.assign({}, fsrc, { fleetInbox: async () => { throw new Error('ENOENT inbox.json'); } }));
  check('fleetQueue: a missing inbox file is reported, not thrown', missing.ok === false && /ENOENT/.test(missing.reason), missing);
  check('fleetQueue: without a fleet source (the page) it says so', (await HS.fleetQueue({ now: NOW })).ok === false);
  check('fleetQueue: exactly one needs-you line per counted item, each saying its issue state or "no issue filed"',
    fq.needsYouLines.length === fq.needsYou && /chipi\/a#9 \(open\) https:\/\/github.com\/chipi\/a\/issues\/9$/.test(fq.needsYouLines[0]) &&
    /no issue filed$/.test(fq.needsYouLines[1]) && /\(state unknown\) https/.test(fq.needsYouLines[2]) && /^bug proposal waiting for your yes: a bug$/.test(fq.needsYouLines[fq.needsYouLines.length - 1]), fq.needsYouLines);
  check('fleetQueue: one open-escalated line per open issue, with its age and link', fq.openEscalatedLines.length === fq.openEscalatedCount &&
    fq.openEscalatedLines[0] === 'chipi/a#9 — boom issue — open 2 days — https://github.com/chipi/a/issues/9', fq.openEscalatedLines);

  // capacity: every host, the X3 included (2026-11-04), from node metrics with its instance label
  const capAsked = [];
  const cap = await HS.capacity({ now: NOW, q: async e => { capAsked.push(e); return [vec(42)]; } });
  check('capacity: mini, dgx, prod and x3, each with disk free and memory used', ['mini', 'dgx', 'prod', 'x3'].every(b => cap[b] && cap[b].diskFreePct === 42 && cap[b].memUsedPct === 42), cap);
  check('capacity: the X3 reads its own instance', capAsked.some(e => /instance="x3",mountpoint="\/"/.test(e)) && capAsked.some(e => /MemAvailable_bytes\{instance="x3"\}/.test(e)), capAsked.filter(e => /x3/.test(e)));

  // assistantSpend: the Spend tab's windows (completed UTC days), split by api_base
  const sqls = [];
  const asrc = { now: Date.UTC(2026, 10, 4, 13) / 1000, litellmSql: async s => { sqls.push(s); return ['x3|10|0|5000', 'openrouter|2|0.0042|800']; } };
  const as = await HS.assistantSpend(asrc);
  check('assistantSpend: month, 30d, 7d, yesterday, each split x3 / openrouter with a local share',
    as.ok && ['month', '30d', '7d', 'yesterday'].every(w => as.windows[w].x3.calls === 10 && as.windows[w].openrouter.usd === 0.0042 && as.windows[w].localShare === 0.8333 && as.windows[w].x3.tokens === 5000), as.windows);
  check('assistantSpend: windows end at UTC midnight today; 7d starts 7 days before; the X3 is told apart by its address',
    sqls.some(s => s.includes('to_timestamp(' + Date.UTC(2026, 10, 4) / 1000 + ')') && s.includes('to_timestamp(' + Date.UTC(2026, 9, 28) / 1000 + ')')) &&
    sqls.every(s => s.includes("api_base ilike '%100.92.54.65%'") && s.includes("model_group in ('assistant','assistant-cloud')")), sqls[2]);
  const as1 = await HS.assistantSpend({ now: Date.UTC(2026, 10, 1, 9) / 1000, litellmSql: async s => { sqls.push(s); return []; } });
  check('assistantSpend: on the 1st, "this month" has no completed day: zero, no query, no share', as1.windows.month.days === 0 && as1.windows.month.localShare === null, as1.windows.month);
  check('assistantSpend: without a LiteLLM source (the page) it says so', (await HS.assistantSpend({ now: NOW })).ok === false);

  // reminders: shown from warn_days before the date, overdue after it, the soonest first, bad entries reported
  const T = Date.UTC(2026, 10, 14, 15, 30);   // 2026-11-14 15:30Z
  const R = HS.reminders([
    { text: 'far', due: '2026-12-30', warn_days: 14 },
    { text: 'soon', due: '2026-11-20', warn_days: 14, link: 'https://x' },
    { text: 'edge', due: '2026-11-28', warn_days: 14 },
    { text: 'past edge', due: '2026-11-29', warn_days: 14 },
    { text: 'today', due: '2026-11-14', warn_days: 0 },
    { text: 'late', due: '2026-11-10', warn_days: 3 },
    { text: 'no date', warn_days: 3 }, { text: 'bad date', due: '14.11.2026', warn_days: 3 },
    { text: 'no warn', due: '2026-11-20' }, { due: '2026-11-20', warn_days: 1 },
  ], T);
  check('reminders: inside the window and overdue shown, soonest first; outside it not',
    R.items.map(r => r.text + ':' + r.days + ':' + r.state).join() === 'late:-4:overdue,today:0:soon,soon:6:soon,edge:14:soon', R.items);
  check('reminders: the link is kept', R.items.find(r => r.text === 'soon').link === 'https://x', R.items);
  check('reminders: a bad entry makes ok false and is named, not dropped silently',
    R.ok === false && R.bad.length === 4 && R.bad.includes('no date') && R.bad.includes('bad date') && R.bad.includes('no warn'), R.bad);
  check('reminders: days count calendar days in UTC, not 24 h from now',
    HS.reminders([{ text: 'x', due: '2026-11-15', warn_days: 1 }], Date.UTC(2026, 10, 14, 23, 59)).items[0].days === 1);
  const repo = HS.reminders(JSON.parse(require('fs').readFileSync(require('path').join(__dirname, 'reminders.json'), 'utf8')), T);
  check('reminders: the repo\'s reminders.json is understood, every entry', repo.ok && repo.bad.length === 0, repo.bad);
  check('reminders: not a list is nothing, not a crash', HS.reminders(null, T).items.length === 0 && HS.reminders(null, T).ok);

  // all: one failing area does not hide the rest
  const all = await HS.all({ now: NOW, q: async e => { if (e.includes('delivery')) throw new Error('boom'); return []; }, alerts: async () => [] });
  check('all: a throwing area is reported as an error, the others still present', all.delivery.error === 'boom' && all.sites.state === 'stale' && all.takenAt, all.delivery);

  console.log(failed ? 'TEST_STATUS FAIL (' + failed + ')' : 'TEST_STATUS PASS');
  process.exit(failed ? 1 : 0);
})();
