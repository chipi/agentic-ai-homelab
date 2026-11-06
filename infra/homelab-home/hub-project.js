// The Projects tab: one page per app (#projects/<app>/<period>/<compare>/<audience>), in bands —
// usage (Umami), delivery (the app's request metrics, the Cloudflare edge, the uptime probes) and
// jobs (its scheduled work) — each a row of cards and a set of charts, every number set against a
// comparison (the previous period, the same day last week, or the average of earlier periods).
// gen.sh inlines this file; test_project.js runs it.
//
// The page code supplies the data access as `src` (same-origin proxies only):
//   src.vmRange(expr, start, end, step) -> [[t, v], ...]   VictoriaMetrics query_range (/vm/)
//   src.vmAt(expr, t)                   -> number | null     VictoriaMetrics instant query (/vm/)
//   src.vmVec(expr, t)                  -> [{metric, value}] VictoriaMetrics instant vector (/vm/)
//   src.sql(sql)                        -> [{col: value}]    Umami Postgres through Grafana (umami-pg)
//   src.vl(query)                       -> [{field: value}]  VictoriaLogs (/vl/select/)
//   src.now()                           -> seconds
'use strict';
(function (root) {
  const DAY = 86400, HOUR = 3600;
  const PERIODS = { today: 'Today', '7d': '7 days', '30d': '30 days' };
  const COMPARES = { prev: 'Previous period', week: 'Same day last week', avg: 'Average' };
  const AUDIENCES = { all: 'Everyone', beta: 'Beta users' };

  // The period's window. Today: the UTC day in hours. 7d / 30d: whole UTC days ending with today.
  // A band with `daily: true` (jobs) always uses days, and at least 7 of them.
  function windowFor(period, nowS, daily) {
    const today = Math.floor(nowS / DAY) * DAY;
    if (period === 'today' && !daily) return { start: today, end: today + DAY, step: HOUR, n: 24, len: DAY };
    const n = period === '30d' ? 30 : 7;
    return { start: today + DAY - n * DAY, end: today + DAY, step: DAY, n, len: n * DAY };
  }
  // How far back each comparison window sits. "Same day last week" only differs from the previous
  // period for Today; "Average" is the mean of the earlier periods (7 days, 4 weeks, 3 months).
  function shifts(period, compare, w) {
    if (compare === 'week') return [7 * DAY];
    if (compare === 'avg') {
      const k = period === 'today' ? 7 : period === '7d' ? 4 : 3, unit = period === 'today' ? DAY : w.len;
      return Array.from({ length: k }, (_, i) => (i + 1) * unit);
    }
    return [w.len];
  }
  function compareLabel(period, compare) {
    if (compare === 'week') return 'same day last week';
    if (compare === 'avg') return period === 'today' ? 'average of the last 7 days' : period === '7d' ? 'average of the last 4 weeks' : 'average of the last 3 months';
    return period === 'today' ? 'yesterday' : period === '7d' ? 'the 7 days before' : 'the 30 days before';
  }
  // Points [t, v] (t = bucket start) into the window's n slots, moved forward by `shift`.
  function align(points, w, shift) {
    const out = Array(w.n).fill(null);
    for (const [t, v] of points || []) {
      const i = Math.floor((+t + shift - w.start) / w.step);
      if (i >= 0 && i < w.n && v != null && isFinite(v)) out[i] = (out[i] || 0) + +v;
    }
    return out;
  }
  const mean = xs => { const ys = xs.filter(x => x != null && isFinite(x)); return ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : null; };
  // Element-wise mean of several aligned series (the "Average" comparison).
  function combine(series) {
    if (!series.length) return [];
    return series[0].map((_, i) => mean(series.map(s => s[i])));
  }

  // Numbers: counts stay whole; the change is shown as a difference, not a percentage, because
  // the counts are small (a handful of sessions a day) and a percentage of 2 means little.
  function fmt(v, unit) {
    if (v == null || !isFinite(v)) return '&mdash;';
    if (unit === 's') return v < 1 ? Math.round(v * 1000) + ' ms' : v.toFixed(v < 10 ? 2 : 1) + ' s';
    if (unit === 'h') return v.toFixed(1) + ' h';
    if (unit === '%') return (v * 100).toFixed(v < 0.001 || v > 0.999 ? 2 : 1) + '%';
    return v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e4 ? (v / 1e3).toFixed(1) + 'k' : String(Math.round(v * 10) / 10);
  }
  function delta(cur, cmp, unit, up) {
    if (cur == null || cmp == null) return { text: 'no comparison', cls: 'flat' };
    const d = cur - cmp, eps = unit === 's' ? 0.005 : unit === '%' ? 0.0005 : unit === 'h' ? 0.05 : 0.5;
    if (Math.abs(d) < eps) return { text: '= ' + fmt(cmp, unit), cls: 'flat' };
    const better = up === false ? d < 0 : d > 0;
    const mag = unit === 's' || unit === 'h' || unit === '%' ? fmt(Math.abs(d), unit) : fmt(Math.abs(d));
    return { text: (d > 0 ? '&#9650; ' : '&#9660; ') + mag + ' vs ' + fmt(cmp, unit), cls: better ? 'good' : 'bad' };
  }
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // A small line for a card: the current period only.
  function sparkline(cur) {
    const xs = cur.filter(x => x != null);
    if (xs.length < 2) return '';
    const w = 64, h = 18, mx = Math.max(...xs) || 1;
    const pts = cur.map((x, i) => x == null ? null : (i * (w - 2) / (cur.length - 1) + 1).toFixed(1) + ',' + (h - 1 - x / mx * (h - 2)).toFixed(1)).filter(Boolean).join(' ');
    return '<svg width=' + w + ' height=' + h + ' viewBox="0 0 ' + w + ' ' + h + '" class=sl><polyline points="' + pts + '" fill=none stroke=#7aa2ff stroke-width=1.5 /></svg>';
  }
  // The chart: the current period (solid) over the comparison (dashed), same axes, with each
  // point's value in its tooltip.
  function chart(m, cur, cmp, w, cmpText) {
    const W = 600, H = 150, L = 46, B = 20, T = 8, all = cur.concat(cmp).filter(x => x != null);
    const mx = (Math.max(...all, 0) || 1) * 1.1;     // an all-zero chart labels its top 1, not 0.9
    const X = i => L + (w.n === 1 ? 0 : i * (W - L - 6) / (w.n - 1)), Y = v => T + (H - T - B) * (1 - v / mx);
    const line = (s, cls) => {
      let d = '', pen = false;
      s.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); pen = true; });
      return d ? '<path d="' + d + '" class=' + cls + ' />' : '';
    };
    const lab = i => { const t = w.start + i * w.step, dt = new Date(t * 1000); return w.step === HOUR ? String(dt.getUTCHours()).padStart(2, '0') + ':00' : (dt.getUTCMonth() + 1) + '-' + String(dt.getUTCDate()).padStart(2, '0'); };
    const ticks = [0, Math.floor((w.n - 1) / 2), w.n - 1].filter((x, i, a) => a.indexOf(x) === i);
    const dots = cur.map((v, i) => v == null ? '' : '<circle cx=' + X(i).toFixed(1) + ' cy=' + Y(v).toFixed(1) + ' r=2.5 class=pc><title>' + lab(i) + ': ' + fmt(v, m.unit).replace('&mdash;', '-') + (cmp[i] != null ? ' (' + cmpText + ': ' + fmt(cmp[i], m.unit) + ')' : '') + '</title></circle>').join('');
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class=pchart role=img aria-label="' + esc(m.label) + '">'
      + '<line x1=' + L + ' y1=' + Y(0) + ' x2=' + W + ' y2=' + Y(0) + ' class=pax />'
      + '<text x=' + (L - 6) + ' y=' + (T + 8) + ' class=pyl>' + (m.unit === '%' ? Math.round(mx / 1.1 * 100) + '%' : fmt(mx / 1.1, m.unit)) + '</text>'
      + '<text x=' + (L - 6) + ' y=' + Y(0) + ' class=pyl>0</text>'
      // the first and last dates sit inside the chart's edges, not centred on them (clipped otherwise)
      + ticks.map(i => '<text x=' + X(i).toFixed(1) + ' y=' + (H - 4) + ' class=pxl' + (i === 0 && w.n > 1 ? ' style="text-anchor:start"' : i === w.n - 1 && w.n > 1 ? ' style="text-anchor:end"' : '') + '>' + lab(i) + '</text>').join('')
      + line(cmp, 'pcmp') + line(cur, 'pcur') + dots + '</svg>';
  }

  // ---- data ----------------------------------------------------------------------------------
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const ts = s => 'to_timestamp(' + Math.floor(s) + ')';
  const inList = ids => '(' + ids.map(i => "'" + i + "'").join(',') + ')';
  // An Umami metric is an aggregate over the events matching its condition, e.g.
  // { agg: 'count(distinct session_id)', cond: 'true' } or { agg: 'count(*)', cond: "event_name = 'x'" }.
  const msql = (m, range) => m.agg + ' filter (where (' + m.cond + ')' + (range ? ' and ' + range : '') + ')';
  // The Umami part of a band: card values for each range, chart points per bucket, and each
  // metric's first event (when it started being tracked), in three queries. Beta users only: the
  // app's own sessions (its operatorIds, Umami distinct_id) are left out.
  async function umamiPart(src, ms, app, audience, ranges, w, lo) {
    const ids = app.umamiIds || [];
    if (!ids.length || !ms.length) return {};
    let where = 'website_id in ' + inList(ids);
    const ops = (app.operatorIds || []).filter(i => UUID.test(i));
    if (audience === 'beta' && ops.length) {
      where += ' and session_id not in (select session_id from session where distinct_id in ' + inList(ops) + ')';
      const sites = (app.operatorSiteIds || []).filter(i => UUID.test(i));
      if (sites.length) where += ' and website_id not in ' + inList(sites);
    }
    const cols = [];
    ms.forEach(m => ranges.forEach(([a, b], j) => cols.push(msql(m, 'created_at >= ' + ts(a) + ' and created_at < ' + ts(b)) + ' as ' + m.id + '_' + j)));
    const card = (await src.sql('select ' + cols.join(', ') + ' from website_event where ' + where + ' and created_at >= ' + ts(lo)))[0] || {};
    const rows = await src.sql('select floor(extract(epoch from created_at) / ' + w.step + ') * ' + w.step + ' as t, ' + ms.map(m => msql(m) + ' as ' + m.id).join(', ')
      + ' from website_event where ' + where + ' and created_at >= ' + ts(lo) + ' group by 1 order by 1');
    const first = (await src.sql('select ' + ms.map(m => 'extract(epoch from min(created_at) filter (where ' + m.cond + ')) as ' + m.id).join(', ') + ' from website_event where website_id in ' + inList(ids)))[0] || {};
    const out = {};
    for (const m of ms) out[m.id] = { ranges: ranges.map((_, j) => card[m.id + '_' + j] == null ? null : +card[m.id + '_' + j]), points: rows.map(r => [+r.t, +r[m.id]]), first: first[m.id] == null ? Infinity : +first[m.id] };
    return out;
  }
  // VictoriaMetrics. Default: a card is one instant query over the elapsed part of the window (and
  // the same stretch of each comparison window); a chart is a range query at the window's step.
  // 'ratio': num / den the same way. 'hourly': the expression is a count per hour (a rolling 1 h
  // gauge such as Cloudflare's), sampled at each hour's end and summed.
  async function vmMetric(src, m, ranges, w, spans) {
    if (m.kind === 'hourly') {
      const pts = [];
      for (const [a, b] of spans) (await src.vmRange(m.expr, a + HOUR, Math.min(b, src.now()), HOUR)).forEach(([t, v]) => pts.push([+t - HOUR, +v]));
      const uniq = {}; pts.forEach(([t, v]) => uniq[t] = v);
      const P = Object.entries(uniq).map(([t, v]) => [+t, v]);
      // the gauge's first sample is where its comparisons can start (Cloudflare's 1 h window began
      // 2026-10-29 18:00; a week that only half has it would read as half the traffic)
      const first = P.length ? Math.min(...P.map(p => p[0])) : Infinity;
      return { ranges: ranges.map(([a, b]) => { const xs = P.filter(([t]) => t >= a && t + HOUR <= b + 1).map(x => x[1]); return xs.length ? xs.reduce((s, x) => s + x, 0) : null; }), points: P, first };
    }
    const at = (e, a, b) => src.vmAt(e.split('$W').join(Math.max(60, Math.round(b - a)) + 's'), b);
    const val = async (a, b) => {
      if (m.kind === 'ratio') { const n = await at(m.num, a, b), d = await at(m.den, a, b); return d ? (n || 0) / d : null; }
      return at(m.expr, a, b);
    };
    const rangesV = [];
    for (const [a, b] of ranges) rangesV.push(await val(a, b));
    const step = w.step + 's', pts = [];
    for (const [a, b] of spans) {
      if (m.kind === 'ratio') {
        const n = await src.vmRange(m.num.split('$W').join(step), a + w.step, b, w.step), d = await src.vmRange(m.den.split('$W').join(step), a + w.step, b, w.step);
        const nm = {}; n.forEach(([t, v]) => nm[t] = +v);
        d.forEach(([t, v]) => { if (+v) pts.push([+t - w.step, (nm[t] || 0) / +v]); });
      } else (await src.vmRange(m.expr.split('$W').join(step), a + w.step, b, w.step)).forEach(([t, v]) => pts.push([+t - w.step, +v]));
    }
    return { ranges: rangesV, points: pts };
  }
  // A metric with its own `rows(src, lo, hi)` -> [[t, value]] (log events, container lifetimes),
  // reduced in the page: a sum per range, or a mean ('mean').
  async function rowsMetric(src, m, ranges, w, lo) {
    const r = await m.rows(src, lo, src.now()), pick = (a, b) => r.filter(([t]) => t >= a && t < b).map(x => x[1]);
    return { ranges: ranges.map(([a, b]) => { const xs = pick(a, b); return m.kind === 'mean' ? mean(xs) : xs.reduce((s, x) => s + x, 0); }), points: r.map(([t, v]) => [Math.floor(t / w.step) * w.step, v]) };
  }

  // One band: its window, its card ranges ([start, now) and the same stretch of each comparison
  // window) and chart spans, fetched, then reduced to card values and aligned chart series.
  async function band(src, app, b, period, compare, audience) {
    // a daily band (jobs) reads Today as the last 7 nights: one night is not a trend
    if (b.daily && period === 'today') { period = '7d'; if (compare === 'week') compare = 'prev'; }
    const nowS = src.now(), w = windowFor(period, nowS, b.daily);
    const sh = shifts(period, compare, w);
    const upto = Math.min(nowS, w.end);
    const ranges = [[w.start, upto]].concat(sh.map(s => [w.start - s, upto - s]));
    const spans = [[w.start, w.end]].concat(sh.map(s => [w.start - s, w.end - s]));
    const lo = Math.min(...spans.map(s => s[0]));
    let data = {};
    try {
      data = await umamiPart(src, b.metrics.filter(m => m.agg), app, audience, ranges, w, lo);
    } catch (e) { data = {}; }
    for (const m of b.metrics) {
      if (m.agg) continue;
      try { data[m.id] = m.fetch ? await m.fetch(src, ranges, w, spans) : m.rows ? await rowsMetric(src, m, ranges, w, lo) : await vmMetric(src, m, ranges, w, spans); } catch (e) { /* no data for this card */ }
    }
    return b.metrics.map(m => {
      const d = data[m.id] || { ranges: [], points: [] };
      // A comparison window that starts before this metric has data — older than the source keeps
      // (VictoriaLogs: 30 days), before its tracking began (an Umami event's first occurrence), or
      // before the app's `since` — is left out: a count there reads 0 and would drag the comparison down.
      const first = Math.max(m.retention ? nowS - m.retention : -Infinity, d.first != null ? d.first : -Infinity, m.since || -Infinity, app.since || -Infinity);
      const counted = m.agg || m.rows || m.kind === 'hourly';
      // A VictoriaMetrics series (not a count of events) that has no point in a comparison window's
      // first bucket started inside that window: its value there covers only part of it (the probes'
      // response time read "vs 212 ms" from the last two days of a week).
      const covers = s => counted || d.points.some(([t]) => t >= w.start - s && t < w.start - s + w.step);
      const ok = sh.map(s => w.start - s >= first && covers(s));
      const series = s => {
        const pts = d.points.filter(([t]) => t >= w.start - s && t < w.end - s);
        const a = align(pts, w, s);
        if (m.kind === 'mean') { const cnt = align(pts.map(([t]) => [t, 1]), w, s); return a.map((v, i) => v == null ? null : v / cnt[i]); }
        // a count with no rows in a past bucket is 0 (Umami, log events and hourly samples only exist
        // where something happened); a mean with no rows stays empty
        if (counted) a.forEach((v, i) => { const t = w.start - s + i * w.step; if (v == null && t <= nowS && t >= first) a[i] = 0; });
        return a;
      };
      const cur = series(0), cmp = combine(sh.filter((_, j) => ok[j]).map(series));
      cur.forEach((_, i) => { if (w.start + i * w.step > nowS) cur[i] = null; });   // future buckets stay empty
      const cmpValue = mean(d.ranges.slice(1).filter((_, j) => ok[j]));
      return { m, w, period, compare, cur, cmp, value: d.ranges[0] == null ? null : d.ranges[0], cmpValue };
    });
  }

  function cardHtml(r, link) {
    const d = delta(r.value, r.cmpValue, r.m.unit, r.m.up);
    if (r.cmpValue != null) d.text += ' <span class=muted>(' + esc(compareLabel(r.period, r.compare)) + ')</span>';
    return '<a class="card pcard" href="' + esc(r.m.link || link || '#') + '" title="' + esc(r.m.help || '') + '"><h3>' + esc(r.m.label) + '</h3>'
      + '<div class=cv>' + fmt(r.value, r.m.unit) + sparkline(r.cur) + '</div>'
      + '<div class="pdelta ' + d.cls + '">' + d.text + '</div></a>';
  }
  function chartHtml(r, link) {
    const c = compareLabel(r.period, r.compare);
    return '<a class="card pchartcard" href="' + esc(r.m.link || link || '#') + '"><h3>' + esc(r.m.label) + (r.w.step === HOUR ? ' per hour' : ' per day') + '</h3>'
      + chart(r.m, r.cur, r.cmp, r.w, c)
      + '<div class=plegend><span class=lcur></span>' + (r.w.step === HOUR ? 'today' : 'this period') + ' <span class=lcmp></span>' + esc(c) + '</div></a>';
  }

  // Render one app's page into `el`. Bands render as they arrive, so a slow source does not hold
  // the others back.
  async function render(el, app, period, compare, src, audience) {
    audience = audience === 'beta' && (app.operatorIds || []).length ? 'beta' : 'all';
    const href = (p, c, a) => '#projects/' + app.id + '/' + p + '/' + c + '/' + a;
    const head = '<nav class=subtabs>' + Object.entries(PERIODS).map(([k, v]) => '<a href="' + href(k, compare === 'week' && k !== 'today' ? 'prev' : compare, audience) + '" target=_self' + (k === period ? ' class=on' : '') + '>' + v + '</a>').join('')
      + '<span style="flex:1"></span>' + Object.entries(COMPARES).filter(([k]) => k !== 'week' || period === 'today').map(([k, v]) => '<a href="' + href(period, k, audience) + '" target=_self' + (k === compare ? ' class=on' : '') + '>' + v + '</a>').join('')
      + ((app.operatorIds || []).length ? '<span style="width:12px"></span>' + Object.entries(AUDIENCES).map(([k, v]) => '<a href="' + href(period, compare, k) + '" target=_self' + (k === audience ? ' class=on' : '') + ' title="' + (k === 'beta' ? 'Usage without your own sessions' : 'Every session, yours included') + '">' + v + '</a>').join('') : '') + '</nav>'
      + '<p class=sec style="margin:-8px 0 14px">Each number is the ' + (period === 'today' ? 'day so far (UTC)' : 'last ' + PERIODS[period] + ' (UTC days, today so far)') + ' against ' + esc(compareLabel(period, compare)) + ', over the same stretch of time. Jobs count whole nights.'
      + (audience === 'beta' ? ' Usage leaves out your own sessions.' : '') + ' A comparison that reaches back before a number was tracked is left out.</p>';
    el.innerHTML = head + app.bands.map((b, i) => '<div class=pband id="pb_' + app.id + '_' + i + '"><h2>' + esc(b.title) + '</h2><p class=muted>loading&hellip;</p></div>').join('');
    await Promise.all(app.bands.map(async (b, i) => {
      const rs = await band(src, app, b, period, compare, audience);
      const box = el.querySelector ? el.querySelector('#pb_' + app.id + '_' + i) : null;
      const html = '<h2>' + esc(b.title) + (b.link ? ' <a href="' + esc(b.link) + '">&rarr;</a>' : '') + '</h2>' + (b.note ? '<p class=sec style="margin:-4px 0 8px">' + esc(b.note) + '</p>' : '')
        + '<div class=charts>' + rs.map(r => cardHtml(r, b.link)).join('') + '</div>'
        + '<div class=pcharts>' + rs.filter(r => r.m.chart).map(r => chartHtml(r, b.link)).join('') + '</div>';
      if (box) box.innerHTML = html; else el.innerHTML += html;
    }));
  }

  // ---- the apps -----------------------------------------------------------------------------
  const G = 'https://grafana.tail6d0ed4.ts.net';
  const visitors = { id: 'visitors', label: 'Visitors', agg: 'count(distinct session_id)', cond: 'true', chart: true, help: 'Distinct Umami sessions' };
  const visits = { id: 'visits', label: 'Visits', agg: 'count(distinct visit_id)', cond: 'true', help: 'Distinct visits (a visitor can visit several times)' };
  const views = { id: 'views', label: 'Page views', agg: 'count(*)', cond: 'event_type = 1', chart: true };
  const ev = (id, label, cond, extra) => Object.assign({ id, label, agg: 'count(*)', cond }, extra || {});
  const is = name => "event_name = '" + name + "'";
  // Delivery from outside: Cloudflare's rolling 1 h request counts per host (summed per hour), and
  // the uptime probes from the mini (availability and response time).
  const hostRe = hosts => hosts.map(h => h.replace(/\./g, '\\\\.')).join('|');
  // by who sent it (cloudflare-edge's traffic_source): Cloudflare's verified-bot verdict, then the
  // user agent; "browser" still includes bots that pose as one
  const bySource = (hosts, source) => 'sum(last_over_time(cloudflare_edge_requests_by_source{instance="homelab",window="1h",source=~"' + source + '",host=~"' + hostRe(hosts) + '"}[15m]))';
  const edge = (hosts, extra) => [
    Object.assign({ id: 'edge', label: 'Edge requests', kind: 'hourly', help: 'Every request Cloudflare answered for the hosts: browsers, bots, our own monitors and SDKs',
      expr: 'sum(last_over_time(cloudflare_edge_requests{instance="homelab",window="1h",host=~"' + hostRe(hosts) + '"}[15m]))' }, extra || {}),
    { id: 'edge_browser', label: 'Browser requests', kind: 'hourly', chart: true, help: 'Requests from browsers and the apps (user agent), not bots, monitors or SDKs. Since 2026-11-06.',
      expr: bySource(hosts, 'browser') },
    { id: 'edge_bot', label: 'Bot requests', kind: 'hourly', up: false, help: 'Crawlers, AI search, link previews and scanners: Cloudflare\'s verified bots and bot user agents. Since 2026-11-06.',
      expr: bySource(hosts, 'bot') },
    // 0 for an hour the gauge has requests but no 5xx; nothing before the gauge existed (a bare
    // `or vector(0)` read every hour before 2026-10-29 as a counted zero)
    { id: 'edge5xx', label: 'Edge 5xx', kind: 'hourly', up: false, help: 'Cloudflare answered 5xx: the origin failed (5xx_server) or was unreachable (52x)',
      expr: 'sum(last_over_time(cloudflare_edge_requests{instance="homelab",window="1h",class=~"5xx_server|5xx_unreachable",host=~"' + hostRe(hosts) + '"}[15m]))'
        + ' or (0 * sum(last_over_time(cloudflare_edge_requests{instance="homelab",window="1h",host=~"' + hostRe(hosts) + '"}[15m])))' },
    { id: 'avail', label: 'Availability', unit: '%', chart: true, help: 'Share of the minute-by-minute probes from the mini that succeeded (all the hosts)',
      expr: 'avg(avg_over_time(probe_success{job="site-probe",run_id="",host=~"' + hostRe(hosts) + '"}[$W]))' },
    { id: 'probe_s', label: 'Response time', unit: 's', up: false, chart: true, help: 'Mean time of the probe request (DNS, TLS, first byte), all the hosts',
      expr: 'avg(avg_over_time(probe_duration_seconds{job="site-probe",run_id="",host=~"' + hostRe(hosts) + '"}[$W]))' }];

  const CL = 'instance="prod-podcast"';
  // Background calls the apps make on their own (health checks, the outbox poll, auth and version
  // polls, internal MCP checks): left out of "App requests".
  const BG = 'handler!~"/internal/.*|/api/health|/metrics|/api/app/auth/status|/api/app/version"';
  const nightlyRows = async (src, lo, hi) => {
    // The nightly's run container (compose-pipeline-llm-run-*, cadvisor, VictoriaMetrics: 6 months):
    // per UTC day the first one started 00:00-02:00Z, its lifetime in hours. The enrichment
    // container that follows it is shorter and later, so it is never the first.
    const days = Math.max(1, Math.ceil((hi - lo) / DAY)), L = 'container_start_time_seconds{' + CL + ',name=~"compose-pipeline-llm-run-.*"}';
    const life = await src.vmVec('max by (name) (max_over_time(timestamp(' + L + ')[' + days + 'd:5m])) - max by (name) (max_over_time(' + L + '[' + days + 'd]))', hi);
    const start = await src.vmVec('max by (name) (max_over_time(' + L + '[' + days + 'd]))', hi);
    const st = {}; start.forEach(x => st[x.metric.name] = +x.value[1]);
    const byDay = {};
    life.forEach(x => { const s = st[x.metric.name]; if (s == null || s < lo || s % DAY >= 7200) return; const d = Math.floor(s / DAY); if (!byDay[d] || s < byDay[d][0]) byDay[d] = [s, +x.value[1] / 3600]; });
    return Object.values(byDay).sort((a, b) => a[0] - b[0]);
  };
  // p95 of what users wait for, from the APIs' access log lines ("-> 200 in 15.7ms trace=..."), which
  // carry the path, so the background calls can be left out (the route-less histogram cannot).
  const BG_PATH = '^(/internal/|/api/health|/metrics|/api/app/auth/status|/api/app/version)';
  const ACCESS = 'container:~"(player-api|operator-api|compose-api)-1" "trace=" | extract "] - <method> <path> -> <status> in <ms>ms trace=" | filter -path:~"' + BG_PATH + '"';
  const appP95 = async (src, ranges, w, spans) => {
    const q = async (a, b, by) => src.vl('_time:[' + Math.floor(a) + ', ' + Math.floor(b) + '] ' + ACCESS + ' | stats ' + (by ? 'by (_time:' + (w.step === HOUR ? '1h' : '1d') + ') ' : '') + 'quantile(0.95, ms) as p');
    const rangesV = [];
    for (const [a, b] of ranges) { const r = (await q(a, b))[0]; rangesV.push(r && r.p !== '' && r.p != null && !isNaN(+r.p) ? +r.p / 1000 : null); }
    const pts = [];
    for (const [a, b] of spans) (await q(a, Math.min(b, src.now()), true)).forEach(r => { if (r.p !== '' && !isNaN(+r.p)) pts.push([Date.parse(r._time) / 1000, +r.p / 1000]); });
    return { ranges: rangesV, points: pts };
  };
  const summaryRows = async (src, lo, hi) => (await src.vl('_time:[' + Math.floor(lo) + ', ' + Math.floor(hi) + '] instance:prod-podcast "Multi-feed run summary" | extract "episodes_processed=<n>" | fields _time, n'))
    .map(r => [Date.parse(r._time) / 1000, +r.n || 0]);
  const enrichFailRows = async (src, lo, hi) => (await src.vl('_time:[' + Math.floor(lo) + ', ' + Math.floor(hi) + '] instance:prod-podcast event_type:"enrichment.enricher.completed" -status:ok | fields _time'))
    .map(r => [Date.parse(r._time) / 1000, 1]);

  const APPS = {
    cl: {
      id: 'cl', name: 'Close Listening', umamiDomains: ['closelistening.app'],
      // The Player identifies its users to Umami (distinct_id), so "Beta users" can leave out the
      // operator's own sessions. Which id is the operator's is not in git (this repo is public): the
      // page sets operatorIds from HUB_OPERATOR_UMAMI_IDS in ~/homelab-hub.env on the mini (gen.sh).
      identifies: true,
      // The operator viewer is the operator's own UI (its sessions carry no distinct_id): "Beta users"
      // leaves the whole site out. A website id is public (each site's tracking script carries it).
      operatorSiteIds: ['a5a60c25-a555-4c2d-b096-c9814c21d25c'],
      bands: [
        { title: 'Usage', link: G + '/d/podcast-player-beta-analytics', note: 'Umami: the player app and the operator viewer together.',
          metrics: [visitors, visits,
            ev('screens', 'Screens viewed', "event_type = 1 or event_name = 'screen_view'", { chart: true }),
            ev('episodes', 'Episodes opened', is('episode_open'), { chart: true }),
            ev('plays', 'Plays started', is('play_start')),
            ev('searches', 'Searches', is('search_submitted')),
            ev('assistant', 'Assistant tool calls', "event_name like 'mcp\\_tool:%'", { chart: true, help: 'Close Listening MCP tools called from an assistant (mcp_tool:* events)' })] },
        { title: 'Delivery', link: G + '/d/podcast-performance',
          note: 'The three APIs (player, operator, podcast). App requests leave out the apps\' own background calls (health checks, the outbox and auth polls); the p95 covers every request, background ones included (the per-route histogram stops at 1 s).',
          metrics: [
            { id: 'app_req', label: 'App requests', chart: true, expr: 'sum(increase(http_requests_total{' + CL + ',' + BG + '}[$W]))', help: 'Requests to the APIs, without health checks, the outbox poll and the auth/version polls' },
            { id: 'bg_req', label: 'Background calls', expr: 'sum(increase(http_requests_total{' + CL + ',handler=~"/internal/.*|/api/health|/metrics|/api/app/auth/status|/api/app/version"}[$W]))', help: 'Health checks, the outbox poll, auth and version polls' },
            { id: 'app_p95', label: 'App p95 latency', unit: 's', up: false, chart: true, fetch: appP95, retention: 30 * DAY,
              help: 'p95 of the app requests (background calls left out), from the access log lines in VictoriaLogs (30 days)' },
            { id: 'p95', label: 'p95, all requests', unit: 's', up: false,
              help: 'p95 of every request, background calls included (the route-less histogram, 6 months)',
              expr: 'histogram_quantile(0.95, sum by (le) (increase(http_request_duration_highr_seconds_bucket{' + CL + '}[$W])))' },
            { id: 'slow1', label: 'App requests over 1 s', up: false, chart: true,
              expr: 'sum(increase(http_request_duration_seconds_count{' + CL + ',' + BG + '}[$W])) - sum(increase(http_request_duration_seconds_bucket{' + CL + ',' + BG + ',le="1.0"}[$W]))' },
            { id: 'slow', label: 'Requests over 10 s', up: false,
              expr: 'sum(increase(http_request_duration_highr_seconds_count{' + CL + '}[$W])) - sum(increase(http_request_duration_highr_seconds_bucket{' + CL + ',le="10.0"}[$W]))' },
            { id: 'err', label: '5xx share', unit: '%', up: false, kind: 'ratio',
              num: '(sum(increase(http_requests_total{' + CL + ',status=~"5.."}[$W])) or vector(0))', den: 'sum(increase(http_requests_total{' + CL + '}[$W]))' }] },
        { title: 'Edge and uptime', link: G + '/d/prod-uptime', note: 'From outside: Cloudflare for closelistening.app and its subdomains, and the uptime probes from the mini.',
          metrics: edge(['closelistening.app', 'mcp.closelistening.app', 'obs.closelistening.app', 'operator.closelistening.app']) },
        { title: 'Jobs', daily: true, link: G + '/d/podcast-jobs',
          note: 'The nightly pipeline (starts 00:00Z) and the enrichment after it, per night. Run time is the nightly container\'s lifetime (cadvisor, 6 months); episodes and enricher failures come from VictoriaLogs, which keeps 30 days.',
          metrics: [
            // since 2026-10-14: the nightly has started at 00:00Z from then on; before it ran on another
            // schedule, and the 00:00-02:00Z rule would pick other containers (0.4 h "nights")
            { id: 'nightly', label: 'Nightly run time', unit: 'h', up: false, kind: 'mean', chart: true, rows: nightlyRows, since: Date.UTC(2026, 9, 14) / 1000 },
            { id: 'processed', label: 'Episodes processed', chart: true, rows: summaryRows, retention: 30 * DAY, help: 'episodes_processed of every run summary (nightly and hand runs)' },
            { id: 'enrich_fail', label: 'Enricher failures', up: false, rows: enrichFailRows, retention: 30 * DAY, help: 'enricher runs that ended in a status other than ok' }] }] },
    orrery: {
      id: 'orrery', name: 'Orrery', umamiDomains: ['orrerylearn.com'],
      bands: [
        { title: 'Usage', note: 'Umami: orrerylearn.com.',
          metrics: [visitors, visits, views,
            ev('missions', 'Missions viewed', is('mission-view'), { chart: true }),
            ev('science', 'Science sections read', is('science-section-view')),
            ev('plans', 'Plans run', is('plan-run')),
            ev('tools', 'Assistant tool calls', is('tool-call'), { chart: true })] },
        { title: 'Edge and uptime', link: G + '/d/prod-uptime', note: 'Cloudflare for orrerylearn.com, the lab API and the MCP host, and the uptime probes.',
          metrics: edge(['orrerylearn.com', 'www.orrerylearn.com', 'lab-api.orrerylearn.com', 'mcp.orrerylearn.com']) }] },
    evals: {
      id: 'evals', name: 'Evals', umamiDomains: ['evals.humancopilot.eu'],
      bands: [
        { title: 'Usage', note: 'Umami: evals.humancopilot.eu.',
          metrics: [visitors, visits, views,
            ev('mcp', 'MCP calls (Umami)', "event_name like 'mcp:%'", { chart: true }),
            ev('outbound', 'Outbound clicks', "event_name like 'outbound%'")] },
        { title: 'Delivery', note: 'The inspector and its MCP server, from their own counters. Requests leave out health checks and /metrics.',
          metrics: [
            { id: 'req', label: 'Inspector requests', chart: true, expr: 'sum(increase(evals_inspector_requests_total{route!~"/api/health|/metrics"}[$W]))' },
            { id: 'ierr', label: 'Inspector errors', up: false, expr: 'sum(increase(evals_inspector_errors_total[$W])) or vector(0)' },
            { id: 'mcpc', label: 'MCP tool calls', chart: true, expr: 'sum(increase(evals_mcp_calls_total[$W]))' },
            { id: 'merr', label: 'MCP errors', up: false, expr: 'sum(increase(evals_mcp_errors_total[$W])) or vector(0)' },
            // /api/compare is most of it, and slow by its nature (2 of 8 under 1 s, 4 of 8 at 10-30 s,
            // 2026-10-31..11-06). The histogram jumps from 10 s to 30 s, so the p95 is an interpolation
            // on few requests; the count over 10 s says the same thing exactly.
            { id: 'islow', label: 'Inspector requests over 10 s', up: false, chart: true,
              expr: 'sum(increase(evals_inspector_request_seconds_count{route!~"/api/health|/metrics"}[$W])) - sum(increase(evals_inspector_request_seconds_bucket{route!~"/api/health|/metrics",le="10.0"}[$W]))' },
            { id: 'ip95', label: 'Inspector p95', unit: 's', up: false, help: 'Interpolated within the 10-30 s bucket on few requests: read with the count over 10 s',
              expr: 'histogram_quantile(0.95, sum by (le) (increase(evals_inspector_request_seconds_bucket{route!~"/api/health|/metrics"}[$W])))' }] },
        { title: 'Edge and uptime', link: G + '/d/prod-uptime', metrics: edge(['evals.humancopilot.eu']) }] },
    web: {
      id: 'web', name: 'Websites', umamiDomains: ['humancopilot.eu', 'markodragoljevic.com', 'airandspacehistory.com', 'devwhateverops.com'],
      bands: [
        { title: 'Usage', note: 'Umami: humancopilot.eu, markodragoljevic.com, airandspacehistory.com and devwhateverops.com together.',
          metrics: [visitors, visits, views,
            ev('outbound', 'Outbound clicks', "event_name like 'outbound%'"),
            ev('cta', 'Email clicks', "event_name like 'cta-email%'")] },
        { title: 'Edge and uptime', link: G + '/d/prod-uptime',
          metrics: edge(['humancopilot.eu', 'www.humancopilot.eu', 'markodragoljevic.com', 'www.markodragoljevic.com', 'airandspacehistory.com', 'devwhateverops.com', 'www.devwhateverops.com']) }] },
  };

  // The app with its Umami site ids, and the operator's own ids when the app identifies its users.
  function resolve(app, umamiSites, operatorIds) {
    const ops = app.identifies ? (operatorIds || []).filter(i => UUID.test(i)) : (app.operatorIds || []);
    return Object.assign({}, app, { operatorIds: ops, umamiIds: (umamiSites || []).filter(([dom, id]) => app.umamiDomains.includes(dom.replace(/^www\./, '')) && UUID.test(id)).map(x => x[1]) });
  }

  const api = { DAY, HOUR, PERIODS, COMPARES, AUDIENCES, APPS, windowFor, shifts, compareLabel, align, combine, fmt, delta, chart, sparkline, band, render, resolve };
  if (typeof module === 'object' && module.exports) module.exports = api; else root.HubProject = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
