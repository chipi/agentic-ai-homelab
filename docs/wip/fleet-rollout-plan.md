# Fleet rollout plan — lab → wild, per-fleet tracks

**Status:** living punch list (tick items as they land; strike stages as they
complete). **Owner:** the operator gates every stage transition; agents tick
build items. The two fleets roll out **independently** — whichever hits its
gate first goes first; today that is **Fleet 2 (triage)**, with Fleet 1 behind
one structural build (real-issue intake) plus its confirmation sweep.

Go-live sections in the design docs point here:
[RFC-0002](../rfc/RFC-0002-autonomous-bug-fix-fleet.md) ·
[RFC-0003](../rfc/RFC-0003-signal-to-action-fleet.md) ·
`signal-fleet/EVAL.md` §1 · `signal-fleet/SIGNALS.md` §10.

The measured foundations behind every claim: triage bar (false-dismiss 0/36
across two fixture sets, escalate ≤0.05), chain economics (~$0.50/chain,
triage $0.01–0.05/signal), fail-safe terminals (no silent wrong action in any
measured run), dead-call guard (billing failure ≠ model verdict).

---

## Shared foundations (once, serve both fleets)

- [ ] **OpenRouter provisioned keys with spend limits** — one key per fleet,
      hard monthly cap each (the backstop that would have caught the
      2026-07-24 exhaustion before it silently emptied completions).
- [ ] **Kill switch convention** — flag file per fleet
      (`~/signal-fleet/STOP`, `~/bugfix-fleet/STOP`) checked at the top of
      every orchestrator cycle; `launchctl unload` as hard stop. Documented
      in each fleet's runbook.
- [ ] **Spend + health panels** — daily $ per fleet (from the fleet's own
      metrics), handled-rate, overturn-rate-per-class; alert on daily spend
      over threshold and on dead-call occurrences.
- [ ] **Incident→fixture pipeline (runbook)** — misbehavior procedure: stop
      via flag → ledger forensics (model, prompt_sha, gates, evidence per
      decision) → incident becomes a labeled fixture → fix must pass it →
      resume. The eval grows from reality; write it down once, both fleets.
- [ ] **Weekly operator ritual (10 min)** — review all escalates + a sample
      of autonomous dismisses/cleanups; every answer becomes an
      `operator-rule` intent source + fixture. This is the
      compounding-autonomy mechanism AND the drift detector.

---

## Track A — Fleet 2 (signal-to-action triage) — AHEAD

### Gate to MVP (start shadow when all ticked)
- [x] Quality bar: false-dismiss = 0 AND escalate ≤5%, k≥3 — passed on the
      10-fixture set (3 sweeps: 0/27, ~0.045) and the expanded 14-fixture
      set (0/9, 0.048). Config: v4-pro + prompt `c2ece738`.
- [x] Fail-loud plumbing: deterministic gates, dead-call guard, append-only
      ledger, producer-separated o11y (environment=operations).
- [ ] **Occurrence-churn fix (R5-4)** — GlitchTip occurrence_id keys on
      `lastSeen`, which advances per event → hot errors re-triage every
      poll. Re-key to firstSeen + resolved→unresolved transition. MANDATORY
      before any daemon.
- [ ] **Recurrence dedup** — same fingerprint re-firing after a disposition
      is (a) an implicit-overturn signal on Dismiss (R2-2), (b) never a
      fresh full-cost triage more than once per window.
- [ ] **Daemon mode** — launchd service on the mini, poll interval ~5–15
      min, kill-switch check per cycle, per-day budget cap.
- [ ] **Propose-first surface** — daily digest (ntfy push or one GH issue
      per day): "dismiss these N, cleanup these M, file this K — object
      within 24h or I act." Timeout-approval converges to autonomy without
      building UI.

### Stage A1 — Shadow (1–2 weeks)
- [ ] Daemon live, decisions recorded + observable, ZERO actions taken.
- [ ] Weekly ritual running; shadow ledger reviewed → labeled real-world
      dataset accumulates.
- [ ] Exit: ≥2 weeks, no false-dismiss found in review, digest mechanics
      proven.

### Stage A2 — Propose-first
- [ ] Digest live with real actions on approval; escalates push immediately.
- [ ] Overturn tracking per class from operator clicks.
- [ ] Exit per class: overturn ≈ 0 over the window operator sets.

### Stage A3 — Autonomy by class (promotion is per-class + reversible)
- [ ] cleanup-with-marker autonomous (write-back: resolve+tag, never delete).
- [ ] dismiss-with-evidence autonomous.
- [ ] File autonomous (cheap mistake, double-gated downstream).
- [ ] escalate: human forever.

### Parallel (not gating shadow)
- [ ] Seeded-defect fixtures (thrown bugs from orrery git history: revert a
      real null-guard fix on a dev deploy, capture the real GlitchTip
      event) — widens the thin file class (3 fixtures, 2 near-dupes).
      Needs operator at keyboard (dev deploy + DSN).
- [ ] Client-side corroboration probe (Umami/session evidence) — the
      durable escalate-rate reducer for browser errors.
- [ ] STAGING-2/3/4 fixture labels — operator call.
- [ ] Langfuse costDetails in `observ.py` (mirror Fleet-1's fix).

## Track B — Fleet 1 (bug-fix) — one structural build behind

**The structural truth:** production has no hidden oracle. The replay eval's
answer key is replaced in the wild by: triage-L1 acceptance → fleet-written
tests → CI green → Claude reviewer → **operator merges, always**. The bake-off
stays alive as the hiring pipeline (models/harnesses earn seats on frozen
replay before touching production).

### Gate to MVP
- [ ] **Confirmation sweep** (running): v3+coverage chain table at k=3 —
      accept if ships ≥ the honest baseline meaningfully (target ~4/5
      family) with zero regressions on shipped chains.
- [x] Regression-cleanliness: every shipped chain in every measured sweep is
      oracle-passed with PASS_TO_PASS intact.
- [x] Reporter loop + coverage protocol (production analog: needs-info goes
      to the issue reporter / operator).
- [ ] **Real-issue intake wiring** — GH `bug`-label → ticket shape →
      orchestrate loop; PR out (branch + PR via the existing App code in
      `src/github/`), NEVER merge. Scope: **orrery only**.
- [ ] **Production acceptance path** — worker must produce a failing-test
      first (repro-first), CI green after; Claude reviewer gate wired on
      the PR.
- [ ] Budget caps per chain + per day; kill switch; ledger as built.

### Stage B1 — Shadow on real backlog
- [ ] Feed real orrery `bug` issues through triage→plan only (no worker
      dispatch): does L1-or-needs-info come out sane? Operator reviews.
### Stage B2 — PR-mode (the real MVP)
- [ ] Full chains on real issues; deliverable = a PR + the chain ledger;
      operator merges or rejects. Every rejection → fixture.
- [ ] Exit: operator-set window of merged-PR rate + zero bad merges (bad =
      would have shipped a defect if merged blind).
### Stage B3 — Scale decisions (explicitly later)
- [ ] podcast_scraper repo; opencode/model columns from the bake-off grid;
      batch `fixes`-branch flow per RFC-0002 if PR volume warrants.

## Explicitly NOT in any MVP
Fleet 3 (remediation) — future RFC-0004; auto-merge of fleet PRs — never in
MVP; autonomy for escalate — never; cross-repo rollout before orrery proves
the loop.
