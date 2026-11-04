// Ask a labelled question set in one evaluation UI, in a real browser, and score each answer against the hub's
// status.json (and timeline.json) taken just before and just after the question (the files the assistant's status tool reads).
//   EVAL_USER=… EVAL_PW=… node run-evalset.mjs <librechat|openwebui> [evalsets/h4-h5.json]
// Writes results/<set>-<ui>-<UTC time>.json; prints one line per question and the score. The password comes
// from the env (see ~/assistant-ui-eval-accounts.env) and is never printed.
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const UI = process.argv[2], RESCORE = UI === "--rescore";
const SET = RESCORE ? null : JSON.parse(readFileSync(join(HERE, process.argv[3] || "evalsets/h4-h5.json"), "utf8"));
const STATUS = "https://hub.tail6d0ed4.ts.net/status.json", TIMELINE = "https://hub.tail6d0ed4.ts.net/timeline.json";
const URLS = { librechat: "https://omarchy.tail6d0ed4.ts.net:8443/", openwebui: "https://omarchy.tail6d0ed4.ts.net:8444/" };
if (!RESCORE && !URLS[UI]) { console.error("usage: node run-evalset.mjs <librechat|openwebui> [set] | --rescore <results file>"); process.exit(2); }
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---------- expected facts from a status snapshot ----------
const num = (label, value, tol) => ({ kind: "num", label, value, tol });
// `not`: phrases that contradict the fact; any of them fails it ("not green" contains "green")
const text = (label, any, not = []) => ({ kind: "text", label, any, not });
const NOT_UP = ["not green", "isn't green", "is not green", "not healthy", "unhealthy", "\"mid\"", "amber", "red", "down"];
const NONE = ["no ", "none", "not ", "all "];
const HOSTS = { mini: ["mini"], dgx: ["dgx"], x3: ["x3"], prod: ["prod"] };
// H7: an answer's clock times (ISO timestamps quoted from refs are not its own), 12-hour times as 24-hour
const hhmm = local => local.slice(-5);
const clockTimes = t => [...t.replace(/\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?(\.\d+)?Z?/g, " ")
  .matchAll(/\b([01]?\d|2[0-3]):([0-5]\d)\b(\s*[ap]\.?m\b)?/gi)]
  .map(m => { let h = +m[1]; const pm = /p/i.test(m[3] || ""), am = /a/i.test(m[3] || ""); if (pm && h < 12) h += 12; if (am && h === 12) h = 0;
              return String(h).padStart(2, "0") + ":" + m[2]; });
// precision: every time in the answer is the time of an event in evs (default: the whole timeline) or one the question names
const traceable = (s, q, evs = s.timeline.events) => { const ok = new Set([...evs.map(e => hhmm(e.local)), ...clockTimes(q)]);
  return { kind: "pred", label: "every time given is in the timeline", test: a => clockTimes(a).every(t => ok.has(t)), want: "times from timeline.json only" }; };
// completeness: each event by its local time, and alerts also by their Grafana annotation id (the ref)
const eventFacts = evs => [...new Map(evs.map(e => [hhmm(e.local) + "|" + e.what, e])).values()].flatMap(e =>
  [{ kind: "pred", label: hhmm(e.local) + " " + e.what.slice(0, 60), want: hhmm(e.local), test: a => clockTimes(a).includes(hhmm(e.local)) },
   ...(/^Grafana annotation (\d+)/.test(e.ref) ? [text("ref " + /^Grafana annotation (\d+)/.exec(e.ref)[1], [/^Grafana annotation (\d+)/.exec(e.ref)[1]])] : [])]);
const lastNight = s => { const end = new Date(Date.parse(s.timeline.to)); end.setHours(7, 0, 0, 0);
  if (end > new Date(Date.parse(s.timeline.to))) end.setDate(end.getDate() - 1);
  const start = new Date(end); start.setDate(start.getDate() - 1); start.setHours(19, 0, 0, 0); return [start.getTime(), end.getTime()]; };
const RULES = {
  sites_up_total: s => [num("sites up", s.sites.up, 0), num("sites total", s.sites.total, 0)],
  sites_down: s => s.sites.down.length ? s.sites.down.map(h => text(h, [h])) : [text("none down", NONE)],
  lowest_site: s => s.sites.lowest ? [text("lowest host", [s.sites.lowest.host]), num("its availability %", +(s.sites.lowest.avail24h * 100).toFixed(2), 0.011)] : [],
  below999_count: s => [num("sites below 99.9%", s.sites.below999.length, 0)],
  podcast_health: s => [text("state " + s.podcast.state, s.podcast.state === "up" ? ["green", "healthy", "passing", " up", "ok"] : [s.podcast.state],
                             s.podcast.state === "up" ? NOT_UP : []),
                        num("age hours", s.podcast.ageHours, 1)],
  alert_names: s => { const a = [...s.alerts.critical, ...s.alerts.warning]; return a.length ? a.map(x => text(x.name, [x.name.toLowerCase().split(/\s+/).slice(0, 2).join(" ")])) : [text("no alerts", NONE)]; },
  boxes: s => Object.entries(s.boxes).map(([b, v]) => text(`${b} ${v.state}`, HOSTS[b] || [b])),
  credit: s => [num("credit $", +s.credit.leftUsd.toFixed(2), 0.011)],
  spend_yesterday: s => [num("yesterday $", +s.spend.yesterdayUsd.toFixed(2), 0.011)],
  spend_avg7d: s => [num("7-day average $/day", +s.spend.avg7dUsd.toFixed(2), 0.011)],
  spend_month: s => [num("month $", +s.spend.monthUsd.toFixed(2), 0.011)],
  disk_free: s => ["mini", "dgx", "prod"].map(b => num(`${b} disk free %`, +s.capacity[b].diskFreePct.toFixed(1), 0.6)),
  // every new GlitchTip issue of the last 24 h (status.json's errors.new) named by its short id
  errors_new24h: s => (s.errors && s.errors.ok ? s.errors.new.map(e => text(e.id, [e.id])) : [text("errors area missing", ["\u0000"])]),
  // H7 incident timelines (timeline.json): the events asked about, all of them, and no time from elsewhere
  cloudflare_timeline: (s, q) => s.timeline ? [...eventFacts(s.timeline.events.filter(e => e.source === "alert" && /cloudflare/i.test(e.what))), traceable(s, q)] : [text("timeline missing", ["\u0000"])],
  deploys_48h: (s, q) => s.timeline ? [...eventFacts(s.timeline.events.filter(e => e.source === "ops_event" && /^deploy /.test(e.what))), traceable(s, q)] : [text("timeline missing", ["\u0000"])],
  last_night_alerts: (s, q) => { if (!s.timeline) return [text("timeline missing", ["\u0000"])]; const [a, b] = lastNight(s);
    const inWindow = s.timeline.events.filter(e => Date.parse(e.at) >= a && Date.parse(e.at) < b), evs = inWindow.filter(e => e.source === "alert");
    // any event of the night may be mentioned; an event from outside the night is a wrong answer
    return [...(evs.length ? eventFacts(evs) : [text("no alerts", NONE)]), traceable(s, q, inWindow)]; },
  max_mem: s => { const [b, v] = Object.entries(s.capacity).sort((x, y) => y[1].memUsedPct - x[1].memUsedPct)[0];
                  return [text("host " + b, HOSTS[b] || [b]), num(`${b} memory %`, +v.memUsedPct.toFixed(1), 0.6)]; },
};
// counts are often written as words ("Six websites"): read zero..twenty as numbers too
const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
               "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"];
const numbers = t => [...[...t.replace(/(\d),(\d{3})/g, "$1$2").matchAll(/-?\d+(?:\.\d+)?/g)].map(m => +m[0]),
                      ...[...t.toLowerCase().matchAll(/\b[a-z]+\b/g)].map(m => WORDS.indexOf(m[0])).filter(i => i >= 0)];
function score(answer, facts) {
  const low = answer.toLowerCase(), ns = numbers(answer);
  const res = facts.map(f => ({ ...f, ok: f.kind === "pred" ? f.test(answer) : f.kind === "num" ? ns.some(n => Math.abs(n - f.value) <= f.tol + 1e-9)
                                                          : f.any.some(w => low.includes(w.toLowerCase())) &&
                                                            !(f.not || []).some(w => low.includes(w.toLowerCase())) }));
  return { pass: res.length > 0 && res.every(r => r.ok), facts: res };
}
// one hub read failed mid-run with an HTTP/2 stream error (2026-11-03); retry a few times
const get = async url => { for (let i = 0; ; i++) { try { return await (await fetch(url)).json(); }
                                                  catch (e) { if (i >= 3) throw e; await sleep(2000); } } };
const snap = async () => Object.assign(await get(STATUS), { timeline: await get(TIMELINE).catch(() => null) });
function judge(answer, rule, before, after, q = "") {
  const sb = score(answer, RULES[rule](before, q)), sa = score(answer, RULES[rule](after, q));
  const best = sb.pass || !sa.pass ? sb : sa;
  return { pass: sb.pass || sa.pass, facts: best.facts.map(f => ({ label: f.label, want: f.kind === "num" ? f.value : f.want || f.any, ok: f.ok })) };
}

// --rescore <results file>: score saved answers again with these rules (no browser, no questions asked)
if (process.argv[2] === "--rescore") {
  const file = process.argv[3], d = JSON.parse(readFileSync(file, "utf8")), set = JSON.parse(readFileSync(join(HERE, "evalsets", d.set + ".json"), "utf8"));
  const rule = Object.fromEntries(set.questions.map(q => [q.id, q.expect])), qs = Object.fromEntries(set.questions.map(q => [q.id, q.q]));
  for (const r of d.results) {
    const j = judge(r.answer, rule[r.id], r.snapshots.before, r.snapshots.after, qs[r.id]);
    if (j.pass !== r.pass) console.log(`${r.id}: ${r.pass ? "PASS" : "FAIL"} -> ${j.pass ? "PASS" : "FAIL"} | ${j.facts.filter(f => !f.ok).map(f => f.label).join("; ")}`);
    Object.assign(r, j);
  }
  d.score = `${d.results.filter(r => r.pass).length}/${d.results.length}`; d.rescored = new Date().toISOString();
  writeFileSync(file, JSON.stringify(d, null, 1));
  console.log(`RESCORED ${d.ui} ${d.set}: ${d.score} -> ${file}`);
  process.exit(0);
}

// ---------- the browser ----------
const port = 9333 + Math.floor(Math.random() * 500), PROFILE = `/tmp/claude-1000/evalset-${UI}-${Date.now()}`;
// the browser and its profile go away however the run ends (a crashed run left 10 processes and ~900 files)
const cleanup = () => { try { ch.kill(); } catch {} try { rmSync(PROFILE, { recursive: true, force: true }); } catch {} };
process.on("exit", cleanup); process.on("SIGINT", () => process.exit(130)); process.on("SIGTERM", () => process.exit(143));
const ch = spawn("chromium", ["--headless=new", "--disable-gpu", "--no-sandbox", `--remote-debugging-port=${port}`,
  "--window-size=1300,900", `--user-data-dir=${PROFILE}`, "about:blank"], { stdio: "ignore" });
let ver; for (let i = 0; i < 50 && !ver; i++) { await sleep(200); try { ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); } catch {} }
const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const ws = new WebSocket(tabs.find(t => t.type === "page").webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0; const pend = {};
ws.onmessage = m => { const d = JSON.parse(m.data); if (d.id && pend[d.id]) { pend[d.id](d); delete pend[d.id]; } };
const call = (method, params = {}) => new Promise(r => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async e => (await call("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true })).result?.result?.value;
const waitFor = async (e, ms) => { for (let t = 0; t < ms; t += 500) { if (await ev(e)) return true; await sleep(500); } return false; };
const type = async (sel, t) => { await ev(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});e.focus();if('value' in e)e.value='';})()`); await call("Input.insertText", { text: t }); };
const enter = async () => { await call("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" });
                             await call("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 }); };
await call("Page.enable");

const ADAPTER = {
  librechat: {
    async login() { await call("Page.navigate", { url: URLS.librechat });
      if (!await waitFor(`!!document.querySelector('input#email')`, 30000)) throw new Error("no login form");
      await type("input#email", process.env.EVAL_USER); await type("input#password", process.env.EVAL_PW);
      await ev(`document.querySelector('button[type=submit]').click()`);
      if (!await waitFor(`!!document.querySelector('#prompt-textarea')`, 30000)) throw new Error("login failed"); },
    async ask(q) { await call("Page.navigate", { url: URLS.librechat + "c/new" });
      await waitFor(`!!document.querySelector('#prompt-textarea')`, 30000); await sleep(2500);
      await type("#prompt-textarea", q); await sleep(300); await enter();
      const LAST = `(()=>{const m=[...document.querySelectorAll('.markdown, [class*=markdown]')].map(e=>e.innerText.trim()).filter(t=>t&&t!==${JSON.stringify(q)});return m[m.length-1]||''})()`;
      // done: an answer, and the send button is back (not the stop button) for 3 s
      let stable = 0, last = "";
      for (let t = 0; t < 180000 && stable < 6; t += 500) { await sleep(500); const a = await ev(LAST);
        const busy = await ev(`!!document.querySelector('[data-testid="stop-generation-button"], button[aria-label*="Stop"]')`);
        stable = (a && a === last && !busy) ? stable + 1 : 0; last = a; }
      const tool = await ev(`[...document.querySelectorAll('*')].some(e=>e.childElementCount===0&&/Ran (getHomelabStatus|getIncidentTimeline)/.test(e.textContent||''))`);
      return { answer: last, toolCalled: tool }; },
  },
  openwebui: {
    async login() { await call("Page.navigate", { url: URLS.openwebui + "auth" });
      if (!await waitFor(`!!document.querySelector('input[type=email]')`, 30000)) throw new Error("no login form");
      await type("input[type=email]", process.env.EVAL_USER); await type("input[type=password]", process.env.EVAL_PW);
      await ev(`document.querySelector('button[type=submit]').click()`);
      if (!await waitFor(`!!document.querySelector('#chat-input')`, 30000)) throw new Error("login failed"); },
    async ask(q) { await call("Page.navigate", { url: URLS.openwebui });
      await waitFor(`!!document.querySelector('#chat-input')`, 30000); await sleep(2500);
      await type("#chat-input", q); await sleep(300); await enter();
      const LAST = `(()=>{const m=[...document.querySelectorAll('#response-content-container')].map(e=>e.innerText.trim()).filter(Boolean);return m[m.length-1]||''})()`;
      let stable = 0, last = "";
      for (let t = 0; t < 180000 && stable < 6; t += 500) { await sleep(500); const a = await ev(LAST);
        const busy = await ev(`!!document.querySelector('button[aria-label="Stop"], #stop-response-button')`);
        stable = (a && a.length > 20 && a === last && !busy) ? stable + 1 : 0; last = a; }
      const tool = /getHomelabStatus|getIncidentTimeline/.test(last);
      return { answer: last.replace(/^View Result from \S+\s*/g, "").trim(), toolCalled: tool }; },
  },
};

const A = ADAPTER[UI];
await A.login();
const results = [];
for (const item of SET.questions) {
  const before = await snap(), t0 = Date.now();
  let r;
  try { r = await A.ask(item.q); } catch (e) { r = { answer: "", toolCalled: false, error: String(e) }; }
  const after = await snap();
  const row = { id: item.id, use: item.use, q: item.q, answer: r.answer, toolCalled: r.toolCalled, seconds: +((Date.now() - t0) / 1000).toFixed(1),
                takenAt: [before.takenAt, after.takenAt], ...judge(r.answer, item.expect, before, after, item.q), snapshots: { before, after } };
  results.push(row);
  console.log(`${row.pass ? "PASS" : "FAIL"} ${item.id} ${row.seconds}s tool=${row.toolCalled ? "yes" : "NO"} | ${row.facts.filter(f => !f.ok).map(f => `missing ${f.label} (${JSON.stringify(f.want)})`).join("; ") || "all facts"} | ${r.answer.replace(/\s+/g, " ").slice(0, 140)}`);
}
// wait for Chromium to exit before deleting its profile: deleted earlier, it writes files back (4 profiles left on 2026-11-03)
ws.close(); await new Promise(r => { ch.once("exit", r); try { ch.kill(); } catch { r(); } setTimeout(r, 10000); }); cleanup();
const n = results.filter(r => r.pass).length, at = new Date().toISOString().replace(/[:.]/g, "").slice(0, 15) + "Z";
mkdirSync(join(HERE, "results"), { recursive: true });
const out = join(HERE, "results", `${SET.name}-${UI}-${at}.json`);
writeFileSync(out, JSON.stringify({ set: SET.name, ui: UI, at, model: "assistant", score: `${n}/${results.length}`, results }, null, 1));
console.log(`SCORE ${UI} ${SET.name}: ${n}/${results.length} pass, tool used ${results.filter(r => r.toolCalled).length}/${results.length} -> ${out}`);
