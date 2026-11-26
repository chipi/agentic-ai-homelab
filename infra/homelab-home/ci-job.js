#!/usr/bin/env node
// The CI view for the hub (RFC-0011, phase A and the drill-down): reads, only reading, the self-hosted runners
// and the workflow runs and jobs of the repos that use them, and writes www/ci.json (served at /ci.json, drawn
// by the CI tab through hub-ci.js), one www/ci-runs/<repo>/<run_id>.json per run (header, jobs, steps: the run
// page), one www/ci-logs/<repo>/<job_id>.txt per finished job (the trimmed log), and the gh_* gauges (Grafana
// alerts). Run every 5 minutes by launchd (com.homelab.hub-ci); one run, then exit.
//
// Token: the assistant's read-only GitHub token, read from HUB_CI_TOKEN_FILE (default ~/assistant-github-readonly.env,
// variable GITHUB_TOKEN, hub-sources.js FILES.github); never logged. Repos: HUB_CI_REPOS (comma list). Output: HUB_CI_OUT (default www/ci.json);
// the state file ci-state.json, ci-runs/ and ci-logs/ sit next to it. HUB_CI_FIXTURES=<dir> reads saved API answers
// (fixtures-ci/) instead of GitHub, with HUB_CI_NOW (unix s) as the clock. VictoriaMetrics: HUB_VM (hub-sources.js).
//
// API use is bounded: the jobs of a finished run are fetched once (kept in the state file for 30 days; at most
// JOBS_PER_REPO such runs per repo per collection, so a first run backfills the 30 days over a few collections);
// a run that is queued or running is read again every time; a job's log is fetched once, for the newest
// LOG_JOBS finished jobs, at most LOG_FETCH_PER_RUN per collection.
'use strict';
const fs = require('fs');
const path = require('path');
const https = require('https');
const S = require('./hub-sources.js');

const E = process.env;
const REPOS = (E.HUB_CI_REPOS || 'chipi/closelistening-studio,chipi/closelistening-common,chipi/closelistening-player,chipi/closelistening-integration,chipi/infra').split(',').map(s => s.trim()).filter(Boolean);
const TOKEN_FILE = E.HUB_CI_TOKEN_FILE || S.FILES.github;
const OUT = E.HUB_CI_OUT || path.join(__dirname, 'www/ci.json');
const STATE = path.join(path.dirname(OUT), 'ci-state.json');
const DAY = 86400, RECENT = 50, KEEP_DAYS = 30;
const RUNS_PAGE = 100, RUNS_PAGES = 4;       // runs read per repo: up to 400 of the newest, while they are in the 30 days
const JOBS_PER_REPO = 100;                   // runs whose jobs are read for the first time, per repo and per collection
const RUNS_IN_DOC = 1000;                    // runs listed in ci.json (the Past runs table pages over them)
const LOG_JOBS = 200, LOG_FETCH_PER_RUN = 40, LOG_TAIL = 600, LOG_MAX_ERR = 50, LINE_MAX = 2000, LOG_MAX_BYTES = 64 << 20;
const GH_RATE_USD_PER_MIN = 0.008;           // GitHub's list price for a Linux 2-core hosted runner minute
const CONCLUSIONS = ['success', 'failure', 'cancelled', 'timed_out'];
const GENERIC = ['self-hosted', 'linux', 'x64'];

const ts = iso => iso ? Date.parse(iso) / 1000 : null;
const iso = s => new Date(s * 1000).toISOString().replace(/\.\d+Z$/, 'Z');
const lower = a => (a || []).map(x => String(typeof x === 'string' ? x : x.name).toLowerCase());
const machineOf = labels => lower(labels).find(l => !GENERIC.includes(l)) || 'unknown';
const short = repo => String(repo).split('/').pop();
const round1 = x => Math.round(x * 10) / 10;
const firstLine = s => String(s || '').split('\n')[0].slice(0, 120);

// api(path) -> parsed JSON; now: unix seconds; state: what the last run left (see emptyState)
const emptyState = () => ({ runs: {}, ledger: {}, offline: {}, logged: {}, partial: {} });

// ---- the numbers of the cards -------------------------------------------------------------------------------
// ledger rows (finished jobs): [done, durS, where, repo, conclusion, queueS, runId, runner]; runs: state.runs.
const median = xs => { if (!xs.length) return null; const a = xs.slice().sort((x, y) => x - y), m = a.length >> 1; return Math.round(a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2); };
const newWindow = () => ({ runs: 0, runsOk: 0, runsFailed: 0, runsCancelled: 0, jobs: 0, jobsOk: 0, jobsFailed: 0, jobsCancelled: 0,
  jobsBy: { 'self-hosted': 0, hosted: 0 }, min: { 'self-hosted': 0, hosted: 0 }, q: { all: [], 'self-hosted': [], hosted: [] } });
function closeWindow(w) {
  const q = w.q;
  delete w.q;
  w.min = { 'self-hosted': round1(w.min['self-hosted']), hosted: round1(w.min.hosted) };
  w.queueMedianS = { all: median(q.all), 'self-hosted': median(q['self-hosted']), hosted: median(q.hosted) };
  w.savedUsd = Math.round(w.min['self-hosted'] * GH_RATE_USD_PER_MIN * 100) / 100;
  return w;
}
const FAILED = ['failure', 'timed_out'];

// When a run ended, how long it took, how long its first job waited: from its jobs, else from updated_at
function runTimes(rec) {
  const js = (rec.jobs || []).filter(j => j.started);
  const done = Math.max.apply(0, [rec.status === 'completed' ? ts(rec.u) : 0].concat((rec.jobs || []).filter(j => j.completed).map(j => ts(j.completed))));
  const start = ts(rec.started || rec.created);
  const q = js.length ? Math.max(0, Math.min.apply(0, js.map(j => ts(j.started))) - Math.min.apply(0, js.map(j => ts(j.created)))) : null;
  return { done: rec.status === 'completed' ? done : null, durS: rec.status === 'completed' && start != null ? Math.max(0, done - start) : null, queueS: q };
}

function computeStats(ledger, runs, repos, now) {
  const mid = Math.floor(now / DAY) * DAY;
  const WIN = { today: [mid, now + 1], yesterday: [mid - DAY, now - DAY + 1], yesterdayFull: [mid - DAY, mid], d7: [now - 7 * DAY, now + 1], p7: [now - 14 * DAY, now - 7 * DAY], d30: [now - 30 * DAY, now + 1] };
  const mk = () => Object.fromEntries(Object.keys(WIN).map(k => [k, newWindow()]));
  const total = mk(), per = Object.fromEntries(repos.map(r => [r, { d7: newWindow(), p7: newWindow(), d30: newWindow() }]));
  const daily = Array.from({ length: 14 }, (_, i) => ({ day: iso(mid - (13 - i) * DAY).slice(0, 10), runs: 0, jobs: 0, failed: 0, 'self-hosted': 0, hosted: 0 }));
  const dayOf = t => { if (t > now) return null; const i = 13 - Math.floor((mid + DAY - 1 - t) / DAY); return i >= 0 && i < 14 ? daily[i] : null; };
  const into = (repo, t, fn) => {
    for (const [k, [a, b]] of Object.entries(WIN)) if (t >= a && t < b) { fn(total[k]); if (per[repo] && per[repo][k]) fn(per[repo][k]); }
  };
  for (const [done, durS, where, repo, conclusion, queueS] of Object.values(ledger)) {
    if (!(repos.includes(repo))) continue;
    into(repo, done, w => {
      w.jobs++; w.jobsBy[where]++; w.min[where] += durS / 60;
      if (conclusion === 'success') w.jobsOk++; else if (FAILED.includes(conclusion)) w.jobsFailed++; else if (conclusion === 'cancelled') w.jobsCancelled++;
      if (queueS != null) { w.q.all.push(queueS); w.q[where].push(queueS); }
    });
    const d = dayOf(done); if (d) { d.jobs++; d[where] += durS / 60; }
  }
  for (const rec of Object.values(runs)) {
    if (rec.status !== 'completed' || !repos.includes(rec.repo)) continue;
    const t = runTimes(rec).done; if (!t) continue;
    into(rec.repo, t, w => { w.runs++; if (rec.conclusion === 'success') w.runsOk++; else if (FAILED.includes(rec.conclusion)) w.runsFailed++; else if (rec.conclusion === 'cancelled') w.runsCancelled++; });
    const d = dayOf(t); if (d) { d.runs++; if (FAILED.includes(rec.conclusion)) d.failed++; }
  }
  Object.values(total).forEach(closeWindow);
  Object.values(per).forEach(p => Object.values(p).forEach(closeWindow));
  daily.forEach(d => { d['self-hosted'] = round1(d['self-hosted']); d.hosted = round1(d.hosted); });
  return { rate: GH_RATE_USD_PER_MIN, windows: Object.fromEntries(Object.entries(WIN).map(([k, [a, b]]) => [k, [iso(a), iso(Math.min(b, now))]])), total, repos: per, daily };
}

// ---- the logs -----------------------------------------------------------------------------------------------
// ANSI colour and cursor codes out; the last LOG_TAIL lines kept; every ##[error] line from before them kept too,
// with its line number, so the cause is not lost in a long log. The page marks any line holding ##[error].
const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b/g;
function trimLog(text, { tail = LOG_TAIL, maxErr = LOG_MAX_ERR, lineMax = LINE_MAX } = {}) {
  const lines = String(text).replace(/^﻿/, '').replace(ANSI, '').split(/\r?\n/);
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  const total = lines.length, cut = Math.max(0, total - tail);
  const clip = l => l.length > lineMax ? l.slice(0, lineMax) + ' [line cut]' : l;
  const errs = [];
  for (let i = 0; i < cut && errs.length < maxErr; i++) if (lines[i].includes('##[error]')) errs.push('[L' + (i + 1) + '] ' + clip(lines[i]));
  const out = ['# ci-log: ' + total + ' lines in the full log' + (cut ? '; kept the last ' + tail + (errs.length ? ' and ' + errs.length + ' ##[error] line(s) from before them' : '') : '; all kept')];
  if (cut) out.push.apply(out, errs.concat(['# ... ' + cut + ' earlier lines left out ...']));
  for (let i = cut; i < total; i++) out.push(clip(lines[i]));
  return out.join('\n') + '\n';
}

const logFile = (dir, repo, id) => path.join(dir, 'ci-logs', short(repo), id + '.txt');
const runFile = (dir, repo, id) => path.join(dir, 'ci-runs', short(repo), id + '.json');

// Remove what is not kept: keep(repoShort, idString) says which files stay; empty directories go too.
function pruneTree(root, keep) {
  let n = 0;
  if (!fs.existsSync(root)) return n;
  for (const d of fs.readdirSync(root)) {
    const sub = path.join(root, d);
    if (!fs.statSync(sub).isDirectory()) continue;
    for (const f of fs.readdirSync(sub)) if (!keep(d, f.replace(/\.(json|txt)$/, '')) || /\.tmp$/.test(f)) { fs.unlinkSync(path.join(sub, f)); n++; }
    if (!fs.readdirSync(sub).length) fs.rmdirSync(sub);
  }
  return n;
}

// One log fetch per finished job, once: want = [{repo, id, done}] newest first (collect's logJobs); logged = the
// state's record of the jobs already fetched (or given up on). A 404/410 within an hour of the job ending is
// retried (the log may not be ready); later it is recorded as gone. Other errors are retried next time.
async function syncLogs({ fetchLog, dir, want, logged, now, perRun = LOG_FETCH_PER_RUN, tail = LOG_TAIL }) {
  const keep = new Set(want.map(j => short(j.repo) + '/' + j.id)), errors = [];
  const next = {};
  for (const j of want) { const l = logged[j.id]; if (l && (l.gone || fs.existsSync(logFile(dir, j.repo, j.id)))) next[j.id] = l; }
  let fetched = 0;
  for (const j of want) {
    if (next[j.id]) continue;
    if (fetched >= perRun) break;
    try {
      const text = await fetchLog(j.repo, j.id);
      S.writeAtomic(logFile(dir, j.repo, j.id), trimLog(text, { tail }));
      next[j.id] = { repo: j.repo, t: now }; fetched++;
    } catch (e) {
      const m = String(e && e.message || e);
      if (/HTTP (404|410)/.test(m) && now - j.done > 3600) next[j.id] = { repo: j.repo, gone: 1 };
      else if (!/HTTP (404|410)/.test(m)) errors.push(short(j.repo) + ' job ' + j.id + ': ' + m.slice(0, 120));
    }
  }
  const pruned = pruneTree(path.join(dir, 'ci-logs'), (r, id) => keep.has(r + '/' + id));
  return { logged: next, fetched, pruned, errors, kept: Object.values(next).filter(l => !l.gone).length };
}

// ---- the collection -------------------------------------------------------------------------------------------
const mapJob = (x, run) => ({ id: x.id, workflow: x.workflow_name || run.name, name: x.name, runner: x.runner_name || null, labels: lower(x.labels), status: x.status, conclusion: x.conclusion,
  created: x.created_at, started: x.started_at, completed: x.completed_at, url: x.html_url, where: lower(x.labels).includes('self-hosted') ? 'self-hosted' : 'hosted', attempt: x.run_attempt || run.run_attempt || 1 });
const stepsOf = x => (x.steps || []).map(s => ({ n: s.number, name: s.name, status: s.status, conclusion: s.conclusion, started: s.started_at, completed: s.completed_at }));
const runRec = (repo, run, jobs) => ({ repo, u: run.updated_at, wf: run.name, br: run.head_branch, sha: run.head_sha || null, msg: firstLine((run.head_commit || {}).message || run.display_title),
  ev: run.event, ac: (run.actor || {}).login || null, at: run.run_attempt || 1, created: run.created_at, started: run.run_started_at || run.created_at, status: run.status, conclusion: run.conclusion, url: run.html_url, jobs });

async function collect({ api, now, repos, state, hasDetail = () => true }) {
  const errors = [], runners = [], queued = [], recent = [], running = [], details = {};
  const st = { runs: {}, ledger: Object.assign({}, state.ledger), offline: {}, logged: state.logged || {}, partial: {} };
  // the 30 days of runs the last collection kept; a repo that fails to read keeps its entries as they were
  const old = {};
  for (const [id, r] of Object.entries(state.runs || {})) if (r.repo && ts(r.u) >= now - KEEP_DAYS * DAY) old[id] = r;
  Object.assign(st.runs, old);

  await Promise.all(repos.map(async repo => {
    try {
      const pageOf = n => api('/repos/' + repo + '/actions/runs?per_page=' + RUNS_PAGE + (n > 1 ? '&page=' + n : ''));
      const [rn, first] = await Promise.all([api('/repos/' + repo + '/actions/runners?per_page=100'), pageOf(1)]);
      for (const r of rn.runners || []) {
        const key = repo + '|' + r.name, up = r.status === 'online';
        if (!up) st.offline[key] = (state.offline || {})[key] != null ? state.offline[key] : now;
        runners.push({ repo, name: r.name, status: r.status, busy: !!r.busy, labels: (r.labels || []).map(l => l.name), machine: machineOf(r.labels),
          offlineSince: up ? null : st.offline[key], now: null, jobs24: 0, min24: 0 });
      }
      const known = run => { const c = old[run.id]; return run.status === 'completed' && c && c.u === run.updated_at && c.jobs && hasDetail(repo, run.id); };
      const seen = new Set(); let filled = 0, page = first;
      for (let n = 1; ; n++) {
        const list = page.workflow_runs || [];
        const wanted = list.filter(run => run.status !== 'completed' || ts(run.updated_at) >= now - KEEP_DAYS * DAY);
        for (const run of wanted) {
          seen.add(String(run.id));
          let jobs;
          if (known(run)) jobs = old[run.id].jobs;
          else if (run.status === 'completed' && filled >= JOBS_PER_REPO) { st.partial[repo] = true; if (old[run.id]) st.runs[run.id] = old[run.id]; continue; }
          else {
            if (run.status === 'completed') filled++;
            const j = await api('/repos/' + repo + '/actions/runs/' + run.id + '/jobs?per_page=100');
            jobs = (j.jobs || []).map(x => mapJob(x, run));
            const rec = runRec(repo, run, jobs);
            details[repo + '|' + run.id] = { repo, id: run.id, workflow: rec.wf, branch: rec.br, sha: rec.sha, msg: rec.msg, event: rec.ev, actor: rec.ac, attempt: rec.at, status: rec.status, conclusion: rec.conclusion,
              created: rec.created, started: rec.started, updated: rec.u, url: rec.url, takenAt: iso(now), jobs: (j.jobs || []).map((x, i) => Object.assign({}, jobs[i], { steps: stepsOf(x) })) };
          }
          st.runs[run.id] = runRec(repo, run, jobs);
          for (const j of jobs) {
            if (j.status === 'queued') { queued.push({ repo, runId: run.id, workflow: j.workflow, name: j.name, url: j.url, createdAt: j.created }); continue; }
            if (j.status === 'in_progress' && j.runner) running.push({ repo, runner: j.runner, runId: run.id, job: j.name, workflow: j.workflow, startedAt: j.started });
            if (j.status !== 'completed' || j.conclusion === 'skipped' || !j.started || !j.completed) continue;
            const done = ts(j.completed), durS = Math.max(0, done - ts(j.started)), queueS = Math.max(0, ts(j.started) - ts(j.created));
            st.ledger[j.id] = [done, durS, j.where, repo, j.conclusion, queueS, run.id, j.runner];
            if (done >= now - DAY) recent.push({ repo, runId: run.id, workflow: j.workflow, job: j.name, runner: j.runner, where: j.where, conclusion: j.conclusion, queueS, durS, url: j.url, completedAt: j.completed });
          }
        }
        // the next page only while this one was full, entirely inside the 30 days, and held a run not yet known (or the last collection left runs unread for the cap)
        if (n >= RUNS_PAGES || list.length < RUNS_PAGE || list.some(run => ts(run.updated_at) < now - KEEP_DAYS * DAY) || (list.every(known) && !(state.partial || {})[repo])) break;
        page = await pageOf(n + 1);
      }
      // a run that was open and is no longer listed has left the newest runs: drop it rather than show it open for 30 days
      for (const [id, r] of Object.entries(old)) if (r.repo === repo && r.status !== 'completed' && !seen.has(id)) delete st.runs[id];
    } catch (e) { errors.push(repo + ': ' + (e && e.message || e)); }
  }));

  // a repo that failed to read keeps its ledger entries; the others are pruned past the 30 days
  for (const [id, l] of Object.entries(st.ledger)) if (l[0] < now - KEEP_DAYS * DAY) delete st.ledger[id];
  recent.sort((a, b) => b.completedAt < a.completedAt ? -1 : 1);
  runners.sort((a, b) => a.repo + a.name < b.repo + b.name ? -1 : 1);
  const rkey = {}; runners.forEach(r => rkey[r.repo + '|' + r.name] = r);
  for (const j of running) { const r = rkey[j.repo + '|' + j.runner]; if (r) r.now = { runId: j.runId, job: j.job, workflow: j.workflow, startedAt: j.startedAt }; }

  const failures = {}, finished24 = {}, minutes = { '24h': { 'self-hosted': 0, hosted: 0 }, '30d': { 'self-hosted': 0, hosted: 0 } };
  const perRepo24 = {}, mins24 = {};
  for (const r of repos) { failures[r] = { failed: 0, finished: 0 }; perRepo24[r] = {}; mins24[r] = { 'self-hosted': 0, hosted: 0 }; }
  let oldest = null;
  for (const [done, durS, where, repo, conclusion, , , runner] of Object.values(st.ledger)) {
    minutes['30d'][where] += durS / 60;
    oldest = oldest == null || done < oldest ? done : oldest;
    if (done < now - DAY || !failures[repo]) continue;
    minutes['24h'][where] += durS / 60; mins24[repo][where] += durS / 60;
    failures[repo].finished++;
    if (conclusion === 'failure' || conclusion === 'timed_out') failures[repo].failed++;
    perRepo24[repo][conclusion] = (perRepo24[repo][conclusion] || 0) + 1;
    const rr = rkey[repo + '|' + runner]; if (rr) { rr.jobs24++; rr.min24 += durS / 60; }
  }
  runners.forEach(r => r.min24 = round1(r.min24));
  for (const w of ['24h', '30d']) for (const k of Object.keys(minutes[w])) minutes[w][k] = Math.round(minutes[w][k] * 10) / 10;
  minutes.since30d = oldest == null ? null : iso(oldest);

  const stats = computeStats(st.ledger, st.runs, repos, now);
  const runsDoc = Object.entries(st.runs).filter(([, r]) => repos.includes(r.repo)).map(([id, r]) => {
    const t = runTimes(r);
    return { repo: r.repo, id: +id, workflow: r.wf, branch: r.br, event: r.ev, actor: r.ac, attempt: r.at, title: r.msg, created: r.created, finishedAt: t.done ? iso(t.done) : null,
      status: r.status, conclusion: r.conclusion, durS: t.durS, queueS: t.queueS, jobs: r.jobs.length, selfHosted: r.jobs.filter(j => j.where === 'self-hosted').length, url: r.url };
  }).sort((a, b) => (b.finishedAt || b.created) < (a.finishedAt || a.created) ? -1 : 1).slice(0, RUNS_IN_DOC);
  const logJobs = [];
  for (const r of Object.values(st.runs)) for (const j of r.jobs) if (j.status === 'completed' && j.started && j.completed && j.conclusion !== 'skipped') logJobs.push({ repo: r.repo, id: j.id, done: ts(j.completed) });
  logJobs.sort((a, b) => b.done - a.done);

  for (const r of repos) if (errors.some(e => e.startsWith(r + ':'))) delete failures[r];
  const doc = { takenAt: iso(now), repos, runners, queued, recent: recent.slice(0, RECENT), runs: runsDoc, failures, minutes, stats, errors };
  const failedRepos = new Set(errors.map(e => e.split(':')[0]));
  const gauges = [];
  for (const r of runners) { const l = { repo: r.repo, runner: r.name, machine: r.machine }; gauges.push(['gh_runner_up', r.status === 'online' ? 1 : 0, l], ['gh_runner_busy', r.busy ? 1 : 0, l]); }
  for (const repo of repos) {
    if (failedRepos.has(repo)) continue;
    const q = queued.filter(j => j.repo === repo);
    gauges.push(['gh_jobs_queued', q.length, { repo }], ['gh_job_queue_seconds_max', q.reduce((m, j) => Math.max(m, now - ts(j.createdAt)), 0), { repo }]);
    for (const c of CONCLUSIONS) gauges.push(['gh_jobs_finished_24h', perRepo24[repo][c] || 0, { repo, conclusion: c }]);
    for (const w of ['self-hosted', 'hosted']) gauges.push(['gh_minutes_24h', Math.round(mins24[repo][w] * 10) / 10, { repo, where: w }]);
  }
  return { doc, gauges, state: st, errors, details, logJobs: logJobs.slice(0, LOG_JOBS) };
}

function fixtureApi(dir) {
  return async p => {
    const m = p.match(/^\/repos\/[^/]+\/([^/]+)\/actions\/(runners|runs)(?:\/(\d+)\/jobs)?/);
    if (!m) throw new Error('fixture: no route for ' + p);
    const f = path.join(dir, m[3] ? 'jobs-' + m[1] + '-' + m[3] + '.json' : m[2] + '-' + m[1] + '.json');
    if (!m[3] && m[2] === 'runs' && /[?&]page=([2-9])/.test(p)) return { workflow_runs: [] };
    if (!fs.existsSync(f)) { if (m[3]) return { jobs: [] }; throw new Error('HTTP 404 (' + path.basename(f) + ')'); }
    return JSON.parse(fs.readFileSync(f, 'utf8'));
  };
}
function fixtureLog(dir) {
  return async (repo, id) => {
    const f = path.join(dir, 'log-' + short(repo) + '-' + id + '.txt');
    if (!fs.existsSync(f)) throw new Error('HTTP 404 (' + path.basename(f) + ')');
    return fs.readFileSync(f, 'utf8');
  };
}

function githubApi(token) {
  return p => S.getJson('https://api.github.com' + p, { headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'homelab-hub' } });
}
// The logs endpoint answers with a redirect to a signed download URL; that URL is followed without the token.
function githubLog(token) {
  const get = (url, headers, hops) => new Promise((ok, no) => {
    const req = https.get(url, { headers }, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location && hops < 3) { res.resume(); return ok(get(res.headers.location, { 'User-Agent': 'homelab-hub' }, hops + 1)); }
      if (res.statusCode !== 200) { res.resume(); return no(new Error('HTTP ' + res.statusCode)); }
      const chunks = []; let n = 0;
      res.on('data', c => { n += c.length; if (n > LOG_MAX_BYTES) req.destroy(new Error('log over ' + (LOG_MAX_BYTES >> 20) + ' MB')); else chunks.push(c); });
      res.on('end', () => ok(Buffer.concat(chunks).toString('utf8')));
      res.on('error', no);
    });
    req.on('error', no); req.setTimeout(60000, () => req.destroy(new Error('timeout')));
  });
  return (repo, id) => get('https://api.github.com/repos/' + repo + '/actions/jobs/' + id + '/logs', { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'homelab-hub' }, 0);
}

async function main() {
  let api, fetchLog, now = Math.floor(Date.now() / 1000);
  const dir = path.dirname(OUT);
  if (E.HUB_CI_FIXTURES) { api = fixtureApi(E.HUB_CI_FIXTURES); fetchLog = fixtureLog(E.HUB_CI_FIXTURES); if (E.HUB_CI_NOW) now = +E.HUB_CI_NOW; }
  else {
    const tok = S.secret(TOKEN_FILE, 'GITHUB_TOKEN');
    if (!tok) { console.error('ci-job: no GITHUB_TOKEN in ' + TOKEN_FILE); process.exit(2); }
    api = githubApi(tok); fetchLog = githubLog(tok);
  }
  let prev = emptyState();
  try { prev = Object.assign(prev, JSON.parse(fs.readFileSync(STATE, 'utf8'))); } catch (e) { /* first run */ }
  const r = await collect({ api, now, repos: REPOS, state: prev, hasDetail: (repo, id) => fs.existsSync(runFile(dir, repo, id)) });
  for (const d of Object.values(r.details)) S.writeAtomic(runFile(dir, d.repo, d.id), JSON.stringify(d));
  const runKeep = new Set(Object.entries(r.state.runs).map(([id, x]) => short(x.repo) + '/' + id));
  const prunedRuns = pruneTree(path.join(dir, 'ci-runs'), (rp, id) => runKeep.has(rp + '/' + id));
  const lg = await syncLogs({ fetchLog, dir, want: r.logJobs, logged: r.state.logged, now });
  r.state.logged = lg.logged;
  r.doc.logs = { kept: lg.kept, fetched: lg.fetched, jobsMax: LOG_JOBS, tail: LOG_TAIL, errors: lg.errors };
  S.writeAtomic(OUT, JSON.stringify(r.doc, null, 1));
  S.writeAtomic(STATE, JSON.stringify(r.state));
  let pushed = 'pushed ' + r.gauges.length + ' gauges';
  try {
    await S.pushGauges(r.gauges);
    // the heartbeat the gh-ci-collector-stale alert reads: only when every repo was read, so a revoked token
    // or a missing permission goes stale instead of looking healthy
    if (!r.errors.length) await S.pushGauge('gh_ci_collector_last_success_timestamp', now);
  } catch (e) { pushed = 'push failed: ' + e.message; r.errors.push('metrics: ' + e.message); }
  console.log(r.doc.takenAt + ' wrote ' + OUT + ': ' + r.doc.runners.length + ' runners, ' + r.doc.queued.length + ' queued, ' + r.doc.runs.length + ' runs (' + Object.keys(r.details).length + ' read, ' + prunedRuns + ' pruned), '
    + lg.fetched + ' logs fetched, ' + lg.kept + ' kept, ' + lg.pruned + ' pruned; ' + pushed + (lg.errors.length ? '; log errors: ' + lg.errors.join('; ') : '')
    + (r.errors.length ? '; errors: ' + r.errors.join('; ') : ''));
  process.exit(r.errors.length ? 1 : 0);
}

if (require.main === module) main().catch(e => { console.error('ci-job failed: ' + (e && e.message || e)); process.exit(2); });
module.exports = { collect, fixtureApi, fixtureLog, machineOf, emptyState, computeStats, trimLog, syncLogs, pruneTree, runFile, logFile, LOG_TAIL, LOG_JOBS, GH_RATE_USD_PER_MIN };
