# signal-fleet — flood hardening (the 2026-08-13→19 escalation storm)

Design for the podcast-project feedback after ~128 fleet-filed issues flooded
`chipi/podcast_scraper` (Aug 13–19, peaking Aug 19 with 71). Root cause fixed;
this doc specifies the resilience changes so the next triager outage can't repeat it.

## What happened (verified)

- **Root cause (#1) — FIXED.** The triager posts to homelab LiteLLM
  (`SF_OPENROUTER_URL=http://localhost:4001/v1/chat/completions`) with a **virtual
  key** (`OPENROUTER_API_KEY` = `sk-S2C0X…` = `LITELLM_FLEET_TRIAGE_KEY`). The
  colima/DB recreate **wiped LiteLLM's key table**, so every call `401`'d
  (reproduced: body names `LiteLLM_VerificationTokenTable`; `/key/info` = `404`).
  With triage broken, `triage.py:255-257` fails **open** — returns
  `escalate / "transient failure — retry?"` per signal. Recreated both keys
  (`fleet-triage` $50, `fleet-bugfix` $100) with their exact values; triage now
  returns `200` + usable JSON. See `infra/litellm/README.md`.
- **Why the safety nets didn't hold.** The fleet *does* dedup escalations by
  fingerprint (`file_escalation → file_or_update`, filing.py:290) and *does* have
  storm-grouping (`group_key_for`). But (a) each fail-open escalation carries the
  **raw signal's own fingerprint** — all distinct — so per-fingerprint dedup can't
  collapse them; and (b) `GROUP_RULES` only cover gemini/dgx-whisper/otel — nothing
  for cost-cap/budget/401. So 128 distinct signals → 128 issues.
- **Scope.** Podcast-only. `chipi/orrery` has 84 open issues but **zero** flood-class
  (cost-cap/budget) and a flat date spread — no storm there.

## The gaps, corrected

The feedback's #3 ("dedup by fingerprint") is **already implemented**. The real
gaps are **#2 fail-closed** and **#4 class-level grouping** — plus classification
(#5), correlation (#6), and test-suppression (#7).

## Design — per point, with code locations

### #2 — Fail CLOSED on triager outage *(highest value after #1)*
A triager outage must produce **one** issue, not N.
- `triage.py::_call` — detect a *persistent* failure (HTTP 401/403 auth, or repeated
  transport failure) and raise a distinct `TriagerDown` exception instead of letting
  `investigate()` return a per-signal `escalate` (triage.py:255-257).
- `orchestrator.py::run_poll` — catch `TriagerDown`: **stop the per-signal loop**,
  and file/update ONE issue via a **fixed fingerprint** `fleet:triager-down` with a
  running count + "N signals unclassified since T" (uses the existing
  `file_or_update` dedup, so re-runs comment rather than re-file). Also emit a
  substrate metric/alert (`observ.py`). Transient one-off flakes keep the current
  retry-in-`investigate` behavior; only persistent/auth failures trip fail-closed.

### #4 — Class-level storm grouping + rate threshold
- `filing.py::GROUP_RULES` — add rules mapping the flood classes to group keys:
  `cost soft cap|CostCapExceeded` → `cost-cap`; `no budget|no credit|402|insufficient`
  → `provider-budget`; `OpenAIProvider not initialized|Fallback tier failed` →
  `provider-fallback` (these collapse onto their root — see #6). Now same-class
  distinct-fingerprint signals collapse to one group issue via the existing
  `ledger_lookup(fp, group_key)` path.
- Rate threshold: when ≥N same-`group_key` file/escalate attempts land in a window,
  open ONE incident issue and attach the rest (extend `file_or_update`/a small
  counter keyed on `group_key`+day).

### #5 — Classify operational states as NOT-a-bug (route to alert, not ticket)
Deterministic gate (not a prompt hope), in `triage.py` alongside the existing gates:
- `CostCapExceeded` / "cost soft cap exceeded" = a **guardrail firing** (the incident
  working as designed) → not a code bug → `dismiss` with an ops annotation, or a
  single `config-enhancement` at most (not per-occurrence).
- "no budget/credit left" + HTTP `402` = a **billing state** → dismiss-as-operational.
- "OpenAIProvider not initialized" / "Fallback tier failed" = **downstream** of the
  budget/cap root (see #6) → not independent bugs.
  Add an `OPERATIONAL_MARKERS` regex + an `_operational_gate` that routes matches to
  dismiss/alert; keep the marker list curated like `CLEANUP_MARKERS`.

### #6 — Correlate root vs symptom within a run
- `correlate.py` — within a run/window, when a cost-cap/budget **root** signal is
  present, mark summarization-failed / fallback-failed / provider-not-initialized /
  GI-invariant signals as **downstream** and attach them to the root's issue rather
  than filing independently. File the root; link the symptoms.

### #7 — Suppress test / synthetic runs at ingestion
- `sources.py` — filter signals whose run-id / source carries a test marker
  (`agentE2E*`, synthetic ids) **before** they reach triage (an `agentE2E…player`
  E2E run was escalated as prod). Cheapest, most contained change.

## Cleanup (after the code lands)
- Bulk-close the podcast flood: open issues on `chipi/podcast_scraper` in the flood
  classes filed Aug 13–19 (cost-cap 63, summariz 24, budget 11, openai 9, e2e 8,
  fallback/init/invariant/402) — comment each with the root cause (triager 401 /
  key wipe) + link this doc, then close. Leave anything ambiguous open.
- Orrery: nothing to close (no storm).

## Bugfix-fleet (after triage-fleet)
- Same key class already fixed (`fleet-bugfix` recreated). Audit its own
  escalation/retry path for an equivalent fail-open, and whether it filed storm
  issues in the window.

## Testing
- `score.py` fixtures + `orchestrator.py --synthetic` for the triage path; a
  `--dry-run` cycle to confirm fail-closed emits ONE `fleet:triager-down` and that
  the new group rules collapse a batch of cost-cap fixtures to one group issue.
- Repo `signal-fleet/mvp/` == mini `~/signal-fleet/mvp/` (verified 0/15 diff); deploy
  = copy changed files to the mini (the mini dir is not a git repo).

## Status
- [x] #1 auth — both keys recreated + documented (`infra/litellm/README.md`)
- [x] #2 fail-closed — `TriagerDown` (triage.py) on 401/403 → orchestrator files ONE
  `grafana:fleet-triager-down` issue on the ops repo (not N escalations)
- [x] #4 group rules — cost-cap / provider-budget / provider-fallback collapse
  distinct-fingerprint same-class signals (filing.py `GROUP_RULES`)
- [x] #5 operational classifier — cost-cap/402/budget/provider-init → dismiss-no-ticket,
  deterministic, no LLM (triage.py `operational_class`)
- [x] #7 suppress test/synthetic at ingestion (sources.py `TEST_RUN_MARKER`)
- [~] #6 — covered via #4 (grouping) + #5 (downstream states dismissed/grouped with root);
  full run-scoped attach-to-root-issue deferred as a refinement
- [x] all unit-tested (classify/group/suppress + the TriagerDown fail-closed flow) + a
  dry-run shadow cycle
- [x] **source tokens OK (my earlier "401 drift" was a test artifact — corrected).**
  `fleetd.json` loads `env_file=fleet-gateway.env`, whose `GRAFANA_TOKEN`/`GLITCHTIP_TOKEN`
  test **200/200**. My first dry-run wrongly sourced `fleet.env` *after* it, and `fleet.env`
  holds **stale duplicate** tokens (glsa_0…/be48a4…, 401). Re-run with only
  `fleet-gateway.env`: clean cycle, **0 source failures**, 3 GlitchTip issues fetched +
  deduped. Fleet is functional. (Minor cleanup: drop the stale token dupes from `fleet.env`
  so nobody trips on them.)
- [x] cleanup — the flood was already ~115-closed in Aug (102 on Aug 19); closed the
  remaining 15 cost-cap duplicates (#1559–#1582) with a root-cause comment. 0 cost-cap
  open. orrery had no storm (nothing to close).
- [x] bugfix-fleet audit — no flood risk: daemon not wired (`fleetd.json` Track B gate +
  stop-flag), no python triage-style fail-open (shell bake-off harness, model-tier
  escalation not GH-issue), `fleet-bugfix` key recreated, orrery clean.

## Minor follow-ups (non-blocking)
- Drop the stale duplicate `GRAFANA_TOKEN`/`GLITCHTIP_TOKEN` from `fleet.env` (unused by
  fleetd, but a landmine for anyone sourcing it).
- The fleet's Langfuse tracing key 401s (`observ.finalize` best-effort push) — another
  recreation casualty; non-blocking (traces only), recreate when convenient.
