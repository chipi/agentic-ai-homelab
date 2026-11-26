#!/usr/bin/env node
// The CI runners' view for the hub (RFC-0011, phase A): reads, only reading, the self-hosted runners and the
// recent workflow jobs of the repos that use them, and writes www/ci.json (served at /ci.json, drawn by the
// CI tab through hub-ci.js) and the gh_* gauges (Grafana alerts). Run every 5 minutes by launchd
// (com.homelab.hub-ci); one run, then exit.
//
// Token: the assistant's read-only GitHub token, read from HUB_CI_TOKEN_FILE (default ~/assistant-github-readonly.env,
// variable GITHUB_TOKEN, hub-sources.js FILES.github); never logged. Repos: HUB_CI_REPOS (comma list). Output: HUB_CI_OUT (default www/ci.json);
// the state file ci-state.json sits next to it. HUB_CI_FIXTURES=<dir> reads saved API answers (fixtures-ci/)
// instead of GitHub, with HUB_CI_NOW (unix s) as the clock. VictoriaMetrics: HUB_VM (hub-sources.js).
//
// API use is small: jobs of a finished run are fetched once (kept in the state file while the run is in the
// 24 h window); a run that is queued or running is read again every time.
'use strict';
const fs = require('fs');
const path = require('path');
const S = require('./hub-sources.js');

const E = process.env;
const REPOS = (E.HUB_CI_REPOS || 'chipi/closelistening-studio,chipi/closelistening-common,chipi/closelistening-player,chipi/closelistening-integration,chipi/infra').split(',').map(s => s.trim()).filter(Boolean);
const TOKEN_FILE = E.HUB_CI_TOKEN_FILE || S.FILES.github;
const OUT = E.HUB_CI_OUT || path.join(__dirname, 'www/ci.json');
const STATE = path.join(path.dirname(OUT), 'ci-state.json');
const DAY = 86400, RECENT = 50, KEEP_DAYS = 30;
const CONCLUSIONS = ['success', 'failure', 'cancelled', 'timed_out'];
const GENERIC = ['self-hosted', 'linux', 'x64'];

const ts = iso => iso ? Date.parse(iso) / 1000 : null;
const iso = s => new Date(s * 1000).toISOString().replace(/\.\d+Z$/, 'Z');
const lower = a => (a || []).map(x => String(typeof x === 'string' ? x : x.name).toLowerCase());
const machineOf = labels => lower(labels).find(l => !GENERIC.includes(l)) || 'unknown';

// api(path) -> parsed JSON; now: unix seconds; state: what the last run left (see emptyState)
const emptyState = () => ({ runs: {}, ledger: {}, offline: {} });

async function collect({ api, now, repos, state }) {
  const errors = [], runners = [], queued = [], recent = [];
  const st = { runs: {}, ledger: Object.assign({}, state.ledger), offline: {} };

  await Promise.all(repos.map(async repo => {
    try {
      const [rn, rs] = await Promise.all([api('/repos/' + repo + '/actions/runners?per_page=100'), api('/repos/' + repo + '/actions/runs?per_page=50')]);
      for (const r of rn.runners || []) {
        const key = repo + '|' + r.name, up = r.status === 'online';
        if (!up) st.offline[key] = (state.offline || {})[key] != null ? state.offline[key] : now;
        runners.push({ repo, name: r.name, status: r.status, busy: !!r.busy, labels: (r.labels || []).map(l => l.name), machine: machineOf(r.labels),
          offlineSince: up ? null : st.offline[key] });
      }
      const wanted = (rs.workflow_runs || []).filter(run => run.status !== 'completed' || ts(run.updated_at) >= now - DAY);
      for (const run of wanted) {
        const cached = state.runs[run.id];
        let jobs;
        if (run.status === 'completed' && cached && cached.u === run.updated_at) jobs = cached.jobs;
        else {
          const j = await api('/repos/' + repo + '/actions/runs/' + run.id + '/jobs?per_page=100');
          jobs = (j.jobs || []).map(x => ({ id: x.id, workflow: x.workflow_name || run.name, name: x.name, runner: x.runner_name || null, status: x.status, conclusion: x.conclusion,
            created: x.created_at, started: x.started_at, completed: x.completed_at, url: x.html_url, where: lower(x.labels).includes('self-hosted') ? 'self-hosted' : 'hosted' }));
        }
        st.runs[run.id] = { u: run.updated_at, jobs };
        for (const j of jobs) {
          if (j.status === 'queued') { queued.push({ repo, workflow: j.workflow, name: j.name, url: j.url, createdAt: j.created }); continue; }
          if (j.status !== 'completed' || j.conclusion === 'skipped' || !j.started || !j.completed) continue;
          const done = ts(j.completed), durS = Math.max(0, done - ts(j.started));
          st.ledger[j.id] = [done, durS, j.where, repo, j.conclusion];
          if (done >= now - DAY) recent.push({ repo, workflow: j.workflow, job: j.name, runner: j.runner, where: j.where, conclusion: j.conclusion,
            queueS: Math.max(0, ts(j.started) - ts(j.created)), durS, url: j.url, completedAt: j.completed });
        }
      }
    } catch (e) { errors.push(repo + ': ' + (e && e.message || e)); }
  }));

  // a repo that failed to read keeps its ledger entries; the others are pruned past the 30 days
  for (const [id, l] of Object.entries(st.ledger)) if (l[0] < now - KEEP_DAYS * DAY) delete st.ledger[id];
  recent.sort((a, b) => b.completedAt < a.completedAt ? -1 : 1);
  runners.sort((a, b) => a.repo + a.name < b.repo + b.name ? -1 : 1);

  const failures = {}, finished24 = {}, minutes = { '24h': { 'self-hosted': 0, hosted: 0 }, '30d': { 'self-hosted': 0, hosted: 0 } };
  const perRepo24 = {}, mins24 = {};
  for (const r of repos) { failures[r] = { failed: 0, finished: 0 }; perRepo24[r] = {}; mins24[r] = { 'self-hosted': 0, hosted: 0 }; }
  let oldest = null;
  for (const [done, durS, where, repo, conclusion] of Object.values(st.ledger)) {
    minutes['30d'][where] += durS / 60;
    oldest = oldest == null || done < oldest ? done : oldest;
    if (done < now - DAY || !failures[repo]) continue;
    minutes['24h'][where] += durS / 60; mins24[repo][where] += durS / 60;
    failures[repo].finished++;
    if (conclusion === 'failure' || conclusion === 'timed_out') failures[repo].failed++;
    perRepo24[repo][conclusion] = (perRepo24[repo][conclusion] || 0) + 1;
  }
  for (const w of ['24h', '30d']) for (const k of Object.keys(minutes[w])) minutes[w][k] = Math.round(minutes[w][k] * 10) / 10;
  minutes.since30d = oldest == null ? null : iso(oldest);

  for (const r of repos) if (errors.some(e => e.startsWith(r + ':'))) delete failures[r];
  const doc = { takenAt: iso(now), repos, runners, queued, recent: recent.slice(0, RECENT), failures, minutes, errors };
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
  return { doc, gauges, state: st, errors };
}

// saved API answers (fixtures-ci/): runners-<name>.json, runs-<name>.json, jobs-<name>-<run id>.json
function fixtureApi(dir) {
  return async p => {
    const m = p.match(/^\/repos\/[^/]+\/([^/]+)\/actions\/(runners|runs)(?:\/(\d+)\/jobs)?/);
    if (!m) throw new Error('fixture: no route for ' + p);
    const f = path.join(dir, m[3] ? 'jobs-' + m[1] + '-' + m[3] + '.json' : m[2] + '-' + m[1] + '.json');
    if (!fs.existsSync(f)) { if (m[3]) return { jobs: [] }; throw new Error('HTTP 404 (' + path.basename(f) + ')'); }
    return JSON.parse(fs.readFileSync(f, 'utf8'));
  };
}

function githubApi(token) {
  return p => S.getJson('https://api.github.com' + p, { headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'homelab-hub' } });
}

async function main() {
  let api, now = Math.floor(Date.now() / 1000);
  if (E.HUB_CI_FIXTURES) { api = fixtureApi(E.HUB_CI_FIXTURES); if (E.HUB_CI_NOW) now = +E.HUB_CI_NOW; }
  else {
    const tok = S.secret(TOKEN_FILE, 'GITHUB_TOKEN');
    if (!tok) { console.error('ci-job: no GITHUB_TOKEN in ' + TOKEN_FILE); process.exit(2); }
    api = githubApi(tok);
  }
  let prev = emptyState();
  try { prev = Object.assign(prev, JSON.parse(fs.readFileSync(STATE, 'utf8'))); } catch (e) { /* first run */ }
  const r = await collect({ api, now, repos: REPOS, state: prev });
  S.writeAtomic(OUT, JSON.stringify(r.doc, null, 1));
  S.writeAtomic(STATE, JSON.stringify(r.state));
  let pushed = 'pushed ' + r.gauges.length + ' gauges';
  try {
    await S.pushGauges(r.gauges);
    // the heartbeat the gh-ci-collector-stale alert reads: only when every repo was read, so a revoked token
    // or a missing permission goes stale instead of looking healthy
    if (!r.errors.length) await S.pushGauge('gh_ci_collector_last_success_timestamp', now);
  } catch (e) { pushed = 'push failed: ' + e.message; r.errors.push('metrics: ' + e.message); }
  console.log(r.doc.takenAt + ' wrote ' + OUT + ': ' + r.doc.runners.length + ' runners, ' + r.doc.queued.length + ' queued, ' + r.doc.recent.length + ' recent jobs; ' + pushed
    + (r.errors.length ? '; errors: ' + r.errors.join('; ') : ''));
  process.exit(r.errors.length ? 1 : 0);
}

if (require.main === module) main().catch(e => { console.error('ci-job failed: ' + (e && e.message || e)); process.exit(2); });
module.exports = { collect, fixtureApi, machineOf, emptyState };
