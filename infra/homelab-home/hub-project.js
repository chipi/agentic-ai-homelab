// The Projects tab: one page per app (#projects/<app>/<period>/<compare>), in three bands — usage
// (Umami), delivery (the app's request metrics) and jobs (its scheduled work) — each band a row of
// cards and a set of charts, every number set against a comparison (the previous period, the same
// day last week, or the average of earlier periods). gen.sh inlines this file; test_project.js runs it.
//
// The page code supplies the data access as `src` (same-origin proxies only):
//   src.vmRange(expr, start, end, step) -> [[t, v], ...]   VictoriaMetrics query_range (/vm/)
//   src.vmAt(expr, t)                   -> number | null     VictoriaMetrics instant query (/vm/)
//   src.sql(sql)                        -> [{col: value}]    Umami Postgres through Grafana (umami-pg)
//   src.vl(query)                       -> [{field: value}]  VictoriaLogs (/vl/select/)
//   src.now()                           -> seconds
'use strict';
(function (root) {
  const DAY = 86400, HOUR = 3600;
  const PERIODS = { today: 'Today', '7d': '7 days', '30d': '30 days' };
  const COMPARES = { prev: 'Previous period', week: 'Same day last week', avg: 'Average' };

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
    if (unit === '%') return (v * 100).toFixed(v < 0.001 ? 2 : 1) + '%';
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
      + '<text x=' + (L - 6) + ' y=' + (T + 8) + ' class=pyl>' + fmt(mx / 1.1, m.unit) + '</text>'
      + '<text x=' + (L - 6) + ' y=' + Y(0) + ' class=pyl>0</text>'
      // the first and last dates sit inside the chart's edges, not centred on them (clipped otherwise)
      + ticks.map(i => '<text x=' + X(i).toFixed(1) + ' y=' + (H - 4) + ' class=pxl' + (i === 0 && w.n > 1 ? ' style="text-anchor:start"' : i === w.n - 1 && w.n > 1 ? ' style="text-anchor:end"' : '') + '>' + lab(i) + '</text>').join('')
      + line(cmp, 'pcmp') + line(cur, 'pcur') + dots + '</svg>';
  }

  // ---- data ----------------------------------------------------------------------------------
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const ts = s => "to_timestamp(" + Math.floor(s) + ")";
  // Every usage metric for the card ranges (current + each comparison) in one query, and the
  // per-bucket series for the charts in a second.
  async function umamiBand(src, band, ids, ranges, w, spans) {
    if (!ids.length) return null;
    const where = "website_id in (" + ids.map(i => "'" + i + "'").join(',') + ")";
    const cols = [];
    band.metrics.forEach(m => ranges.forEach(([a, b], j) => cols.push("(" + m.sql.replace('FILTER', "created_at >= " + ts(a) + " and created_at < " + ts(b)) + ") as " + m.id + "_" + j)));
    const lo = Math.min(...ranges.map(r => r[0]), ...spans.map(s => s[0]));
    const card = (await src.sql("select " + cols.join(', ') + " from website_event where " + where + " and created_at >= " + ts(lo)))[0] || {};
    const sel = band.metrics.map(m => "(" + m.sql.replace('FILTER', 'true') + ") as " + m.id).join(', ');
    const rows = await src.sql("select floor(extract(epoch from created_at) / " + w.step + ") * " + w.step + " as t, " + sel
      + " from website_event where " + where + " and created_at >= " + ts(lo) + " group by 1 order by 1");
    const out = {};
    for (const m of band.metrics) {
      out[m.id] = { ranges: ranges.map((_, j) => card[m.id + '_' + j] == null ? null : +card[m.id + '_' + j]), points: rows.map(r => [+r.t, +r[m.id]]) };
    }
    return out;
  }
  // VictoriaMetrics: a card is one instant query over the elapsed part of the window (and the same
  // stretch of each comparison window); a chart is a range query at the window's step.
  async function vmMetric(src, m, ranges, w, spans) {
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
  // VictoriaLogs: the band's rows, each [t, value] per metric, reduced in the page.
  async function vlBand(src, band, ranges, w, spans) {
    const lo = Math.min(...ranges.map(r => r[0]), ...spans.map(s => s[0])), hi = src.now();
    const rows = {};
    for (const m of band.metrics) rows[m.id] = await m.rows(src, lo, hi);
    const out = {};
    for (const m of band.metrics) {
      const r = rows[m.id], pick = (a, b) => r.filter(([t]) => t >= a && t < b).map(x => x[1]);
      out[m.id] = { ranges: ranges.map(([a, b]) => { const xs = pick(a, b); return m.kind === 'mean' ? mean(xs) : xs.reduce((s, x) => s + x, 0); }), points: r.map(([t, v]) => [Math.floor(t / w.step) * w.step, v]) };
    }
    return out;
  }

  // One band: its window, its card ranges ([start, now) and the same stretch of each comparison
  // window) and chart spans, fetched, then reduced to card values and aligned chart series.
  async function band(src, app, b, period, compare) {
    // a daily band (jobs) reads Today as the last 7 nights: one night is not a trend
    if (b.daily && period === 'today') { period = '7d'; if (compare === 'week') compare = 'prev'; }
    const nowS = src.now(), w = windowFor(period, nowS, b.daily);
    // A comparison window older than the source keeps (VictoriaLogs: 30 days), or older than the
    // app's first Umami event, is left out: a count there reads 0 and would drag the average down.
    let first = b.retention ? nowS - b.retention : -Infinity;
    if (b.src === 'umami' && (app.umamiIds || []).length) {
      try {
        const r = (await src.sql("select extract(epoch from min(created_at)) as first from website_event where website_id in (" + app.umamiIds.map(i => "'" + i + "'").join(',') + ")"))[0];
        if (r && r.first != null) first = Math.max(first, +r.first);
      } catch (e) { /* no first-event date: keep every comparison */ }
    }
    const sh = shifts(period, compare, w).filter(s => w.start - s >= first);
    const upto = Math.min(nowS, w.end);
    const ranges = [[w.start, upto]].concat(sh.map(s => [w.start - s, upto - s]));
    const spans = [[w.start, w.end]].concat(sh.map(s => [w.start - s, w.end - s]));
    let data = {};
    try {
      if (b.src === 'umami') data = await umamiBand(src, b, app.umamiIds || [], ranges, w, spans) || {};
      else if (b.src === 'vl') data = await vlBand(src, b, ranges, w, spans);
      else for (const m of b.metrics) data[m.id] = await vmMetric(src, m, ranges, w, spans);
    } catch (e) { data = {}; }
    return b.metrics.map(m => {
      const d = data[m.id] || { ranges: [], points: [] };
      const curPts = d.points.filter(([t]) => t >= w.start && t < w.end);
      // the chart's own series: point values per bucket (a sum per bucket; a mean for 'mean')
      const series = s => {
        const a = align(d.points.filter(([t]) => t >= w.start - s && t < w.end - s), w, s);
        // a count with no rows in a past bucket is 0 (Umami and VictoriaLogs only return buckets
        // that have events); a mean with no rows stays empty
        if (m.kind !== 'mean') { if (b.src !== 'vm') a.forEach((v, i) => { if (v == null && w.start - s + i * w.step <= nowS) a[i] = 0; }); return a; }
        const cnt = align(d.points.filter(([t]) => t >= w.start - s && t < w.end - s).map(([t]) => [t, 1]), w, s);
        return a.map((v, i) => v == null ? null : v / cnt[i]);
      };
      const cur = series(0), cmp = combine(sh.map(series));
      // future buckets of the current period stay empty
      cur.forEach((_, i) => { if (w.start + i * w.step > nowS) cur[i] = null; });
      return { m, w, period, compare, cur, cmp, value: d.ranges[0] == null ? null : d.ranges[0], cmpValue: mean(d.ranges.slice(1)), havePoints: curPts.length > 0 };
    });
  }

  function cardHtml(r, period, compare, link) {
    const d = delta(r.value, r.cmpValue, r.m.unit, r.m.up);
    d.text += ' <span class=muted>(' + esc(compareLabel(r.period, r.compare)) + ')</span>';
    return '<a class="card pcard" href="' + esc(r.m.link || link || '#') + '" title="' + esc(r.m.help || '') + '"><h3>' + esc(r.m.label) + '</h3>'
      + '<div class=cv>' + fmt(r.value, r.m.unit) + sparkline(r.cur) + '</div>'
      + '<div class="pdelta ' + d.cls + '">' + d.text + '</div></a>';
  }
  function chartHtml(r, period, compare, link) {
    period = r.period; compare = r.compare;
    const c = compareLabel(period, compare);
    return '<a class="card pchartcard" href="' + esc(r.m.link || link || '#') + '"><h3>' + esc(r.m.label) + (r.w.step === HOUR ? ' per hour' : ' per day') + '</h3>'
      + chart(r.m, r.cur, r.cmp, r.w, c)
      + '<div class=plegend><span class=lcur></span>' + (period === 'today' && r.w.step === HOUR ? 'today' : 'this period') + ' <span class=lcmp></span>' + esc(c) + '</div></a>';
  }

  // Render one app's page into `el`. Bands render as they arrive, so a slow source does not hold
  // the others back.
  async function render(el, app, period, compare, src) {
    const head = '<nav class=subtabs>' + Object.entries(PERIODS).map(([k, v]) => '<a href="#projects/' + app.id + '/' + k + '/' + compare + '" target=_self' + (k === period ? ' class=on' : '') + '>' + v + '</a>').join('')
      + '<span style="flex:1"></span>' + Object.entries(COMPARES).filter(([k]) => k !== 'week' || period === 'today').map(([k, v]) => '<a href="#projects/' + app.id + '/' + period + '/' + k + '" target=_self' + (k === compare ? ' class=on' : '') + '>' + v + '</a>').join('') + '</nav>'
      + '<p class=sec style="margin:-8px 0 14px">Each number is the ' + (period === 'today' ? 'day so far (UTC)' : 'last ' + PERIODS[period] + ' (UTC days, today so far)') + ' against ' + esc(compareLabel(period, compare)) + ', over the same stretch of time. Jobs count whole nights.</p>';
    el.innerHTML = head + app.bands.map((b, i) => '<div class=pband id="pb_' + app.id + '_' + i + '"><h2>' + esc(b.title) + (b.link ? ' <a href="' + esc(b.link) + '">&rarr;</a>' : '') + '</h2><p class=muted>loading&hellip;</p></div>').join('');
    await Promise.all(app.bands.map(async (b, i) => {
      const rs = await band(src, app, b, period, compare);
      const box = el.querySelector ? el.querySelector('#pb_' + app.id + '_' + i) : null;
      const html = '<h2>' + esc(b.title) + (b.link ? ' <a href="' + esc(b.link) + '">&rarr;</a>' : '') + '</h2>' + (b.note ? '<p class=sec style="margin:-4px 0 8px">' + esc(b.note) + '</p>' : '')
        + '<div class=charts>' + rs.map(r => cardHtml(r, period, compare, b.link)).join('') + '</div>'
        + '<div class=pcharts>' + rs.filter(r => r.m.chart).map(r => chartHtml(r, period, compare, b.link)).join('') + '</div>';
      if (box) box.innerHTML = html; else el.innerHTML += html;
    }));
  }

  // ---- the apps -----------------------------------------------------------------------------
  const G = 'https://grafana.tail6d0ed4.ts.net';
  const ev = name => "count(*) filter (where event_name = '" + name + "' and FILTER)";
  const CL = 'instance="prod-podcast"';
  const nightlyRows = async (src, lo, hi) => (await src.vl('_time:[' + Math.floor(lo) + ', ' + Math.floor(hi) + '] instance:prod-podcast event_type:run_timing run_id:* | stats by (run_id) min(_time) as started, max(_time) as last'))
    .map(r => [Date.parse(r.started) / 1000, (Date.parse(r.last) - Date.parse(r.started)) / 3600000])
    .filter(([t]) => t % DAY < 7200);     // the nightly starts at 00:00Z (01:00 on 10-29); hand runs are left out
  const summaryRows = async (src, lo, hi) => (await src.vl('_time:[' + Math.floor(lo) + ', ' + Math.floor(hi) + '] instance:prod-podcast "Multi-feed run summary" | extract "episodes_processed=<n>" | fields _time, n'))
    .map(r => [Date.parse(r._time) / 1000, +r.n || 0]);
  const enrichFailRows = async (src, lo, hi) => (await src.vl('_time:[' + Math.floor(lo) + ', ' + Math.floor(hi) + '] instance:prod-podcast event_type:"enrichment.enricher.completed" -status:ok | fields _time'))
    .map(r => [Date.parse(r._time) / 1000, 1]);
  const APPS = {
    cl: {
      id: 'cl', name: 'Close Listening', umamiDomains: ['closelistening.app'],
      bands: [
        { title: 'Usage', src: 'umami', link: G + '/d/podcast-player-beta-analytics', note: 'Umami: the player app and the operator viewer together.',
          metrics: [
            { id: 'visitors', label: 'Visitors', sql: "count(distinct session_id) filter (where FILTER)", chart: true, help: 'Distinct Umami sessions' },
            { id: 'visits', label: 'Visits', sql: "count(distinct visit_id) filter (where FILTER)", help: 'Distinct visits (a visitor can visit several times)' },
            { id: 'screens', label: 'Screens viewed', sql: "count(*) filter (where (event_type = 1 or event_name = 'screen_view') and FILTER)", chart: true },
            { id: 'episodes', label: 'Episodes opened', sql: ev('episode_open'), chart: true },
            { id: 'plays', label: 'Plays started', sql: ev('play_start') },
            { id: 'searches', label: 'Searches', sql: ev('search_submitted') },
            { id: 'assistant', label: 'Assistant tool calls', sql: "count(*) filter (where event_name like 'mcp\\_tool:%' and FILTER)", chart: true, help: 'Close Listening MCP tools called from an assistant (mcp_tool:* events)' }] },
        { title: 'Delivery', src: 'vm', link: G + '/d/podcast-performance',
          note: 'The three APIs (player, operator, podcast): requests, latency, errors.',
          metrics: [
            { id: 'requests', label: 'API requests', expr: 'sum(increase(http_requests_total{' + CL + '}[$W]))', chart: true },
            { id: 'p95', label: 'p95 latency', unit: 's', up: false, chart: true,
              expr: 'histogram_quantile(0.95, sum by (le) (increase(http_request_duration_highr_seconds_bucket{' + CL + '}[$W])))' },
            { id: 'err', label: '5xx share', unit: '%', up: false, kind: 'ratio',
              num: '(sum(increase(http_requests_total{' + CL + ',status=~"5.."}[$W])) or vector(0))', den: 'sum(increase(http_requests_total{' + CL + '}[$W]))' },
            { id: 'slow', label: 'Requests over 10 s', up: false, chart: true,
              expr: 'sum(increase(http_request_duration_highr_seconds_count{' + CL + '}[$W])) - sum(increase(http_request_duration_highr_seconds_bucket{' + CL + ',le="10.0"}[$W]))' }] },
        { title: 'Jobs', src: 'vl', daily: true, retention: 30 * DAY, link: G + '/d/podcast-jobs',
          note: 'The nightly pipeline (starts 00:00Z) and the enrichment after it, per night. From VictoriaLogs, which keeps 30 days: the 30-day view has no comparison. Run times start 2026-10-27, when runs got their run_id.',
          metrics: [
            { id: 'nightly', label: 'Nightly run time', unit: 'h', up: false, kind: 'mean', chart: true, rows: nightlyRows },
            { id: 'processed', label: 'Episodes processed', chart: true, rows: summaryRows, help: 'episodes_processed of every run summary (nightly and hand runs)' },
            { id: 'enrich_fail', label: 'Enricher failures', up: false, rows: enrichFailRows, help: 'enricher runs that ended in a status other than ok' }] }] },
  };

  function resolve(app, umamiSites) {
    return Object.assign({}, app, { umamiIds: (umamiSites || []).filter(([dom, id]) => app.umamiDomains.includes(dom.replace(/^www\./, '')) && UUID.test(id)).map(x => x[1]) });
  }

  const api = { DAY, HOUR, PERIODS, COMPARES, APPS, windowFor, shifts, compareLabel, align, combine, fmt, delta, chart, sparkline, band, render, resolve };
  if (typeof module === 'object' && module.exports) module.exports = api; else root.HubProject = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
