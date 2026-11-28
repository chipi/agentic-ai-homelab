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

  // all of chipi's repos with Actions (2026-11-27): runners only where the X3's are, a budget of job reads shared by
  // all repos, each repo public or private, the queue gauges (the long-queue alert) only for the X3's repos
  const paths = [], counted = async p => { paths.push(p); return /\/repos\/chipi\/closelistening-common$/.test(p) ? { private: false } : api(p); };
  const run6 = await JOB.collect({ api: counted, now: NOW, repos: REPOS, runnerRepos: ['chipi/closelistening-player'], jobsBudget: 30, state: JOB.emptyState() });
  check('repos: runners are read only on the runner repos', paths.filter(p => /\/actions\/runners/.test(p)).length === 1 && run6.doc.runners.every(r => r.repo === 'chipi/closelistening-player') && run6.doc.runners.length === 3, run6.doc.runners.map(r => r.name));
  check('repos: the job reads of first-seen finished runs share one budget over all repos', paths.filter(p => /\/runs\/\d+\/jobs/.test(p)).length <= 30 + REPOS.length * 10 && Object.keys(run6.details).filter(k => run6.details[k].status === 'completed').length === 30, Object.keys(run6.details).length);
  check('repos: each repo is public or private (from GitHub), and the doc says which repos have runners', run6.doc.visibility['chipi/closelistening-common'] === 'public' && run6.doc.visibility['chipi/infra'] === 'private' && run6.doc.runnerRepos.join() === 'chipi/closelistening-player');
  check('repos: the queue gauges are only for the runner repos; the 24 h gauges for all', run6.gauges.filter(g => g[0] === 'gh_jobs_queued').map(g => g[2].repo).join() === 'chipi/closelistening-player' && new Set(run6.gauges.filter(g => g[0] === 'gh_minutes_24h').map(g => g[2].repo)).size === 5);
  check('repos: a failed public/private read keeps the last answer', (await JOB.collect({ api: async p => { if (/\/repos\/chipi\/infra$/.test(p)) throw new Error('HTTP 502'); return api(p); }, now: NOW, repos: REPOS, state: Object.assign(JOB.emptyState(), { vis: { 'chipi/infra': 'public' } }) })).doc.visibility['chipi/infra'] === 'public');
  check('repos: the doc says how many runs are held and the cap of the list', run1.doc.runsHeld === run1.doc.runs.length && run1.doc.runsCap === 3000);
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
  check('html: cards, by repo, runners, queue, failures, past runs, links to GitHub', ['Runs</h3>', 'Jobs</h3>', 'Minutes on the X3', 'Minutes on GitHub', 'Success rate', 'Median queue wait', 'GitHub minutes saved', 'By repo &middot; ', 'Runners', 'Queue now', 'Failures, last 24 h', 'Past runs'].every(s => html.includes(s)) && /href="https:\/\/github\.com\/chipi\//.test(html), html.slice(0, 200));
  check('html: the Grafana runners board under Runners, and each X3 runner\'s name opens it on that runner', /Runners<\/h3><p class=sec[^>]*><a href="https:\/\/grafana\.tail6d0ed4\.ts\.net\/d\/ci-runners">Grafana dashboard<\/a>/.test(html)
    && html.includes('href="https://grafana.tail6d0ed4.ts.net/d/ci-runners?var-runner=x3-closelistening-player-3"'));
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
  const T = d.stats.total, PW = JOB.periodWindows(NOW).W;
  for (const k of ['today', '7d', '7dPrev', '30d', 'yesterday', 'month']) {
    const w = T[k], js = within(PW[k][0], PW[k][1]);
    check('stats ' + k + ': jobs and minutes split X3 / GitHub match the saved jobs', w.jobs === js.length && Math.abs(w.min[SH] - sumMin(js, SH)) < 0.2 && Math.abs(w.min.hosted - sumMin(js, 'hosted')) < 0.2
      && w.jobsBy[SH] + w.jobsBy.hosted === w.jobs, [w.jobs, js.length, w.min, sumMin(js, SH), sumMin(js, 'hosted')]);
  }
  check('stats: the fixtures hold both kinds in the last 7 days, and some earlier history', T['7d'].jobsBy[SH] > 0 && T['7d'].jobsBy.hosted > 0 && T['7dPrev'].jobs > 0 && T['30d'].jobs > T['7d'].jobs);
  check('stats: runs counted, outcomes never above runs; jobs the same', T['7d'].runs > 0 && T['7d'].runsOk + T['7d'].runsFailed + T['7d'].runsCancelled <= T['7d'].runs && T['7d'].jobsOk + T['7d'].jobsFailed + T['7d'].jobsCancelled <= T['7d'].jobs);
  check('stats: 30 days of runs are in the list, newest first, each with a result or a status', d.runs.length > 100 && d.runs.every((r, i, a) => r.status && (i === 0 || (a[i - 1].finishedAt || a[i - 1].created) >= (r.finishedAt || r.created))), d.runs.length);
  check('stats: per repo, every period, the repos add up to the total', ['7d', '30d', 'month', 'yesterday', '7dPrev'].every(k => Object.values(d.stats.repos).reduce((s, p) => s + p[k].jobs, 0) === T[k].jobs) && Object.keys(d.stats.repos).length === 5);
  check('stats: saved is the X3 minutes at the stated rate', T['30d'].savedUsd === Math.round(T['30d'].min[SH] * 0.008 * 100) / 100 && d.stats.rate === 0.008);
  check('stats: the days of each period and the oldest record held are stated', d.stats.days['7d'] === 7 && d.stats.days['30d'] === 30 && d.stats.days.yesterday === 1 && d.stats.days.month === 25 && /^2026-1[01]-\d\dT/.test(d.stats.since), [d.stats.days, d.stats.since]);
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
  check('windows: the periods are completed UTC days and leave today out; yesterday is the whole day', W0.yesterday.jobs === 2 && W0.yesterday.min[SH] === 5 && W0.yesterday.min.hosted === 50 && W0.yesterdayPrev.jobs === 0, [W0.yesterday, W0.yesterdayPrev]);
  check('windows: 7 days and the 7 before do not overlap; 30 days holds both and the 20-day-old one; the 40-day-old one is only in the 30 before', W0['7d'].jobs === 3 && W0['7dPrev'].jobs === 1 && W0['7dPrev'].min.hosted === 1 && W0['30d'].jobs === 5 && W0['30d'].min[SH] === 37 && W0['30dPrev'].jobs === 1, [W0['7d'].jobs, W0['7dPrev'].jobs, W0['30d']]);
  check('windows: this month is the 1st to yesterday (25 days); the month before is the same 25 days before the 1st', S0.days.month === 25 && W0.month.jobs === 5 && W0.monthPrev.jobs === 1 && S0.windows.month[0] === '2026-11-01T00:00:00Z' && S0.windows.month[1] === '2026-11-26T00:00:00Z' && S0.windows.monthPrev[0] === '2026-10-07T00:00:00Z', [S0.windows.month, S0.windows.monthPrev]);
  check('windows: the oldest record held is stated, so a period before it is not compared', S0.since === new Date(at(40, 12) * 1000).toISOString().replace(/\.\d+Z$/, 'Z'));
  const S1 = JOB.computeStats(led, runs0, ['r/a', 'r/b'], Date.parse('2026-12-01T10:00:00Z') / 1000);
  check('windows: on the 1st, this month has no completed day and holds nothing', S1.days.month === 0 && S1.total.month.jobs === 0 && S1.total.monthPrev.jobs === 0);
  check('windows: medians of the queue waits, split X3 / GitHub; none gives null', W0.today.queueMedianS.all === 20 && W0['7d'].queueMedianS.all === 20 && W0['7d'].queueMedianS[SH] === 10 && W0['7dPrev'].queueMedianS[SH] === null && W0['7dPrev'].queueMedianS.hosted === 40, W0['7d'].queueMedianS);
  check('windows: saved = X3 minutes x $0.008, rounded to the cent', W0.today.savedUsd === 0.08 && W0['30d'].savedUsd === 0.3 && W0['7dPrev'].savedUsd === 0, [W0.today.savedUsd, W0['30d'].savedUsd]);
  check('windows: runs by result (an open run is not counted); the 7 days keep cancelled apart', W0.today.runs === 2 && W0['7d'].runs === 3 && W0['7d'].runsOk === 1 && W0['7d'].runsFailed === 1 && W0['7d'].runsCancelled === 1 && W0.yesterday.runs === 1, W0['7d']);
  check('windows: per repo', S0.repos['r/a']['7d'].jobs === 1 && S0.repos['r/b']['7d'].jobs === 2 && S0.repos['r/b']['30d'].jobs === 3, [S0.repos['r/a']['7d'].jobs, S0.repos['r/b']['7d'].jobs]);
  check('windows: daily has today last, yesterday before it', S0.daily[13].jobs === 2 && S0.daily[12].jobs === 2 && S0.daily[11].jobs === 0 && S0.daily[10].jobs === 1 && S0.daily[13].runs === 2, S0.daily.slice(-4));
  check('delta: whole percent, direction, from 0, nothing when both empty or unknown', CI.delta(150, 100).pct === 50 && CI.delta(150, 100).dir === 'up' && CI.delta(50, 100).dir === 'down' && CI.delta(5, 0).dir === 'new' && CI.delta(0, 0) === null && CI.delta(1, null) === null && CI.delta(100, 100).dir === 'flat');
  check('delta: a rate moves in percentage points; success rate counts success of success + failure', CI.deltaPP(0.9, 0.8).pct === 10 && CI.deltaPP(0.9, 0.8).dir === 'up' && CI.rate(2, 2) === 0.5 && CI.rate(0, 0) === null);
  check('delta: text carries the arrow and the label', /&#9650;50% vs the 7 days before/.test(CI.deltaText(CI.delta(150, 100), 'the 7 days before')) && /&#9660;/.test(CI.deltaText(CI.delta(50, 100))));

  // flaky jobs and time lost, by hand: ledger rows are [done, durS, where, repo, conclusion, queueS, runId, runner, name, attempt]
  const led2 = {
    1: [at(1, 8), 120, SH, 'r/a', 'failure', 30, 201, 'x3-a-1', 'build', 1], 2: [at(1, 9), 60, SH, 'r/a', 'success', 150, 201, 'x3-a-1', 'build', 2],
    3: [at(1, 10), 60, SH, 'r/a', 'failure', 0, 202, 'x3-a-1', 'build', 1], 4: [at(1, 11), 60, SH, 'r/a', 'failure', 0, 202, 'x3-a-1', 'build', 2],
    5: [at(1, 12), 60, SH, 'r/a', 'success', 0, 203, 'x3-a-1', 'test', 1], 6: [at(1, 13), 60, SH, 'r/a', 'failure', 0, 203, 'x3-a-1', 'test', 2],
    7: [at(3, 9), 180, SH, 'r/b', 'timed_out', 0, 204, 'x3-b-1', 'build', 1], 8: [at(3, 10), 60, SH, 'r/b', 'success', 0, 204, 'x3-b-1', 'build', 2],
    9: [at(1, 14), 60, 'hosted', 'r/a', 'failure', 0, 205, null, 'build', 1], 10: [at(1, 15), 60, 'hosted', 'r/a', 'success', 0, 205, null, 'build', 2],
    11: [at(1, 16), 600, 'hosted', 'r/a', 'cancelled', 500, 206, null, 'lint', 1], 12: [at(1, 17), 60, SH, 'r/a', 'failure', 0, 207, null] };
  const S2 = JOB.computeStats(led2, {}, ['r/a', 'r/b'], N0), F = S2.total;
  check('flaky: failed on one attempt, succeeded on a later one of the same run and job: counted, in the period the success finished', F.yesterday.flaky === 2 && F['7d'].flaky === 3 && F['7dPrev'].flaky === 0 && F.today.flaky === 0, [F.yesterday.flaky, F['7d'].flaky]);
  check('flaky: a run whose retry failed too is not flaky; nor is a success followed by a failure; nor a row without name and attempt', F.yesterday.flaky === 2 && !F.yesterday.flakyTop.some(j => j.job === 'test'), F.yesterday.flakyTop);
  check('flaky: the top job names by count, then name; per repo the same', JSON.stringify(F['7d'].flakyTop) === JSON.stringify([{ repo: 'r/a', job: 'build', n: 2 }, { repo: 'r/b', job: 'build', n: 1 }])
    && S2.repos['r/a']['7d'].flaky === 2 && S2.repos['r/b']['7d'].flaky === 1 && S2.repos['r/b'].yesterday.flaky === 0 && !('fl' in F['7d']), F['7d'].flakyTop);
  check('flaky: three attempts (two failed, then success) count once', JOB.computeStats({ 1: [at(1, 8), 60, SH, 'r/a', 'failure', 0, 9, 'x3', 'j', 1], 2: [at(1, 9), 60, SH, 'r/a', 'timed_out', 0, 9, 'x3', 'j', 2], 3: [at(1, 11), 60, SH, 'r/a', 'success', 0, 9, 'x3', 'j', 3] }, {}, ['r/a'], N0).total.yesterday.flaky === 1);
  check('lost: failed and cancelled minutes split X3 / GitHub, timeouts are failures', JSON.stringify(F.yesterday.lost) === JSON.stringify({ failed: { 'self-hosted': 6, hosted: 1 }, cancelled: { 'self-hosted': 0, hosted: 10 }, queueX3: 1.5 })
    && F['7d'].lost.failed[SH] === 9 && F['7dPrev'].lost.failed[SH] === 0, F.yesterday.lost);
  check('lost: the X3 queue counts only beyond 60 s, a GitHub wait not at all; per repo and total agree', F.yesterday.lost.queueX3 === 1.5 && S2.repos['r/a'].yesterday.lost.queueX3 === 1.5 && S2.repos['r/b']['7d'].lost.failed[SH] === 3 && S2.repos['r/b'].yesterday.lost.queueX3 === 0, S2.repos['r/a'].yesterday.lost);
  check('collect: the ledger keeps each job\'s name and attempt, for the flaky count', Object.values(run1.state.ledger).every(l => l.length === 10 && typeof l[8] === 'string' && l[9] >= 1), Object.values(run1.state.ledger)[0]);

  // the cards and tables drawn from them
  const vv = CI.view(d, NOW + 60), ph = CI.html(vv, NOW + 60);
  // the period row, as on Spend: the default is the last 30 days; the cards show the chosen period only
  check('period row: the Spend tab\'s four periods, the default (last 30 days) marked, the days stated', /<nav class=subtabs id=ci_period>/.test(ph) && ['This month', 'Last 30 days', 'Last 7 days', 'Yesterday'].every(s => ph.includes('>' + s + '</a>'))
    && /href="#ci" data-p=30d target=_self class=on>/.test(ph) && /href="#ci\/7d" data-p=7d/.test(ph) && ph.includes('2026-10-27 to 2026-11-25 (UTC, 30 days)') && /only "Today so far" is live/.test(ph));
  check('cards: no fixed time rows inside a card any more (no "Yesterday, same time", no "Last 30 days" row)', !/Yesterday, same time|Yesterday, whole day|The 7 days before<|Today vs that/.test(ph));
  check('cards: the 30 days are not compared: the 30 before are not held', /no comparison: the 30 days before are not all held/.test(ph) && /The 30 days before<\/span><b>&mdash;/.test(ph));
  check('cards: the saved estimate states the rate and that wall-clock understates', /\$0\.008 a minute/.test(ph) && /rounds every job up to the whole minute/.test(ph));
  check('cards: the numbers on the page are the collector\'s for the period (jobs, X3 minutes of 30 days), and today so far is live', ph.includes('>' + T['30d'].jobs.toLocaleString('en-US') + '<') && ph.includes('>' + Math.round(T['30d'].min[SH]).toLocaleString('en-US') + '<') && /Today so far \(live\)/.test(ph));
  const p7 = CI.html(vv, NOW + 60, { route: CI.parseRoute('#ci/7d') });
  const dv = JSON.parse(JSON.stringify(d)); dv.visibility['chipi/infra'] = 'public'; dv.runsHeld = d.runs.length + 500;
  const pv = CI.html(CI.view(dv, NOW + 60), NOW + 60, { route: CI.parseRoute('#ci/7d') }), ghCard = pv.slice(pv.indexOf('>Minutes on GitHub</h3>'), pv.indexOf('>Success rate</h3>'));
  const ghPub = Math.round(d.stats.repos['chipi/infra']['7d'].min.hosted), ghAll = d.stats.total['7d'].min.hosted;
  check('repos: GitHub minutes split private (billed) and public (free), from each repo\'s visibility', ghCard.includes('Public (free)</span><b>' + ghPub.toLocaleString('en-US') + '<') && ghCard.includes('Private (billed)</span><b>' + Math.round(ghAll - d.stats.repos['chipi/infra']['7d'].min.hosted).toLocaleString('en-US') + '<'), ghCard.slice(0, 200));
  check('repos: a minutes bar shows the 4 largest repos and the rest as "other"; a public repo is tagged in the table', (ghCard.match(/&#9632;<\/span> /g) || []).length === 5 && /other \(1 repo\)/.test(ghCard) && /closelistening-[a-z]+<\/a> |infra<\/a> <span class=muted style="font-size:11px" title="public/.test(pv) && /infra<\/a> <span class=muted[^>]*>public</.test(pv));
  check('repos: without visibility known for every repo the split is left out, not guessed', !/Public \(free\)/.test(CI.html(CI.view(Object.assign({}, d, { visibility: {} }), NOW + 60), NOW + 60)));
  check('repos: the past runs say when the list is the cap', /the list holds the newest [\d,]+ of the [\d,]+ runs held, from 20/.test(pv) && !/the list holds the newest/.test(ph));
  check('repos: the title is no longer only the self-hosted runners', /<h2>CI &middot; GitHub Actions and the X3 runners<\/h2>/.test(pv));
  const cardOf = (h, t, next) => h.slice(h.indexOf('>' + t + '</h3>'), h.indexOf('>' + next + '</h3>'));
  const shares = c => (c.match(/(\d+(?:\.\d)?)% (succeeded|failed|cancelled|other)/g) || []);
  const rC = cardOf(p7, 'Runs', 'Jobs'), jC = cardOf(p7, 'Jobs', 'Minutes on the X3'), sum100 = c => Math.abs(shares(c).reduce((s, x) => s + parseFloat(x), 0) - 100) < 0.5;
  const W7 = T['7d'], pc = (v, t) => (Math.round(v / t * 1000) / 10) + '%';
  check('cards: Runs and Jobs have the same bar, by result, in percent adding to 100, counts in the tooltip', shares(rC).length >= 2 && shares(jC).length >= 2 && sum100(rC) && sum100(jC)
    && rC.includes(pc(W7.runsOk, W7.runs) + ' succeeded') && jC.includes(pc(W7.jobsOk, W7.jobs) + ' succeeded') && rC.includes('title="' + W7.runsOk.toLocaleString('en-US') + ' runs succeeded"') && !/X3 \(self-hosted\)/.test(jC), [shares(rC), shares(jC)]);
  const x3Card = p7.slice(p7.indexOf('Minutes on the X3'), p7.indexOf('Minutes on GitHub')), topRepo = Object.keys(d.stats.repos).sort((a, b) => d.stats.repos[b]['7d'].min[SH] - d.stats.repos[a]['7d'].min[SH])[0];
  check('cards: the minutes cards have a bar split per repo, largest first, the repo\'s minutes of the period', /display:flex;height:6px/.test(x3Card) && x3Card.indexOf(topRepo.split('/').pop()) > 0
    && x3Card.includes(Math.round(d.stats.repos[topRepo]['7d'].min[SH]).toLocaleString('en-US') + ' ' + topRepo.split('/').pop()) && /Minutes on GitHub[^]*closelistening-[a-z]+[^]*Success rate/.test(p7), x3Card.slice(0, 300));
  check('cards, 7 days: the 7 days\' numbers, compared with the 7 before', /href="#ci\/7d" data-p=7d target=_self class=on>/.test(p7) && p7.includes('>' + T['7d'].jobs.toLocaleString('en-US') + '<') && /vs the 7 days before/.test(p7) && p7.includes('2026-11-19 to 2026-11-25 (UTC, 7 days)') && /By repo &middot; 2026-11-19 to 2026-11-25/.test(p7));
  check('cards: Runs opens the runs of the period, Success rate its failed runs', /<a class="card ci" href="#ci\/runs\/1\/all\/all\/7d\/period"/.test(p7) && /<a class="card ci" href="#ci\/runs\/1\/all\/failure\/7d\/period"/.test(p7));
  check('by repo: one row per repo and the total, each repo links to its runs in the period', (p7.match(/href="#ci\/runs\/1\/closelistening-[a-z]+\/all\/7d\/period"/g) || []).length >= 4 && />All</.test(p7));
  const quiet = JSON.parse(JSON.stringify(d)); delete quiet.stats;
  check('cards: without stats (an old ci.json) it says so, shows no zero', /No history yet/.test(CI.html(CI.view(quiet, NOW), NOW)));
  // the four cards of 2026-11: slot pressure (VictoriaMetrics), runner use, flaky jobs, time lost
  const cardAt = (h, t) => { const i = h.indexOf('>' + t + '</h3>'); return i < 0 ? '' : h.slice(i, h.indexOf('</div></div>', h.indexOf('class=subkv', i)) + 12); };
  const slotHtml = (slots, per) => CI.html(CI.view(d, NOW + 60), NOW + 60, { route: CI.parseRoute('#ci/' + per), slots });
  const SLOTS = { '7d': { st: 'ok', cur: { share: 0.2, wait: 600, peak: 6, total: 8 }, prev: { share: 0.3, wait: 60, peak: 3, total: 8 }, today: { share: 0.05, wait: 30, peak: 2, total: 8 } } };
  const slotCard = cardAt(slotHtml(SLOTS, '7d'), 'Slot pressure (X3)');
  check('slot card: the share of the period with a job waiting, against the period before in points, the longest wait, the peak of the slots', />20%</.test(slotCard) && /&#9660;10 pp vs the 7 days before/.test(slotCard) && /Longest wait<\/span><b>10 min</.test(slotCard) && /Peak slots held<\/span><b>6 of 8</.test(slotCard)
    && />30%<\/b>/.test(slotCard) && />5%<\/b>/.test(slotCard), slotCard);
  check('slot card: it links to the runners board in Grafana', /<a class="card ci" href="https:\/\/grafana\.tail6d0ed4\.ts\.net\/d\/ci-runners"/.test(slotHtml(SLOTS, '7d')));
  const slErr = cardAt(slotHtml({ '7d': { st: 'error' } }, '7d'), 'Slot pressure (X3)'), slNone = cardAt(slotHtml(undefined, '7d'), 'Slot pressure (X3)');
  check('slot card: VictoriaMetrics not reachable shows a dash and says so; before the answer it says it is reading; no NaN', /<div class=cv>&mdash;</.test(slErr) && /VictoriaMetrics did not answer/.test(slErr) && /reading VictoriaMetrics/.test(slNone) && /<div class=cv>&mdash;</.test(slNone) && !/NaN|undefined/.test(slErr + slNone), slErr);
  check('slot card: a period VictoriaMetrics holds no series for says so', /no slot numbers in VictoriaMetrics for this period/.test(slotHtml({ '7d': { st: 'ok', cur: { share: null, wait: null, peak: null, total: null }, prev: null, today: null } }, '7d')));
  const asked = [], fakeQ = async (e, t) => { asked.push([e, t]); return /bool/.test(e) ? 0.5 : 7; };
  const sst = await CI.slotStats(fakeQ, d.stats, '7d'), w7 = d.stats.windows['7d'], to7 = Date.parse(w7[1]) / 1000;
  check('slotStats: queries the four x3 gauges over the period\'s window, ending at its end, and the same for the period before and today', sst.cur.share === 0.5 && sst.cur.peak === 7 && sst.prev && sst.today && asked.length === 12
    && asked.some(([e, t]) => e === 'avg_over_time((x3_ci_jobs_waiting_for_slot{box="x3"} > bool 0)[604800s:1m])' && t === to7) && asked.some(([e]) => e === 'max_over_time(x3_ci_slot_wait_oldest_seconds{box="x3"}[604800s])')
    && asked.some(([e]) => e === 'max_over_time(x3_ci_slots_held{box="x3"}[604800s])') && asked.some(([e]) => e === 'max_over_time(x3_ci_slots_total{box="x3"}[604800s])'), asked.slice(0, 4));
  check('slotStats: a VictoriaMetrics that does not answer rejects, so the page shows the error state', await CI.slotStats(async () => { throw new Error('down'); }, d.stats, '7d').then(() => false, () => true));
  const nov = await CI.slotStats(async () => null, d.stats, 'month'), early = JSON.parse(JSON.stringify(d.stats)); early.windows.month = [early.windows.month[1], early.windows.month[1]];
  check('slotStats: no series gives nulls; an empty window (no completed day) is not asked', nov.cur.share === null && (await CI.slotStats(async () => { throw new Error('asked'); }, { windows: { month: early.windows.month } }, 'month')).cur === null);

  const x3r = new Set(d.runners.filter(r => r.machine === 'x3').map(r => r.name)), up = new Set(d.runners.filter(r => r.machine === 'x3' && r.status === 'online').map(r => r.name));
  const top3 = Object.keys(d.stats.repos).filter(r => d.stats.repos[r]['7d'].min[SH] > 0).sort((a, b) => d.stats.repos[b]['7d'].min[SH] - d.stats.repos[a]['7d'].min[SH]).slice(0, 3);
  const ru = cardAt(p7, 'Runner use (X3)'), ruV = T['7d'].min[SH] * 60 / (x3r.size * 7 * D), ruP = T['7dPrev'].min[SH] * 60 / (x3r.size * 7 * D);
  check('runner use: X3 job seconds of the period over the X3 runners times the period\'s seconds', x3r.size === 8 && ru.includes('<div class=cv>' + (Math.round(ruV * 1000) / 10) + '%<'), [ru.slice(0, 120), ruV]);
  check('runner use: the 3 repos with most X3 minutes, and the runners online now', top3.length >= 1 && top3.length <= 3 && top3.every(r => ru.includes('<span title="X3 minutes of the period">' + r.split('/').pop() + '</span><b>' + Math.round(d.stats.repos[r]['7d'].min[SH]).toLocaleString('en-US') + ' min<')) && ru.includes('Runners online now</span><b>' + up.size + ' of ' + x3r.size + '<'), ru.slice(0, 500));
  check('runner use: compared with the period before in points, and the day so far is the live row', (T['7dPrev'].jobs ? new RegExp('(&#9650;|&#9660;)\\d+ pp vs the 7 days before|no change vs the 7 days before').test(ru) : true) && /Today so far \(live\)/.test(ru), [ru.slice(0, 300), ruP]);
  const noRun = JSON.parse(JSON.stringify(d)); noRun.runners = [];
  check('runner use: with no X3 runner registered it shows a dash, not a division by zero', /<div class=cv>&mdash;</.test(cardAt(CI.html(CI.view(noRun, NOW + 60), NOW + 60, { route: CI.parseRoute('#ci/7d') }), 'Runner use (X3)')));

  const dd = JSON.parse(JSON.stringify(d)); dd.stats.total['7d'] = S2.total['7d']; dd.stats.total['7dPrev'] = S2.total['7dPrev']; dd.stats.total.today = S2.total.today;
  dd.stats.total['7d'].flakyTop = [{ repo: 'chipi/r-a', job: '<b>build</b>', n: 2 }, { repo: 'chipi/r-b', job: 'test', n: 1 }];
  const p7d = CI.html(CI.view(dd, NOW + 60), NOW + 60, { route: CI.parseRoute('#ci/7d') }), fk = cardAt(p7d, 'Flaky jobs'), tlost = cardAt(p7d, 'Time lost');
  check('flaky card: the count, the top job names (repo, job, count) escaped, against the period before', />3<\/div>/.test(fk) && /<span[^>]*>r-a &middot; &lt;b&gt;build&lt;\/b&gt;<\/span><b>2</.test(fk) && /<span[^>]*>r-b &middot; test<\/span><b>1</.test(fk) && !/<b>build<\/b>/.test(fk) && /from 0 vs the 7 days before/.test(fk), fk);
  check('time lost card: failed, cancelled and X3 queue beyond a minute, split X3 / GitHub, the sum is the big number', />22</.test(tlost) && /Failed \(min\)<\/span><b>9 X3 &middot; 1 GitHub</.test(tlost) && /Cancelled \(min\)<\/span><b>0 X3 &middot; 10 GitHub</.test(tlost) && /Queue beyond 1 min \(X3\)<\/span><b>2</.test(tlost), tlost);
  const oldDoc = JSON.parse(JSON.stringify(d));
  for (const t of Object.values(oldDoc.stats.total)) { delete t.flaky; delete t.flakyTop; delete t.lost; }
  for (const r of Object.values(oldDoc.stats.repos)) for (const t of Object.values(r)) { delete t.flaky; delete t.flakyTop; delete t.lost; }
  const po = CI.html(CI.view(oldDoc, NOW + 60), NOW + 60, { route: CI.parseRoute('#ci/7d') });
  check('old ci.json: without the new fields all four cards still draw; flaky and time lost show a dash, never NaN, undefined or a zero', ['Slot pressure (X3)', 'Runner use (X3)', 'Flaky jobs', 'Time lost'].every(t => cardAt(po, t))
    && /<div class=cv>&mdash;</.test(cardAt(po, 'Flaky jobs')) && /<div class=cv>&mdash;</.test(cardAt(po, 'Time lost')) && /not counted in this ci.json yet/.test(po) && !/NaN|undefined/.test(po) && /Runner use \(X3\)/.test(po), cardAt(po, 'Flaky jobs'));
  check('cards: the four new cards come after the old seven, so the others keep their place', p7.indexOf('GitHub minutes saved') < p7.indexOf('Slot pressure (X3)') && p7.indexOf('Slot pressure (X3)') < p7.indexOf('Runner use (X3)') && p7.indexOf('Runner use (X3)') < p7.indexOf('>Flaky jobs<') && p7.indexOf('>Flaky jobs<') < p7.indexOf('>Time lost<'));
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
  check('route: the period is in the hash (#ci/7d; a filtered list carries it), an unknown one is the default', R('#ci/7d').period === '7d' && R('#ci').period === '30d' && R('#ci/bogus').period === '30d' && CI.listHref({ period: '30d' }) === '#ci' && CI.listHref({ period: 'month' }) === '#ci/month'
    && R(CI.listHref({ page: 2, repo: 'infra', concl: 'all', period: 'yesterday', when: 'period' })).period === 'yesterday' && R(CI.listHref({ page: 2, repo: 'infra', period: 'yesterday', when: 'period' })).when === 'period' && R('#ci/runs/2/infra/all').when === 'any' && R('#ci/runs/2/infra/all/7d/bogus').when === 'any');
  const fw = Date.parse('2026-11-19T00:00:00Z'), tw = Date.parse('2026-11-26T00:00:00Z'), inP = d.runs.filter(r => r.finishedAt && Date.parse(r.finishedAt) >= fw && Date.parse(r.finishedAt) < tw).length;
  check('route: "when: period" lists only the runs that finished in the period', CI.pageRuns(d.runs, { page: 1, repo: 'all', concl: 'all', win: [fw, tw] }).total === inP && inP > 0 && inP < d.runs.length
    && /finished in the period/.test(CI.html(vv, NOW + 60, { route: R('#ci/runs/1/all/all/7d/period') })) && /<option value="period" selected>last 7 days \(2026-11-19 to 2026-11-25\)/.test(CI.html(vv, NOW + 60, { route: R('#ci/runs/1/all/all/7d/period') })), inP);
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

  // slowest steps, X3 against GitHub: synthetic runs (the step names are made up); days are UTC days back from 2026-11-26
  const MID = Math.floor(NOW / D) * D, dayAt = day => new Date((MID - day * D + 3600) * 1000).toISOString().replace(/\.\d+Z$/, 'Z');
  const sruns = {}, sdet = {};
  let sid = 0;
  // job: [name, runner, where, conclusion, daysBack, [[step, secs, conclusion]...]]
  const addRun = (repo, [name, runner, where, conclusion, back, steps]) => {
    const id = ++sid, jobs = [{ id, workflow: 'CI', name, runner, where, conclusion, completed: dayAt(back), steps: steps.map(([n, s, c], i) => ({ n: i + 1, name: n, status: 'completed', conclusion: c || 'success', started: dayAt(back), completed: new Date(Date.parse(dayAt(back)) + s * 1000).toISOString().replace(/\.\d+Z$/, 'Z') })) }];
    sruns[id] = { repo, status: 'completed', jobs: jobs.map(j => ({ name: j.name, runner: j.runner, where: j.where, conclusion: j.conclusion, completed: j.completed })) };
    sdet[repo + '|' + id] = { jobs };
  };
  const X3 = 'x3-a-1', HOSTED = 'GitHub Actions 7';
  const job = (runner, back, steps, concl) => ['test', runner, runner === X3 ? 'self-hosted' : 'hosted', concl || 'success', back, steps];
  for (const s of [10, 20, 60]) addRun('chipi/r1', job(X3, 2, [['Build', s], ['Cache', 100], ['Flaky', 500, 'failure']]));
  for (const s of [5, 7]) addRun('chipi/r1', job(HOSTED, 3, [['Build', s], ['Cache', 100], ['GhOnly', 900]]));
  for (const s of [30, 30]) addRun('chipi/r1', job(X3, 4, [['NoGH', s]]));
  addRun('chipi/r1', job(X3, 2, [['Failed job step', 999]], 'failure'));
  addRun('chipi/r1', ['test', 'mac-1', 'self-hosted', 'success', 2, [['Other self-hosted', 999]]]);
  addRun('chipi/r2', job(X3, 1, [['Yesterday only', 40]]));
  for (const s of [40, 80]) addRun('chipi/r1', job(X3, 10, [['Build', s]]));
  for (const s of [8, 12]) addRun('chipi/r1', job(HOSTED, 9, [['Build', s]]));
  const SINCE = Date.parse('2026-10-01T00:00:00Z') / 1000;
  const detailOf = (repo, id) => sdet[repo + '|' + id] || null;
  const stp = JOB.computeSteps({ runs: sruns, detailOf, repos: ['chipi/r1', 'chipi/r2'], now: NOW, since: SINCE });
  const row = (p, step) => stp[p].find(r => r.step === step);
  check('steps: X3 and GitHub medians and counts per (repo, job, step); the other self-hosted runner and GitHub-less keys', JSON.stringify(row('7d', 'Build').x3) === '{"med":20,"n":3}' && JSON.stringify(row('7d', 'Build').gh) === '{"med":6,"n":2}' && row('7d', 'Build').job === 'test' && row('7d', 'Build').repo === 'chipi/r1', row('7d', 'Build'));
  check('steps: lost is (X3 median - GitHub median) x X3 runs; with no GitHub sample, the whole X3 time and gh null', row('7d', 'Build').lost === 42 && row('7d', 'NoGH').gh === null && row('7d', 'NoGH').lost === 60 && row('7d', 'Cache').lost === 0, stp['7d']);
  check('steps: ranked by time lost', stp['7d'].map(r => r.step).join() === 'NoGH,Build,Yesterday only,Cache' && stp['7d'].every((r, i, a) => !i || a[i - 1].lost >= r.lost), stp['7d'].map(r => r.step));
  check('steps: failed steps, steps of failed jobs, other runners and GitHub-only steps are left out', !['Flaky', 'Failed job step', 'Other self-hosted', 'GhOnly'].some(n => stp['30d'].some(r => r.step === n)), stp['30d'].map(r => r.step));
  check('steps: each period has its own window (yesterday: the one job of that day; today and older ones not)', stp.yesterday.length === 1 && stp.yesterday[0].step === 'Yesterday only' && stp.yesterday[0].repo === 'chipi/r2' && row('30d', 'Build').x3.n === 5, stp.yesterday);
  check('steps: the X3 median of the window before, with its count; null when it had none', JSON.stringify(row('7d', 'Build').x3Prev) === '{"med":60,"n":2}' && row('7d', 'NoGH').x3Prev === null, row('7d', 'Build'));
  const shortSince = JOB.computeSteps({ runs: sruns, detailOf, repos: ['chipi/r1', 'chipi/r2'], now: NOW, since: Date.parse('2026-11-14T00:00:00Z') / 1000 });
  check('steps: a previous window the collector does not hold whole is not compared', shortSince['7d'].every(r => r.x3Prev === null) && JOB.computeSteps({ runs: sruns, detailOf, repos: ['chipi/r1'], now: NOW, since: null })['7d'].every(r => r.x3Prev === null));
  const slow = {}, slowDet = {};
  for (let i = 1; i <= 20; i++) { slow[i] = { repo: 'chipi/r1', status: 'completed', jobs: [{ name: 'j', runner: X3, where: 'self-hosted', conclusion: 'success', completed: dayAt(1) }] }; slowDet['chipi/r1|' + i] = { jobs: [{ name: 'j', runner: X3, where: 'self-hosted', conclusion: 'success', completed: dayAt(1), steps: [{ name: 's' + i, conclusion: 'success', started: dayAt(1), completed: new Date(Date.parse(dayAt(1)) + i * 1000).toISOString() }] }] }; }
  const top = JOB.computeSteps({ runs: slow, detailOf: (r, id) => slowDet[r + '|' + id], repos: ['chipi/r1'], now: NOW, since: SINCE })['7d'];
  check('steps: the top 15 only, the slowest first', top.length === 15 && top[0].step === 's20' && top[14].step === 's6', top.map(r => r.step));
  const ids = stp['30d'].map(r => r.id);
  check('steps: each row has a 12-hex id from repo, workflow, job and step, the same in every period and run', ids.every(i => /^[0-9a-f]{12}$/.test(i)) && new Set(ids).size === ids.length && row('7d', 'Build').id === row('30d', 'Build').id && row('7d', 'Build').workflow === 'CI'
    && row('7d', 'Build').id === JOB.computeSteps({ runs: sruns, detailOf, repos: ['chipi/r1'], now: NOW + 3600, since: SINCE })['7d'].find(r => r.step === 'Build').id, ids);
  const wf2 = JSON.parse(JSON.stringify(sdet)), wfr = Object.keys(wf2).find(k => wf2[k].jobs[0].steps.some(s => s.name === 'NoGH'));
  wf2[wfr].jobs[0].workflow = 'Other';
  check('steps: the same job and step name in another workflow is another row', JOB.computeSteps({ runs: sruns, detailOf: (r, id) => wf2[r + '|' + id], repos: ['chipi/r1'], now: NOW, since: SINCE })['7d'].filter(r => r.step === 'NoGH').length === 2);
  check('steps: windows per period, [from, to) and the one before, and whether that one is held', JSON.stringify(stp.windows['7d']) === JSON.stringify({ from: '2026-11-19T00:00:00Z', to: '2026-11-26T00:00:00Z', prevFrom: '2026-11-12T00:00:00Z', prevTo: '2026-11-19T00:00:00Z', prevHeld: true })
    && shortSince.windows['7d'].prevHeld === false && Object.keys(stp.windows).join() === 'month,30d,7d,yesterday', stp.windows);
  let opened = 0;
  JOB.computeSteps({ runs: Object.assign({ x: { repo: 'chipi/r1', status: 'completed', jobs: [{ name: 'j', runner: X3, where: 'self-hosted', conclusion: 'failure', completed: dayAt(1) }] }, y: { repo: 'chipi/r1', status: 'completed', jobs: [{ name: 'j', runner: X3, where: 'self-hosted', conclusion: 'success', completed: dayAt(100) }] } }, slow), detailOf: (r, id) => { opened++; return slowDet[r + '|' + id]; }, repos: ['chipi/r1'], now: NOW, since: SINCE });
  check('steps: a run with no successful job in the windows is not opened', opened === 20, opened);
  check('collect: ci.json carries steps for every period, at most 15 each, the collector\'s own X3 runners only', ['month', '30d', '7d', 'yesterday'].every(p => Array.isArray(d.steps[p]) && d.steps[p].length <= 15)
    && d.steps['30d'].length > 0 && d.steps['30d'].every(r => r.x3.n >= 1 && r.x3.med >= 0 && (r.gh === null || r.gh.n >= 1) && r.lost >= 0), d.steps['30d'].slice(0, 2));

  // the table on the CI tab
  const sdoc = Object.assign({}, JSON.parse(JSON.stringify(d)), { steps: {
    '7d': [{ repo: 'chipi/r1', job: '<i>job</i>', step: '"><b>step</b>', x3: { med: 120, n: 9 }, gh: { med: 30, n: 4 }, lost: 810, x3Prev: { med: 100, n: 5 } },
      { repo: 'chipi/r2', job: 'build', step: 'Only here', x3: { med: 45, n: 2 }, gh: null, lost: 90, x3Prev: null },
      { repo: 'chipi/r1', job: 'build', step: 'Faster', x3: { med: 10, n: 3 }, gh: { med: 40, n: 3 }, lost: 0, x3Prev: { med: 20, n: 3 } }],
    '30d': [{ repo: 'chipi/r1', job: 'only30', step: 'in 30 days', x3: { med: 5, n: 1 }, gh: null, lost: 5, x3Prev: null }], yesterday: [], month: [] } });
  const sv = CI.view(sdoc, NOW + 60), s7 = CI.html(sv, NOW + 60, { route: CI.parseRoute('#ci/7d') }), s30 = CI.html(sv, NOW + 60), sy = CI.html(sv, NOW + 60, { route: CI.parseRoute('#ci/yesterday') });
  const tbl = s7.slice(s7.indexOf('Slowest steps on the X3 vs GitHub'), s7.indexOf('Runners</h3>'));
  check('steps html: a table under the repo table, following the period', s7.indexOf('By repo') < s7.indexOf('Slowest steps on the X3 vs GitHub') && s7.indexOf('Slowest steps on the X3 vs GitHub') < s7.indexOf('Runners</h3>') && /Only here/.test(tbl) && !/in 30 days/.test(tbl)
    && /in 30 days/.test(s30) && !/Only here/.test(s30) && /No successful step ran on the X3 in this period/.test(sy), tbl.slice(0, 200));
  check('steps html: GitHub and X3 medians with counts, the difference signed, a dash where there is no GitHub run', /2 min <span class=muted>\(9\)<\/span><\/td><td>30 s <span class=muted>\(4\)<\/span><\/td><td>\+2 min<\/td>/.test(tbl) && /<td>45 s <span class=muted>\(2\)<\/span><\/td><td>&mdash;<\/td><td>&mdash;<\/td><td>&mdash;<\/td>/.test(tbl) && /&minus;30 s/.test(tbl), tbl);
  check('steps html: the X3 before, with the change up or down; a dash when there is none', /2 min <span class=muted>\(5\)<\/span> <span class=u>&#9650;20%<\/span>/.test(tbl) && /20 s <span class=muted>\(3\)<\/span> <span class=u>&#9660;50%<\/span>/.test(tbl), tbl);
  check('steps html: names are escaped; a row links to the repo\'s runs of the period', /&lt;i&gt;job&lt;\/i&gt;/.test(tbl) && /&quot;&gt;&lt;b&gt;step&lt;\/b&gt;/.test(tbl) && !/<i>job|<b>step/.test(tbl)
    && tbl.includes('href="#ci/runs/1/r1/all/7d/period"') && tbl.includes('href="#ci/runs/1/r2/all/7d/period"') && s30.includes('href="#ci/runs/1/r1/all/30d/period"'),tbl.slice(0, 300));
  const noSteps = JSON.parse(JSON.stringify(d)); delete noSteps.steps;
  check('steps html: an old ci.json without steps draws no table', !/Slowest steps/.test(CI.html(CI.view(noSteps, NOW), NOW)));

  // the process: ci-job.js over the fixtures, gauges to a fake VictoriaMetrics
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'hub-ci-test-'));
  const bodies = [];
  const srv = http.createServer((req, res) => { let b = ''; req.on('data', c => b += c); req.on('end', () => { bodies.push(b); res.end(); }); });
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const env = Object.assign({}, process.env, { HUB_CI_FIXTURES: FX, HUB_CI_NOW: String(NOW), HUB_CI_OUT: path.join(dir, 'ci.json'), HUB_CI_REPOS: 'chipi/closelistening-studio,chipi/closelistening-common,chipi/closelistening-player,chipi/closelistening-integration,chipi/infra', HUB_CI_JOBS_BUDGET: '1000', HUB_VM: 'http://127.0.0.1:' + srv.address().port });
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
