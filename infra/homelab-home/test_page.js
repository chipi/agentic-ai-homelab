#!/usr/bin/env node
// Deterministic test of the home page's podcastHealth() traffic lights.
// No deps: extracts the function from gen.sh's generated HTML (or gen.sh itself),
// runs it against a stub DOM + fixture VM responses, asserts the rendered state.
// Run: node infra/homelab-home/test_page.js   (exit 0 = PASS)
'use strict';
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, 'gen.sh'), 'utf8');
const m = src.match(/async function podcastHealth\(\)\{[\s\S]*?\n\}/);
if (!m) { console.error('FAIL: podcastHealth() not found in gen.sh'); process.exit(1); }

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
  const fn = new Function('q', 'g1', 'document', 'Date',
    m[0] + '\nreturn podcastHealth();');
  return fn(q, g1, document, FrozenDate).then(() => ({ byId, chartsRow }));
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
    const fn = new Function('q', 'g1', 'document', 'Date', m[0] + '\nreturn podcastHealth;');
    const ph = fn(q, g1, document, { now: () => NOW * 1000 });
    await ph(); await ph();
    check('one selftest card after two refreshes', chartsRow.cards.length === 2, String(chartsRow.cards.length));
    check('selftest still GREEN', /GREEN/.test(byId.ph_selftest.innerHTML), byId.ph_selftest.innerHTML);
  }

  if (failures) { console.log('TEST_PAGE FAIL (' + failures + ')'); process.exit(1); }
  console.log('TEST_PAGE PASS');
})();
