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
const check = (name, cond, got) => { if (cond) console.log('ok   ' + name); else { failed++; console.error('FAIL ' + name + (got !== undefined ? ' (got ' + JSON.stringify(got) + ')' : '')); } };

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
  check('html: runners, queue, failures, minutes, recent jobs, links to GitHub', ['Runners', 'Queue now', 'Failures, last 24 h', 'Minutes: runners vs GitHub', 'Recent jobs'].every(s => html.includes(s)) && /href="https:\/\/github\.com\/chipi\//.test(html), html.slice(0, 200));
  check('html: the offline runner is said so', /offline 0 s|offline 5 min|offline/.test(html) && /dot down/.test(html));
  const stale = CI.html(CI.view(d, NOW + 3600), NOW + 3600);
  check('html: stale numbers are grey with a notice, no green, amber or red dot', /dot stale/.test(stale) && !/dot up|dot mid|dot down/.test(stale) && /60 minutes old/.test(stale));
  check('html: a missing ci.json says so, shows nothing green', /missing or unreadable/.test(CI.html(CI.view(null, NOW), NOW)) && !/dot up/.test(CI.html(CI.view(null, NOW), NOW)));
  const evil = JSON.parse(JSON.stringify(d)); evil.recent[0].job = '<b>x</b>'; evil.recent[0].url = 'javascript:alert(1)';
  const eh = CI.html(CI.view(evil, NOW), NOW);
  check('html: names are escaped and only github.com links are made', /&lt;b&gt;x&lt;\/b&gt;/.test(eh) && !/<b>x<\/b>/.test(eh) && !/javascript:/.test(eh));
  check('html: a collector error is shown', /could not read: chipi\/closelistening-player: HTTP 403/.test(CI.html(CI.view(run4.doc, NOW), NOW)));
  check('dur: seconds, minutes, hours', CI.dur(30) === '30 s' && CI.dur(1500) === '25 min' && CI.dur(11400) === '3 h 10 min');

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
  bodies.length = 0; env.HUB_CI_REPOS = 'chipi/nope';
  r = await run();
  check('job: a repo it cannot read exits 1 and pushes no heartbeat', r.code === 1 && /chipi\/nope: HTTP 404/.test(r.out) && !/last_success_timestamp/.test(bodies.join('')), r);
  srv.close(); fs.rmSync(dir, { recursive: true, force: true });

  console.log(failed ? 'TEST_CI FAIL (' + failed + ')' : 'TEST_CI PASS');
  process.exit(failed ? 1 : 0);
})();
