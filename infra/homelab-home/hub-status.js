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
  const BOX_SIGNAL = { mini: 'mini_cpu_used_percent', dgx: 'DCGM_FI_DEV_GPU_TEMP', prod: 'node_load1{instance="prod-podcast"}' };
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

  // Everything, with when it was taken; each area isolated so one failing source does not hide the rest.
  const AREAS = { sites, boxes, podcast, alerts, needsYou, delivery, credit, spend, capacity };
  async function all(src) {
    const out = { takenAt: new Date(src.now * 1000).toISOString() };
    for (const [k, f] of Object.entries(AREAS)) {
      try { out[k] = await f(src); } catch (e) { out[k] = { error: String(e && e.message || e) }; }
    }
    return out;
  }

  const api = { sites, boxes, podcast, alerts, needsYou, delivery, credit, spend, capacity, all, AREAS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.HubStatus = api;
})(typeof window !== 'undefined' ? window : globalThis);
