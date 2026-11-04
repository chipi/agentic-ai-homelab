# Handover: evaluating and improving the triage fleet

**From:** the homelab session (X3 assistant work, RFC-0008). **To:** the `fleet` session, checkout
`/work/agentic-ai-homelab-fleet-evals`, tmux `agentic-ai-homelab:fleet-evals`. **Date:** 2026-11-04.

The triage fleet (signal-fleet, Fleet 2) and its evaluation are now yours. This note is what you need to
start, and what is already known about improving the fleet. The homelab session keeps the X3 assistant.

## Read first

1. `docs/signal-fleet-guide.md`: how the fleet works and why.
2. `signal-fleet/EVAL.md`: the fleet's evaluation design (the reference set, asymmetric metrics, replay).
3. `signal-fleet/EVAL-LESSONS-0.6.0.md`: what eval-harness's replay of the fleet's 233 Orrery decisions
   found, moved here today from eval-harness at the owner's instruction (original: chipi/eval-harness
   `d42e0437c`, `research/internal/TRIAGE_FLEET_LESSONS_0.6.0.md`).

## What is already known to improve (from EVAL-LESSONS-0.6.0.md)

- **F7, a crash with its fix named:** an empty reply on the last turn makes `triage.investigate()` return
  `None`; acting on it fails. Fix: fall through to the existing "no terminal decision" escalation, as the
  non-JSON path does. The smallest concrete change on the list.
- **F1:** the dismiss gate, not the model, makes 39 of production's 49 escalations: a browser error has
  no server-side probe to corroborate a dismissal with (21% escalated against the prompt's ~5%).
- **F2:** the brief makes every error-shaped signal a filing; it names none of the noise classes the
  operator closes (stale clients and version skew, injected extension code, mirrored staging bundles).
- **F3:** the release's age is fetched (`firstRelease`/`lastRelease`) but not shown to the model.
- **F4:** the model uses 1-2 of its 3 probes; `event_detail` is one choice among six.
- Six suggested changes (section 3), each to be measured as one arm before it ships; how to run an arm
  with `evh` is section 5. Its own limits: section 6 (the ten models' results) was never filled in, and
  **none of the suggestions has been tried**.

## Open in NEXT_STEPS (Fleets, Triage fleet)

Cleanup autonomy (track A3); seeded-defect fixtures (EVAL.md's "thin spot"); a client-side
corroboration probe from Umami for front-end signals; ground-truth labels for STAGING-2/3/4; a
`muted-class` label for bugs whose fingerprint keeps changing.

For the Umami probe: since today the hub computes Umami numbers per site every 5 minutes
(`https://hub.tail6d0ed4.ts.net/analytics.json`, `infra/homelab-home/hub-status.js` `analytics`). It holds
site-level totals, not per-error user spread, so whether it helps F1 is untested.

## Where the evaluation lives

- eval-harness, `/work/eval-harness/main`, `examples/triage-fleet/`: the replay adapter (calls the
  fleet's own `triage.investigate` with frozen probe answers), arm configs, labelling tools. The
  `eval harness` session owns it; ask it for the run state.
- Dataset `chipi-nbgd/orrery-triage` on Hugging Face (built by `signal-fleet/datasets/build_orrery_items.py`);
  93 decisions with an owner label.
- Not verified by me: the state of eval-harness branch 062 (commit `c039c3696`, waiting for the
  operator's push approval per NEXT_STEPS) and whether the v1 model results exist.

## What the homelab session changed in the fleet (this arc)

- `3d5e52a`: a LiteLLM error whose event names the X3 assistant backend (the `assistant` alias failing
  over) is an operational state, `assistant-failover`, dismissed without a ticket. Replay-proven over the
  five failover-test issues (#133-#137, closed by hand); live-verified: it dismissed LITELLM-1B.
- Per-decision probe capture was deployed on 2026-10-29 (`1805d1b`), so decisions from then on replay
  exactly (EVAL-LESSONS section 4).

## What transfers from the assistant evals (docs/wip/x3-assistant-evals.md)

- **Code selects, the model writes.** Qwen3-30B-A3B could not pick and copy events out of a long tool
  result: it changed times, took UTC fields, invented entries. Moving selection into code and giving it one
  short list took H7 from 1/3 to 11/12. A fleet prompt that hands the model a lot to choose from has
  the same risk.
- **Check the scorer before trusting it:** hand-made answers (correct, one item missing, an invented one)
  over live data must score as intended. Twice today the check found a scorer bug first.

## Working rules here

- Two checkouts commit to the same `main`: fetch and look at `git log HEAD..origin/main` before every
  push, and rebase. While GitHub's SSH push fails (2026-11-04 incident), push over HTTPS:
  `git push https://github.com/chipi/agentic-ai-homelab.git main`.
- A change to the fleet's decision logic gets the `replay-proven-fix` loop (old code from git, mutants).
- Deploys to the mini: `git pull` in `~/agentic-ai-homelab` there; the fleet's own deploy steps are in
  `signal-fleet/deploy/`. I have not checked what the fleet needs beyond the pull.
