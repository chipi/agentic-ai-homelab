# 0007 — docs/wip cleanup: 26 notes closed (25 deleted, 1 moved)

**Date:** 2026-10-29
**Operator:** Marko (chipi)
**Agent:** Claude Opus 5.5, via Claude Code (homelab session)
**Outcome:** `docs/wip/` went from 32 notes to 6. Every note was read in full, and each
open item it listed was checked against git history, the current repo, and (where only a
live host could answer) the mini and the DGX's metrics. Finished notes were deleted;
anything still needed was folded into the living doc where a reader would look for it;
still-open work was regrouped into `wip/NEXT_STEPS.md`. This entry is the record of what
each closed note was and how it ended. The full text of every note stays in git history
(`git log --all -- docs/wip/<name>`).

## Why

The operator asked why so many wip notes were open. Nothing ever closed one: the docs rules
only covered `NEXT_STEPS.md` (strike items, don't delete them) and `close-arc` only struck
items there. Every session that wrote a handover or plan left it behind. Decision D-0016 adds
the missing rule: a wip note is closed when its work ships.

## What happened to each note

| Note | Date | What it was | How it ended | Lasting parts now in |
|---|---|---|---|---|
| `handover-daily-recap-and-recommendations-email-templates-2026-09-12` | 09-12 | two missing delivery email templates, "built, NOT deployed" | deployed with 6483321 (10-09) | `infra/delivery/README.md`; delivery moves to chipi/infra (D-0014) |
| `handover-delivery-alert-routing-2026-08-05` | 08-05 | the fleet's alert intake contract and 3 routing fixes | all 3 done (b8c9020, 4811e0b, 0e1852e) | alerting `README.md` "Notification policies" (rewritten: it still described the removed GlitchTip route and a 4h repeat) |
| `handover-fleetd-alert-resolution-2026-08-02` | 08-02 | fleetd-cycle-failing NoData fixed | nothing open | `docs/fleet-architecture.md` invariant 7; rules.yaml comments |
| `handover-homelab-home-podcast-section-2026-08-29` | 08-29 | run gen.sh so the Podcast section is served | served (`podcastHealth` in the live page, 10-29) | `infra/homelab-home/` |
| `handover-homelab-session-2026-10-10` | 10-10 | session handover and watch-list | DGX converge done (NEXT_STEPS, 10-15); podcast items are podcast_scraper's | `docs/recipes/agent-access.md` |
| `EVAL_HARNESS_EXTRACTION_PLAN` | 09-26 | split the eval harness into its own repo | done: chipi/eval-harness (a1d9025), removed here in dec3575 (D-0015) | `README.md`, `docs/index.md` |
| `skills-usage-review-2026-10-17` | 10-17 | why agents didn't run the skills; 4 decisions | all 4 done (skill-nudge hook, secrets-scan script a21d0d3, `index.py --check-install`, homelab-endpoint shrunk) | this entry, below |
| `fastcontext-recon-guide` | 07-03 | FastContext install and wiring guide | installed; parked for opencode | `infra/fastcontext/README.md` "Why FastContext, and where it stands" |
| `fleet-rollout-plan` | 07-25 | lab → wild plan per fleet | Track A at propose since 07-29; Track B paused | `docs/fleet-architecture.md` "Rollout status"; open items in NEXT_STEPS |
| `multi-agent-fleet-pi-and-opencode` | 07-03 | external-style guide to an 8-role fleet | superseded by the oh-my-opencode plugin fleet | `workstation/config/AGENTS.md` fleet map |
| `openrouter-fleet-guide` | 07-03 | OpenRouter reference | production routing moved to LiteLLM | `infra/litellm/README.md` |
| `operator-playbook-fleets` | 07-29 | the operator's fleet rituals | folded; its "keys per vertical now live" was false (2fb91ee) | `docs/recipes/signal-fleet-runbook.md` §7 |
| `operator-preferences-review` | 07-24 | generated index of rules and 147 memories from other repos | rules promoted to `workstation/config/AGENTS.md`; it quoted other repos' private memory text, so it is not kept | 3 unresolved points in NEXT_STEPS |
| `seat-auction-round2` | 07-26 | round-2 plan for the bug-fix fleet's model seats | executed the same day (BAKEOFF 3m) | per-vertical keys item in NEXT_STEPS |
| `seat-auction-2026-07-26-report` | 07-26 | review-grade record of the seat auction | **moved**, not deleted | `bugfix-fleet/bakeoff/results-snapshots/2026-07-26-seat-auction/README.md` |
| `signal-fleet-flood-hardening` | 08-19 | the 2026-08-13→19 escalation flood (below) and fixes #2–#7 | complete (d763042) | `docs/signal-fleet-guide.md` (fail closed, operational markers, Known gaps) |
| `signal-fleet-triage-enhancements` | 08-27 | 8 triage improvements (normalized key, signal class, low-signal rollup, …) | all built (ceda02b) | guide; 2 gaps added to its Known gaps |
| `agentic-coding-fleet/README` | 07-03 | tracker for an interactive opencode/Pi coding fleet | dormant since 07-03; opencode side superseded by the plugin fleet | decisions below; "test ride" in NEXT_STEPS Deferred |
| `DGX-WEDGE-DIFFERENTIAL` | 09-18 | hypothesis log for 4 DGX wedges | superseded by the power-off reference | `wip/DGX-SPARK-KNOWN-HARDWARE-ISSUE.md` §1.6 |
| `dgx-telemetry-integration` | 08-16 | DGX moss/pyannote → GlitchTip wiring | done | `agent-access.md` (the shared `.env` DSN gotcha) |
| `mac-mini-headless-server` | 08-15 | OrbStack → colima, login-less boot, exposure redesign | done | ADR-0006 "Implementation update"; `infra/README.md` prerequisites (FileVault, pmset; Tailscale corrected to the standalone macsys build); `infra/engine/`, `infra/tailscale/` |
| `mini-box-pruning` | 08-30 | remove desktop-era software from the mini | executed 08-30 | 2 leftovers in NEXT_STEPS |
| `level3-prod-handover` | 08-15 | move prod telemetry to the TLS nodes | done (#1665 merged; chipi/infra workflows) | chipi/infra PROD_RUNBOOK |
| `level3-orrery-moss-telemetry-handover` | 08-16 | move orrery and moss off raw GlitchTip/Umami ports | done (orrery caddy files; ports closed) | orrery `ops/caddy/` |
| `handover-dgx-autoresearch-2026-08-30` | 08-30 | autoresearch vLLM was under the `ops` account | done; ops checkout reset 10-17 | `infra/dgx/AGENTS.md` |
| `handover-dgx-o11y-gaps-closed-2026-08-30` | 08-30 | DGX instrumentation gaps 1–4 | closed (podcast_scraper#1887) | `infra/observability/dcgm-counters.csv`, rules.yaml `dgx-gpu-metrics-stale` |

Still open in `docs/wip/`: `NEXT_STEPS.md`, `README.md`, `DGX-SPARK-KNOWN-HARDWARE-ISSUE.md`,
`colima-vcpu-8-to-4-runbook.md`, `tailscale-exit-node-mini.md`, `otel-pipeline-end-to-end.md`.

## Records worth keeping from the closed notes

**The 2026-08-13→19 escalation flood.** A LiteLLM virtual-key wipe made the triager's model
calls fail with 401; the triage step failed open and filed about 128 issues in
chipi/podcast_scraper. Fixes: fail closed in one place (`TriagerDown`, `fleet-triager-down`),
an operational classifier for cost-cap/402 errors (dismiss, no ticket, no LLM), group rules for
run-scoped causes, and test/synthetic suppression at ingestion. The frozen corpus is
`signal-fleet/reference-hardening/`.

**Skills usage review (2026-10-17).** Over every saved transcript: 893 `git push` against 2
`ship` invocations, 626 hand-written VictoriaMetrics/Logs/Traces queries against 5
`o11y-review`, and 8 of 18 skills never invoked. Main cause: a skill loads on the operator's
words, not on the agent's own next step, so nothing brings `ship` up while `git push` is being
typed. The fix was the `skill-nudge.py` hook (a context note when a prompt or Bash command
matches a skill's `triggers.json`), scripts for checklist-only skills, and five new skills
(`host-run`, `telemetry-probe`, `mint-credential`, `infra-drift`, `deploy-verify`).

**Agentic coding fleet decisions (2026-06-24).** OpenRouter with two workspaces (opencode, Pi),
one key each, model-locked by a workspace allowlist (D1/D2); FastContext local-only, never via
OpenRouter (D4); Claude stays the out-of-loop reviewer (D5); OpenRouter prompt logging and
Langfuse export on (D7/D8); Kimi K2.6 as Pi's default (D9); RTK skipped in opencode and Pi (D10);
FastContext parked for opencode (D11). The opencode fleet was later built from the
oh-my-opencode plugin instead of hand-written agents; the first test ride never happened.
