// The hub's status semantics, in one place (RFC-0008, section 0). Each function queries, decides and
// returns data; it never touches the page. The page draws from it, and a Node job on the mini runs
// the same functions and writes status.json for the briefing and the assistant.
//
// src: { q(promql) -> [{metric, value:[ts, "v"]}], alerts() -> alertmanager v2 list, now: unix seconds }
(function (root) {
  'use strict';
  const v = r => (r && r.length ? +r[0].value[1] : null);
  const one = async (src, e) => v(await src.q(e));
  const byLabel = async (src, e, key) => { const m = {}; (await src.q(e)).forEach(r => { m[r.metric[key]] = +r.value[1]; }); return m; };

  // Sites: outside-in probes (job site-probe). A probe only counts while the mini itself reaches the
  // internet, so a mini outage reads "unknown", not "every site down".
  const PROBE = 'probe_success{job="site-probe",run_id=""}';
  const PROBE_OK = '(max by (host) (' + PROBE + ') and on () (last_over_time(mini_vm_egress_ok{instance="homelab",target="internet"}[5m]) == 1))';
  async function sites(src) {
    const cur = await byLabel(src, 'max by (host) (last_over_time(' + PROBE + '[3m]))', 'host');
    const d1 = await byLabel(src, 'avg_over_time(' + PROBE_OK + '[24h:1m])', 'host');
    const eg = await one(src, 'last_over_time(mini_vm_egress_ok{instance="homelab",target="internet"}[5m])');
    const hosts = Object.keys(cur).sort(), offline = eg === 0;
    const down = hosts.filter(h => cur[h] === 0);
    const below = hosts.filter(h => d1[h] != null && d1[h] < 0.999);
    let lowest = null; hosts.forEach(h => { if (d1[h] != null && (lowest == null || d1[h] < d1[lowest])) lowest = h; });
    const avail = hosts.map(h => d1[h]).filter(x => x != null);
    const state = !hosts.length || offline ? 'stale' : (down.length ? 'down' : (below.length ? 'mid' : 'up'));
    return {
      state, up: hosts.length - down.length, total: hosts.length, down, offline,
      avail24h: avail.length ? avail.reduce((a, b) => a + b, 0) / avail.length : null,
      lowest: lowest ? { host: lowest, avail24h: d1[lowest] } : null,
      below999: below.map(h => ({ host: h, avail24h: d1[h] })), hosts: hosts.map(h => ({ host: h, up: cur[h] === 1, avail24h: d1[h] ?? null })),
    };
  }

  // Boxes: a collector is fresh under 3 minutes, lagging after, gone when no sample comes back.
  const BOX_SIGNAL = { mini: 'mini_cpu_used_percent', dgx: 'DCGM_FI_DEV_GPU_TEMP', x3: 'node_load1{instance="x3"}', prod: 'node_load1{instance="prod-podcast"}' };
  async function boxes(src) {
    const out = {};
    for (const [box, e] of Object.entries(BOX_SIGNAL)) {
      const r = await src.q(e), ts = r.length ? +r[0].value[0] : null, age = ts == null ? null : Math.round(src.now - ts);
      out[box] = { state: age == null ? 'down' : (age < 180 ? 'up' : 'stale'), ageSeconds: age };
    }
    return out;
  }

  // Close Listening prod health (podcast_scraper prod-ops-health): 1 green, 0.5 orange, 0 red. The
  // pusher runs daily; older than 26 hours means the check itself is not running: stale, never green.
  const PH_EXPECTED = ['gateway', 'o11y_logs', 'o11y_metrics', 'o11y_traces', 'o11y_glitchtip'];
  async function podcast(src) {
    const A = '{app="podcast"}';
    const ts = await one(src, 'last_over_time(prod_ops_health_last_run_timestamp' + A + '[28h])');
    const agg = await one(src, 'last_over_time(prod_ops_health_aggregate' + A + '[28h])');
    const stale = ts == null || src.now - ts > 26 * 3600;
    const st = x => (x == null || stale ? 'stale' : (x === 1 ? 'up' : (x === 0 ? 'down' : 'mid')));
    const checks = {};
    (await src.q('last_over_time(prod_ops_health_check' + A + '[28h])')).forEach(r => { checks[r.metric.check] = st(+r.value[1]); });
    // an expected check with no sample is "no data" (null), not "stale"
    PH_EXPECTED.forEach(c => { if (!(c in checks)) checks[c] = null; });
    return { state: agg == null ? 'stale' : st(agg), known: agg != null, stale, ageHours: ts == null ? null : Math.floor((src.now - ts) / 3600), checks };
  }

  // Alerts: one notification surface (Grafana's alertmanager). Plumbing states are wiring problems,
  // counted apart and never shown as incidents. One entry per alertname + instance.
  const PLUMB = new Set(['DatasourceNoData', 'DatasourceError', 'Watchdog']);
  async function alerts(src) {
    let list = [];
    try { list = await src.alerts(); } catch (e) { return { ok: false, critical: [], warning: [], plumbing: 0 }; }
    const seen = new Set(), uniq = [];
    for (const a of list.filter(a => (a.status || {}).state === 'active')) {
      const l = a.labels || {}, k = l.alertname + '|' + (l.instance || '');
      if (!seen.has(k)) { seen.add(k); uniq.push(a); }
    }
    const item = a => { const l = a.labels || {}, an = a.annotations || {};
      return { name: l.alertname, instance: l.instance || null, severity: l.severity || null, summary: an.summary || null, since: a.startsAt || null, substrate: l.meta === 'true' }; };
    const real = uniq.filter(a => !PLUMB.has((a.labels || {}).alertname));
    return {
      ok: true,
      critical: real.filter(a => (a.labels || {}).severity === 'critical').map(item),
      warning: real.filter(a => (a.labels || {}).severity !== 'critical').map(item),
      plumbing: uniq.length - real.length,
    };
  }

  // Needs you: actionable now only, the triage fleet's bug queue plus its escalations of the last 7
  // days. Config-enhancement and cleanup drafts are backlog, not operator debt (2026-08-05).
  async function needsYou(src) {
    const bug = await one(src, 'sum(last_over_time(signal_fleet_queue_depth{kind="bug"}[2h]))');
    const esc = await one(src, 'sum(last_over_time(signal_fleet_escalations_7d[2h]))');
    return { total: bug == null && esc == null ? null : (bug || 0) + (esc || 0), bugQueue: bug, escalations7d: esc };
  }

  // Delivery: the lamp follows the delivery alert rules: red when a worker is down; amber on
  // bounce/complaint over 5%, a dead letter in the last hour, the events cursor older than an hour,
  // or mail pending with nothing sent for an hour; grey when there are no workers to read.
  async function delivery(src) {
    const up = await one(src, 'sum(up{job="delivery"})'), tot = await one(src, 'count(up{job="delivery"})');
    const br = await one(src, 'sum(rate(delivery_sent_total{status=~"bounced|complaint"}[1h]))/clamp_min(sum(rate(delivery_sent_total{status=~"delivered|bounced|complaint"}[1h])),1)*100');
    const dead1 = await one(src, 'sum(increase(delivery_sent_total{status="dead_lettered"}[1h]))');
    const sent1 = await one(src, 'sum(increase(delivery_sent_total{status="delivered"}[1h]))');
    const pend = await one(src, 'sum(delivery_batch_pending)'), ca = await one(src, 'max(delivery_events_cursor_age_seconds)');
    const n = x => x || 0, t = tot || 0, reasons = [];
    if (n(br) > 5) reasons.push('bounce/complaint ' + n(br).toFixed(1) + '%');
    if (n(dead1) > 0) reasons.push(n(dead1).toFixed(0) + ' dead-lettered in the last hour');
    if (n(ca) > 3600) reasons.push('events cursor ' + Math.round(n(ca) / 60) + ' min old');
    if (n(pend) > 0 && n(sent1) === 0) reasons.push(n(pend).toFixed(0) + ' pending, nothing sent in an hour');
    const state = !t ? 'stale' : (n(up) < t ? 'down' : (reasons.length ? 'mid' : 'up'));
    return { state, workersUp: n(up), workers: t, reasons };
  }

  // OpenRouter credit: credits minus usage, as OpenRouter reports them (account totals). Low below $10,
  // the threshold of the billing-openrouter-credit-low alert.
  async function credit(src) {
    const left = await one(src, 'max(last_over_time(openrouter_account_usd{kind="credits"}[2h])) - max(last_over_time(openrouter_account_usd{kind="usage"}[2h]))');
    return { leftUsd: left, low: left != null && left < 10 };
  }

  // OpenRouter spend: per key x model series with a key (key!="": the old collector's keyless series
  // double-count), as the Spend tab sums them. Completed UTC days, as the collector windows them.
  async function spend(src) {
    const w = win => one(src, 'sum(last_over_time(openrouter_model_usd{window="' + win + '",key!=""}[2h]))');
    const y = await w('yesterday'), d7 = await w('7d'), m = await w('month');
    return { yesterdayUsd: y, avg7dUsd: d7 == null ? null : d7 / 7, monthUsd: m };
  }

  // Capacity, as numbers only: disk free and memory used per box. Warnings are not decided here; the
  // disk and memory alert rules decide them (see alerts).
  async function capacity(src) {
    const pct = e => one(src, e);
    return {
      mini: {
        diskFreePct: await pct('100*node_filesystem_avail_bytes{instance="homelab",mountpoint="/System/Volumes/Data"}/node_filesystem_size_bytes{instance="homelab",mountpoint="/System/Volumes/Data"}'),
        memUsedPct: await pct('mini_mem_used_percent'), swapBytes: await pct('mini_swap_used_bytes'),
      },
      dgx: {
        diskFreePct: await pct('100*node_filesystem_avail_bytes{instance="dgx-llm-1",mountpoint="/"}/node_filesystem_size_bytes{instance="dgx-llm-1",mountpoint="/"}'),
        memUsedPct: await pct('100-node_memory_MemAvailable_bytes{instance="dgx-llm-1"}/node_memory_MemTotal_bytes{instance="dgx-llm-1"}*100'),
      },
      prod: {
        diskFreePct: await pct('100*node_filesystem_avail_bytes{instance="prod-podcast",mountpoint="/"}/node_filesystem_size_bytes{instance="prod-podcast",mountpoint="/"}'),
        memUsedPct: await pct('100-node_memory_MemAvailable_bytes{instance="prod-podcast"}/node_memory_MemTotal_bytes{instance="prod-podcast"}*100'),
      },
    };
  }

  // GlitchTip: issues first seen since `from` (unix seconds), newest first. One definition of "new error"
  // for status.json (last 24 h) and the briefing (its overnight window). src.glitchtip(path) returns the
  // parsed API response; the page has no GlitchTip token, so it never calls this.
  async function newIssues(src, from) {
    const list = await src.glitchtip('/api/0/organizations/homelab/issues/?query=&limit=100&sort=-first_seen');
    return list.filter(i => i.firstSeen && Date.parse(i.firstSeen) / 1000 >= from)
      .map(i => ({ id: i.shortId, project: (i.project || {}).slug || null, title: i.title, count: +i.count || 0,
                   firstSeen: i.firstSeen, status: i.status || null, link: 'https://glitchtip.tail6d0ed4.ts.net/homelab/issues/' + i.id }));
  }
  // Open = still unresolved. New issues already resolved or ignored are counted, not listed: they need
  // nobody, and listing them made the assistant's answers differ run to run (operator, 2026-11-04).
  const isOpen = i => i.status === 'unresolved';
  async function errors(src) {
    if (!src.glitchtip) return { ok: false, reason: 'no GlitchTip source' };
    const list = await newIssues(src, src.now - 86400), open = list.filter(isOpen);
    return { ok: true, windowHours: 24, newCount: open.length, new: open, resolvedCount: list.length - open.length };
  }

  // Alert state changes from Grafana's state history (annotations), oldest first: fired = into Alerting,
  // resolved = Alerting back to Normal. Plumbing states left out. src.annotations(fromMs, toMs).
  async function alertChanges(src, fromMs, toMs) {
    const out = [];
    for (const a of await src.annotations(fromMs, toMs)) {
      const ns = a.newState || '', ps = a.prevState || '', name = a.alertName || '';
      if (!name || PLUMB.has(name)) continue;
      const fired = ns.startsWith('Alerting') && !ps.startsWith('Alerting');
      const resolved = ns.startsWith('Normal') && ps.startsWith('Alerting');
      if (!fired && !resolved) continue;
      // text: "<name> {k=v, k=v, ...} - q=..."; values may hold ", " (alert names do), keys never do
      const body = (/\{(.*)\}/.exec(a.text || '') || [])[1] || '', lab = {};
      body.split(/, (?=[a-z_]+=)/).forEach(kv => { const i = kv.indexOf('='); if (i > 0) lab[kv.slice(0, i)] = kv.slice(i + 1); });
      out.push({ at: a.time, name, instance: lab.instance || null, host: lab.host || null, severity: lab.severity || null,
                 // a provider incident's own name, stage and page (Cloudflare, Hetzner status alerts)
                 detail: [lab.name, lab.status, lab.impact && 'impact ' + lab.impact].filter(Boolean).join(', ') || null,
                 link: lab.link || null, change: fired ? 'fired' : 'resolved', annotationId: a.id });
    }
    return out.sort((a, b) => a.at - b.at);
  }

  // Incident timeline (use case H7): what happened between fromMs and toMs, oldest first, one entry per
  // event, each with its source and a reference that finds it there, so every time in a write-up can be
  // traced. Sources: alert state changes (Grafana), ops events (VictoriaLogs ops_event/v1: deploys,
  // backups, drills, drift, failed CI runs; passing, cancelled and skipped left out: 299 runs in 48 h on 2026-11-04), GlitchTip issues
  // first seen, containers started (the inventory keeps only each container's latest start). A failed
  // source is named in `missing`, never read as "nothing happened". src: annotations, logs(logsql), glitchtip, q.
  // Grouped by kind, and "last night" computed here: picking 8 deploys out of 120 mixed events, and working
  // out which night is "last night", is where the model failed (2026-11-04: invented deploys, the wrong night).
  const localTime = ms => new Date(ms).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  const KINDS = ['alert', 'deploy', 'backup', 'drill', 'drift', 'ci_failure', 'error', 'container_start'];
  // last night: 19:00 to 07:00 (local), the one that ended at the latest 07:00 at or before toMs
  function lastNightWindow(toMs) {
    const end = new Date(toMs); end.setHours(7, 0, 0, 0); if (end.getTime() > toMs) end.setDate(end.getDate() - 1);
    const start = new Date(end); start.setDate(start.getDate() - 1); start.setHours(19, 0, 0, 0);
    return [start.getTime(), end.getTime()];
  }
  async function timeline(src, fromMs, toMs) {
    const events = [], missing = [];
    const add = async (label, f) => { try { (await f()).forEach(e => events.push(e)); } catch (e) { missing.push(label + ': ' + (e && e.message || e)); } };
    await add('alert history (Grafana)', async () => (await alertChanges(src, fromMs, toMs)).map(c => ({
      at: c.at, kind: 'alert', what: 'alert ' + c.change + ': ' + c.name + ((c.host || c.instance) ? ' on ' + (c.host || c.instance) : '') + (c.detail ? ' (' + c.detail + ')' : ''),
      severity: c.severity, ref: 'Grafana annotation ' + c.annotationId + (c.link ? ', ' + c.link : '') })));
    const span = Math.max(60, Math.ceil((toMs - fromMs) / 1000));
    await add('ops events (VictoriaLogs)', async () => (await src.logs('_time:' + span + 's schema:"ops_event/v1" (event_type:(deploy OR backup OR drill OR drift) OR (event_type:ci_run status:failure))'))
      .filter(l => Date.parse(l._time) >= fromMs && Date.parse(l._time) <= toMs)
      .map(l => ({ at: Date.parse(l._time), kind: l.event_type === 'ci_run' ? 'ci_failure' : l.event_type,
                   what: l.event_type + ' ' + (l.status || '') + ': ' + (l._msg || '') + (l.app ? ' (' + l.app + (l.env ? ', ' + l.env : '') + ')' : ''),
                   ref: 'VictoriaLogs ops_event ' + l.event_type + ' _time ' + Math.floor(Date.parse(l._time) / 1000) + ' (unix)' })));
    await add('GlitchTip', async () => (await newIssues(src, fromMs / 1000)).filter(i => Date.parse(i.firstSeen) <= toMs).map(i => ({
      at: Date.parse(i.firstSeen), kind: 'error', what: 'new error ' + i.id + ' (' + (i.status || '?') + '): ' + i.title, ref: i.link })));
    await add('container inventory', async () => (await src.q('container_uptime_seconds{state="running"} < ' + Math.max(60, Math.round((src.now * 1000 - fromMs) / 1000))))
      .map(r => ({ at: Math.round(src.now * 1000 - (+r.value[1]) * 1000), box: r.metric.box, name: r.metric.name }))
      .filter(c => c.at <= toMs)
      .map(c => ({ at: c.at, kind: 'container_start', what: 'container started: ' + c.name + ' on ' + c.box, ref: 'container_uptime_seconds{box="' + c.box + '",name="' + c.name + '"}' })));
    events.sort((a, b) => a.at - b.at);
    const [n0, n1] = lastNightWindow(toMs), byKind = {};
    KINDS.forEach(k => { byKind[k] = []; });
    // line: the finished timeline line, "<local time> — <what> — <ref>", on the operator's clock (the job's
    // time zone). Built from three fields, the model dropped refs, dropped times and paired real refs with
    // invented times (2026-11-04, 4 runs); copying a line it picked is the whole task now. No UTC `at` next
    // to it: with one there, the model "copied" lines with the hour taken from it (7909 at 04:52, not 05:52).
    for (const e of events) {
      const ev = { line: localTime(e.at) + ' — ' + e.what + ' — ' + e.ref };
      if (e.severity) ev.severity = e.severity;
      if (e.at >= n0 && e.at < n1) ev.lastNight = true;
      (byKind[e.kind] = byKind[e.kind] || []).push(ev);
    }
    // last night across every kind, oldest first (byKind loses the order between kinds)
    const lastNightLines = events.filter(e => e.at >= n0 && e.at < n1).map(e => localTime(e.at) + ' — ' + e.what + ' — ' + e.ref);
    return { from: new Date(fromMs).toISOString(), to: new Date(toMs).toISOString(), count: events.length, lastNightLines,
             lastNight: { from: new Date(n0).toISOString(), to: new Date(n1).toISOString(), local: localTime(n0) + ' to ' + localTime(n1) },
             counts: Object.fromEntries(Object.entries(byKind).map(([k, v]) => [k, v.length])), byKind, missing };
  }

  // Fleet queue (use case H6): what the triage fleet wants from the operator. The count is the fleet's own
  // (needsYou: bug-queue proposals + escalations of the last 7 days, signal-fleet/mvp/inbox.py); the items
  // are the same two lists, each escalation linked to its issue through the fleet's filed ledger (newest
  // row for the fingerprint) and given the issue's state and title from GitHub. Also every OPEN escalated
  // issue of any age: the backlog the 7-day count leaves out. src.fleetFiles() -> {dispositions, filed,
  // queue} (parsed rows), src.github(path), src.fleetRepos. A repo GitHub refuses is named in `unreadable`.
  async function fleetQueue(src) {
    if (!src.fleetFiles) return { ok: false, reason: 'no fleet source' };
    const nowMs = Math.round(src.now * 1000), files = await src.fleetFiles(), unreadable = [];
    const lt = ms => new Date(ms).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    const filedFor = fp => files.filed.filter(r => r.fingerprint === fp).sort((a, b) => (a.filed_at < b.filed_at ? 1 : -1))[0] || null;
    const issues = {};
    const issue = async (repo, n) => {
      const k = repo + '#' + n;
      if (!(k in issues)) {
        try { const i = await src.github('/repos/' + repo + '/issues/' + n); issues[k] = { state: i.state, title: i.title }; }
        catch (e) { issues[k] = { state: null, title: null, error: String(e && e.message || e) }; }
      }
      return issues[k];
    };
    const escalations = [];
    for (const r of files.dispositions.filter(r => r.disposition === 'escalate' && Date.parse(r.ts) >= nowMs - 7 * 86400e3)
                                     .sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts))) {
      const f = filedFor(r.fingerprint);
      const gi = f ? await issue(f.repo, f.issue) : null;
      // "needs me" is open, not closed (operator, 2026-11-04; the fleet counts the same since 6a59983).
      // Unfiled stays; an issue GitHub cannot read (state null) stays.
      if (gi && gi.state === 'closed') continue;
      escalations.push({ local: lt(Date.parse(r.ts)), signal: (r.alertname || '').slice(0, 140), fingerprint: r.fingerprint,
                         reason: (r.reason || '').slice(0, 200),
                         issue: f ? Object.assign({ repo: f.repo, number: +f.issue, url: 'https://github.com/' + f.repo + '/issues/' + f.issue }, gi) : null });
    }
    const bugQueue = files.queue.filter(q => q.kind === 'bug').map(q => ({ title: q.title, fingerprint: q.fingerprint, queued: q.queued_at || null }));
    const openEscalated = [];
    for (const repo of src.fleetRepos) {
      try {
        const list = await src.github('/repos/' + repo + '/issues?state=open&labels=triage-fleet/escalated&per_page=100');
        list.filter(i => !i.pull_request).forEach(i => openEscalated.push({ repo, number: i.number, title: i.title, url: i.html_url,
          opened: lt(Date.parse(i.created_at)), ageDays: Math.floor((nowMs - Date.parse(i.created_at)) / 86400e3) }));
      } catch (e) { unreadable.push(repo + ': ' + (e && e.message || e)); }
    }
    openEscalated.sort((a, b) => a.ageDays - b.ageDays);
    // finished lines for the assistant, one list per question: with both lists side by side it answered
    // "9 things" with the first 9 open escalated issues (2026-11-04, both UIs)
    const needsYouLines = [
      ...escalations.map(e => e.local + ' — escalated: ' + e.signal + ' — ' +
        (e.issue ? e.issue.repo + '#' + e.issue.number + ' (' + (e.issue.state || 'state unknown') + ') ' + e.issue.url : 'no issue filed')),
      ...bugQueue.map(b => 'bug proposal waiting for your yes: ' + b.title)];
    const openEscalatedLines = openEscalated.map(i => i.repo + '#' + i.number + ' — ' + i.title + ' — open ' + i.ageDays + ' days — ' + i.url);
    return { ok: true, needsYou: bugQueue.length + escalations.length, bugQueue, escalations7d: escalations,
             openEscalated, openEscalatedCount: openEscalated.length, repos: src.fleetRepos, unreadable, needsYouLines, openEscalatedLines };
  }

  // Site analytics (Umami), for the assistant: per site, visitors and pageviews today, yesterday and the
  // last 7 days (with the 7 days before), and the 7 days' top pages, referrers, countries and click events.
  // Day boundaries are the job's local midnight, so the model never does date math. Dev sites (localhost)
  // are left out. src.umami(path) returns the parsed API response; a failing site is reported, not dropped.
  async function analytics(src) {
    if (!src.umami) return { ok: false, reason: 'no Umami source' };
    const now = Math.round(src.now * 1000), day = new Date(now); day.setHours(0, 0, 0, 0);
    const today = day.getTime(), yday = new Date(day); yday.setDate(yday.getDate() - 1);
    const wk = now - 7 * 86400e3;
    const sites = ((await src.umami('/api/websites?pageSize=100')).data || []).filter(w => w.domain && w.domain !== 'localhost');
    const stat = async (id, a, b) => { const s = await src.umami('/api/websites/' + id + '/stats?startAt=' + a + '&endAt=' + b);
      return { visitors: s.visitors, pageviews: s.pageviews, visits: s.visits, bouncePct: s.visits ? Math.round(100 * s.bounces / s.visits) : null }; };
    const top = async (id, type, n) => (await src.umami('/api/websites/' + id + '/metrics?startAt=' + wk + '&endAt=' + now + '&type=' + type + '&limit=' + n))
      .map(m => ({ name: m.x == null || m.x === '' ? '(none)' : m.x, count: m.y }));
    // one request at a time: the first live run sent ~60 at once through the lima port forward, and the
    // forward broke ~1.5 min later (2026-11-04 10:44Z). Not shown to be the cause; not worth the risk.
    const out = [];
    for (const w of sites) {
      try {
        const t = await stat(w.id, today, now), y = await stat(w.id, yday.getTime(), today);
        const l7 = await stat(w.id, wk, now), p7 = await stat(w.id, wk - 7 * 86400e3, wk);
        const pages = await top(w.id, 'path', 10), referrers = await top(w.id, 'referrer', 10);
        const countries = await top(w.id, 'country', 10), events = await top(w.id, 'event', 10);
        const active = (await src.umami('/api/websites/' + w.id + '/active')).visitors;
        out.push({ site: w.name, domain: w.domain, activeNow: active ?? null, today: t, yesterday: y, last7d: l7, previous7d: p7,
                   top7d: { pages, referrers: referrers.filter(r => r.name !== '(none)'), countries, events } });
      } catch (e) { out.push({ site: w.name, domain: w.domain, error: String(e && e.message || e) }); }
    }
    const lt = ms => new Date(ms).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    return { ok: true, takenAt: new Date(now).toISOString(),
             periods: { today: lt(today) + ' to now', yesterday: lt(yday.getTime()) + ' to ' + lt(today), last7d: lt(wk) + ' to now', previous7d: lt(wk - 7 * 86400e3) + ' to ' + lt(wk) },
             sites: out.sort((a, b) => ((b.last7d || {}).visitors || 0) - ((a.last7d || {}).visitors || 0)) };
  }

  // Everything, with when it was taken; each area isolated so one failing source does not hide the rest.
  const AREAS = { sites, boxes, podcast, alerts, needsYou, delivery, credit, spend, capacity, errors };
  async function all(src) {
    const out = { takenAt: new Date(src.now * 1000).toISOString() };
    for (const [k, f] of Object.entries(AREAS)) {
      try { out[k] = await f(src); } catch (e) { out[k] = { error: String(e && e.message || e) }; }
    }
    return out;
  }

  const api = { sites, boxes, podcast, alerts, needsYou, delivery, credit, spend, capacity, errors, newIssues, isOpen, alertChanges, timeline, analytics, fleetQueue, all, AREAS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.HubStatus = api;
})(typeof window !== 'undefined' ? window : globalThis);
