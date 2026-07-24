# Signal-fleet handover — for a fresh Fable 5 session (2026-07-25)

Written by the outgoing (Opus) session at the operator's request. The operator is
switching to a stronger model in a clean session. This is the honest state — what
works, what does NOT, the bar that must be hit, and the mistakes not to repeat.

---

## TL;DR

Fleet 2 ("signal-to-action" / triage fleet) reads live observability signals
(GlitchTip errors, Grafana alerts) and decides one of four dispositions:
**dismiss / cleanup / file / escalate**. The investigation loop + probe menu + gates
+ a dual-label eval are all BUILT and run end-to-end. **The blocker is quality, not
plumbing:** no configuration yet meets the operator's bar, and the last prompt change
that tries to is UNTESTED.

**The operator's hard bar (stated 2026-07-25, non-negotiable):**
- **Escalate rate ≤ 5%** (≤10% worst case). An escalate spends the operator's
  attention — the one resource the fleet exists to save. A fleet that escalates the
  majority is worthless.
- **AND false-dismiss = 0** (never silently drop a real defect).
- Both must hold at once. High autonomy AND high safety. Nobody has hit this yet.

Do NOT invent an "acceptable" escalate rate from the fixture labels (the outgoing
session did this — claimed ~0.5 was "ideal" because it had labeled 5/10 fixtures as
escalate; the operator rejected it outright). The target is ≤5%, full stop.

---

## The core unsolved problem (read this first)

There is a real design tension:
- The **reviewer's intent-gate** (SIGNALS §4.1): "if you cannot cite an intent source
  for what 'correct' means, ESCALATE." This pushes the escalate rate UP.
- The **operator wants escalate ≤5%.** The fleet must DECIDE, not defer.

These fight directly. The eval proved it:

| Cell (k=3, 10 fixtures) | false-dismiss | escalate rate | notes |
|---|---|---|---|
| flash · prompt v1 (sha 6a87a97f) | **0.67** (6/9) | 0.13 | dismiss-biased — silently drops real bugs. Dangerous. |
| flash · prompt v2 (sha 0c4a9be3) | 0.00 | **0.60** (18/30) | crux rule killed false-dismiss but ballooned escalate |
| **v4-pro · prompt v2** (0c4a9be3) | 0.00 | **0.81** (22/27) | safest + most consistent, but punts 81% to operator = useless |

So: prompt v1 → dangerous (drops defects). prompt v2 → safe but useless (escalates
everything). **Neither is shippable.** The pendulum swung from one failure to the other.

**The attempted resolution (UNTESTED — working tree only, sha d3104eb6):** reframe the
prompt so escalate is the ~1/20 exception and an *error-shaped signal is itself a
citable `code-invariant` violation* ("code must not throw uncaught / null-deref /
failed load") — so the fleet FILES the error (cheap, hands work to the fix-fleet)
instead of escalating to the operator. If this holds, escalate should drop hard while
false-dismiss stays 0 (real errors → file, not dismiss). **This has not been run.
First job for the next session: sync it to the mini and score v4-pro, measure the
escalate rate.** If it doesn't get near ≤5%, the approach may be over-engineered — a
stronger model with a much simpler prompt may beat this whole gate stack.

---

## Where everything lives + how to run

- **Repo code:** `signal-fleet/mvp/*.py` (this working tree).
- **Deployed copy:** `homelab:~/signal-fleet/mvp/` — a MANUAL rsync, NOT git, NOT a
  symlink. After editing repo `.py`, you MUST rsync to the mini before running:
  `rsync -a -e "ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes" ./signal-fleet/mvp/*.py homelab:~/signal-fleet/mvp/`
- **Access the mini:** `ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab`
- **Creds:** `homelab:~/signal-fleet/fleet.env` (chmod 600, mini-local, NEVER in repo).
  Source it before running: `set -a; . ~/signal-fleet/fleet.env; set +a`
- **Backends (tailnet, no auth):** VM `:8428`, VictoriaLogs `:9428`, VictoriaTraces
  `:10428`; GlitchTip `:8090`; Grafana `:3000`; Langfuse `:4000`. Reachable from the
  laptop too (on tailnet).
- **Run the eval (on the mini):**
  ```
  cd ~/signal-fleet/mvp
  set -a; . ~/signal-fleet/fleet.env; set +a
  export SF_OBSERV_DISABLED=1        # keep eval replays out of live traces/metrics
  python3 freeze.py --refreeze       # re-record probe tables from stored signals (preserves labels)
  SF_TRIAGE_MODEL=deepseek/deepseek-v4-pro python3 score.py 3
  ```
  Note: probe tables are model/prompt-INDEPENDENT — a prompt change does NOT require a
  re-freeze. Only re-freeze if the signals or probe code change.

---

## What is BUILT and verified

- **Investigation loop** (`triage.py investigate()`): menu-driven probe loop, hard cap
  N=3, four terminal dispositions. Verified: reaches clean terminals, self-probes.
- **Probe menu** (`probes.py`): 6 typed probes (event_detail, occurrence_history,
  service_logs, metric, trace, source_state). Model requests BY NAME. Deterministic.
- **Deterministic gates** (`triage.py`): intent gate on file; cleanup gate (machine
  marker); dismiss gate (requires `dismissal_evidence` + an independent/benign-content
  corroborating probe — occurrence_history is content-checked, not just usability).
- **Probe→response table eval** (`freeze.py` / `score.py`): freeze eagerly records the
  WHOLE 6-probe menu (+ the model's actual args) so replays don't miss on probe
  selection; args-axis misses fall back and are counted as `table_miss` NOISE, excluded
  from model metrics. Verified: replay is deterministic, table-miss handling works.
- **Dual-label scoring**: each fixture has `true_nature` (scores false-dismiss = safety)
  and `correct_autonomous` (scores silent-drop = autonomy). See labeling caveat below.
- **Fixtures**: 10, mini-local at `homelab:~/signal-fleet/reference/*.json` (real logs,
  NEVER committed — data hygiene). All probe-schema, all labeled.

## What does NOT work / is NOT done

- **No shippable config** — see the core problem above. Escalate rate is 0.60–0.81; the
  bar is ≤5%. This is THE open item.
- **The untested prompt (sha d3104eb6)** in the working tree — hypothesis, not a result.
- **file-recall is UNTESTABLE with this fixture set.** All 3 file-fixtures (PLAYER-4/5,
  PODCAST-4) are things the outgoing session labeled `correct_autonomous=escalate`, so
  File is never the "right" answer in the labels — the File path is unexercised. Need a
  fixture where File is unambiguously correct (reviewer's point: seed a real defect from
  the Fleet-1 replay set, shaped as a signal).
- **The `correct_autonomous` labels encode a ~50% escalate philosophy the operator
  REJECTS.** They were set by the outgoing session (only PLAYER-4/5→escalate came from
  the reviewer; ORRERY-5/6 and PODCAST-4→escalate were derived). Under "escalate ≤5% +
  errors→file", most of these should become `file` or a confident action. **Re-label
  before trusting the autonomy-hit metric.** (true_nature labels are fine and
  operator-confirmed; only the second column is suspect.)
- **Escalate-rate tolerance** is now known (≤5%) but was NOT wired into score.py as a
  pass/fail gate — add it.
- **Nothing is pushed for the eval branch beyond commits below; nothing is live/daemon.**

---

## Exact tree / commit / deploy state

- **Committed, unpushed (2 commits):** `63ba041` (R7 impl: dual-label + prompt v2 +
  gate content-check), `d7161a9` (round-7 review notes). Last TESTED prompt = the one in
  `63ba041`, **PROMPT_SHA `0c4a9be3`** → scored escalate 0.81 (v4-pro).
- **Working tree, UNCOMMITTED, UNTESTED:** `signal-fleet/mvp/triage.py` — prompt
  **sha `d3104eb6`** (escalate-rare + errors-are-filable hypothesis). Decide: test it,
  revise it, or `git checkout signal-fleet/mvp/triage.py` to revert to the tested v2.
- **Mini deployed copy:** has prompt v2 (`0c4a9be3`) + all other files as of the sweep.
  The untested d3104eb6 triage.py is NOT yet rsynced to the mini.
- **Review ask:** `signal-fleet/REVIEW-ASK-round7.md` (committed). Reviewer's Round 7
  findings are folded; the reviewer works in this tree.

---

## Mistakes the outgoing session made — do NOT repeat

1. **Presented an obviously-failing 0.81 escalate rate as a neutral "result" and asked
   the operator to supply the tolerance** — instead of recognizing 22/27-to-the-desk as
   a self-evident failure and fixing it. When a number is garbage, say so and fix it.
2. **Invented an "ideal escalate rate ~0.5" from its own labels** and attributed it to
   the data. Circular. The operator sets the bar (≤5%), not the labels.
3. General over-reach earlier in the project (building unasked). The operator values:
   do exactly what's asked, act on stated goals, stop and don't invent scope.

## Persistent constraints (carry these)

- Secrets NEVER in the repo; `fleet.env` is mini-local, chmod 600. Secrets-scan before
  every commit. NEVER push without explicit per-push approval.
- NO DB hacks / use prescribed normal-consumer methods per platform.
- NEVER commit real evidence/logs (fixtures stay mini-local).
- The operator's name must never appear in code/docs (use "the operator").
- Producer identity is separated: environment=`operations`, service=`triage-fleet`,
  own GlitchTip project + Langfuse project (so the fleet's own telemetry never mixes
  with the systems it watches). `SF_OBSERV_DISABLED=1` for eval replays.

## Design docs (source of truth)

- `signal-fleet/SIGNALS.md` — north-star design (§4.1 intent gate, §7 dispositions,
  §7.3 investigation-driven triage). NOTE: §4.1's "can't cite intent → escalate" is in
  tension with the ≤5% escalate bar — this needs reconciling in the doc.
- `signal-fleet/EVAL.md` — eval design (3-transition go-live gate, model axis §3.6).
- `signal-fleet/REVIEW-2026-07-24-fleet1-architectural.md` — 7 rounds of reviewer notes.
- `docs/rfc/RFC-0003-signal-to-action-fleet.md` — the RFC.
