#!/usr/bin/env node
// Deterministic test of the home page's podcastHealth() traffic lights.
// No deps: extracts the function from gen.sh's generated HTML (or gen.sh itself),
// runs it against a stub DOM + fixture VM responses, asserts the rendered state.
// Run: node infra/homelab-home/test_page.js   (exit 0 = PASS)
'use strict';
const fs = require('fs');
const path = require('path');
const HubStatus = require('./hub-status.js'); // the page's status semantics (gen.sh inlines the same file)
const HubSlo = require('./hub-slo.js');       // the service levels the page draws (gen.sh inlines it too)

const src = fs.readFileSync(path.join(__dirname, 'gen.sh'), 'utf8');
const m = src.match(/async function podcastHealth\(\)\{[\s\S]*?\n\}/);
if (!m) { console.error('FAIL: podcastHealth() not found in gen.sh'); process.exit(1); }
const mSloFetch = src.match(/async function sloLevels\(\)\{[\s\S]*?\n\}/), mSloPaint = src.match(/function sloPaint\(\)\{[\s\S]*?\n\}/);
if (!mSloFetch || !mSloPaint) { console.error('FAIL: sloLevels() / sloPaint() not found in gen.sh'); process.exit(1); }

// --- minimal DOM stub -------------------------------------------------------
function makeDom() {
  const byId = {};
  const mkEl = (tag) => {
    const el = {
      tag, className: '', href: '', textContent: '', _html: '', h3: null,
      get innerHTML() { return this._html; },
      set innerHTML(v) {
        this._html = v;
        const idm = v.match(/id="([^"]+)"/);         // grow() injects <div id="...">
        if (idm) { const d = mkEl('div'); d.id = idm[1]; byId[idm[1]] = d; }
        if (/<h3>/.test(v)) this.h3 = mkEl('h3');
      },
      querySelector(sel) { return sel === 'h3' ? this.h3 : null; },
      closest() { return this._card || this; },
    };
    return el;
  };
  const chartsRow = {
    cards: [],
    insertBefore(a, before) {
      const i = this.cards.indexOf(before);
      this.cards.splice(i < 0 ? this.cards.length : i, 0, a);
    },
  };
  for (const id of ['ph_agg', 'ph_overall', 'ph_gateway', 'ph_o11y_logs', 'ph_o11y_metrics',
    'ph_o11y_traces', 'ph_o11y_glitchtip', 'ph_age']) {
    byId[id] = mkEl('div'); byId[id].id = id; byId[id]._html = '…';
  }
  const ageCard = mkEl('a'); ageCard.className = 'card';
  byId['ph_age']._card = ageCard;                     // ph_age.closest('a.card')
  chartsRow.cards.push(ageCard);
  const document = {
    getElementById: (id) => byId[id] || null,
    querySelector: (sel) => (sel === '#podcast_prod .charts' ? chartsRow : null),
    createElement: (tag) => mkEl(tag),
  };
  return { byId, chartsRow, document };
}

// --- fixture plumbing -------------------------------------------------------
const NOW = 1788047143; // frozen "now" (s); fixtures are offsets from it
const vec = (name, extraLabels, value, tsOffsetH = 0) =>
  ({ metric: Object.assign({ __name__: name }, extraLabels),
     value: [NOW, String(value)], _tsOffsetH: tsOffsetH });

function runScenario(fixtures) {
  const { byId, chartsRow, document } = makeDom();
  const q = async (query) => {
    for (const [needle, result] of fixtures) if (query.includes(needle)) return result;
    return [];
  };
  const g1 = async (mq) => { const r = await q(mq); return r.length ? r[0].value : null; };
  const FrozenDate = { now: () => NOW * 1000 };
  const fn = new Function('q', 'g1', 'document', 'Date', 'HubStatus', 'HS',
    m[0] + '\nreturn podcastHealth();');
  return fn(q, g1, document, FrozenDate, HubStatus, { q, now: NOW, alerts: async () => [] }).then(() => ({ byId, chartsRow }));
}

const CHECKS = ['gateway', 'o11y_logs', 'o11y_metrics', 'o11y_traces', 'o11y_glitchtip', 'selftest'];
const checksResult = (vals) => CHECKS.map((c, i) =>
  ({ metric: { __name__: 'prod_ops_health_check', app: 'podcast', check: c }, value: [NOW, String(vals[i])] }));
const tsResult = (ageSec) =>
  [{ metric: { __name__: 'prod_ops_health_last_run_timestamp', app: 'podcast' }, value: [NOW, String(NOW - ageSec)] }];
const aggResult = (v) =>
  [{ metric: { __name__: 'prod_ops_health_aggregate', app: 'podcast' }, value: [NOW, String(v)] }];

let failures = 0;
const check = (name, cond, detail) => {
  if (cond) console.log('  ok  ' + name);
  else { failures++; console.log('  FAIL ' + name + (detail ? ' — ' + detail : '')); }
};

(async () => {
  // 1. all green, fresh run 46 min ago (mirrors the real 2026-08-29 VM state,
  //    incl. the 6th check "selftest" the static HTML has no card for)
  {
    console.log('scenario: all green, 46m old, 6th check present');
    const { byId, chartsRow } = await runScenario([
      ['prod_ops_health_last_run_timestamp', tsResult(46 * 60)],
      ['prod_ops_health_aggregate', aggResult(1)],
      ['prod_ops_health_check', checksResult([1, 1, 1, 1, 1, 1])],
    ]);
    check('aggregate dot green', byId.ph_agg.className === 'dot up', byId.ph_agg.className);
    check('overall GREEN', /dot up/.test(byId.ph_overall.innerHTML) && /GREEN/.test(byId.ph_overall.innerHTML), byId.ph_overall.innerHTML);
    for (const c of CHECKS.slice(0, 5))
      check(c + ' GREEN', /GREEN/.test(byId['ph_' + c].innerHTML), byId['ph_' + c].innerHTML);
    check('unknown check grows a card', !!byId.ph_selftest && /GREEN/.test(byId.ph_selftest.innerHTML), String(byId.ph_selftest && byId.ph_selftest.innerHTML));
    check('grown card sits before Last check', chartsRow.cards.length === 2 && chartsRow.cards[1].className === 'card' && chartsRow.cards[0].h3 && chartsRow.cards[0].h3.textContent === 'selftest', JSON.stringify(chartsRow.cards.map(c => c.h3 && c.h3.textContent)));
    check('age <1h (floor, not round)', /&lt;1h ago/.test(byId.ph_age.innerHTML), byId.ph_age.innerHTML);
    check('no STALE note when fresh', !/STALE/.test(byId.ph_age.innerHTML), byId.ph_age.innerHTML);
  }
  // 2. one degraded check → ORANGE, aggregate 0.5 → ORANGE
  {
    console.log('scenario: degraded (0.5) → ORANGE');
    const { byId } = await runScenario([
      ['prod_ops_health_last_run_timestamp', tsResult(3600)],
      ['prod_ops_health_aggregate', aggResult(0.5)],
      ['prod_ops_health_check', checksResult([1, 0.5, 1, 1, 1, 1])],
    ]);
    check('aggregate dot mid', byId.ph_agg.className === 'dot mid', byId.ph_agg.className);
    check('o11y_logs ORANGE', /dot mid/.test(byId.ph_o11y_logs.innerHTML) && /ORANGE/.test(byId.ph_o11y_logs.innerHTML), byId.ph_o11y_logs.innerHTML);
    check('gateway stays GREEN', /GREEN/.test(byId.ph_gateway.innerHTML), byId.ph_gateway.innerHTML);
  }
  // 3. hard failure → RED
  {
    console.log('scenario: failed (0) → RED');
    const { byId } = await runScenario([
      ['prod_ops_health_last_run_timestamp', tsResult(3600)],
      ['prod_ops_health_aggregate', aggResult(0)],
      ['prod_ops_health_check', checksResult([0, 1, 1, 1, 1, 1])],
    ]);
    check('aggregate dot red', byId.ph_agg.className === 'dot down', byId.ph_agg.className);
    check('gateway RED', /RED/.test(byId.ph_gateway.innerHTML), byId.ph_gateway.innerHTML);
  }
  // 4. staleness overrides green: last run 27h ago, values all 1
  {
    console.log('scenario: 27h old → STALE overrides green');
    const { byId } = await runScenario([
      ['prod_ops_health_last_run_timestamp', tsResult(27 * 3600)],
      ['prod_ops_health_aggregate', aggResult(1)],
      ['prod_ops_health_check', checksResult([1, 1, 1, 1, 1, 1])],
    ]);
    check('aggregate dot grey', byId.ph_agg.className === 'dot stale', byId.ph_agg.className);
    check('overall STALE not GREEN', /STALE/.test(byId.ph_overall.innerHTML) && !/GREEN/.test(byId.ph_overall.innerHTML), byId.ph_overall.innerHTML);
    check('gateway STALE', /STALE/.test(byId.ph_gateway.innerHTML), byId.ph_gateway.innerHTML);
    check('age shows 27h + STALE note', /27h ago/.test(byId.ph_age.innerHTML) && /check not running/.test(byId.ph_age.innerHTML), byId.ph_age.innerHTML);
  }
  // 5. nothing in VM (never ran, or >28h → last_over_time window empty)
  {
    console.log('scenario: no samples in 28h');
    const { byId } = await runScenario([]);
    check('aggregate dot grey', byId.ph_agg.className === 'dot stale', byId.ph_agg.className);
    check('overall grey dash', /dot stale/.test(byId.ph_overall.innerHTML) && /&mdash;/.test(byId.ph_overall.innerHTML), byId.ph_overall.innerHTML);
    for (const c of CHECKS.slice(0, 5))
      check(c + ' grey dash, not stuck ellipsis', /&mdash;/.test(byId['ph_' + c].innerHTML), byId['ph_' + c].innerHTML);
    check('age says no run in 28h', /no run in 28h/.test(byId.ph_age.innerHTML), byId.ph_age.innerHTML);
  }
  // 6. second refresh must not duplicate the grown card
  {
    console.log('scenario: refresh twice → grown card not duplicated');
    const { byId, chartsRow, document } = makeDom();
    const fixtures = [
      ['prod_ops_health_last_run_timestamp', tsResult(3600)],
      ['prod_ops_health_aggregate', aggResult(1)],
      ['prod_ops_health_check', checksResult([1, 1, 1, 1, 1, 1])],
    ];
    const q = async (query) => { for (const [n, r] of fixtures) if (query.includes(n)) return r; return []; };
    const g1 = async (mq) => { const r = await q(mq); return r.length ? r[0].value : null; };
    const fn = new Function('q', 'g1', 'document', 'Date', 'HubStatus', 'HS', m[0] + '\nreturn podcastHealth;');
    const ph = fn(q, g1, document, { now: () => NOW * 1000 }, HubStatus, { q, now: NOW, alerts: async () => [] });
    await ph(); await ph();
    check('one selftest card after two refreshes', chartsRow.cards.length === 2, String(chartsRow.cards.length));
    check('selftest still GREEN', /GREEN/.test(byId.ph_selftest.innerHTML), byId.ph_selftest.innerHTML);
  }

  // 7. Service levels: the page draws the status job's slo.json, grey when it is old, never green without numbers
  {
    console.log('scenario: service levels (Levels tab, Overview card, Projects band)');
    const row = (service, group, state, left, app) => ({ service, group, sli: 'availability', objective: 0.995, state, left, leftSeconds: left == null ? null : Math.round(left * 12096), budgetSeconds: 12096,
      ratio: { '28d': left == null ? null : 0.995 + left * 0.005, '7d': null, '1d': null }, daily: Array(28).fill(0.999), link: '#projects/' + (app || 'cl'), app: app || null });
    const rows = [row('Orrery www', 'Public sites and apps', 'meeting', 0.9, 'orrery'), row('analytics.closelistening.app', 'Telemetry intake', 'breached', -4.8, 'cl'), row('Hub status job', 'Platform', 'meeting', 1)];
    const takenAt = ago => new Date((NOW - ago) * 1000).toISOString();
    const run = async (doc, hash) => {
      const els = {};
      const document = { getElementById: id => els[id] || (els[id] = { innerHTML: '' }) };
      const fetchStub = async () => doc === null ? { ok: false, json: async () => ({}) } : doc instanceof Error ? (() => { throw doc; })() : { ok: true, json: async () => doc };
      const body = 'let SLO_DOC=null;' + mSloFetch[0] + '\n' + mSloPaint[0] + '\nreturn sloLevels();';
      await new Function('document', 'fetch', 'location', 'Date', 'HubSlo', 'HubProject', body)(document, fetchStub, { hash }, { now: () => NOW * 1000 }, HubSlo, require('./hub-project.js'));
      return els;
    };
    let e = await run({ takenAt: takenAt(60), rows }, '#overview');
    check('levels tab: breached row first in its group, groups as headings', /Telemetry intake/.test(e.slo_tab.innerHTML) && /dot down/.test(e.slo_tab.innerHTML) && /BREACHED|breached/.test(e.slo_tab.innerHTML), e.slo_tab.innerHTML.slice(0, 200));
    check('overview card: "2 of 3 meeting", red because one is breached', />2 of 3</.test(e.ov_slo.innerHTML) && /meeting/.test(e.ov_slo.innerHTML) && /color:#f85149/.test(e.ov_slo.innerHTML), e.ov_slo.innerHTML);
    check('projects band: empty off the Projects tab', e.pj_slo.innerHTML === '', e.pj_slo.innerHTML);
    e = await run({ takenAt: takenAt(60), rows }, '#projects/orrery/7d/prev/all');
    check('projects band: Orrery page shows Orrery rows only', /Orrery www/.test(e.pj_slo.innerHTML) && !/analytics\.closelistening/.test(e.pj_slo.innerHTML), e.pj_slo.innerHTML.slice(0, 200));
    e = await run({ takenAt: takenAt(60), rows }, '#projects');
    check('projects band: no app in the hash is Close Listening', /analytics\.closelistening/.test(e.pj_slo.innerHTML) && !/Orrery www/.test(e.pj_slo.innerHTML));
    e = await run({ takenAt: takenAt(20 * 60), rows }, '#overview');
    check('stale slo.json (20 min): every row grey, no green or red dot', /dot stale/.test(e.slo_tab.innerHTML) && !/dot up|dot down|dot mid/.test(e.slo_tab.innerHTML), e.slo_tab.innerHTML.slice(0, 200));
    check('stale slo.json: the card is grey, not red or green', /color:#7a7a8c/.test(e.ov_slo.innerHTML) && !/f85149/.test(e.ov_slo.innerHTML) && /old/.test(e.ov_slo.innerHTML), e.ov_slo.innerHTML);
    for (const [name, doc] of [['missing (404)', null], ['unreachable', new Error('offline')], ['not a snapshot', { rows: 'x' }]]) {
      e = await run(doc, '#overview');
      check('slo.json ' + name + ': says so, grey dash, nothing green', /missing or unreadable/.test(e.slo_tab.innerHTML) && /7a7a8c/.test(e.ov_slo.innerHTML) && !/dot up/.test(e.slo_tab.innerHTML + e.ov_slo.innerHTML), e.slo_tab.innerHTML);
    }
    // gen.sh wiring: the tab between Sites and Hosts, the card, the Projects slot, the module inlined, the refresh
    check('gen.sh: Levels tab sits between Sites and Hosts, in TABS too', /<a href="#sites"[^>]*>Sites<\/a><a href="#levels"[^>]*>Levels<\/a><a href="#hosts"/.test(src) && /TABS=\['overview','projects','sites','levels','hosts'/.test(src));
    check('gen.sh: the section, the Overview card and the Projects slot exist', /<section class=tab id=t-levels>/.test(src) && /id=slo_tab/.test(src) && /id=ov_slo/.test(src) && /id=pj_slo/.test(src));
    check('gen.sh: hub-slo.js is inlined and refreshed with the page', /cat .*\/hub-slo\.js"/.test(src) && /function refresh\(\)\{sloLevels\(\);/.test(src));
    check('gen.sh: mobile first (a row stacks by default, one line from 641 px)', /\.slo-row\{[^}]*flex-direction:column/.test(src) && /@media\(min-width:641px\)\{\s*\.slo-row\{display:grid/.test(src));
  }

  if (failures) { console.log('TEST_PAGE FAIL (' + failures + ')'); process.exit(1); }
  console.log('TEST_PAGE PASS');
})();
