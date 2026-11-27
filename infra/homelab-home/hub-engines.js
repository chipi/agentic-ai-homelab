// The Hub's "Docker disk" tables (operator, 2026-11-27): each box's Docker engines by what holds the disk
// (images, build cache, volumes, containers), what docker counts as reclaimable, and the box's weekly prune:
// when it last ran and what it freed. The numbers come from mini-metrics/engine-df.py (hourly on each box)
// and the prune jobs' pushes; the page queries them and this draws them. Pure: no I/O of its own.
(function (root) {
  'use strict';
  const TYPES = [['images', 'Images'], ['build_cache', 'Build cache'], ['volumes', 'Volumes'], ['containers', 'Containers']];
  // Which job prunes which engine; an engine not here has none (the DGX: its vLLM images must stay, RFC-0011).
  const PRUNE = { 'mini/prod': 'docker-prune', 'x3/dev': 'dev-engine-prune' };
  const STALE = 3 * 3600;            // a reading older than this (s) is shown as old: the jobs measure hourly
  const PRUNE_LATE = 8 * 86400;      // the alerts' 8 days (docker-prune-stale, dev-engine-prune-stale)

  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const gb = b => (b >= 100e9 ? (b / 1e9).toFixed(0) : (b / 1e9).toFixed(1)) + ' GB';
  const ago = s => s < 3600 ? Math.round(s / 60) + ' min ago' : s < 2 * 86400 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' days ago';

  // vectors: { bytes, reclaim, count, measured, pruned, freed } as VictoriaMetrics instant results
  // ([{metric:{...}, value:[t, "v"]}]); pruned holds homelab_maintenance_last_run_timestamp for every job.
  function model(v, box, now) {
    const eng = {};
    const at = (r) => { const e = r.metric.engine || 'default'; return (eng[e] = eng[e] || { engine: e, types: {} }); };
    for (const r of v.bytes || []) (at(r).types[r.metric.type] = at(r).types[r.metric.type] || {}).bytes = +r.value[1];
    for (const r of v.reclaim || []) (at(r).types[r.metric.type] = at(r).types[r.metric.type] || {}).reclaim = +r.value[1];
    for (const r of v.count || []) (at(r).types[r.metric.type] = at(r).types[r.metric.type] || {}).count = +r.value[1];
    for (const r of v.measured || []) at(r).measured = +r.value[1];
    const out = Object.values(eng).sort((a, b) => a.engine.localeCompare(b.engine));
    for (const e of out) {
      e.total = TYPES.reduce((s, [t]) => s + ((e.types[t] || {}).bytes || 0), 0);
      e.reclaim = TYPES.reduce((s, [t]) => s + ((e.types[t] || {}).reclaim || 0), 0);
      e.age = e.measured ? now - e.measured : null;
      const job = PRUNE[box + '/' + e.engine];
      e.prune = null;
      if (job) {
        const p = (v.pruned || []).find(r => r.metric.job === job);
        const f = (v.freed || []).find(r => (r.metric.engine || 'default') === e.engine);
        e.prune = { job, last: p ? +p.value[1] : null, freed: f ? +f.value[1] : null };
        e.prune.age = e.prune.last ? now - e.prune.last : null;
        e.prune.late = e.prune.age === null || e.prune.age > PRUNE_LATE;
      }
    }
    return out;
  }

  function summary(engines) {
    if (!engines.length) return 'Docker disk &middot; <span class=muted>no data</span>';
    const t = engines.reduce((s, e) => s + e.total, 0), r = engines.reduce((s, e) => s + e.reclaim, 0);
    const late = engines.some(e => e.prune && e.prune.late);
    return 'Docker disk &middot; <b>' + gb(t) + '</b> &middot; ' + gb(r) + ' reclaimable'
      + (late ? ' &middot; <span style=color:#d29922>prune late</span>' : '');
  }

  function rows(engines) {
    if (!engines.length) return '<tr><td class=muted colspan=4>no data (the hourly measurement has not arrived)</td></tr>';
    const h = [];
    for (const e of engines) {
      const old = e.age === null || e.age > STALE;
      h.push('<tr><td colspan=4><b>' + esc(e.engine) + '</b> engine &middot; ' + gb(e.total)
        + ' <span class=muted>measured ' + (e.age === null ? 'never' : ago(e.age)) + '</span>'
        + (old && e.age !== null ? ' <span style=color:#d29922>(old)</span>' : '') + '</td></tr>');
      for (const [t, label] of TYPES) {
        const x = e.types[t] || {};
        h.push('<tr><td>' + label + '</td><td>' + (x.bytes != null ? gb(x.bytes) : '&mdash;') + '</td>'
          + '<td class=u>' + (x.reclaim != null ? gb(x.reclaim) + ' reclaimable' : '') + '</td>'
          + '<td class=u>' + (x.count != null ? x.count : '') + '</td></tr>');
      }
      const p = e.prune;
      h.push('<tr><td colspan=4 class=u>' + (!p ? 'No prune job for this engine.'
        : p.last === null ? '<span style=color:#d29922>Prune (' + esc(p.job) + '): no run recorded.</span>'
          : 'Prune (' + esc(p.job) + '): ' + (p.late ? '<span style=color:#d29922>' + ago(p.age) + ', late</span>' : ago(p.age))
          + (p.freed != null ? ', freed ' + gb(p.freed) : '')) + '</td></tr>');
    }
    return h.join('');
  }

  const api = { TYPES, PRUNE, STALE, PRUNE_LATE, model, summary, rows, gb, ago };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.HubEngines = api;
})(typeof window !== 'undefined' ? window : globalThis);
