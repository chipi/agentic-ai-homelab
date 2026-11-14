#!/usr/bin/env node
// Deterministic test of the home page's reminders() bar (reminders.json through HubStatus.reminders).
// No deps: extracts the function from gen.sh, runs it against a stub DOM, a fixed clock and fixture
// reminders, asserts the rendered HTML. Run: node infra/homelab-home/test_reminders_bar.js (exit 0 = PASS)
'use strict';
const fs = require('fs');
const path = require('path');
const HubStatus = require('./hub-status.js');

const src = fs.readFileSync(path.join(__dirname, 'gen.sh'), 'utf8');
const m = src.match(/\nfunction reminders\(\)\{[\s\S]*?\n\}/);
if (!m) { console.error('FAIL: reminders() not found in gen.sh'); process.exit(1); }

const el = { innerHTML: 'stale' };
const document = { getElementById: id => (id === 'remindbar' ? el : null) };
const T = Date.UTC(2026, 10, 14, 15, 30);
const DateStub = { now: () => T };
const make = list => new Function('document', 'HubStatus', 'REMINDERS', 'Date', m[0] + '\nreturn reminders;')(document, HubStatus, list, DateStub);

let failed = 0;
const check = (name, cond, got) => { if (cond) console.log('ok   ' + name); else { failed++; console.error('FAIL: ' + name + (got !== undefined ? ' (got ' + got + ')' : '')); } };

make([])();
check('no reminders: no bar', el.innerHTML === '', el.innerHTML);

make([{ text: 'far off', due: '2027-02-12', warn_days: 14 }])();
check('outside its warn_days: no bar', el.innerHTML === '', el.innerHTML);

make([{ text: 'Renew the <token>', due: '2026-11-20', warn_days: 14, link: 'https://github.com/settings' }])();
check('coming: an amber bar with the date, the days and the link',
  el.innerHTML.includes('class="abar warn"') && el.innerHTML.includes('href="https://github.com/settings"') &&
  el.innerHTML.includes('Reminder &middot; 2026-11-20') && el.innerHTML.includes('(in 6 days)'), el.innerHTML);
check('the text is escaped', el.innerHTML.includes('Renew the &lt;token&gt;') && !el.innerHTML.includes('<token>'), el.innerHTML);

make([{ text: 'one', due: '2026-11-13', warn_days: 1 }, { text: 'two', due: '2026-11-14', warn_days: 0 }, { text: 'three', due: '2026-11-15', warn_days: 1 }])();
check('overdue is red, its days counted', el.innerHTML.includes('class="abar crit"') && el.innerHTML.includes('(1 day overdue)'), el.innerHTML);
check('today and tomorrow say so', el.innerHTML.includes('(today)') && el.innerHTML.includes('(in 1 day)'), el.innerHTML);
check('the soonest first', el.innerHTML.indexOf('one') < el.innerHTML.indexOf('two') && el.innerHTML.indexOf('two') < el.innerHTML.indexOf('three'), el.innerHTML);

make([{ text: 'no date', warn_days: 1 }])();
check('a bad entry: a plumbing bar that names it', el.innerHTML.includes('class="abar plumb"') && el.innerHTML.includes('1 entry in reminders.json not understood: no date'), el.innerHTML);

make(undefined)();
check('REMINDERS missing: no bar, no crash', el.innerHTML === '', el.innerHTML);

console.log(failed ? 'TEST_REMINDERS_BAR FAIL (' + failed + ')' : 'TEST_REMINDERS_BAR PASS');
process.exit(failed ? 1 : 0);
