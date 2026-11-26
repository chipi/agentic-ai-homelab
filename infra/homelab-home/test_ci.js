#!/usr/bin/env node
// Deterministic test of hub-ci.js (the CI tab's status semantics and HTML) and ci-job.js (the collector),
// the collector run over saved GitHub API answers (fixtures-ci/, taken 2026-11-26 from the five repos) and
// once as a process against a fake VictoriaMetrics. No network, no token. Run: node infra/homelab-home/test_ci.js (exit 0 = PASS)
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const { execFile } = require('child_process');
const CI = require('./hub-ci.js');
const JOB = require('./ci-job.js');

const FX = path.join(__dirname, 'fixtures-ci');
const NOW = Date.parse('2026-11-26T22:03:00Z') / 1000;
const REPOS = ['chipi/closelistening-studio', 'chipi/closelistening-common', 'chipi/closelistening-player', 'chipi/closelistening-integration', 'chipi/infra'];

let failed = 0;
// Printed as '## [': the Actions runner reads '##[error]' in a step's output as an error annotation.
const check = (name, cond, got) => { name = name.replace(/##\[/g, '## ['); if (cond) console.log('ok   ' + name); else { failed++; console.error('FAIL ' + name + (got !== undefined ? ' (got ' + JSON.stringify(got) + ')' : '')); } };

(async () => {
  // semantics
  check('queue: under 5 min ok, 5 to 30 amber, 30 or more red', CI.queueState(299) === 'ok' && CI.queueState(300) === 'warn' && CI.queueState(1799) === 'warn' && CI.queueState(1800) === 'bad');
  check('job: success ok, cancelled amber, failure and timeout red, skipped unjudged', CI.jobState('success') === 'ok' && CI.jobState('cancelled') === 'warn' && CI.jobState('failure') === 'bad' && CI.jobState('timed_out') === 'bad' && CI.jobState('skipped') === 'none');
  check('runner: online ok; offline under 15 min amber, 15 min or more red, unknown since red', CI.runnerState({ status: 'online' }, NOW) === 'ok'
    && CI.runnerState({ status: 'offline', offlineSince: NOW - 600 }, NOW) === 'warn' && CI.runnerState({ status: 'offline', offlineSince: NOW - 900 }, NOW) === 'bad' && CI.runnerState({ status: 'offline' }, NOW) === 'bad');
  check('repo: no failure ok; one amber; half of 3 or more red; 2 of 2 only amber', CI.repoState({ failed: 0, finished: 9 }) === 'ok' && CI.repoState({ failed: 1, finished: 9 }) === 'warn'
    && CI.repoState({ failed: 3, finished: 6 }) === 'bad' && CI.repoState({ failed: 2, finished: 2 }) === 'warn');

  // the collector over the fixtures
  // the saved answers have every runner online; one is taken offline here (player-3), as GitHub reports it
  const base = JOB.fixtureApi(FX);
  const api = async p => { const j = await base(p); if (/closelistening-player\/actions\/runners/.test(p)) j.runners.find(r => r.name === 'x3-closelistening-player-3').status = 'offline'; return j; };
  const run1 = await JOB.collect({ api, now: NOW, repos: REPOS, state: JOB.emptyState() });
  const d = run1.doc;
  check('collect: no errors, 5 repos', run1.errors.length === 0 && d.repos.length === 5, run1.errors);
  check('collect: runners carry the machine label, not self-hosted/linux/x64', d.runners.length === 8 && d.runners.every(r => r.machine === 'x3'), d.runners.map(r => r.machine));
  const off = d.runners.find(r => r.status === 'offline');
  check('collect: the offline runner has an offlineSince, an online one does not', off && off.offlineSince === NOW && d.runners.filter(r => r.status === 'online').every(r => r.offlineSince === null), off);
  check('collect: queued jobs are the fixtures\' queued ones', d.queued.length > 0 && d.queued.every(j => j.repo && j.createdAt && /github\.com/.test(j.url)), d.queued.length);
  check('collect: recent is newest first, capped at 50, each finished with a conclusion', d.recent.length > 0 && d.recent.length <= 50 && d.recent.every((j, i, a) => j.conclusion && j.durS >= 0 && j.queueS >= 0 && (i === 0 || a[i - 1].completedAt >= j.completedAt)), d.recent.length);
  check('collect: jobs split by the runner labels; both kinds seen', d.recent.every(j => j.where === (/^x3-/.test(j.runner || '') ? 'self-hosted' : 'hosted')) && d.minutes['24h']['self-hosted'] > 0 && d.minutes['24h'].hosted > 0, d.minutes);
  const f = Object.values(d.failures);
  check('collect: failures per repo, failed never above finished', f.length === 5 && f.every(x => x.failed <= x.finished) && f.some(x => x.failed > 0), d.failures);
  check('collect: 30 d minutes cover the 24 h ones', d.minutes['30d']['self-hosted'] >= d.minutes['24h']['self-hosted'] && !!d.minutes.since30d, d.minutes);
  const g = n => run1.gauges.filter(x => x[0] === n);
  check('metrics: runner up/busy per runner, bounded labels', g('gh_runner_up').length === 8 && g('gh_runner_busy').length === 8
    && run1.gauges.every(x => Object.keys(x[2]).every(k => ['repo', 'runner', 'machine', 'conclusion', 'where'].includes(k))));
  const qmax = g('gh_job_queue_seconds_max'), qn = g('gh_jobs_queued');
  check('metrics: queued count and longest wait per repo, the sum matching ci.json', qmax.length === 5 && qn.reduce((n, x) => n + x[1], 0) === d.queued.length
    && Math.max.apply(0, qmax.map(x => x[1])) === Math.max.apply(0, d.queued.map(j => NOW - Date.parse(j.createdAt) / 1000)), qmax);
  check('metrics: finished by conclusion (4) and minutes by where (2) per repo', g('gh_jobs_finished_24h').length === 20 && g('gh_minutes_24h').length === 10);

  // state: a second run reads no job it already has, and keeps the totals
  let jobCalls = 0;
  const counting = async p => { if (/\/jobs/.test(p)) jobCalls++; return api(p); };
  const run2 = await JOB.collect({ api: counting, now: NOW + 300, repos: REPOS, state: JSON.parse(JSON.stringify(run1.state)) });
  const open = d.recent.length ? Object.values(run1.state.runs).filter(r => r.jobs.some(j => j.status !== 'completed')).length : 0;
  check('state: the second run fetches jobs only of runs still open', jobCalls <= 5 * 4 + open * 2 && jobCalls < 40, jobCalls);
  check('state: the second run keeps the minutes', run2.doc.minutes['30d']['self-hosted'] === d.minutes['30d']['self-hosted'], run2.doc.minutes);
  check('state: an offline runner keeps its first offlineSince', run2.doc.runners.find(r => r.name === off.name).offlineSince === NOW);
  const old = JSON.parse(JSON.stringify(run1.state));
  const run3 = await JOB.collect({ api, now: NOW + 40 * 86400, repos: REPOS, state: old });
  check('state: a job older than 30 days leaves the ledger', Object.keys(run3.state.ledger).length === 0 && run3.doc.minutes['30d']['self-hosted'] === 0);

  // one repo failing to read does not take the others down, and shows no false green
  const flaky = async p => { if (/closelistening-player/.test(p)) throw new Error('HTTP 403'); return api(p); };
  const run4 = await JOB.collect({ api: flaky, now: NOW, repos: REPOS, state: JOB.emptyState() });
  check('error: the failing repo is named; the others are read; it has no failure row and no gauges', run4.errors.length === 1 && /closelistening-player: HTTP 403/.test(run4.errors[0]) && run4.doc.runners.length === 5
    && !('chipi/closelistening-player' in run4.doc.failures) && !run4.gauges.some(x => x[2].repo === 'chipi/closelistening-player' && x[0] === 'gh_jobs_queued'), run4.errors);
  check('error: the token never appears in an error', !JSON.stringify(run4).includes('Bearer'));

  // the view and the page
  let v = CI.view(d, NOW + 60);
  check('view: fresh, runners grouped by machine, the longest wait first', v.ok && !v.stale && v.machines.length === 1 && v.machines[0].machine === 'x3' && v.queued.every((j, i, a) => i === 0 || a[i - 1].waitS >= j.waitS), v.machines.map(m => m.machine));
  check('view: counts online, busy and offline', v.machines[0].online === 7 && v.machines[0].offline === 1 && v.machines[0].busy >= 1, v.machines[0]);
  check('view: a queue of over 30 minutes makes the whole state red', d.queued.some(j => NOW - Date.parse(j.createdAt) / 1000 >= 1800) ? v.state === 'bad' : true, v.state);
  v = CI.view(d, NOW + 16 * 60);
  check('view: older than 15 minutes is stale, never green', v.stale && v.state === 'stale');
  check('view: exactly 15 minutes is fresh', !CI.view(d, NOW + 900).stale);
  check('view: a missing ci.json is not ok', !CI.view(null, NOW).ok && !CI.view({ takenAt: 'x' }, NOW).ok);

  const html = CI.html(CI.view(d, NOW + 60), NOW + 60);
  check('html: cards, by repo, runners, queue, failures, past runs, links to GitHub', ['Runs</h3>', 'Jobs</h3>', 'Minutes on the X3', 'Minutes on GitHub', 'Success rate', 'Median queue wait', 'GitHub minutes saved', 'By repo, last 7 days', 'Runners', 'Queue now', 'Failures, last 24 h', 'Past runs'].every(s => html.includes(s)) && /href="https:\/\/github\.com\/chipi\//.test(html), html.slice(0, 200));
  check('html: the offline runner is said so', /offline 0 s|offline 5 min|offline/.test(html) && /dot down/.test(html));
  const stale = CI.html(CI.view(d, NOW + 3600), NOW + 3600);
  check('html: stale numbers are grey with a notice, no green, amber or red dot', /dot stale/.test(stale) && !/dot up|dot mid|dot down/.test(stale) && /60 minutes old/.test(stale));
  check('html: a missing ci.json says so, shows nothing green', /missing or unreadable/.test(CI.html(CI.view(null, NOW), NOW)) && !/dot up/.test(CI.html(CI.view(null, NOW), NOW)));
  const evil = JSON.parse(JSON.stringify(d)); evil.runs[0].title = '<b>x</b>'; evil.runs[0].url = 'javascript:alert(1)'; evil.runs[0].branch = '"><img src=x>';
  const eh = CI.html(CI.view(evil, NOW), NOW);
  check('html: names are escaped and only github.com links are made', /&lt;b&gt;x&lt;\/b&gt;/.test(eh) && !/<b>x<\/b>/.test(eh) && !/javascript:/.test(eh) && !/<img src=x>/.test(eh));
  check('html: a collector error is shown', /could not read: chipi\/closelistening-player: HTTP 403/.test(CI.html(CI.view(run4.doc, NOW), NOW)));
  check('dur: seconds, minutes, hours', CI.dur(30) === '30 s' && CI.dur(1500) === '25 min' && CI.dur(11400) === '3 h 10 min');

  // ---- the cards: the numbers
  // from the fixtures, derived here again straight from the saved jobs (not through the collector)
  const D = 86400, SH = 'self-hosted';
  const fxJobs = fs.readdirSync(FX).filter(f => /^jobs-/.test(f)).flatMap(f => JSON.parse(fs.readFileSync(path.join(FX, f), 'utf8')).jobs);
  const fin = fxJobs.filter(j => j.status === 'completed' && j.conclusion !== 'skipped' && j.started_at && j.completed_at);
  const within = (a, b) => fin.filter(j => { const t = Date.parse(j.completed_at) / 1000; return t >= a && t < b; });
  const sumMin = (js, where) => js.filter(j => (j.labels.includes(SH) ? SH : 'hosted') === where).reduce((s, j) => s + (Date.parse(j.completed_at) - Date.parse(j.started_at)) / 60000, 0);
  const T = d.stats.total;
  for (const [name, a, b] of [['today', Math.floor(NOW / D) * D, NOW + 1], ['last 7 d', NOW - 7 * D, NOW + 1], ['the 7 d before', NOW - 14 * D, NOW - 7 * D], ['last 30 d', NOW - 30 * D, NOW + 1]]) {
    const w = T[{ today: 'today', 'last 7 d': 'd7', 'the 7 d before': 'p7', 'last 30 d': 'd30' }[name]], js = within(a, b);
    check('stats ' + name + ': jobs and minutes split X3 / GitHub match the saved jobs', w.jobs === js.length && Math.abs(w.min[SH] - sumMin(js, SH)) < 0.2 && Math.abs(w.min.hosted - sumMin(js, 'hosted')) < 0.2
      && w.jobsBy[SH] + w.jobsBy.hosted === w.jobs, [w.jobs, js.length, w.min, sumMin(js, SH), sumMin(js, 'hosted')]);
  }
  check('stats: the fixtures hold both kinds in the last 7 days, and some earlier history', T.d7.jobsBy[SH] > 0 && T.d7.jobsBy.hosted > 0 && T.p7.jobs > 0 && T.d30.jobs > T.d7.jobs);
  check('stats: runs counted, outcomes never above runs; jobs the same', T.d7.runs > 0 && T.d7.runsOk + T.d7.runsFailed + T.d7.runsCancelled <= T.d7.runs && T.d7.jobsOk + T.d7.jobsFailed + T.d7.jobsCancelled <= T.d7.jobs);
  check('stats: 30 days of runs are in the list, newest first, each with a result or a status', d.runs.length > 100 && d.runs.every((r, i, a) => r.status && (i === 0 || (a[i - 1].finishedAt || a[i - 1].created) >= (r.finishedAt || r.created))), d.runs.length);
  check('stats: per repo, the repos add up to the total', Object.values(d.stats.repos).reduce((s, p) => s + p.d7.jobs, 0) === T.d7.jobs && Object.keys(d.stats.repos).length === 5);
  check('stats: saved is the X3 minutes at the stated rate', T.d30.savedUsd === Math.round(T.d30.min[SH] * 0.008 * 100) / 100 && d.stats.rate === 0.008);
  check('stats: 14 daily points, oldest first, ending today', d.stats.daily.length === 14 && d.stats.daily[13].day === '2026-11-26' && d.stats.daily[0].day === '2026-11-13');

  // the windows, by hand: 2026-11-26 12:00 UTC; today so far against yesterday up to 12:00, 7 d against the 7 before
  const N0 = Date.parse('2026-11-26T12:00:00Z') / 1000, at = (days, h) => Date.parse('2026-11-26T00:00:00Z') / 1000 - days * D + h * 3600;
  const led = {
    1: [at(0, 10), 600, SH, 'r/a', 'success', 10, 101, 'x3-a-1'], 2: [at(0, 11.5), 1200, 'hosted', 'r/a', 'failure', 30, 102, null], 3: [at(0, 13), 60, SH, 'r/a', 'success', 1, 103, null],
    4: [at(1, 9), 300, SH, 'r/a', 'success', 20, 104, null], 5: [at(1, 15), 3000, 'hosted', 'r/b', 'success', 60, 105, null], 6: [at(3, 12), 120, SH, 'r/b', 'cancelled', 0, 106, null],
    7: [at(9, 12), 60, 'hosted', 'r/a', 'success', 40, 107, null], 8: [at(20, 12), 1800, SH, 'r/b', 'success', 5, 108, null], 9: [at(40, 12), 999, SH, 'r/b', 'success', 5, 109, null] };
  const mkRun = (repo, u, c) => ({ repo, u: new Date(u * 1000).toISOString(), status: 'completed', conclusion: c, created: new Date((u - 60) * 1000).toISOString(), started: new Date((u - 60) * 1000).toISOString(), jobs: [] });
  const runs0 = { 1: mkRun('r/a', at(0, 10), 'success'), 2: mkRun('r/a', at(0, 11.5), 'failure'), 3: mkRun('r/b', at(3, 12), 'cancelled'), 4: mkRun('r/a', at(1, 9), 'success'), 5: mkRun('r/b', at(2, 9), 'timed_out'),
    6: Object.assign(mkRun('r/a', at(0, 11), null), { status: 'in_progress' }) };
  const S0 = JOB.computeStats(led, runs0, ['r/a', 'r/b'], N0), W0 = S0.total;
  check('windows: today so far is 00:00 UTC to now (a job "after now" and one 40 days old are in none)', W0.today.jobs === 2 && W0.today.min[SH] === 10 && W0.today.min.hosted === 20 && W0.today.jobsOk === 1 && W0.today.jobsFailed === 1, W0.today);
  check('windows: yesterday the same time is 00:00 to 12:00, the whole day is more', W0.yesterday.jobs === 1 && W0.yesterday.min[SH] === 5 && W0.yesterdayFull.jobs === 2 && W0.yesterdayFull.min.hosted === 50, [W0.yesterday, W0.yesterdayFull]);
  check('windows: 7 d and the 7 before do not overlap; 30 d holds both and the older one', W0.d7.jobs === 5 && W0.p7.jobs === 1 && W0.p7.min.hosted === 1 && W0.d30.jobs === 7 && W0.d30.min[SH] === 47, [W0.d7.jobs, W0.p7.jobs, W0.d30]);
  check('windows: medians of the queue waits, split X3 / GitHub; none gives null', W0.today.queueMedianS.all === 20 && W0.d7.queueMedianS.all === 20 && W0.d7.queueMedianS[SH] === 10 && W0.p7.queueMedianS[SH] === null && W0.p7.queueMedianS.hosted === 40, W0.d7.queueMedianS);
  check('windows: saved = X3 minutes x $0.008, rounded to the cent', W0.today.savedUsd === 0.08 && W0.d30.savedUsd === 0.38 && W0.p7.savedUsd === 0, [W0.today.savedUsd, W0.d30.savedUsd]);
  check('windows: runs by result (an open run is not counted); the 7 days keep cancelled apart', W0.today.runs === 2 && W0.d7.runs === 5 && W0.d7.runsOk === 2 && W0.d7.runsFailed === 2 && W0.d7.runsCancelled === 1 && W0.yesterday.runs === 1, W0.d7);
  check('windows: per repo', S0.repos['r/a'].d7.jobs === 3 && S0.repos['r/b'].d7.jobs === 2 && S0.repos['r/b'].d30.jobs === 3, [S0.repos['r/a'].d7.jobs, S0.repos['r/b'].d7.jobs]);
  check('windows: daily has today last, yesterday before it', S0.daily[13].jobs === 2 && S0.daily[12].jobs === 2 && S0.daily[11].jobs === 0 && S0.daily[10].jobs === 1 && S0.daily[13].runs === 2, S0.daily.slice(-4));
  check('delta: whole percent, direction, from 0, nothing when both empty or unknown', CI.delta(150, 100).pct === 50 && CI.delta(150, 100).dir === 'up' && CI.delta(50, 100).dir === 'down' && CI.delta(5, 0).dir === 'new' && CI.delta(0, 0) === null && CI.delta(1, null) === null && CI.delta(100, 100).dir === 'flat');
  check('delta: a rate moves in percentage points; success rate counts success of success + failure', CI.deltaPP(0.9, 0.8).pct === 10 && CI.deltaPP(0.9, 0.8).dir === 'up' && CI.rate(2, 2) === 0.5 && CI.rate(0, 0) === null);
  check('delta: text carries the arrow and the label', /&#9650;50% vs the 7 days before/.test(CI.deltaText(CI.delta(150, 100), 'the 7 days before')) && /&#9660;/.test(CI.deltaText(CI.delta(50, 100))));

  // the cards and tables drawn from them
  const vv = CI.view(d, NOW + 60), ph = CI.html(vv, NOW + 60);
  check('cards: the Spend tab\'s card, subkv rows and comparisons: today, yesterday, 7 d vs 7 d, 30 d', /class="card ci"/.test(ph) && /class=subkv/.test(ph) && ['Today so far', 'Yesterday, same time', 'Yesterday, whole day', 'The 7 days before', 'Last 30 days'].every(s => ph.includes(s)) && /vs the 7 days before/.test(ph));
  check('cards: the saved estimate states the rate and that wall-clock understates', /\$0\.008 per minute/.test(ph) && /understates the billed minutes/.test(ph) && /rounds every job up to the whole minute/.test(ph));
  check('cards: the numbers on the page are the collector\'s (jobs of 7 d, X3 minutes)', ph.includes('>' + T.d7.jobs.toLocaleString('en-US') + '<') && ph.includes('>' + Math.round(T.d7.min[SH]).toLocaleString('en-US') + '<'));
  check('by repo: one row per repo and the total, each repo links to its filtered list', (ph.match(/href="#ci\/runs\/1\/closelistening-/g) || []).length >= 4 && />All</.test(ph));
  const quiet = JSON.parse(JSON.stringify(d)); delete quiet.stats;
  check('cards: without stats (an old ci.json) it says so, shows no zero', /No history yet/.test(CI.html(CI.view(quiet, NOW), NOW)));
  const busyR = d.runners.filter(x => x.busy && x.now);
  check('runners: a card each with state, the run it is on (our page), jobs and minutes in 24 h', busyR.length >= 1 && ph.includes('href="#ci/run/' + encodeURIComponent(busyR[0].repo.split('/').pop()) + '/' + busyR[0].now.runId + '"') && /Jobs, 24 h/.test(ph) && /Minutes, 24 h/.test(ph) && (ph.match(/class="card ci"><h3>closelistening|class="card ci"><h3>infra/g) || []).length === 8);
  check('runners: jobs in 24 h per runner come from the ledger', d.runners.reduce((s, x) => s + x.jobs24, 0) === Object.values(run1.state.ledger).filter(l => l[0] >= NOW - D && d.runners.some(x => x.repo === l[3] && x.name === l[7])).length);
  check('runners: the note that runners are per repo; the queue says how many are idle elsewhere', /personal account/.test(ph) && (!d.queued.length || /idle in repos with nothing queued/.test(ph) === (vv.idleOther > 0)));
  check('queue: each queued job links to our run page', d.queued.every(j => j.runId) && ph.includes('href="#ci/run/'));

  // routes and paging
  const R = CI.parseRoute;
  check('route: #ci, #ci/runs/2/repo/failure and #ci/run/repo/id parse; anything else is the list; other tabs are not ours', R('#ci').kind === 'list' && R('#ci').page === 1 && R('#ci/runs/3/closelistening-player/failure').repo === 'closelistening-player' && R('#ci/runs/3/closelistening-player/failure').concl === 'failure'
    && R('#ci/run/closelistening-player/45901968925').kind === 'run' && R('#ci/run/closelistening-player/45901968925').id === '45901968925' && R('#ci/run/x/notanumber').kind === 'list' && R('#spend') === null);
  check('route: a hostile repo or result in the hash is dropped, a page below 1 is page 1', R('#ci/runs/0/..%2F..%2Fetc/x').repo === 'all' && R('#ci/runs/0/a/x').concl === 'all' && R('#ci/runs/0/a/x').page === 1 && R('#ci/run/..%2Fx/12') .kind === 'list' && R('#ci/runs/abc').page === 1);
  check('route: hrefs round-trip', CI.listHref({}) === '#ci' && R(CI.listHref({ page: 4, repo: 'closelistening-player', concl: 'failure' })).page === 4 && CI.runHref('chipi/closelistening-player', 7) === '#ci/run/closelistening-player/7');
  const many = Array.from({ length: 60 }, (_, i) => ({ repo: i % 3 ? 'chipi/infra' : 'chipi/closelistening-studio', id: i, status: i % 10 === 0 ? 'in_progress' : 'completed', conclusion: i % 10 === 0 ? null : i % 4 === 0 ? 'failure' : i % 7 === 0 ? 'timed_out' : i % 5 === 0 ? 'cancelled' : 'success', created: '2026-11-26T00:00:00Z' }));
  const p1 = CI.pageRuns(many, { page: 1, repo: 'all', concl: 'all' }), p3 = CI.pageRuns(many, { page: 3, repo: 'all', concl: 'all' }), p9 = CI.pageRuns(many, { page: 9, repo: 'all', concl: 'all' });
  check('paging: 25 a page, 60 runs are 3 pages, the last holds 10; a page past the end is the last', p1.rows.length === 25 && p1.pages === 3 && p1.total === 60 && p3.rows.length === 10 && p9.page === 3 && p9.rows[0].id === p3.rows[0].id && p1.rows[0].id === 0 && p1.rows[24].id === 24);
  const fi = CI.pageRuns(many, { page: 1, repo: 'infra', concl: 'failure' });
  check('paging: filters by repo and result (failure includes timed_out), pages recounted', fi.total === many.filter(r => r.repo.endsWith('/infra') && (r.conclusion === 'failure' || r.conclusion === 'timed_out')).length && fi.rows.every(r => r.repo === 'chipi/infra') && fi.pages === 1);
  check('paging: running means not finished; cancelled and success are exact', CI.pageRuns(many, { page: 1, repo: 'all', concl: 'running' }).total === 6 && CI.pageRuns(many, { page: 1, repo: 'all', concl: 'cancelled' }).rows.every(r => r.conclusion === 'cancelled') && CI.pageRuns(many, { page: 1, repo: 'all', concl: 'success' }).rows.every(r => r.conclusion === 'success'));
  const lv = CI.view(Object.assign({}, d, { runs: many.map(r => Object.assign({ workflow: 'W', branch: 'main', event: 'push', actor: 'a', attempt: 1, title: 't', durS: 5, queueS: 1, jobs: 2, selfHosted: 1, url: 'https://github.com/chipi/x/actions/runs/1' }, r)) }), NOW + 60);
  const lh = CI.html(lv, NOW + 60, { route: { kind: 'list', page: 2, repo: 'all', concl: 'all' } });
  check('paging html: rows link to our run page and to GitHub, the pager links the other pages, the filters keep their choice', (lh.match(/href="#ci\/run\//g) || []).length >= 25 && /GitHub &#8599;/.test(lh) && /page 2 of 3/.test(lh) && /href="#ci\/runs\/3\/all\/all"/.test(lh) && /href="#ci"[^>]*>&laquo; first|href="#ci" target=_self>&laquo; first/.test(lh)
    && /<option value="infra"/.test(lh) && /id=ci_f_concl/.test(lh));
  check('paging html: a filter with no match says so; a selected filter stays selected', /No run matches this filter/.test(CI.html(lv, NOW, { route: { kind: 'list', page: 1, repo: 'nope', concl: 'all' } })) && /<option value="failure" selected>/.test(CI.html(lv, NOW, { route: { kind: 'list', page: 1, repo: 'all', concl: 'failure' } })));

  // ---- the logs: trimming, ANSI, pruning
  const realLog = fs.readFileSync(path.join(FX, 'log-closelistening-common-140148519612.txt'), 'utf8');
  const tl = JOB.trimLog(realLog), tlLines = tl.split('\n'), rawLines = realLog.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '').split(/\r?\n/).filter((l, i, a) => !(i === a.length - 1 && l === ''));
  check('log (real, 1159 lines): ANSI codes are gone, the real one had some', /\x1b/.test(realLog) && !/\x1b/.test(tl) && !/\[36;1m/.test(tl));
  check('log (real): the last 600 lines are kept, in order, the first lines are not; the ##[error] line stays', tlLines.slice(-601, -1).join('\n') === rawLines.slice(-600).join('\n').replace(/^﻿/, '') && !tl.includes('Current runner version') && /##\[error\]Process completed with exit code 2\./.test(tl) && /^# ci-log: \d+ lines in the full log; kept the last 600/.test(tl), tlLines.slice(0, 2));
  const big = Array.from({ length: 2000 }, (_, i) => 'line ' + (i + 1) + (i + 1 === 10 || i + 1 === 700 || i + 1 === 1900 ? ' ##[error]boom ' + (i + 1) : ''));
  const bt = JOB.trimLog('﻿' + big.join('\r\n') + '\r\n'), bl = bt.split('\n');
  check('log: 2000 lines keep the last 600 plus the header', bl.includes('line 2000') && bl.includes('line 1401') && !bl.includes('line 1400') && bl.filter(l => /^line \d+/.test(l)).length === 600, bl.length);
  check('log: ##[error] lines from before the tail are kept, marked with their line number; the one in the tail stays in place once', bl.includes('[L10] line 10 ##[error]boom 10') && bl.includes('[L700] line 700 ##[error]boom 700') && bl.filter(l => /boom 1900/.test(l)).length === 1 && bl.indexOf('[L10] line 10 ##[error]boom 10') < bl.indexOf('line 1401'), bl.slice(0, 6));
  check('log: the header says what was cut; a leading BOM and CRLF are gone', /^# ci-log: 2000 lines in the full log; kept the last 600 and 2 ##\[error\] line\(s\) from before them$/.test(bl[0]) && bl.includes('# ... 1400 earlier lines left out ...') && !/﻿|\r/.test(bt));
  const many2 = JOB.trimLog(Array.from({ length: 900 }, (_, i) => i < 80 ? '##[error]e' + i : 'x' + i).join('\n')).split('\n');
  check('log: at most 50 early error lines are kept', many2.filter(l => /^\[L\d+\] ##\[error\]/.test(l)).length === 50);
  check('log: ANSI colour, cursor and a bare ESC are stripped; a long line is cut; a short log is kept whole', JOB.trimLog('\x1b[31;1mred\x1b[0m \x1b[2K\x1b[1Gok\x1b').includes('red ok\n') && JOB.trimLog('a'.repeat(5000)).split('\n')[1].length < 2100 && /; all kept$/.test(JOB.trimLog('a\nb\n').split('\n')[0]) && JOB.trimLog('a\nb\n').split('\n').length === 4);

  const ldir = fs.mkdtempSync(path.join(os.tmpdir(), 'hub-ci-logs-')), fetches = [];
  const want = [1, 2, 3, 4].map(i => ({ repo: i < 4 ? 'chipi/aa' : 'chipi/bb', id: 100 + i, done: NOW - i * 60 - 7200 }));
  const fl = async (repo, id) => { fetches.push(id); if (id === 102) throw new Error('HTTP 404 (gone)'); if (id === 103) throw new Error('HTTP 502'); return 'hello ' + id + '\n##[error]x\n'; };
  let lgd = {};
  let sl = await JOB.syncLogs({ fetchLog: fl, dir: ldir, want, logged: lgd, now: NOW, perRun: 40 });
  check('logs: each wanted job is fetched once; a 404 on an old job is given up on; another error is reported and retried', fetches.join() === '101,102,103,104' && sl.fetched === 2 && sl.logged[102].gone === 1 && !sl.logged[103] && sl.errors.length === 1 && /job 103: HTTP 502/.test(sl.errors[0]) && fs.existsSync(JOB.logFile(ldir, 'chipi/aa', 101)) && /##\[error\]x/.test(fs.readFileSync(JOB.logFile(ldir, 'chipi/aa', 101), 'utf8')), sl);
  fetches.length = 0; lgd = sl.logged;
  sl = await JOB.syncLogs({ fetchLog: fl, dir: ldir, want, logged: lgd, now: NOW + 300, perRun: 40 });
  check('logs: the second pass fetches only the one that failed, nothing it already has or gave up on', fetches.join() === '103', fetches);
  fetches.length = 0; fs.unlinkSync(JOB.logFile(ldir, 'chipi/aa', 101));
  sl = await JOB.syncLogs({ fetchLog: fl, dir: ldir, want, logged: sl.logged, now: NOW + 600, perRun: 40 });
  check('logs: a log file that has gone is fetched again', fetches.includes(101));
  fetches.length = 0;
  const young = [{ repo: 'chipi/aa', id: 201, done: NOW - 60 }], fy = async () => { fetches.push(1); throw new Error('HTTP 404'); };
  sl = await JOB.syncLogs({ fetchLog: fy, dir: ldir, want: young, logged: {}, now: NOW, perRun: 40 });
  check('logs: a 404 within an hour of the job ending is retried, not given up on', !sl.logged[201] && sl.errors.length === 0 && fetches.length === 1);
  fetches.length = 0;
  const wide = Array.from({ length: 10 }, (_, i) => ({ repo: 'chipi/cc', id: 300 + i, done: NOW - 9000 - i }));
  sl = await JOB.syncLogs({ fetchLog: fl, dir: ldir, want: wide, logged: {}, now: NOW, perRun: 4 });
  check('logs: at most perRun fetches in one pass (the API budget), the newest first', sl.fetched === 4 && fetches.join() === '300,301,302,303', fetches);
  // pruning: jobs that fall out of the kept set lose their file, empty repo directories go too
  sl = await JOB.syncLogs({ fetchLog: fl, dir: ldir, want: [wide[0]], logged: sl.logged, now: NOW + 900, perRun: 0 });
  const left = fs.readdirSync(path.join(ldir, 'ci-logs')).flatMap(r => fs.readdirSync(path.join(ldir, 'ci-logs', r)).map(f => r + '/' + f));
  check('logs: files of jobs no longer kept are removed (and empty directories); the kept one stays', left.join() === 'cc/300.txt' && sl.pruned >= 3 && !sl.logged[301], left);
  fs.writeFileSync(path.join(ldir, 'ci-logs', 'cc', '400.txt.tmp'), 'x');
  sl = await JOB.syncLogs({ fetchLog: fl, dir: ldir, want: [wide[0]], logged: sl.logged, now: NOW + 900, perRun: 0 });
  check('logs: a half-written .tmp is cleaned up', !fs.existsSync(path.join(ldir, 'ci-logs', 'cc', '400.txt.tmp')));
  fs.rmSync(ldir, { recursive: true, force: true });
  // the collector hands over the newest 200 finished jobs (never skipped ones), newest first
  check('logs: the collector wants the newest finished jobs, at most 200, none skipped, newest first', run1.logJobs.length === 200 && run1.logJobs.every((j, i, a) => i === 0 || a[i - 1].done >= j.done) && !run1.logJobs.some(j => { const r = Object.values(run1.state.runs).find(x => x.jobs.some(y => y.id === j.id)); return r.jobs.find(y => y.id === j.id).conclusion === 'skipped'; }), run1.logJobs.length);

  // the run page
  const detail = { repo: 'chipi/closelistening-common', id: 7, workflow: 'Tests <b>', branch: 'feat/<x>', sha: 'b35605ac12', msg: 'fix "quotes" & <script>alert(1)</script>', event: 'push', actor: 'chipi', attempt: 2, status: 'completed', conclusion: 'failure',
    created: '2026-11-26T20:00:00Z', started: '2026-11-26T20:01:00Z', url: 'https://github.com/chipi/closelistening-common/actions/runs/7',
    jobs: [{ id: 11, name: 'test <img onerror=1>', workflow: 'Tests', runner: 'x3-1', labels: ['self-hosted', 'x3'], where: 'self-hosted', status: 'completed', conclusion: 'failure', created: '2026-11-26T20:00:00Z', started: '2026-11-26T20:02:00Z', completed: '2026-11-26T20:12:00Z', url: 'https://github.com/chipi/closelistening-common/actions/runs/7/job/11',
      steps: [{ n: 1, name: 'Set up job', status: 'completed', conclusion: 'success', started: '2026-11-26T20:02:00Z', completed: '2026-11-26T20:02:05Z' }, { n: 2, name: 'make <test>', status: 'completed', conclusion: 'failure', started: '2026-11-26T20:02:05Z', completed: '2026-11-26T20:12:00Z' }, { n: 3, name: 'Post', status: 'completed', conclusion: 'skipped', started: null, completed: null }] },
    { id: 12, name: 'lint', runner: 'GitHub Actions 1', labels: ['ubuntu-latest'], where: 'hosted', status: 'completed', conclusion: 'success', created: '2026-11-26T20:00:00Z', started: '2026-11-26T20:00:30Z', completed: '2026-11-26T20:03:30Z', url: 'https://github.com/chipi/closelistening-common/actions/runs/7/job/12', steps: [] },
    { id: 13, name: 'later', runner: null, labels: [], where: 'hosted', status: 'in_progress', conclusion: null, created: '2026-11-26T20:00:00Z', started: '2026-11-26T20:05:00Z', completed: null, url: 'https://github.com/chipi/closelistening-common/actions/runs/7/job/13', steps: [] }] };
  const rv = CI.view(d, NOW + 60), rroute = { kind: 'run', repo: 'closelistening-common', id: '7' };
  const logs = { 11: { st: 'ok', text: '# ci-log: 700 lines in the full log; kept the last 600 and 1 ##[error] line(s) from before them\n[L9] 2026-11-26T20:03:00Z ##[error]early <b>boom</b>\n# ... 99 earlier lines left out ...\nplain line\n2026-11-26T20:11:59Z ##[error]Process completed with exit code 2.\n##[warning]careful\n' }, 12: { st: 'none' } };
  const rp = CI.html(rv, NOW + 60, { route: rroute, run: { st: 'ok', d: detail }, logs });
  check('run page: header has repo, workflow, branch, commit sha + message, event, actor, attempt, times, duration, queue wait, result', ['closelistening-common', 'Tests', 'feat/', '<code>b35605a</code>', 'push', 'chipi', '>2<', 'Created', 'Started', 'Finished', 'Total duration', 'Queue wait', 'failure'].every(s => rp.includes(s))
    && /Total duration<\/span><b>11 min/.test(rp) && /Queue wait<\/span><b>30 s/.test(rp) && /href="https:\/\/github\.com\/chipi\/closelistening-common\/commit\/b35605ac12"/.test(rp) && /href="https:\/\/github\.com\/chipi\/closelistening-common\/actions\/runs\/7"/.test(rp), rp.slice(0, 300));
  check('run page: the jobs table has runner, labels, X3 or GitHub, queue, duration, result', /x3 \(self-hosted\)/.test(rp) && /GitHub \(hosted\)/.test(rp) && /self-hosted, x3/.test(rp) && /<td>2 min<\/td><td>10 min<\/td>/.test(rp));
  check('run page: each job\'s steps with their own timing and result; a skipped one has no time', /Set up job/.test(rp) && /<td>5 s<\/td>/.test(rp) && /<td>10 min<\/td>/.test(rp) && /skipped/.test(rp) && />Steps</.test(rp));
  check('run page: the log shows in a scrollable pre; ##[error] lines are marked, ##[warning] too, a log not fetched yet says so, a running job says so', /<pre class=ci-log tabindex=0>/.test(rp) && (rp.match(/class="ln err"/g) || []).length === 2 && /class="ln warn"/.test(rp) && /2 ##\[error\] lines/.test(rp)
    && /The log is not fetched yet/.test(rp) && /The job has not finished/.test(rp) && /full log on GitHub/.test(rp) && /href="https:\/\/github\.com\/chipi\/closelistening-common\/actions\/runs\/7\/job\/11"/.test(rp));
  check('run page: nothing from GitHub is injected (names, branch, commit message, step names, log lines are escaped)', !/<script>|<img onerror|<b>boom|<b>"|<test>|<x>/.test(rp) && /&lt;script&gt;alert\(1\)/.test(rp) && /&lt;b&gt;boom&lt;\/b&gt;/.test(rp) && /test &lt;img onerror=1&gt;/.test(rp));
  check('run page: a log that is loading, or failed to load, says so', /loading the log/.test(CI.html(rv, NOW, { route: rroute, run: { st: 'ok', d: detail }, logs: { 11: { st: 'loading' } } })) && /could not be loaded \(HTTP 500\)/.test(CI.html(rv, NOW, { route: rroute, run: { st: 'ok', d: detail }, logs: { 11: { st: 'error', msg: 'HTTP 500' } } })));
  check('run page: loading, no detail file (with a GitHub link) and a failed load each say so', /loading the run/.test(CI.html(rv, NOW, { route: rroute })) && /No detail for run 7[^]*Open it on GitHub/.test(CI.html(rv, NOW, { route: rroute, run: { st: 'missing' } })) && /could not be loaded \(HTTP 500\)/.test(CI.html(rv, NOW, { route: rroute, run: { st: 'error', msg: 'HTTP 500' } })));
  const stRun = CI.html(CI.view(d, NOW + 3600), NOW + 3600, { route: rroute, run: { st: 'ok', d: detail }, logs });
  check('run page: stale numbers show the banner and no coloured dot', /60 minutes old/.test(stRun) && !/dot up|dot mid|dot down/.test(stRun) && /All runs/.test(stRun));
  check('run page: a back link to the list; an open run is grey, not green or red', /href="#ci" target=_self>&larr; All runs/.test(rp) && /dot stale/.test(CI.html(rv, NOW, { route: rroute, run: { st: 'ok', d: Object.assign({}, detail, { status: 'in_progress', conclusion: null }) }, logs })));
  const sm = CI.runSummary(detail);
  check('run summary: finished at the last job, duration from the run start, queue wait from the first job created to the first started', sm.finishedAt === '2026-11-26T20:12:00Z' && sm.durS === 660 && sm.queueS === 30 && sm.selfHosted === 1, sm);
  check('log lines: ##[error], ##[warning] and the collector\'s notes are told apart; no trailing blank line', CI.logLines('a\n##[error]b\n##[warning]c\n# ci-log: 5\nd\n').map(l => l.kind).join() === ',err,warn,meta,');

  // collecting more than a page of runs, and the budget for first reads
  const mkRuns = (n, off) => Array.from({ length: n }, (_, i) => ({ id: 9000000 + off + i, name: 'W', status: 'completed', conclusion: 'success', event: 'push', head_branch: 'main', head_sha: 'abcdef1', run_attempt: 1, actor: { login: 'a' }, head_commit: { message: 'm' },
    created_at: '2026-11-25T10:00:00Z', run_started_at: '2026-11-25T10:00:00Z', updated_at: '2026-11-25T10:' + String(10 + (i % 40)).padStart(2, '0') + ':00Z', html_url: 'https://github.com/chipi/big/actions/runs/' + (9000000 + off + i) }));
  let jobCalls2 = 0, pageCalls = 0;
  const bigApi = async p => {
    if (/\/runners/.test(p)) return { runners: [] };
    if (/\/jobs/.test(p)) { jobCalls2++; return { jobs: [{ id: +p.match(/runs\/(\d+)/)[1] * 10, name: 'j', labels: ['ubuntu-latest'], status: 'completed', conclusion: 'success', created_at: '2026-11-25T10:00:00Z', started_at: '2026-11-25T10:00:05Z', completed_at: '2026-11-25T10:05:00Z', html_url: 'https://github.com/chipi/big/actions/runs/1/job/1', run_id: 1, steps: [] }] }; }
    pageCalls++;
    const pg = +((p.match(/[?&]page=(\d+)/) || [])[1] || 1);
    return { workflow_runs: pg === 1 ? mkRuns(100, 0) : pg === 2 ? mkRuns(60, 100) : [] };
  };
  const b1 = await JOB.collect({ api: bigApi, now: NOW, repos: ['chipi/big'], state: JOB.emptyState() });
  check('collect: pages through the runs while a page is full; jobs of first-seen runs are read at most 100 per repo per collection', pageCalls >= 2 && Object.keys(b1.state.runs).length === 100 && jobCalls2 === 100, [pageCalls, jobCalls2, Object.keys(b1.state.runs).length]);
  jobCalls2 = 0;
  const b2 = await JOB.collect({ api: bigApi, now: NOW + 300, repos: ['chipi/big'], state: JSON.parse(JSON.stringify(b1.state)) });
  check('collect: the next collection fills the rest and re-reads none it has', Object.keys(b2.state.runs).length === 160 && jobCalls2 === 60, [jobCalls2, Object.keys(b2.state.runs).length]);
  jobCalls2 = 0;
  const b3 = await JOB.collect({ api: bigApi, now: NOW + 600, repos: ['chipi/big'], state: JSON.parse(JSON.stringify(b2.state)), hasDetail: () => false });
  check('collect: a run whose detail file is missing is read again (self-healing), nothing else is', jobCalls2 === 100 && Object.keys(b3.state.runs).length === 160, jobCalls2);
  check('collect: details carry steps, the commit and the actor for the run page', Object.values(run1.details).length === 250 && Object.values(run1.details).every(x => x.sha && x.actor && x.jobs.every(j => Array.isArray(j.steps))) && Object.values(run1.details).some(x => x.jobs.some(j => j.steps.length > 3)), Object.keys(run1.details).length);
  check('collect: state keeps the runs of the 30 days and drops older ones', Object.keys(run1.state.runs).length >= 245 && Object.keys(run3.state.runs).filter(id => run3.state.runs[id].status === 'completed').length === 0);

  // the process: ci-job.js over the fixtures, gauges to a fake VictoriaMetrics
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'hub-ci-test-'));
  const bodies = [];
  const srv = http.createServer((req, res) => { let b = ''; req.on('data', c => b += c); req.on('end', () => { bodies.push(b); res.end(); }); });
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const env = Object.assign({}, process.env, { HUB_CI_FIXTURES: FX, HUB_CI_NOW: String(NOW), HUB_CI_OUT: path.join(dir, 'ci.json'), HUB_VM: 'http://127.0.0.1:' + srv.address().port });
  const run = () => new Promise(r => execFile(process.execPath, [path.join(__dirname, 'ci-job.js')], { env }, (err, out, errOut) => r({ code: err ? err.code : 0, out, errOut })));
  let r = await run();
  const written = fs.existsSync(env.HUB_CI_OUT) ? JSON.parse(fs.readFileSync(env.HUB_CI_OUT, 'utf8')) : null;
  const pushed = bodies.join('');
  check('job: exits 0, writes ci.json and the state file, one line of output', r.code === 0 && written && written.runners.length === 8 && fs.existsSync(path.join(dir, 'ci-state.json')) && r.out.trim().split('\n').length === 1, r);
  check('job: pushes the gauges and the heartbeat to VictoriaMetrics', /gh_runner_up\{repo="chipi\/closelistening-player",runner="x3-closelistening-player-3",machine="x3"\} 1/.test(pushed) && /gh_ci_collector_last_success_timestamp \d+/.test(pushed) && /gh_job_queue_seconds_max\{repo=/.test(pushed), pushed.slice(0, 300));
  check('job: leaves no half-written file', fs.readdirSync(dir).every(f => !f.endsWith('.tmp')), fs.readdirSync(dir));
  const rdir = path.join(dir, 'ci-runs', 'closelistening-common'), ldir2 = path.join(dir, 'ci-logs', 'closelistening-common');
  const runFiles = fs.existsSync(rdir) ? fs.readdirSync(rdir) : [];
  const owner = runFiles.map(f => JSON.parse(fs.readFileSync(path.join(rdir, f), 'utf8'))).find(x => x.jobs.some(j => j.id === 140148519612));
  check('job: writes one detail file per run (250 over the five repos) with jobs and steps, and the log of the job the fixtures have', runFiles.length > 40 && owner && owner.jobs.find(j => j.id === 140148519612).steps.length > 5 && fs.existsSync(path.join(ldir2, '140148519612.txt'))
    && fs.readdirSync(path.join(dir, 'ci-runs')).length === 5 && written.logs.kept === 1 && written.logs.fetched === 1, [runFiles.length, written && written.logs]);
  const logTxt = fs.readFileSync(path.join(ldir2, '140148519612.txt'), 'utf8'), logM = fs.statSync(path.join(ldir2, '140148519612.txt')).mtimeMs;
  check('job: the stored log has no ANSI codes, keeps the ##[error] line and is far smaller than the 1159 lines of the original', !/\x1b/.test(logTxt) && /##\[error\]Process completed with exit code 2\./.test(logTxt) && logTxt.split('\n').length < 610, logTxt.split('\n').length);
  const pageFromFiles = CI.html(CI.view(written, NOW + 60), NOW + 60, { route: { kind: 'run', repo: 'closelistening-common', id: String(owner && owner.id) }, run: { st: 'ok', d: owner }, logs: { 140148519612: { st: 'ok', text: logTxt } } });
  check('job: a run page drawn from the files it wrote shows the steps and the highlighted error', /class="ln err"/.test(pageFromFiles) && /make type|Run /.test(pageFromFiles) && /full log on GitHub/.test(pageFromFiles));
  r = await run();
  check('job: a second run reads no log twice and writes no log again', r.code === 0 && /0 logs fetched, 1 kept/.test(r.out) && fs.statSync(path.join(ldir2, '140148519612.txt')).mtimeMs === logM, r.out);
  bodies.length = 0; env.HUB_CI_REPOS = 'chipi/nope';
  r = await run();
  check('job: a repo it cannot read exits 1 and pushes no heartbeat', r.code === 1 && /chipi\/nope: HTTP 404/.test(r.out) && !/last_success_timestamp/.test(bodies.join('')), r);
  srv.close(); fs.rmSync(dir, { recursive: true, force: true });

  console.log(failed ? 'TEST_CI FAIL (' + failed + ')' : 'TEST_CI PASS');
  process.exit(failed ? 1 : 0);
})();
