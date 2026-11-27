// The hub's service levels (RFC-0009, docs/wip/slo-plan.md): one catalogue entry per SLI, each a PromQL
// ratio of good to all over a window; this module runs them, turns the ratio into an error budget and a
// state, and draws the Levels tab, the Overview card and the Projects bands from the result. The status
// job (status-job.js) writes the result as www/slo.json; the page only reads that file, so no number is
// computed in two places. Pure: no I/O of its own.
//
// src: { q(promql) -> [{metric, value:[ts, "v"]}], qr(promql, start, end, step) -> [{metric, values:[[ts, "v"], ...]}], now: unix seconds }
(function (root) {
  'use strict';
  const DAY = 86400, WINDOW_DAYS = 28, WINDOW_S = WINDOW_DAYS * DAY;
  const AT_RISK = 0.25;       // budget left under this share: at risk
  const STALE_AFTER = 900;    // a snapshot older than this (s) is grey, never green
  const POOL = 6;
  // The Sites tab's gate (hub-status.js PROBE_OK): a probe minute counts only while the mini itself reaches
  // the internet, so a home outage is not charged to a site.
  const EGRESS = 'last_over_time(mini_vm_egress_ok{instance="homelab",target="internet"}[5m]) == 1';

  const num = x => { const n = +x; return x != null && x !== '' && Number.isFinite(n) ? n : null; };
  const fill = (expr, w) => expr.replace(/\[window/g, '[' + w);
  const rowKey = e => e.service + ' | ' + e.sli;

  // Why the catalogue cannot be used, one line each; empty when it is sound.
  function lint(cat) {
    if (!Array.isArray(cat) || !cat.length) return ['catalogue is empty'];
    const bad = [], seen = new Set();
    for (const e of cat) {
      const k = e && e.service ? rowKey(e) : JSON.stringify(e);
      for (const f of ['service', 'group', 'sli', 'good_ratio', 'link']) if (!e || typeof e[f] !== 'string' || !e[f]) bad.push(k + ': no ' + f);
      // the row's stable name for readers that compare snapshots (flotilla, RFC-0017): kept when service or sli text changes
      if (!e || typeof e.id !== 'string' || !/^[a-z0-9][a-z0-9-]*$/.test(e.id)) bad.push(k + ': no id (lowercase letters, digits, dashes)');
      if (!e || !(e.objective > 0 && e.objective < 1)) bad.push(k + ': objective must be between 0 and 1');
      if (!e || typeof e.good_ratio !== 'string') continue;
      if (!/\[window[\]:]/.test(e.good_ratio)) bad.push(k + ': good_ratio has no [window] placeholder');
      if (/probe_(success|duration_seconds)/.test(e.good_ratio) && !e.good_ratio.includes(EGRESS)) bad.push(k + ': a probe query without the egress gate');
      if (seen.has(k) || (e && e.id && seen.has('id:' + e.id))) bad.push(k + ': listed twice'); seen.add(k); if (e && e.id) seen.add('id:' + e.id);
    }
    return bad;
  }

  // Share of the error budget left: 1 at a perfect ratio, 0 at the objective, negative below it.
  function judge(ratio, objective) {
    if (ratio == null) return { left: null, state: 'stale' };
    const left = (ratio - objective) / (1 - objective);
    return { left, state: left < 0 ? 'breached' : left < AT_RISK ? 'at risk' : 'meeting' };
  }

  async function evaluate(src, e) {
    const row = { id: e.id, service: e.service, group: e.group, sli: e.sli, app: e.app || null, link: e.link, note: e.note || null, objective: e.objective,
                  ratio: { '28d': null, '7d': null, '1d': null }, daily: Array(WINDOW_DAYS).fill(null), errors: [] };
    const inst = async w => { try { const r = await src.q(fill(e.good_ratio, w)); return r && r.length ? num(r[0].value[1]) : null; } catch (x) { row.errors.push(w + ': ' + (x && x.message || x)); return null; } };
    const clamp = v => v == null ? null : Math.min(1, Math.max(0, v));
    row.ratio['28d'] = clamp(await inst('28d'));
    row.ratio['7d'] = clamp(await inst('7d'));
    // one daily value per day, each the ratio over the 24 h ending then; the last one is "now, over 1 d"
    const end = Math.floor(src.now), start = end - (WINDOW_DAYS - 1) * DAY;
    try {
      const r = await src.qr(fill(e.good_ratio, '1d'), start, end, DAY);
      for (const [t, v] of r && r.length ? r[0].values : []) { const i = Math.round((t - start) / DAY); if (i >= 0 && i < WINDOW_DAYS) row.daily[i] = clamp(num(v)); }
    } catch (x) { row.errors.push('daily: ' + (x && x.message || x)); }
    row.ratio['1d'] = row.daily[WINDOW_DAYS - 1];
    const j = judge(row.ratio['28d'], e.objective);
    row.left = j.left; row.state = j.state;
    row.budgetSeconds = Math.round((1 - e.objective) * WINDOW_S);
    row.leftSeconds = j.left == null ? null : Math.round(j.left * row.budgetSeconds);
    return row;
  }

  async function pool(items, n, f) {
    const out = Array(items.length); let i = 0;
    await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => { while (i < items.length) { const k = i++; out[k] = await f(items[k]); } }));
    return out;
  }

  function summarise(rows) {
    const s = { total: rows.length, meeting: 0, atRisk: 0, breached: 0, stale: 0 };
    for (const r of rows) s[r.state === 'at risk' ? 'atRisk' : r.state]++;
    return s;
  }

  // Every SLI of the catalogue; one failing query leaves that row stale (never 100 %), it does not stop the rest.
  async function all(src, catalogue) {
    const bad = lint(catalogue);
    if (bad.length) throw new Error('slo catalogue: ' + bad.join('; '));
    const eg = await src.q('last_over_time(mini_vm_egress_ok{instance="homelab",target="internet"}[5m])').then(r => r && r.length ? num(r[0].value[1]) : null, () => null);
    const rows = await pool(catalogue, POOL, e => evaluate(src, e));
    return { takenAt: new Date(src.now * 1000).toISOString(), windowDays: WINDOW_DAYS, egressOk: eg == null ? null : eg === 1, summary: summarise(rows), rows };
  }

  // ---- the page ------------------------------------------------------------------------------------------

  // What the page draws from slo.json and the clock: a snapshot that is missing, unreadable or older than
  // 15 minutes turns every row grey; rows sort by budget left inside each group (closest to breaking first).
  function view(doc, nowS) {
    const ok = doc && Array.isArray(doc.rows) && doc.takenAt && !isNaN(Date.parse(doc.takenAt));
    const ageS = ok ? Math.max(0, nowS - Date.parse(doc.takenAt) / 1000) : null;
    const stale = !ok || ageS > STALE_AFTER;
    const rows = (ok ? doc.rows : []).map(r => stale ? Object.assign({}, r, { state: 'stale' }) : r);
    const order = [], by = {};
    for (const r of rows) { if (!by[r.group]) { by[r.group] = []; order.push(r.group); } by[r.group].push(r); }
    const groups = order.map(g => ({ group: g, rows: by[g].slice().sort((a, b) => (a.left == null) - (b.left == null) || a.left - b.left) }));
    return { ok: !!ok, stale, ageS, takenAt: ok ? doc.takenAt : null, groups, rows, counts: summarise(rows) };
  }

  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const DOT = { meeting: 'up', 'at risk': 'mid', breached: 'down', stale: 'stale' };
  const pct = v => v == null ? '&mdash;' : (v * 100).toFixed(2) + '&nbsp;%';
  function dur(s) {
    s = Math.abs(s);
    if (s < 60) return Math.round(s) + ' s';
    const mins = Math.round(s / 60), h = Math.floor(mins / 60), m = mins % 60;
    if (h >= 24) return Math.floor(h / 24) + ' d ' + h % 24 + ' h';
    return h ? h + ' h ' + m + ' min' : m + ' min';
  }
  const budgetText = r => r.leftSeconds == null ? 'no data' : (r.leftSeconds >= 0 ? dur(r.leftSeconds) + ' left of ' + dur(r.budgetSeconds) : 'over by ' + dur(r.leftSeconds) + ' (budget ' + dur(r.budgetSeconds) + ')');

  // 28 daily values as a line, the target dashed; a day with no data breaks the line.
  function spark(r, grey) {
    const W = 112, H = 24, v = (r.daily || []).filter(x => x != null);
    if (!v.length) return '<svg class="slo-spark" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none"></svg>';
    const lo = Math.min(r.objective, Math.min.apply(0, v)), span = (1 - lo) || 1, y = x => (2 + (1 - (x - lo) / span) * (H - 4)).toFixed(1);
    const segs = []; let cur = [];
    r.daily.forEach((x, i) => { if (x == null) { if (cur.length) segs.push(cur); cur = []; } else cur.push((i / (r.daily.length - 1) * W).toFixed(1) + ',' + y(x)); });
    if (cur.length) segs.push(cur);
    return '<svg class="slo-spark' + (grey ? ' grey' : '') + '" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none"><line x1="0" x2="' + W + '" y1="' + y(r.objective) + '" y2="' + y(r.objective) + '"/>'
      + segs.map(s => s.length > 1 ? '<polyline points="' + s.join(' ') + '"/>' : '<circle cx="' + s[0].split(',')[0] + '" cy="' + s[0].split(',')[1] + '" r="1.2"/>').join('') + '</svg>';
  }

  // the window is 28 days, but a series can be younger: say so rather than let the number pass for 28 days
  const daysOfData = r => { const n = (r.daily || []).filter(x => x != null).length; return n && n < WINDOW_DAYS ? '<span class=slo-days>' + n + ' of ' + WINDOW_DAYS + ' days have data</span>' : ''; };

  function rowHtml(r) {
    const href = r.link || '#', self = href.charAt(0) === '#';
    return '<div class="slo-row ' + (DOT[r.state] || 'stale') + '"' + (r.note ? ' title="' + esc(r.note) + '"' : '') + '>'
      + '<div class=slo-head><span class="dot ' + (DOT[r.state] || 'stale') + '"></span><span class=slo-id><a class=slo-svc href="' + esc(href) + '"' + (self ? ' target=_self' : '') + '>' + esc(r.service) + '</a><span class=slo-sli>' + esc(r.sli) + '</span></span><span class=slo-state>' + esc(r.state) + '</span></div>'
      + '<div class=slo-nums><span><i>now</i><b>' + pct(r.ratio && r.ratio['28d']) + '</b></span><span><i>target</i><b>' + pct(r.objective) + '</b></span>'
      + '<span><i>budget</i><b>' + (r.left == null ? '&mdash;' : Math.round(r.left * 100) + '&nbsp;%') + '</b></span><span class=slo-left>' + esc(budgetText(r)) + '</span>' + daysOfData(r) + '</div>'
      + spark(r, r.state === 'stale') + '</div>';
  }

  const hhmm = iso => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const countsText = c => [c.breached && c.breached + ' below target', c.atRisk && c.atRisk + ' at risk', c.meeting + ' meeting', c.stale && c.stale + ' stale'].filter(Boolean).join(' &middot; ');

  // The Levels tab.
  function levelsHtml(v) {
    const head = '<h2>Service levels &middot; ' + WINDOW_DAYS + ' days rolling</h2>';
    if (!v.ok) return head + '<div class="abar plumb">No service-level numbers: slo.json is missing or unreadable. Nothing is shown as green.</div>';
    return head + '<p class=sec>updated ' + hhmm(v.takenAt) + ' &middot; ' + v.rows.length + ' SLIs &middot; ' + countsText(v.counts) + '</p>'
      + (v.stale ? '<div class="abar warn">The numbers are ' + Math.round(v.ageS / 60) + ' minutes old (the status job writes them every 5): every row is grey until it runs again.</div>' : '')
      + v.groups.map(g => '<h3 class=sectitle>' + esc(g.group) + '</h3><div class=slo-list>' + g.rows.map(rowHtml).join('') + '</div>').join('')
      + '<p class=sec>SLI = the share of good probes, requests or fresh runs over the last ' + WINDOW_DAYS + ' days; target = the level promised (RFC-0009); budget = how much of the allowed failure is left (25 % or more is meeting, under that at risk, under 0 breached). The line is one value per day, the dashed line the target. Probe minutes while the mini itself was offline are left out.</p>';
  }

  // The Overview card: "<meeting> of <all> meeting", red when one is breached, grey when the numbers are old.
  function cardHtml(v) {
    if (!v.ok || !v.rows.length) return '<div class=cv style="color:#7a7a8c">&mdash;</div><span class=muted>no numbers</span>';
    const c = v.counts, colour = v.stale ? '#7a7a8c' : (c.breached ? '#f85149' : '');
    return '<div class=cv style="' + (colour ? 'color:' + colour : '') + '">' + c.meeting + ' of ' + c.total + '</div><span class=muted>' + (v.stale ? 'meeting (numbers old)' : 'meeting' + (c.breached ? ' &middot; ' + c.breached + ' breached' : '')) + '</span>';
  }

  // One app's rows, for its Projects page; '' when the app has none.
  function bandHtml(v, app) {
    const rows = v.rows.filter(r => r.app === app).sort((a, b) => (a.left == null) - (b.left == null) || a.left - b.left);
    if (!v.ok || !rows.length) return '';
    return '<h2>Service levels <a href="#levels" target=_self>&rarr;</a></h2><p class=sec style="margin:-4px 0 8px">' + WINDOW_DAYS + ' days rolling, closest to breaking first.' + (v.stale ? ' The numbers are old: grey.' : '') + '</p><div class=slo-list>' + rows.map(rowHtml).join('') + '</div>';
  }

  const api = { WINDOW_DAYS, AT_RISK, STALE_AFTER, EGRESS, lint, judge, evaluate, all, summarise, view, dur, levelsHtml, cardHtml, bandHtml, rowHtml, spark };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.HubSlo = api;
})(typeof window !== 'undefined' ? window : globalThis);
