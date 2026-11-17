# Flotilla items (owned by the flotilla session)

Open items about the fleets and the fleet session's evaluation work, moved here from
[`NEXT_STEPS.md`](NEXT_STEPS.md) on 2026-11-17 so the flotilla session owns them from now on. The fleet
code moved to [flotilla](https://github.com/chipi/flotilla) (`fleetd/`, `signal-fleet/` and
`bugfix-fleet/` left this repo on 2026-11-16), so paths below such as `signal-fleet/` and `fleetd/` are
as recorded at the time; some may point at code that is now in flotilla or retired. The flotilla
session decides what carries over into its own repo and closes this note when it has
([wip/README.md](README.md) "Closing a note"). Items marked "Operator" are the operator's decisions.

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

## Fleets

Where each fleet stands: [fleet architecture → Rollout status](../fleet-architecture.md#rollout-status).

**Triage fleet (Fleet 2)**
- [ ] **Cleanup autonomy** (track A3): cleanup still waits for the operator.
- [ ] **Seeded-defect fixtures** — `signal-fleet/EVAL.md` calls them "still the thin spot".
- [ ] **Client-side corroboration probe** (Umami) for front-end signals.
- [ ] **Ground-truth labels for STAGING-2/3/4** (`signal-fleet/reference/glitchtip-ORRERY-STAGING-*.json`,
      `ground_truth.disposition` is null).
- [ ] **Escalations with no issue filed:** 3 of the 9 escalations of 2026-10-28..11-04 (LiteLLM key errors,
      2026-11-01 15:13, 15:23, 16:33 UTC) have no row in `filed.tsv`. Why the fleet escalated without filing is
      not known. check: `grep -c "" ~/signal-fleet/results/filed.tsv` against the escalate rows' fingerprints.
- [ ] **No CI covers `signal-fleet/`.** No workflow's paths include it; 6a59983 (the open-only count) got 0
      checks. Its only gates are `deploy.sh`'s on the mini.
- [ ] **`deploy.sh` skips a gate it adds.** bash reads the script before its own `git pull`, so the deploy
      that adds a gate runs the old list (2026-11-04: `eval_inbox_open_replay` ran by hand). Fix: re-exec the
      script after the pull.
- [ ] **A plain `git pull` on the mini deploys the fleet without its gates:** the mini's checkout is the
      fleet's live code. Pull it with `bash deploy/mini-deploy.sh`, even for hub-only commits
      (2026-11-04: hub deploys used plain pulls until 6a59983; none carried fleet code).
- [ ] **`muted-class` label** for bugs whose fingerprint keeps changing (guide, Known gaps).
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
- [x] ~~Operator: close eval-harness round r4~~ — *done 2026-11-04 (eval-harness 62e148cdc): closed, nothing
      promoted (own-code-loads is not separated from the noise-gate arm), the $4.27 spend accepted.*
- [ ] **(fleet session) The plan for what comes next:** [triage fleet improvement plan](triage-fleet-improvement-plan.md)
      (code evals first: filing, the gates, the rest of the fleet's code as black boxes; then a held-out set and a tuning loop); its decisions are the operator's.
- [ ] **Operator: one label to check, ORRERY-PROD-S** (`TypeError: Failed to fetch`, labelled real because its issue
      closed as fixed). Two other `Failed to fetch` decisions are labelled noise: a real fix, or an umbrella close?
- [x] ~~Delete the stale `~/signal-fleet/fleet.env` on the mini~~ — *done 2026-10-30 (c739792):
      every live value was in `fleet-gateway.env` or the litellm `.env`, its GitHub and Langfuse
      values were dead; `ls` → No such file.*

**Bug-fix fleet (Fleet 1)** — paused by the operator after one real batch
- [ ] **Resume B1/B2** (shadow on the real backlog, then PR mode), and **B3**: add
      podcast_scraper next to orrery in `fleetd/deploy/chain.json`.
- [ ] **Per-vertical OpenRouter keys** (pi / opencode / fleet). Intended since 2026-07-26,
      never done: only 2 OpenRouter keys exist (2fb91ee; `openrouter-spend.sh`).
- [ ] **Langfuse span emission is a stub** (`bugfix-fleet/src/observability/langfuse.ts:22`
      `TODO(langfuse)`). Gateway-side traces exist since e4e396f; the chain's own spans don't.
- [ ] **Structured-output retry policy for flash workers** (`BAKEOFF.md:603`): about 1 in 11
      structured outputs flake; a flash fleet collects silent `stuck` chains without it.
- [ ] **Flash worker under the kick-back/advisor path is unmeasured** (`BAKEOFF.md:891`).
- [ ] **A test for `fleet/dispatch.ts`.** The vitest suite exists since 98420f6; dispatch
      routing is the named target still without a test.
- [ ] **pi/opencode worker adapters are skeletons** (`piAdapter.ts`, `opencodeAdapter.ts`):
      real harness integration is its own work item.
- [ ] **Split advisor consultation** (redirect → glm, confirm → flash), deferred on 2026-07-26;
      `fleetd/chain.go` still has one advisor.
