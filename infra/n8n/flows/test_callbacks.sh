#!/bin/bash
# Case 3 callback test on the mini: signed calls to n8n's two webhooks, as flotilla's plumbing.call sends them.
# Writes ONE labelled test task and ONE labelled test line (each re-sent once: must not duplicate).
# Secrets go from the files on stdin into node inside the n8n container; nothing prints them.
set -u
export PATH=/usr/local/bin:$PATH
run() {  # secret file, webhook path, action, params JSON
  { tr -d '[:space:]' < "$1"; echo; } | docker exec -i -e WH="$2" -e ACTION="$3" -e PARAMS="$4" n8n node -e '
const crypto = require("crypto");
let secret = ""; process.stdin.on("data", d => secret += d).on("end", async () => {
  secret = secret.trim();
  const url = "http://127.0.0.1:5678/webhook/" + process.env.WH, action = process.env.ACTION, params = JSON.parse(process.env.PARAMS);
  const delivery = "plan-test" + Date.now().toString(16), caseId = "case-test-homelab-n8n";
  const call = async (mode, opts = {}) => {
    const body = JSON.stringify(mode === "send" ? { mode, action, case_id: caseId, plan_hash: "test", params } : { mode, action, case_id: caseId, plan_hash: "test" });
    const ts = String(opts.ts || Math.floor(Date.now() / 1000));
    const sig = "sha256=" + crypto.createHmac("sha256", opts.secret || secret).update(ts + "." + (opts.delivery || delivery) + "." + body).digest("hex");
    const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json", "x-flotilla-timestamp": ts, "x-flotilla-delivery": opts.delivery || delivery, "x-flotilla-signature": sig }, body });
    return [r.status, (await r.text()).slice(0, 220)];
  };
  const out = [];
  const t = async (name, want, p) => { const [s, b] = await p; const ok = s === want; out.push((ok ? "PASS " : "FAIL ") + name + ": " + s + " " + b); return [s, b]; };
  await t("status before send (not done)", 200, call("status"));
  await t("bad signature", 401, call("send", { secret: "0".repeat(64) }));
  await t("stale timestamp", 401, call("send", { ts: Math.floor(Date.now() / 1000) - 3600 }));
  const [, b1] = await t("send", 200, call("send"));
  const [, b2] = await t("re-send, same delivery", 200, call("send"));
  out.push((b1 === b2 ? "PASS " : "FAIL ") + "re-send answers the same ref");
  const [, b3] = await t("status after send", 200, call("status"));
  out.push((/"done":true/.test(b3) ? "PASS " : "FAIL ") + "status says done");
  console.log(out.join("\n")); console.log("delivery " + delivery);
});'
}
echo "== create_tasks"
run ~/flotilla/config/plumbing/create_tasks.secret flotilla-create-tasks plumbing.create_tasks \
  '{"items":[{"who":"operator","what":"[test] case 3 n8n callback check (homelab session), delete me","by":"2026-11-30"}]}'
echo "== post_decisions"
run ~/flotilla/config/plumbing/post_decisions.secret flotilla-post-decisions plumbing.post_decisions \
  '{"page":"decisions","text":"[test] case 3 n8n callback check by the homelab session; this line can be deleted."}'
