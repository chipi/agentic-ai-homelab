# Fleet items (owned by the fleet session)

Open items about running, measuring, labelling and tuning the fleets, and the X3 assistant's gaps, split
out of [flotilla items](flotilla-items.md) on 2026-11-17 (the operator's call): flotilla owns the platform
and the fleet code, the fleet session owns these. Paths such as `signal-fleet/` are as recorded at the time;
the fleet code is now in [flotilla](https://github.com/chipi/flotilla). Items marked "Operator" are the
operator's decisions.

Same conventions as `NEXT_STEPS.md`: strike an item when it's done, don't delete it.

## X3 assistant (RFC-0008), the fleet session's gaps (recorded 2026-11-04)

- [ ] **(fleet session) A hung X3 costs ~31 s on every call.** LiteLLM's `assistant` has one deployment, so it never cools
      down: each call waits the 30 s timeout, then fails over (measured 2026-11-03; a stopped X3 fails over in
      2.7 s). Options: a health check that takes the deployment out, or a shorter connect timeout.
- [ ] **(fleet session) The 30 s timeout is short for long answers** (the H7 timelines take up to ~90 s in the UIs end to end;
      a single slow generation can hit the timeout and fail over mid-answer). Not measured per call.
- [ ] **(fleet session) Rebuild-test the Langfuse judge scripts** (`infra/langfuse/judge/`) on a throwaway
      Langfuse, or after the next Langfuse upgrade: the tRPC payloads were last run on 3.225.11.
- [ ] **(fleet session) For the eval agent:** re-measure H6 after the open-only count (6a59983; the last run was on the 9-item
      count), and more rounds of H7 (two per UI) and analytics (one per UI). Sets in
      `infra/x3/assistant-ui-eval/evalsets/`, notes in `docs/wip/x3-assistant-evals.md`.

## Triage fleet (Fleet 2)

Where each fleet stands: [fleet architecture → Rollout status](../fleet-architecture.md#rollout-status).

- [ ] **Seeded-defect fixtures** — `signal-fleet/EVAL.md` calls them "still the thin spot".
- [ ] **Ground-truth labels for STAGING-2/3/4** (`signal-fleet/reference/glitchtip-ORRERY-STAGING-*.json`,
      `ground_truth.disposition` is null).
- [ ] **Escalations with no issue filed:** 3 of the 9 escalations of 2026-10-28..11-04 (LiteLLM key errors,
      2026-11-01 15:13, 15:23, 16:33 UTC) have no row in `filed.tsv`. Why the fleet escalated without filing is
      not known. check: `grep -c "" ~/signal-fleet/results/filed.tsv` against the escalate rows' fingerprints.
- [ ] **(fleet session) See the shipped brief change live.** Prompt `219b34bf` (a failed dynamic import or
      service-worker load is filed, not dismissed) deployed 2026-11-04 16:30 UTC (`8213775`); no decision used it in
      its first hour. check: `awk -F'\t' '$11=="219b34bf"' ~/signal-fleet/results/dispositions.tsv | wc -l`, then
      the escalation share of the week after against the week before. Measured effect:
      `signal-fleet/EVAL-LESSONS-0.6.0.md` section 7.
- [ ] **(fleet session) A held-out set.** Every r4 change was designed and measured on the same 65 labelled
      decisions. The decisions captured exactly since 2026-10-29 (`~/signal-fleet/results/probes/`, 75 on
      2026-11-04, about 15 of them Orrery) need labels (outcome rules first, the operator on disagreements) before the
      next change is confirmed on them.
- [ ] **(fleet session) Parked: the client-noise gate** (`01226ca`, branch `fleet/noise-gate`, not pushed). The
      gate's marker works; the brief around it made 4 real problems cleanup/dismiss in 1 of 3 passes. A smaller version
      (the gate, extension and old-browser classes, no mirrored-bundle sentence) is to be confirmed on the held-out
      set, not on the 65 it was designed from.
- [ ] **(fleet session) Parked: a stale-client rule in filing** (an event from a build older than the fix's close is
      not a reopen). 3 of the fleet's 63 real reopens/regressions are that case; GlitchTip's releases cannot tell which
      build was live (it records a release on its first event), so it needs deploy history. Corpus freezer:
      `freeze_stale_client.py`, in the private repo chipi/fleet-eval-data `projects/stale-client-rule/` (moved 2026-11-05).
- [ ] **(fleet session) The plan for what comes next:** [triage fleet improvement plan](triage-fleet-improvement-plan.md)
      (code evals first: filing, the gates, the rest of the fleet's code as black boxes; then a held-out set and a tuning loop); its decisions are the operator's.
- [ ] **Operator: cleanup autonomy** (track A3): cleanup still waits for the operator.
- [ ] **Operator: one label to check, ORRERY-PROD-S** (`TypeError: Failed to fetch`, labelled real because its issue
      closed as fixed). Two other `Failed to fetch` decisions are labelled noise: a real fix, or an umbrella close?
- [x] ~~Operator: close eval-harness round r4~~ — *done 2026-11-04 (eval-harness 62e148cdc): closed, nothing
      promoted (own-code-loads is not separated from the noise-gate arm), the $4.27 spend accepted.*
