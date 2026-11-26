// The hub's CI view (RFC-0011, phase A): what counts as ok, slow or bad for the self-hosted runners and the
// jobs on them, and the CI tab drawn from the collector's ci.json. The collector (ci-job.js) writes the
// numbers; the page only reads that file and applies these rules, so no threshold lives in two places.
// Pure: no I/O of its own.
(function (root) {
  'use strict';
  const QUEUE_WARN = 300;        // a job waiting longer than this (s) is amber
  const QUEUE_BAD = 1800;        // ... and this long is red (the Grafana alert "a job queued > 30 min")
  const OFFLINE_BAD = 900;       // a runner offline this long (s) is red (the alert's 15 minutes); shorter is amber
  const STALE_AFTER = 900;       // a ci.json older than this (s) is grey, never green
  const FAILED = ['failure', 'timed_out'];

  const runnerState = (r, now) => {
    if (r.status === 'online') return 'ok';
    return r.offlineSince != null && now - r.offlineSince < OFFLINE_BAD ? 'warn' : 'bad';
  };
  const queueState = s => s >= QUEUE_BAD ? 'bad' : s >= QUEUE_WARN ? 'warn' : 'ok';
  // success is ok; cancelled is amber (someone or a newer push stopped it); failure and timeout are red;
  // anything else (neutral, action_required) is left unjudged
  const jobState = c => c === 'success' ? 'ok' : c === 'cancelled' ? 'warn' : FAILED.includes(c) ? 'bad' : 'none';
  // a repo with any failure in 24 h is amber; red when at least 3 jobs finished and half or more of them failed
  const repoState = f => !f || !f.failed ? 'ok' : f.failed >= 3 && f.failed / f.finished >= 0.5 ? 'bad' : 'warn';
  const WORST = ['none', 'ok', 'warn', 'bad'];
  const worst = list => list.reduce((a, b) => WORST.indexOf(b) > WORST.indexOf(a) ? b : a, 'ok');

  function view(doc, now) {
    const ok = !!(doc && doc.takenAt && Array.isArray(doc.runners) && Array.isArray(doc.queued));
    const taken = ok ? Date.parse(doc.takenAt) / 1000 : null;
    const ageS = ok && Number.isFinite(taken) ? now - taken : null;
    const stale = !ok || ageS == null || ageS > STALE_AFTER;
    if (!ok) return { ok: false, stale: true, ageS: null, takenAt: null, machines: [], queued: [], recent: [], failures: [], minutes: null, errors: [], state: 'stale' };
    const machines = {};
    for (const r of doc.runners) {
      const m = machines[r.machine || 'unknown'] || (machines[r.machine || 'unknown'] = { machine: r.machine || 'unknown', runners: [], online: 0, busy: 0, offline: 0 });
      const st = runnerState(r, now);
      m.runners.push(Object.assign({}, r, { state: st }));
      if (r.status === 'online') { m.online++; if (r.busy) m.busy++; } else m.offline++;
    }
    const ms = Object.values(machines).sort((a, b) => a.machine < b.machine ? -1 : 1);
    ms.forEach(m => { m.runners.sort((a, b) => a.repo < b.repo ? -1 : a.repo > b.repo ? 1 : a.name < b.name ? -1 : 1); m.state = worst(m.runners.map(r => r.state)); });
    const queued = doc.queued.map(j => { const w = Math.max(0, now - Date.parse(j.createdAt) / 1000); return Object.assign({}, j, { waitS: w, state: queueState(w) }); })
      .sort((a, b) => b.waitS - a.waitS);
    const recent = (doc.recent || []).map(j => Object.assign({}, j, { state: jobState(j.conclusion) }));
    const failures = Object.entries(doc.failures || {}).map(([repo, f]) => Object.assign({ repo }, f, { state: repoState(f) })).sort((a, b) => b.failed - a.failed || (a.repo < b.repo ? -1 : 1));
    const state = stale ? 'stale' : worst([].concat(ms.map(m => m.state), queued.map(q => q.state), failures.map(f => f.state)));
    return { ok: true, stale, ageS, takenAt: doc.takenAt, machines: ms, queued, recent, failures, minutes: doc.minutes || null, errors: doc.errors || [], state };
  }

  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const DOT = { ok: 'up', warn: 'mid', bad: 'down', none: 'stale', stale: 'stale' };
  const dot = (st, stale) => '<span class="dot ' + (stale ? 'stale' : DOT[st] || 'stale') + '"></span>';
  function dur(s) {
    if (s == null) return '&mdash;';
    s = Math.abs(s);
    if (s < 60) return Math.round(s) + ' s';
    const mins = Math.round(s / 60), h = Math.floor(mins / 60), m = mins % 60;
    return h ? h + ' h ' + m + ' min' : m + ' min';
  }
  const short = repo => String(repo).replace(/^chipi\//, '');
  const hhmm = iso => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const mins = x => x == null ? '&mdash;' : Math.round(x).toLocaleString('en-US');
  const link = (u, t) => /^https:\/\/github\.com\//.test(u || '') ? '<a href="' + esc(u) + '">' + t + '</a>' : t;

  function runnerRow(r, now, stale) {
    const what = r.status !== 'online' ? 'offline' + (r.offlineSince != null ? ' ' + dur(now - r.offlineSince) : '') : r.busy ? 'busy' : 'idle';
    return '<tr><td>' + dot(r.state, stale) + esc(r.name) + '</td><td class=u>' + esc(short(r.repo)) + '</td><td>' + what + '</td></tr>';
  }

  function html(v, now) {
    const head = '<h2>CI &middot; self-hosted runners</h2>';
    if (!v.ok) return head + '<div class="abar plumb">No CI numbers: ci.json is missing or unreadable. Nothing is shown as green.</div>';
    const st = v.stale;
    let h = head + '<p class=sec>updated ' + hhmm(v.takenAt) + ' &middot; ' + v.machines.map(m => esc(m.machine) + ': ' + m.online + ' online, ' + m.busy + ' busy' + (m.offline ? ', ' + m.offline + ' offline' : '')).join(' &middot; ')
      + ' &middot; ' + v.queued.length + ' queued</p>';
    if (st) h += '<div class="abar warn">The numbers are ' + Math.round(v.ageS / 60) + ' minutes old (the CI job writes them every 5): everything is grey until it runs again.</div>';
    if (v.errors.length) h += '<div class="abar warn">The collector could not read: ' + v.errors.map(esc).join('; ') + '. Those repos are missing below.</div>';

    h += '<h3 class=sectitle>Runners</h3>' + (v.machines.length ? v.machines.map(m => '<h3 class=sectitle style="margin-top:8px">' + dot(m.state, st) + esc(m.machine) + '</h3><table class=ctbl>' + m.runners.map(r => runnerRow(r, now, st)).join('') + '</table>').join('')
      : '<p class=muted>no runners registered on these repos</p>');

    h += '<h3 class=sectitle>Queue now</h3>' + (v.queued.length ? '<table class=ctbl>' + v.queued.map(j => '<tr><td>' + dot(j.state, st) + esc(short(j.repo)) + '</td><td>' + link(j.url, esc(j.workflow) + ' / ' + esc(j.name)) + '</td><td>waiting ' + dur(j.waitS) + '</td></tr>').join('') + '</table>'
      : '<p class=muted>nothing queued</p>');

    h += '<h3 class=sectitle>Failures, last 24 h</h3><table class=ctbl>' + v.failures.map(f => '<tr><td>' + dot(f.state, st) + esc(short(f.repo)) + '</td><td>' + f.failed + ' failed</td><td class=u>of ' + f.finished + ' finished</td></tr>').join('') + '</table>';

    const m = v.minutes;
    if (m) {
      const row = (label, w) => '<tr><td>' + label + '</td><td>' + mins(w && w['self-hosted']) + ' min on the runners</td><td class=u>' + mins(w && w.hosted) + ' min on GitHub</td></tr>';
      h += '<h3 class=sectitle>Minutes: runners vs GitHub</h3><table class=ctbl>' + row('24 h', m['24h']) + row('30 d' + (m.since30d ? ' (since ' + esc(String(m.since30d).slice(0, 10)) + ')' : ''), m['30d']) + '</table>'
        + '<p class=sec>Wall-clock minutes of finished jobs, by the runner labels. GitHub bills parallel jobs separately and rounds up, so this understates what the runners saved. The 30 d figure counts from the first run of the collector.</p>';
    }

    h += '<h3 class=sectitle>Recent jobs</h3>' + (v.recent.length ? '<table class=ctbl>' + v.recent.map(j => '<tr><td>' + dot(j.state, st) + esc(j.conclusion) + '</td><td>' + esc(short(j.repo)) + '</td><td>' + esc(j.workflow) + ' / ' + esc(j.job) + '</td><td class=u>' + esc(j.runner || j.where) + '</td><td>queue ' + dur(j.queueS) + '</td><td>' + dur(j.durS) + '</td><td>' + link(j.url, 'open') + '</td></tr>').join('') + '</table>'
      : '<p class=muted>no finished jobs in the last 24 h</p>');
    h += '<p class=sec>Amber: a job waiting over ' + QUEUE_WARN / 60 + ' min, a runner offline under ' + OFFLINE_BAD / 60 + ' min, a cancelled job, a repo with a failure in 24 h. Red: a job waiting over ' + QUEUE_BAD / 60 + ' min, a runner offline ' + OFFLINE_BAD / 60 + ' min or more, a failed or timed-out job, a repo where half of 3 or more jobs failed.</p>';
    return h;
  }

  const api = { QUEUE_WARN, QUEUE_BAD, OFFLINE_BAD, STALE_AFTER, runnerState, queueState, jobState, repoState, view, html, dur };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.HubCi = api;
})(typeof window !== 'undefined' ? window : globalThis);
