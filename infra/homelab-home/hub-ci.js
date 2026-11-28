// The hub's CI view (RFC-0011, phase A and the drill-down): what counts as ok, slow or bad for the self-hosted
// runners, the runs and the jobs on them, and the CI tab drawn from the collector's ci.json (the cards, the
// per-repo table, the runners, the queue, the paged list of past runs) and, at #ci/run/<repo>/<id>, one run's
// page drawn from its ci-runs/<repo>/<id>.json and its jobs' ci-logs/<repo>/<job>.txt. The collector (ci-job.js)
// writes the numbers; the page only reads those files and applies these rules, so no threshold lives in two
// places. Everything that comes from GitHub (names, branches, commit messages, log lines) is untrusted text and
// is escaped. Pure: no I/O of its own.
(function (root) {
  'use strict';
  const QUEUE_WARN = 300;        // a job waiting longer than this (s) is amber
  const QUEUE_BAD = 1800;        // ... and this long is red (the Grafana alert "a job queued > 30 min")
  const OFFLINE_BAD = 900;       // a runner offline this long (s) is red (the alert's 15 minutes); shorter is amber
  const STALE_AFTER = 900;       // a ci.json older than this (s) is grey, never green
  const PER_PAGE = 25;           // rows of the Past runs table
  const FAILED = ['failure', 'timed_out'];
  const CONCLUSIONS = ['all', 'success', 'failure', 'cancelled', 'running'];

  const runnerState = (r, now) => {
    if (r.status === 'online') return 'ok';
    return r.offlineSince != null && now - r.offlineSince < OFFLINE_BAD ? 'warn' : 'bad';
  };
  const queueState = s => s >= QUEUE_BAD ? 'bad' : s >= QUEUE_WARN ? 'warn' : 'ok';
  // success is ok; cancelled is amber (someone or a newer push stopped it); failure and timeout are red;
  // anything else (neutral, action_required, skipped) is left unjudged
  const jobState = c => c === 'success' ? 'ok' : c === 'cancelled' ? 'warn' : FAILED.includes(c) ? 'bad' : 'none';
  // a run or a step that has not finished is unjudged (grey); a finished one is judged like a job
  const runState = r => r.status && r.status !== 'completed' ? 'none' : jobState(r.conclusion);
  // a repo with any failure in 24 h is amber; red when at least 3 jobs finished and half or more of them failed
  const repoState = f => !f || !f.failed ? 'ok' : f.failed >= 3 && f.failed / f.finished >= 0.5 ? 'bad' : 'warn';
  const WORST = ['none', 'ok', 'warn', 'bad'];
  const worst = list => list.reduce((a, b) => WORST.indexOf(b) > WORST.indexOf(a) ? b : a, 'ok');

  const short = repo => String(repo).split('/').pop();

  function view(doc, now) {
    const ok = !!(doc && doc.takenAt && Array.isArray(doc.runners) && Array.isArray(doc.queued));
    const taken = ok ? Date.parse(doc.takenAt) / 1000 : null;
    const ageS = ok && Number.isFinite(taken) ? now - taken : null;
    const stale = !ok || ageS == null || ageS > STALE_AFTER;
    if (!ok) return { ok: false, stale: true, ageS: null, takenAt: null, repos: [], machines: [], queued: [], recent: [], runs: [], failures: [], minutes: null, stats: null, steps: null, logs: null, idleOther: 0, errors: [], state: 'stale' };
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
    // idle runners in repos with nothing queued: they cannot take another repo's jobs (a personal account has no shared runner pool)
    const queuedRepos = new Set(queued.map(j => j.repo));
    const idleOther = doc.runners.filter(r => r.status === 'online' && !r.busy && !queuedRepos.has(r.repo)).length;
    const recent = (doc.recent || []).map(j => Object.assign({}, j, { state: jobState(j.conclusion) }));
    const runs = (doc.runs || []).map(r => Object.assign({}, r, { state: runState(r) }));
    const failures = Object.entries(doc.failures || {}).map(([repo, f]) => Object.assign({ repo }, f, { state: repoState(f) })).sort((a, b) => b.failed - a.failed || (a.repo < b.repo ? -1 : 1));
    const state = stale ? 'stale' : worst([].concat(ms.map(m => m.state), queued.map(q => q.state), failures.map(f => f.state)));
    return { ok: true, stale, ageS, takenAt: doc.takenAt, visibility: doc.visibility || {}, runsHeld: doc.runsHeld == null ? (doc.runs || []).length : doc.runsHeld, repos: doc.repos || [], machines: ms, queued, recent, runs, failures, minutes: doc.minutes || null, stats: doc.stats || null, steps: doc.steps || null, logs: doc.logs || null, idleOther, errors: doc.errors || [], state };
  }

  // ---- the period row, as on the Spend tab: completed UTC days; the collector's windows (ci-job.js periodWindows)
  const PERIODS = [['month', 'This month'], ['30d', 'Last 30 days'], ['7d', 'Last 7 days'], ['yesterday', 'Yesterday']];
  const PERIOD_DEFAULT = '30d';
  const isPeriod = p => PERIODS.some(x => x[0] === p);

  // ---- routes: #ci[/<period>] (the list), #ci/runs/<page>/<repo>/<conclusion>[/<period>] (the list, paged and
  // filtered), #ci/run/<repo>/<id> (one run)
  const SAFE = /^[A-Za-z0-9._-]+$/;
  function parseRoute(hash) {
    const p = String(hash || '').replace(/^#/, '').split('/');
    if (p[0] !== 'ci') return null;
    const dec = s => { try { return decodeURIComponent(s); } catch (e) { return ''; } };
    if (p[1] === 'run' && p[2] && /^\d+$/.test(p[3] || '') && SAFE.test(dec(p[2]))) return { kind: 'run', repo: dec(p[2]), id: p[3] };
    if (p[1] === 'runs') {
      const repo = p[3] && SAFE.test(dec(p[3])) ? dec(p[3]) : 'all';
      return { kind: 'list', page: Math.max(1, parseInt(p[2], 10) || 1), repo, concl: CONCLUSIONS.includes(p[4]) ? p[4] : 'all', period: isPeriod(p[5]) ? p[5] : PERIOD_DEFAULT, when: p[6] === 'period' ? 'period' : 'any' };
    }
    return { kind: 'list', page: 1, repo: 'all', concl: 'all', period: isPeriod(p[1]) ? p[1] : PERIOD_DEFAULT, when: 'any' };
  }
  const runHref = (repo, id) => '#ci/run/' + encodeURIComponent(short(repo)) + '/' + id;
  // when: 'any' (every run held) or 'period' (runs that finished in the chosen period: where a card leads)
  const listHref = (o) => {
    const page = Math.max(1, o.page || 1), repo = o.repo && o.repo !== 'all' ? o.repo : 'all', concl = o.concl || 'all', per = isPeriod(o.period) ? o.period : PERIOD_DEFAULT, when = o.when === 'period' ? 'period' : 'any';
    if (page === 1 && repo === 'all' && concl === 'all' && when === 'any') return per === PERIOD_DEFAULT ? '#ci' : '#ci/' + per;
    return '#ci/runs/' + page + '/' + encodeURIComponent(repo) + '/' + concl + (per === PERIOD_DEFAULT && when === 'any' ? '' : '/' + per + (when === 'period' ? '/period' : ''));
  };
  // f.win: [from, to) in ms; only runs that finished inside it
  function filterRuns(runs, f) {
    return runs.filter(r => (!f.win || (r.finishedAt && Date.parse(r.finishedAt) >= f.win[0] && Date.parse(r.finishedAt) < f.win[1]))
      && (!f.repo || f.repo === 'all' || short(r.repo) === f.repo)
      && (f.concl === 'all' || !f.concl || (f.concl === 'running' ? r.status !== 'completed' : f.concl === 'failure' ? r.status === 'completed' && FAILED.includes(r.conclusion) : r.status === 'completed' && r.conclusion === f.concl)));
  }
  function pageRuns(runs, route, per) {
    per = per || PER_PAGE;
    const all = filterRuns(runs, route), pages = Math.max(1, Math.ceil(all.length / per)), page = Math.min(Math.max(1, route.page || 1), pages);
    return { rows: all.slice((page - 1) * per, page * per), total: all.length, page, pages, per };
  }

  // ---- numbers
  // a change against the period before: direction and whole percent; nothing when both are empty or the old one is unknown
  function delta(a, b) {
    if (a == null || b == null) return null;
    if (!a && !b) return null;
    if (!b) return { dir: 'new', pct: null };
    const pct = Math.round(Math.abs(a - b) / b * 100);
    return { dir: pct === 0 ? 'flat' : a > b ? 'up' : 'down', pct };
  }
  const deltaText = (d, label) => !d ? '' : d.dir === 'new' ? 'from 0' + (label ? ' vs ' + label : '') : d.dir === 'flat' ? 'no change' + (label ? ' vs ' + label : '') : (d.dir === 'up' ? '&#9650;' : '&#9660;') + (d.pct >= 1000 ? '&gt;10&times;' : d.pct + '%') + (label ? ' vs ' + label : '');
  // a rate against the period before, in percentage points
  function deltaPP(a, b) {
    if (a == null || b == null) return null;
    const pp = Math.round((a - b) * 100);
    return { dir: pp === 0 ? 'flat' : pp > 0 ? 'up' : 'down', pct: Math.abs(pp), pp: true };
  }
  const deltaPPText = (d, label) => !d ? '' : d.dir === 'flat' ? 'no change' + (label ? ' vs ' + label : '') : (d.dir === 'up' ? '&#9650;' : '&#9660;') + d.pct + ' pp' + (label ? ' vs ' + label : '');
  // success rate: finished runs that succeeded of those that succeeded or failed; cancelled runs are not a verdict
  const rate = (ok, failed) => ok + failed ? ok / (ok + failed) : null;

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
  const hhmm = iso => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const when = iso => iso ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '&mdash;';
  const whenFull = iso => iso ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '&mdash;';
  const num = x => x == null ? '&mdash;' : Math.round(x).toLocaleString('en-US');
  const mins = x => x == null ? '&mdash;' : Math.round(x).toLocaleString('en-US');
  const usd = x => x == null ? '&mdash;' : '$' + (x >= 100 ? x.toFixed(0) : x.toFixed(2));
  const pct = x => x == null ? '&mdash;' : (Math.round(x * 1000) / 10) + '%';
  const link = (u, t) => /^https:\/\/github\.com\//.test(u || '') ? '<a href="' + esc(u) + '">' + t + '</a>' : t;
  const ghRunUrl = (repos, repo, id) => { const full = (repos || []).find(r => short(r) === short(repo)); return full ? 'https://github.com/' + full + '/actions/runs/' + id : null; };
  const GRAFANA_RUNNERS = 'https://grafana.tail6d0ed4.ts.net/d/ci-runners';
  const RUNNER_NOTE ='Runners belong to one repo each (chipi is a personal account, so there is no organisation pool): a queue in one repo does not use idle runners in another.';

  const sq = c => '<span style="color:' + c + '">&#9632;</span> ';
  const bar = parts => {
    const p = parts.filter(x => x[1] > 0);
    return p.length ? '<div style="display:flex;height:6px;border-radius:3px;overflow:hidden;margin:6px 0 4px">' + p.map(([, v, c]) => '<span style="flex:' + v + ';background:' + c + '"></span>').join('') + '</div>'
      + '<div class=muted style="font-size:12px">' + p.map(([k, v, c]) => sq(c) + num(v) + ' ' + k).join(' &middot; ') + '</div>' : '';
  };
  // Runs and Jobs: the same split by result, as shares of the total so the two cards compare directly; the counts are
  // in the tooltip. "other" is what is neither (a neutral or skipped-by-condition result), so the shares add to 100%.
  const resultBar = (total, ok, failed, cancelled, what) => {
    const other = Math.max(0, total - ok - failed - cancelled);
    const p = [['succeeded', ok, '#3fb950'], ['failed', failed, '#f85149'], ['cancelled', cancelled, '#55556b'], ['other', other, '#8888aa']].filter(x => x[1] > 0);
    if (!total || !p.length) return '';
    const share = v => (Math.round(v / total * 1000) / 10) + '%';
    return '<div style="display:flex;height:6px;border-radius:3px;overflow:hidden;margin:6px 0 4px">' + p.map(([k, v, c]) => '<span title="' + num(v) + ' ' + what + ' ' + k + '" style="flex:' + v + ';background:' + c + '"></span>').join('') + '</div>'
      + '<div class=muted style="font-size:12px">' + p.map(([k, v, c]) => '<span title="' + num(v) + ' ' + what + '">' + sq(c) + share(v) + ' ' + k + '</span>').join(' &middot; ') + '</div>';
  };
  const mut = t => t ? '<div class=muted style="font-size:12px">' + t + '</div>' : '';
  // a small daily line, like the Spend tab's
  function spark(d) {
    if (!d || !d.some(x => x != null && x > 0)) return '';
    const w = 56, h = 16, mx = Math.max.apply(0, d.map(x => x || 0)) || 1;
    const pts = d.map((x, i) => (i * (w - 2) / (d.length - 1) + 1).toFixed(1) + ',' + (h - 1 - (x || 0) / mx * (h - 2)).toFixed(1)).join(' ');
    return ' <svg width=' + w + ' height=' + h + ' viewBox="0 0 ' + w + ' ' + h + '" class=sl style="vertical-align:middle" aria-label="daily values, 14 days"><polyline points="' + pts + '" fill=none stroke=#7aa2ff stroke-width=1.5 vector-effect=non-scaling-stroke /></svg>';
  }
  const kv = rows => '<div class=subkv>' + rows.filter(Boolean).map(([l, x, t]) => '<span' + (t ? ' title="' + esc(t) + '"' : '') + '>' + l + '</span><b>' + x + '</b>').join('') + '</div>';
  const card = (title, tip, body) => '<div class="card ci"><h3' + (tip ? ' title="' + esc(tip) + '"' : '') + '>' + title + '</h3>' + body + '</div>';

  // The chosen period (the row above the cards, as on the Spend tab): its number is the big one, set against the period of
  // the same length before it; "Today so far" is the one live row. A period that starts before the oldest run or job the
  // collector holds is not complete, so it is shown as not held and not compared.
  function periodInfo(st, per) {
    const w = st.windows && st.windows[per], pw = st.windows && st.windows[per + 'Prev'], n = (st.days || {})[per] || 0;
    const day = iso => String(iso).slice(0, 10), lastDay = iso => new Date(Date.parse(iso) - 86400000).toISOString().slice(0, 10);
    const label = n && w ? day(w[0]) + ' to ' + lastDay(w[1]) + ' (UTC, ' + n + ' day' + (n > 1 ? 's' : '') + ')' : 'no completed day this month yet';
    const held = !!(pw && st.since && Date.parse(pw[0]) >= Date.parse(st.since));
    const before = n === 1 ? 'the day before' : 'the ' + n + ' days before';
    return { n, label, held, before, cur: st.total[per], prev: held ? st.total[per + 'Prev'] : null };
  }
  function periodNav(per, route) {
    return '<nav class=subtabs id=ci_period>' + PERIODS.map(([p, t]) => '<a href="' + listHref(Object.assign({}, route, { page: route.page, period: p })) + '" data-p=' + p + ' target=_self' + (p === per ? ' class=on' : '') + '>' + t + '</a>').join('') + '</nav>';
  }

  function metricCard(title, tip, pi, today, o) {
    const g = o.get, f = o.fmt, cur = pi.cur ? g(pi.cur) : null, prev = pi.prev ? g(pi.prev) : null;
    const dl = o.pp ? deltaPPText(deltaPP(cur, prev), pi.before) : deltaText(delta(cur, prev), pi.before);
    const body = '<div class=cv>' + (pi.n ? f(cur) : '&mdash;') + (o.spark || '') + '</div>' + (o.extra || '')
      + mut(dl || (pi.n && !pi.held ? 'no comparison: ' + pi.before + ' are not all held' : ''))
      + kv((o.rows || []).concat([o.perDay && pi.n ? ['Per day', o.perDay(cur / pi.n)] : null,
        [pi.before.charAt(0).toUpperCase() + pi.before.slice(1), pi.held ? f(prev) : '&mdash;', pi.held ? '' : 'The collector holds 30 days of finished runs and jobs; this period starts before them'],
        ['Today so far (live)', f(g(today)), 'Since 00:00 UTC']]));
    return o.href ? '<a class="card ci" href="' + o.href + '" target=_self' + (tip ? ' title="' + esc(tip) + '"' : '') + '><h3>' + title + '</h3>' + body + '</a>' : card(title, tip, body);
  }

  // The X3 slot gauges the runners' sync job pushes to VictoriaMetrics each minute, read over a collector window: the share of it
  // with a job waiting for a slot, the longest wait, the peak slots held and the slots there are. q(expr, time) answers a number
  // or null (no series) and rejects when VictoriaMetrics does not answer; the page passes its /vm query.
  const SLOT = '{box="x3"}';
  async function slotStats(q, st, per) {
    const one = async w => {
      if (!w) return null;
      const to = Date.parse(w[1]) / 1000, r = Math.round(to - Date.parse(w[0]) / 1000), R = '[' + r + 's]';
      if (!(r > 0)) return null;
      const [share, wait, peak, total] = await Promise.all([q('avg_over_time((x3_ci_jobs_waiting_for_slot' + SLOT + ' > bool 0)[' + r + 's:1m])', to), q('max_over_time(x3_ci_slot_wait_oldest_seconds' + SLOT + R + ')', to),
        q('max_over_time(x3_ci_slots_held' + SLOT + R + ')', to), q('max_over_time(x3_ci_slots_total' + SLOT + R + ')', to)]);
      return { share, wait, peak, total };
    };
    const ws = st.windows || {}, [cur, prev, today] = await Promise.all([one(ws[per]), one(ws[per + 'Prev']), one(ws.today)]);
    return { cur, prev, today };
  }

  function cardsHtml(v, per, route, slots) {
    const st = v.stats;
    if (!st || !st.total || !st.total[per]) return '<p class=muted>No history yet: the collector has not written the numbers for the cards (it fills them over its first runs).</p>';
    const pi = periodInfo(st, per), W = pi.cur, T = st.total.today, d = st.daily || [], series = k => d.map(x => x[k]);
    const sh = 'self-hosted', gh = 'hosted', one = x => Math.round(x * 10) / 10;
    const by = (a, b) => [['X3 (self-hosted)', a, '#7aa2ff'], ['GitHub (hosted)', b, '#8888aa']];
    const runs = o => listHref(Object.assign({ period: per }, o));
    // the period's minutes split per repo: the 4 largest, the rest as one "other". A repo keeps its colour across the two
    // cards: colours go by the repo's X3 + GitHub minutes in the period, so the largest repos get distinct ones.
    const REPO_COLOURS = ['#7aa2ff', '#d29922', '#3fb950', '#bc8cff', '#f778ba', '#39c5cf', '#e3b341', '#a5d6ff'];
    const minOf = (r, where) => ((st.repos[r][per] || {}).min || {})[where] || 0;
    const ranked = Object.keys(st.repos || {}).sort((a, b) => (minOf(b, sh) + minOf(b, gh)) - (minOf(a, sh) + minOf(a, gh)) || (a < b ? -1 : 1));
    const colour = r => REPO_COLOURS[ranked.indexOf(r) % REPO_COLOURS.length];
    const repoBar = where => {
      const xs = ranked.map(r => [r, minOf(r, where)]).filter(x => x[1] > 0).sort((a, b) => b[1] - a[1]), top = xs.slice(0, 4), rest = xs.slice(4);
      const restMin = rest.reduce((s, x) => s + x[1], 0);
      return bar(top.map(([r, m]) => [short(r), Math.round(m), colour(r)]).concat(rest.length ? [['other (' + rest.length + ' repo' + (rest.length > 1 ? 's' : '') + ')', Math.round(restMin), '#55556b']] : []));
    };
    // GitHub-hosted minutes are free on public repos; private repos use the account's minutes
    const vis = v.visibility || {}, ghBy = k => Object.keys(st.repos || {}).filter(r => vis[r] === k).reduce((s, r) => s + minOf(r, gh), 0);
    const ghKnown = Object.keys(st.repos || {}).every(r => vis[r]);
    const ghRows = ghKnown ? [['Private (billed)', mins(ghBy('private')), 'Repos that are private: these minutes count against the account'], ['Public (free)', mins(ghBy('public')), 'Public repos: GitHub-hosted minutes are free']] : [];
    const cs = [
      metricCard('Runs', 'Workflow runs that finished in the period. Opens the past runs', pi, T, { get: w => w.runs, fmt: num, spark: spark(series('runs')), perDay: one, href: runs({ when: 'period' }),
        extra: resultBar(W.runs, W.runsOk, W.runsFailed, W.runsCancelled, 'runs') }),
      metricCard('Jobs', 'Jobs that finished in the period (skipped jobs not counted)', pi, T, { get: w => w.jobs, fmt: num, spark: spark(series('jobs')), perDay: one,
        extra: resultBar(W.jobs, W.jobsOk, W.jobsFailed, W.jobsCancelled, 'jobs') }),
      metricCard('Minutes on the X3', 'Wall-clock minutes of finished jobs that ran on the self-hosted runners', pi, T, { get: w => w.min[sh], fmt: mins, spark: spark(series(sh)), perDay: mins,
        extra: repoBar(sh), rows: [['Jobs', num(W.jobsBy[sh])]] }),
      metricCard('Minutes on GitHub', 'Wall-clock minutes of finished jobs that ran on GitHub-hosted runners. GitHub bills each job separately and rounds it up to the whole minute, so this understates the billed minutes', pi, T, { get: w => w.min[gh], fmt: mins, spark: spark(series(gh)), perDay: mins,
        extra: repoBar(gh), rows: ghRows.concat([['Jobs', num(W.jobsBy[gh])]]) }),
      metricCard('Success rate', 'Finished runs that succeeded, of those that succeeded or failed (a cancelled run is not a verdict; a timeout is a failure). Opens the failed runs', pi, T, { pp: true, get: w => rate(w.runsOk, w.runsFailed), fmt: pct, href: runs({ concl: 'failure', when: 'period' }),
        extra: bar([['succeeded', W.runsOk, '#3fb950'], ['failed', W.runsFailed, '#f85149']]),
        rows: [['Over jobs', pct(rate(W.jobsOk, W.jobsFailed)), 'The same, counted over jobs'], ['Cancelled runs', num(W.runsCancelled)]] }),
      metricCard('Median queue wait', 'The time from a job being created to a runner starting it, the middle one of the finished jobs', pi, T, { get: w => w.queueMedianS.all, fmt: dur,
        rows: [['X3', dur(W.queueMedianS[sh])], ['GitHub', dur(W.queueMedianS[gh])]] }),
      metricCard('GitHub minutes saved (est.)', 'The minutes the self-hosted runners ran, at GitHub\'s list price of $' + st.rate + ' a minute for a Linux 2-core hosted runner. Wall-clock time understates what GitHub would bill: it rounds every job up to the whole minute, and runs parallel jobs separately. The private repos\' free monthly minutes are not subtracted', pi, T,
        { get: w => w.savedUsd, fmt: usd, spark: spark(d.map(x => x[sh] * st.rate)), perDay: usd,
          rows: [['X3 minutes', mins(W.min[sh])], ['Rate', '$' + st.rate + ' / min']] })];
    // Slot pressure: from VictoriaMetrics (slotStats), so it can be missing or still loading; compared with the period before as the others are
    const s = slots && slots[per], sOk = s && s.st === 'ok', sv = sOk && s.cur || {};
    const slotNote = !s || s.st === 'loading' ? 'reading VictoriaMetrics&hellip;' : !sOk ? 'VictoriaMetrics did not answer: no slot numbers' : sv.share == null && sv.wait == null && sv.peak == null ? 'no slot numbers in VictoriaMetrics for this period' : '';
    cs.push(metricCard('Slot pressure (X3)', 'The share of the period with a job waiting for an X3 job slot (x3_ci_jobs_waiting_for_slot, pushed every minute), the longest wait and the most slots held at once. Opens the runners board in Grafana', Object.assign({}, pi, { held: true, cur: sOk ? s.cur : null, prev: sOk ? s.prev : null }), sOk && s.today || {},
      { get: w => w.share, fmt: pct, pp: true, href: GRAFANA_RUNNERS, extra: mut(slotNote),
        rows: [['Longest wait', dur(sv.wait), 'The oldest job waiting for a slot, at its worst minute'], ['Peak slots held', sv.peak == null ? '&mdash;' : num(sv.peak) + (sv.total == null ? '' : ' of ' + num(sv.total))]] }));
    // Runner use: the X3 job wall-clock seconds of the period over the X3 runners there are now times the period's seconds
    const x3 = v.machines.find(m => m.machine === 'x3'), x3Names = x3 ? new Set(x3.runners.map(r => r.name)) : new Set(), x3Up = x3 ? new Set(x3.runners.filter(r => r.status === 'online').map(r => r.name)) : new Set();
    const secsOf = w => w === T ? (st.windows && st.windows.today ? (Date.parse(st.windows.today[1]) - Date.parse(st.windows.today[0])) / 1000 : null) : pi.n * 86400;
    const topX3 = Object.keys(st.repos || {}).filter(r => minOf(r, sh) > 0).sort((a, b) => minOf(b, sh) - minOf(a, sh) || (a < b ? -1 : 1)).slice(0, 3);
    cs.push(metricCard('Runner use (X3)', 'The X3 jobs\' wall-clock time in the period as a share of what the X3 runners could have run: the runners registered now times the period\'s length. The earlier period is measured against today\'s runner count too', pi, T,
      { get: w => { const sec = secsOf(w); return x3Names.size && sec > 0 && w.min ? w.min[sh] * 60 / (x3Names.size * sec) : null; }, fmt: pct, pp: true,
        rows: topX3.map(r => [esc(short(r)), mins(minOf(r, sh)) + ' min', 'X3 minutes of the period']).concat([['Runners online now', x3 ? x3Up.size + ' of ' + x3Names.size : '&mdash;']]) }));
    // Flaky jobs and Time lost: counted by the collector from the finished jobs it holds (ci-job.js computeStats); an older ci.json has neither
    const flk = (W.flakyTop || []).slice(0, 3).map(j => [esc(short(j.repo)) + ' &middot; ' + esc(j.job), num(j.n), 'Flaky runs of this job in the period']);
    cs.push(metricCard('Flaky jobs', 'Jobs that failed on one attempt of a run and succeeded on a later attempt of the same run, counted when the later attempt finished. Only attempts the collector saw finish are known: a retry started before it read the failed one does not count', pi, T,
      { get: w => w.flaky, fmt: num, perDay: W.flaky == null ? null : one, extra: W.flaky == null ? mut('not counted in this ci.json yet') : '', rows: flk }));
    const lostOf = w => w.lost ? w.lost.failed[sh] + w.lost.failed[gh] + w.lost.cancelled[sh] + w.lost.cancelled[gh] + w.lost.queueX3 : null, L = W.lost;
    const split = k => L ? mins(L[k][sh]) + ' X3 &middot; ' + mins(L[k][gh]) + ' GitHub' : '&mdash;';
    cs.push(metricCard('Time lost', 'Minutes of finished jobs that failed, timed out or were cancelled, plus the minutes X3 jobs waited for a runner beyond the first minute', pi, T,
      { get: lostOf, fmt: mins, perDay: L ? mins : null, extra: L ? bar(by(Math.round(L.failed[sh] + L.cancelled[sh]), Math.round(L.failed[gh] + L.cancelled[gh]))) : mut('not counted in this ci.json yet'),
        rows: [['Failed (min)', split('failed'), 'Failed and timed-out jobs'], ['Cancelled (min)', split('cancelled')], ['Queue beyond 1 min (X3)', L ? mins(L.queueX3) : '&mdash;', 'Minutes X3 jobs waited past the first minute between being created and starting']] }));
    return '<div class=charts>' + cs.join('') + '</div>';
  }

  function repoTable(v, per) {
    const st = v.stats;
    if (!st || !st.repos || !st.total || !st.total[per]) return '';
    const pi = periodInfo(st, per), sh = 'self-hosted', gh = 'hosted', T = st.total;
    const repos = Object.keys(st.repos).sort((a, b) => st.repos[b][per].runs - st.repos[a][per].runs || (a < b ? -1 : 1));
    const row = (label, c, p) => '<td>' + label + '</td><td>' + num(c.runs) + '</td><td class=u>' + ((pi.held && deltaText(delta(c.runs, p.runs))) || '&mdash;') + '</td><td>' + pct(rate(c.runsOk, c.runsFailed)) + '</td><td>' + num(c.jobs)
      + '</td><td>' + mins(c.min[sh]) + '</td><td>' + mins(c.min[gh]) + '</td><td>' + dur(c.queueMedianS.all) + '</td><td>' + usd(c.savedUsd) + '</td>';
    return '<h3 class=sectitle>By repo &middot; ' + esc(pi.label) + '</h3><table class=ctbl><thead><tr><th>Repo</th><th>Runs</th><th title="against ' + pi.before + '">vs before</th><th title="succeeded of succeeded or failed">Success</th><th>Jobs</th><th>X3 min</th><th>GitHub min</th><th title="median, created to started">Queue</th><th title="X3 minutes at the list price">Saved</th></tr></thead><tbody>'
      + repos.map(r => '<tr>' + row('<a href="' + listHref({ repo: short(r), period: per, when: 'period' }) + '" target=_self>' + esc(short(r)) + '</a>' + ((v.visibility || {})[r] === 'public' ? ' <span class=muted style="font-size:11px" title="public: GitHub-hosted minutes are free">public</span>' : ''), st.repos[r][per], st.repos[r][per + 'Prev']) + '</tr>').join('')
      + '<tr style="font-weight:600">' + row('All', T[per], T[per + 'Prev']) + '</tr></tbody></table>'
      + '<p class=sec>A repo links to its past runs. A repo that could not be read keeps its last numbers.</p>';
  }

  // The steps that cost the X3 most against GitHub (ci-job.js computeSteps): median of the successful runs of the step in the
  // period, the GitHub median beside it, the X3 median of the period before. Each row opens the repo's runs of the period.
  function slowStepsTable(v, per) {
    const rows = v.steps && v.steps[per];
    if (!rows) return '';
    const st = v.stats, pi = st && st.total && st.total[per] ? periodInfo(st, per) : null;
    const head = '<h3 class=sectitle>Slowest steps on the X3 vs GitHub' + (pi ? ' &middot; ' + esc(pi.label) : '') + '</h3>';
    if (!rows.length) return head + '<p class=muted>No successful step ran on the X3 in this period.</p>';
    const med = x => x ? dur(x.med) + ' <span class=muted>(' + num(x.n) + ')</span>' : '&mdash;';
    const diff = r => !r.gh ? '&mdash;' : (r.x3.med >= r.gh.med ? '+' : '&minus;') + dur(r.x3.med - r.gh.med);
    return head + '<table class=ctbl><thead><tr><th>Repo / job / step</th><th title="median of the successful runs of the step on the X3, and how many">X3</th><th title="the same on GitHub-hosted runners">GitHub</th><th title="X3 minus GitHub, the median of each">Difference</th>'
      + '<th title="the X3 median in ' + esc(pi ? pi.before : 'the period before') + ', and the change to this period">X3 before</th></tr></thead><tbody>'
      + rows.map(r => '<tr><td><a href="' + listHref({ repo: short(r.repo), period: per, when: 'period' }) + '" target=_self>' + esc(short(r.repo)) + '</a> &middot; ' + esc(r.job) + ' &middot; ' + esc(r.step) + '</td><td>' + med(r.x3) + '</td><td>' + med(r.gh) + '</td><td>' + diff(r)
        + '</td><td>' + med(r.x3Prev) + (r.x3Prev ? ' <span class=u>' + (deltaText(delta(r.x3.med, r.x3Prev.med)) || '') + '</span>' : '') + '</td></tr>').join('') + '</tbody></table>'
      + '<p class=sec>Successful steps of successful jobs, the 15 where the X3 loses most time against GitHub (the difference of the medians times the X3 runs; a step GitHub did not run is ranked by its whole X3 time). A step links to its repo\'s runs of the period.</p>';
  }

  function runnerCard(r, now, stale) {
    const what = r.status !== 'online' ? 'offline' + (r.offlineSince != null ? ' ' + dur(now - r.offlineSince) : '') : r.busy ? 'busy' : 'idle';
    const cur = r.now ? '<a href="' + runHref(r.repo, r.now.runId) + '" target=_self title="' + esc(r.now.workflow + ' / ' + r.now.job) + '">' + esc(r.now.job) + '</a>'
      : r.status !== 'online' ? '&mdash;' : r.busy ? 'a job (not in the runs read)' : 'nothing';
    return '<div class="card ci"><h3>' + esc(short(r.repo)) + '</h3><div class=cv style="font-size:15px">' + dot(r.state, stale) + what + '</div>'
      + kv([['Runner', /^x3-/.test(r.name || '') ? '<a href="' + GRAFANA_RUNNERS + '?var-runner=' + encodeURIComponent(r.name) + '" title="This runner in Grafana">' + esc(r.name) + '</a>' : esc(r.name)], ['Running', cur], ['Jobs, 24 h', num(r.jobs24)], ['Minutes, 24 h', mins(r.min24)]]) + '</div>';
  }

  function listHtml(v, now, route, slots) {
    const st = v.stale;
    let h = '';
    const per = route.period || PERIOD_DEFAULT;
    h += periodNav(per, route) + (v.stats && v.stats.total && v.stats.total[per] ? '<p class=sec style="margin:-8px 0 12px">' + esc(periodInfo(v.stats, per).label)
      + ' &middot; every number covers the same completed UTC days; only "Today so far" is live</p>' : '');
    h += cardsHtml(v, per, route, slots) + repoTable(v, per) + slowStepsTable(v, per);

    h += '<h3 class=sectitle>Runners</h3><p class=sec style="margin:-6px 0 10px"><a href="' + GRAFANA_RUNNERS + '">Grafana dashboard</a> for the X3 fleet: CPU, memory, disk, job slots, the sync log</p>' + (v.machines.length ? v.machines.map(m => '<h3 class=sectitle style="margin-top:8px;border:0">' + dot(m.state, st) + esc(m.machine) + ' <span class=muted style="font-weight:400;text-transform:none">' + m.online + ' online, ' + m.busy + ' busy' + (m.offline ? ', ' + m.offline + ' offline' : '') + '</span></h3><div class=charts>' + m.runners.map(r => runnerCard(r, now, st)).join('') + '</div>').join('')
      : '<p class=muted>no runners registered on these repos</p>') + '<p class=sec>' + RUNNER_NOTE + '</p>';

    h += '<h3 class=sectitle>Queue now</h3>' + (v.queued.length ? '<table class=ctbl>' + v.queued.map(j => '<tr><td>' + dot(j.state, st) + esc(short(j.repo)) + '</td><td>' + (j.runId ? '<a href="' + runHref(j.repo, j.runId) + '" target=_self>' + esc(j.workflow) + ' / ' + esc(j.name) + '</a>' : esc(j.workflow) + ' / ' + esc(j.name)) + '</td><td>waiting ' + dur(j.waitS) + '</td><td class=u>' + link(j.url, 'GitHub') + '</td></tr>').join('') + '</table>'
      + (v.idleOther ? '<p class=sec>' + v.queued.length + ' queued while ' + v.idleOther + ' runner' + (v.idleOther === 1 ? ' is' : 's are') + ' idle in repos with nothing queued. ' + RUNNER_NOTE + '</p>' : '')
      : '<p class=muted>nothing queued</p>');

    h += '<h3 class=sectitle>Failures, last 24 h</h3><table class=ctbl>' + v.failures.map(f => '<tr><td>' + dot(f.state, st) + '<a href="' + listHref({ repo: short(f.repo), concl: 'failure', period: route.period }) + '" target=_self>' + esc(short(f.repo)) + '</a></td><td>' + f.failed + ' failed</td><td class=u>of ' + f.finished + ' finished jobs</td></tr>').join('') + '</table>';

    h += pastRuns(v, route, st);
    h += '<p class=sec>Amber: a job waiting over ' + QUEUE_WARN / 60 + ' min, a runner offline under ' + OFFLINE_BAD / 60 + ' min, a cancelled run or job, a repo with a failure in 24 h. Red: a job waiting over ' + QUEUE_BAD / 60 + ' min, a runner offline ' + OFFLINE_BAD / 60 + ' min or more, a failed or timed-out run or job, a repo where half of 3 or more jobs failed.</p>';
    return h;
  }

  function pastRuns(v, route, stale) {
    const per = route.period || PERIOD_DEFAULT, pw = v.stats && v.stats.windows && v.stats.windows[per];
    const win = route.when === 'period' && pw ? [Date.parse(pw[0]), Date.parse(pw[1])] : null;
    const pg = pageRuns(v.runs, Object.assign({}, route, { win }), undefined), repos = v.repos.map(short);
    const opt = (val, label, cur) => '<option value="' + esc(val) + '"' + (val === cur ? ' selected' : '') + '>' + esc(label) + '</option>';
    const perLabel = (PERIODS.find(x => x[0] === per) || [, per])[1];
    let h = '<h3 class=sectitle id=ci_runs>Past runs</h3>';
    h += '<div class=ci-bar><label>When <select id=ci_f_when>' + opt('any', 'any time', route.when || 'any') + opt('period', perLabel.toLowerCase() + (pw ? ' (' + String(pw[0]).slice(0, 10) + ' to ' + new Date(Date.parse(pw[1]) - 86400000).toISOString().slice(0, 10) + ')' : ''), route.when || 'any') + '</select></label> '
      + '<label>Repo <select id=ci_f_repo>' + opt('all', 'all repos', route.repo) + repos.map(r => opt(r, r, route.repo)).join('') + '</select></label> '
      + '<label>Result <select id=ci_f_concl>' + CONCLUSIONS.map(c => opt(c, c === 'all' ? 'any result' : c === 'running' ? 'running or queued' : c === 'failure' ? 'failed or timed out' : c, route.concl)).join('') + '</select></label>'
      + '<span class=muted> ' + num(pg.total) + ' run' + (pg.total === 1 ? '' : 's') + (v.runs.length ? win ? ' finished in the period' : ' of the last 30 days' : '')
      + (v.runsHeld > v.runs.length ? ' (the list holds the newest ' + num(v.runs.length) + ' of the ' + num(v.runsHeld) + ' runs held, from ' + esc(String(v.runs[v.runs.length - 1].finishedAt || v.runs[v.runs.length - 1].created).slice(0, 10)) + ')' : '') + '</span></div>';
    if (!v.runs.length) return h + '<p class=muted>The collector has not listed any run yet.</p>';
    if (!pg.total) return h + '<p class=muted>No run matches this filter.</p>';
    h += '<table class=ctbl><thead><tr><th>Result</th><th>Repo</th><th>Run</th><th>Branch</th><th>Event</th><th>Finished</th><th>Duration</th><th title="from the first job being created to a runner starting it">Queue</th><th title="jobs, of them on the X3">Jobs</th><th></th></tr></thead><tbody>'
      + pg.rows.map(r => '<tr><td>' + dot(r.state, stale) + esc(r.status === 'completed' ? r.conclusion || 'done' : r.status === 'in_progress' ? 'running' : r.status) + '</td><td class=u>' + esc(short(r.repo)) + '</td><td><a href="' + runHref(r.repo, r.id) + '" target=_self>' + esc(r.workflow) + '</a>'
        + (r.attempt > 1 ? ' <span class=muted>#' + r.attempt + '</span>' : '') + '<div class=muted style="font-size:12px;max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + esc(r.title) + '">' + esc(r.title) + '</div></td><td class=u>' + esc(r.branch) + '</td><td class=u>' + esc(r.event)
        + '</td><td>' + (r.finishedAt ? when(r.finishedAt) : '&mdash;') + '</td><td>' + dur(r.durS) + '</td><td>' + dur(r.queueS) + '</td><td class=u>' + r.jobs + (r.selfHosted ? ' (' + r.selfHosted + ' X3)' : '') + '</td><td style="white-space:nowrap">' + link(r.url, '<span class=muted style="font-size:11px">GitHub &#8599;</span>') + '</td></tr>').join('') + '</tbody></table>';
    const a = (p, t) => p < 1 || p > pg.pages || p === pg.page ? '<span class=muted>' + t + '</span>' : '<a href="' + listHref(Object.assign({}, route, { page: p })) + '" target=_self>' + t + '</a>';
    h += '<p class=sec style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">' + a(1, '&laquo; first') + a(pg.page - 1, '&lsaquo; newer') + '<span>page ' + pg.page + ' of ' + pg.pages + ' &middot; ' + pg.per + ' per page</span>' + a(pg.page + 1, 'older &rsaquo;') + a(pg.pages, 'last &raquo;') + '</p>';
    return h;
  }

  // ---- one run
  const whereLabel = j => j.where === 'self-hosted' ? (((j.labels || []).find(l => !['self-hosted', 'linux', 'x64'].includes(l))) || 'self-hosted') + ' (self-hosted)' : 'GitHub (hosted)';
  const secs = (a, b) => a && b ? Math.max(0, (Date.parse(b) - Date.parse(a)) / 1000) : null;
  function runSummary(d) {
    const js = d.jobs || [], started = js.filter(j => j.started), done = js.filter(j => j.completed);
    const finished = d.status === 'completed' && done.length ? done.map(j => j.completed).sort().slice(-1)[0] : null;
    return { finishedAt: finished, durS: finished ? secs(d.started || d.created, finished) : null,
      queueS: started.length ? Math.max(0, Math.min.apply(0, started.map(j => Date.parse(j.started))) / 1000 - Math.min.apply(0, js.map(j => Date.parse(j.created))) / 1000) : null,
      selfHosted: js.filter(j => j.where === 'self-hosted').length };
  }

  // log text -> lines marked: ##[error] red, ##[warning] amber, the collector's own header lines dim
  function logLines(text) {
    return String(text).split('\n').map(l => ({ text: l, kind: /^# (ci-log|\.\.\.)/.test(l) ? 'meta' : l.includes('##[error]') ? 'err' : l.includes('##[warning]') ? 'warn' : /##\[(group|endgroup)\]/.test(l) ? 'grp' : '' }))
      .filter((l, i, a) => !(i === a.length - 1 && l.text === ''));
  }
  const logHtml = text => {
    const ls = logLines(text), errs = ls.filter(l => l.kind === 'err').length;
    return '<div class=muted style="font-size:12px;margin:2px 0">' + ls.length + ' lines kept' + (errs ? ' &middot; <span style="color:#f85149">' + errs + ' ##[error] line' + (errs === 1 ? '' : 's') + '</span>' : '') + '</div>'
      + '<pre class=ci-log tabindex=0>' + ls.map(l => '<span class="ln' + (l.kind ? ' ' + l.kind : '') + '">' + (l.text === '' ? ' ' : esc(l.text)) + '</span>').join('') + '</pre>';
  };

  function jobLog(j, logs, keep) {
    const L = logs && logs[j.id];
    const ghLink = ' ' + link(j.url, 'full log on GitHub');
    if (j.status !== 'completed') return '<p class=muted>The job has not finished; its log is fetched after it does.' + ghLink + '</p>';
    if (j.conclusion === 'skipped') return '<p class=muted>The job was skipped: it has no log.</p>';
    if (!L || L.st === 'loading') return '<p class=muted>loading the log&hellip;</p>';
    if (L.st === 'none') return '<p class=muted>The log is not fetched yet: the collector reads the log of each finished job once, for the newest ' + (keep || 200) + ' jobs, every 5 minutes. Older jobs are not kept.' + ghLink + '</p>';
    if (L.st === 'error') return '<p class=muted>The log could not be loaded (' + esc(L.msg || 'error') + ').' + ghLink + '</p>';
    return logHtml(L.text) + '<p class=sec style="margin-top:4px">The last lines of the log, and every ##[error] line from before them, as the collector kept them.' + ghLink + '</p>';
  }

  function stepsTable(j, stale) {
    if (!j.steps || !j.steps.length) return '<p class=muted>No steps recorded.</p>';
    return '<table class=ctbl><thead><tr><th>#</th><th>Step</th><th>Result</th><th>Started</th><th>Duration</th></tr></thead><tbody>'
      + j.steps.map(s => '<tr><td class=u>' + esc(s.n) + '</td><td>' + esc(s.name) + '</td><td>' + dot(s.status !== 'completed' ? 'none' : jobState(s.conclusion), stale) + esc(s.status === 'completed' ? s.conclusion : s.status) + '</td><td class=u>' + (s.started ? hhmm(s.started) : '&mdash;') + '</td><td>' + (s.conclusion === 'skipped' ? '&mdash;' : dur(secs(s.started, s.completed))) + '</td></tr>').join('') + '</tbody></table>';
  }

  function runHtml(v, route, ctx) {
    const st = v.stale, back = '<p><a href="#ci" target=_self>&larr; All runs</a></p>', run = ctx && ctx.run || { st: 'loading' };
    const gh = ghRunUrl(v.repos, route.repo, route.id);
    if (run.st === 'loading') return back + '<p class=muted>loading the run&hellip;</p>';
    if (run.st === 'missing') return back + '<div class="abar plumb">No detail for run ' + esc(route.id) + ' of ' + esc(route.repo) + ': the collector writes a run\'s page when it reads the run (every 5 minutes) and keeps runs for 30 days.' + (gh ? ' ' + link(gh, 'Open it on GitHub') : '') + '</div>';
    if (run.st !== 'ok' || !run.d) return back + '<div class="abar warn">The run could not be loaded' + (run.msg ? ' (' + esc(run.msg) + ')' : '') + '.' + (gh ? ' ' + link(gh, 'Open it on GitHub') : '') + '</div>';
    const d = run.d, sm = runSummary(d), rs = runState(d), repoFull = (v.repos || []).find(r => short(r) === short(d.repo)) || d.repo;
    const commit = d.sha && /^[0-9a-f]{7,40}$/.test(d.sha) ? link('https://github.com/' + repoFull + '/commit/' + d.sha, '<code>' + esc(d.sha.slice(0, 7)) + '</code>') + ' ' : '';
    const result = d.status === 'completed' ? d.conclusion || 'done' : d.status === 'in_progress' ? 'running' : d.status;
    let h = back + '<h2>' + dot(rs, st) + esc(short(d.repo)) + ' &middot; ' + esc(d.workflow) + ' <span class=muted style="font-weight:400">' + esc(result) + '</span></h2>'
      + '<p class=sec style="margin-top:-4px">' + link(d.url, 'Run on GitHub &#8599;') + '</p>';
    h += '<div class="card ci ci-wide"><h3>Run</h3>' + kv([['Repo', '<a href="' + listHref({ repo: short(d.repo) }) + '" target=_self>' + esc(short(d.repo)) + '</a>'], ['Workflow', esc(d.workflow)], ['Branch', esc(d.branch)],
      ['Commit', commit + esc(d.msg || '')], ['Event', esc(d.event)], ['Actor', esc(d.actor)], ['Attempt', esc(d.attempt)],
      ['Created', whenFull(d.created)], ['Started', whenFull(d.started)], ['Finished', sm.finishedAt ? whenFull(sm.finishedAt) : d.status === 'completed' ? '&mdash;' : 'not yet'],
      ['Total duration', dur(sm.durS), 'From the run starting to its last job ending'], ['Queue wait', dur(sm.queueS), 'From the first job being created to a runner starting a job'],
      ['Result', dot(rs, st) + esc(result)]]).replace(/class=subkv/, 'class="subkv ci-kv"') + '</div>';

    h += '<h3 class=sectitle>Jobs</h3>' + ((d.jobs || []).length ? '<table class=ctbl><thead><tr><th>Job</th><th>Where</th><th>Runner</th><th>Labels</th><th>Queue</th><th>Duration</th><th>Result</th></tr></thead><tbody>'
      + d.jobs.map(j => '<tr><td>' + esc(j.name) + '</td><td>' + esc(whereLabel(j)) + '</td><td class=u>' + esc(j.runner || '') + '</td><td class=u>' + esc((j.labels || []).join(', ')) + '</td><td>' + dur(secs(j.created, j.started)) + '</td><td>' + dur(secs(j.started, j.completed)) + '</td><td>'
        + dot(j.status !== 'completed' ? 'none' : jobState(j.conclusion), st) + esc(j.status === 'completed' ? j.conclusion : j.status) + '</td></tr>').join('') + '</tbody></table>'
      : '<p class=muted>The run has no jobs (yet).</p>');
    for (const j of d.jobs || []) {
      h += '<h3 class=sectitle>' + dot(j.status !== 'completed' ? 'none' : jobState(j.conclusion), st) + esc(j.name) + ' <span class=muted style="font-weight:400;text-transform:none">' + esc(whereLabel(j)) + ' &middot; ' + dur(secs(j.started, j.completed)) + '</span> ' + link(j.url, '<span class=muted style="font-weight:400;text-transform:none">GitHub &#8599;</span>') + '</h3>'
        + '<div class=ci-job data-job="' + esc(j.id) + '"><h4 class=ci-h4>Steps</h4>' + stepsTable(j, st) + '<h4 class=ci-h4>Log</h4>' + jobLog(j, ctx && ctx.logs, v.logs && v.logs.jobsMax) + '</div>';
    }
    return h;
  }

  function html(v, now, ctx) {
    const head = '<h2>CI &middot; GitHub Actions and the X3 runners</h2>';
    if (!v.ok) return head + '<div class="abar plumb">No CI numbers: ci.json is missing or unreadable. Nothing is shown as green.</div>';
    const st = v.stale, route = ctx && ctx.route || { kind: 'list', page: 1, repo: 'all', concl: 'all' };
    let h = head + '<p class=sec>updated ' + hhmm(v.takenAt) + ' &middot; ' + v.machines.map(m => esc(m.machine) + ': ' + m.online + ' online, ' + m.busy + ' busy' + (m.offline ? ', ' + m.offline + ' offline' : '')).join(' &middot; ')
      + ' &middot; ' + v.queued.length + ' queued</p>';
    if (st) h += '<div class="abar warn">The numbers are ' + Math.round(v.ageS / 60) + ' minutes old (the CI job writes them every 5): everything is grey until it runs again.</div>';
    if (v.errors.length) h += '<div class="abar warn">The collector could not read: ' + v.errors.map(esc).join('; ') + '. Those repos are missing from the queue and the failures; the history numbers use their last successful read.</div>';
    if (v.logs && v.logs.errors && v.logs.errors.length) h += '<div class="abar plumb">Some logs could not be fetched: ' + v.logs.errors.slice(0, 3).map(esc).join('; ') + '.</div>';
    return h + (route.kind === 'run' ? runHtml(v, route, ctx) : listHtml(v, now, route, ctx && ctx.slots));
  }

  const api = { QUEUE_WARN, QUEUE_BAD, OFFLINE_BAD, STALE_AFTER, PER_PAGE, runnerState, queueState, jobState, runState, repoState, view, html, dur, parseRoute, runHref, listHref, filterRuns, pageRuns, delta, deltaText, deltaPP, rate, slotStats, logLines, logHtml, runSummary, whereLabel };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.HubCi = api;
})(typeof window !== 'undefined' ? window : globalThis);
