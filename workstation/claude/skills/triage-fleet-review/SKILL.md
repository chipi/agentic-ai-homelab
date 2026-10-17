---
name: triage-fleet-review
description: Weekly health and quality review of the homelab triage fleet (signal-fleet, Fleet 2) across every repo it files into (podcast_scraper, orrery, agentic-ai-homelab), plus triage of the proposals it parks for the operator. Use when the operator asks "how is the fleet doing", "what did the fleet do this week", "what can we optimize in the fleet", or "triage the fleet queue / parked proposals". Read-only: checks cycle health, the dispositions and filed ledgers, and what the fleet did on GitHub, and flags fan-out, reopens, issues buried in low-signal rollups, escalations and dismissals to audit.
---

# triage-fleet-review

A read-only weekly review of the triage fleet, in the same shape every time, so a
different agent each week gets comparable answers. It never changes the fleet,
the ledgers, or any issue.

Background, read once per session if you haven't:
- **What the fleet is and why each rule exists:** `docs/signal-fleet-guide.md` in `chipi/agentic-ai-homelab`.
- **How to operate and improve it:** `docs/recipes/signal-fleet-runbook.md`. §4 is the review this skill automates; §5 is the improvement loop.

## Run

```bash
python3 ~/.claude/skills/triage-fleet-review/scripts/review.py --days 7
```

It needs SSH to the fleet host and an authenticated `gh`.
- **SSH command:** the default is the Mac mini: `ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab`. Override with `--ssh` or `HOMELAB_SSH` if the fleet moved.
- **Repos:** the default is the three repos the fleet files into; override with `--repos`.

The host side runs a stdlib-only Python script over SSH (the mini has Python 3.9) and reads `~/fleetd/fleetd.log` and `~/signal-fleet/results/`. The GitHub side reads issues and comments with `gh api`.

## What the script checks, and what healthy looks like

| Section | Healthy |
|---|---|
| 1. Alive | all cycles `ok`, about 144 a day; no STOP flag |
| 2. Decided | escalations are rare. Recurrence rows: one per count change. Dozens for one fingerprint *after 2026-10-01* = a regression of fix `b3c4c5f`. |
| 3. Did on GitHub | new issues are real problems; comments land on the right issue |
| 4. Flags | **fan-out**: none (one condition → several issues means the source rule is too fine-grained). **Reopens**: each justified. **Rollup comments**: none is a real bug buried as one line. |
| 5. Dismiss sample | the cited evidence holds up when you open it in GlitchTip or Grafana |
| 6. Ledger health | no lingering `.deferred.json` entries |

## Your job after the script: judge, then report

The script finds candidates; it can't tell right from wrong. For each flag:

1. **Check against explicit links, not titles.** Before calling a fleet action wrong, look at:
   - GitHub's duplicate link: GraphQL `ClosedEvent.duplicateOf`;
   - the ledger row's own signal: `filed.tsv`, plus the alert name in `dispositions.tsv`;
   - whether a GlitchTip short id was reused by a new project.
   
   Titles misled a reviewer on 2026-10-02.
2. **Separate before-the-fix history from current behaviour.** The window can span a deploy; check `git log` on the fleet host's checkout.
3. **Report in four parts, each with numbers:**
   - **did:** cycles, dispositions, GitHub writes, new issues;
   - **went wrong:** flags you confirmed, with the evidence;
   - **missed:** what never reached the fleet. Run the `o11y-review` skill for the same window to find warnings and errors.
   - **improve:** each confirmed problem as one of: an operator action (close, mute or route an issue), a fleet fix through the runbook's §5 loop (use the `replay-proven-fix` skill), or a known gap to add to the guide.
4. **Follow the operator's rules:**
   - never open GitHub issues without approval;
   - never close or reopen issues on your own;
   - a fleet code change goes through `replay-proven-fix` and the operator's go before deploy.

## Triage the parked proposals (`proposals.py`)

The fleet parks proposals it may not act on alone (`cleanup`, `config-enhancement`) in
`~/signal-fleet/queue/` as `*.json`. Nobody reviewing them is how 54 piled up between September
and 2026-10-17. Its own gauge, `signal_fleet_queue_oldest_age_seconds`, is the signal that the
operator is the bottleneck.

```bash
P=~/.claude/skills/triage-fleet-review/scripts/proposals.py
~/.claude/skills/host-run/scripts/run.sh homelab $P            # read-only list with a proposed action each
~/.claude/skills/host-run/scripts/run.sh homelab $P --apply    # only after the operator's go
```

Each proposal's fingerprint (`glitchtip:<SHORT-ID>`, `grafana:<hash>`) is looked up in GlitchTip,
across every project, or in `dispositions.tsv`.

| Action | When | `--apply` does |
|---|---|---|
| done | the issue is already resolved or deleted | marks the proposal `.resolved` |
| resolve | a cleanup of an unresolved test, probe or smoke issue (matched by title) | resolves it in GlitchTip (superuser session), re-reads it, then marks |
| stale | a tuning proposal whose issue was last seen > 14 days ago, or a grafana alert the fleet hasn't seen in 14 days | marks `.resolved` |
| review | anything else | nothing: a person decides |

**Before `--apply`,** read the `review` list, and hand items owned by another project (orrery,
the mobile app) to that project's session. On 2026-10-17 orrery decided its three itself.

Replayed on the 56 proposals of 2026-10-17: 39 done, 10 stale, and 7 review. The 7 were the
tuning proposals whose errors were still recent, e.g. the podcast pipeline's deadline messages.

## Not covered

- **Spend:** check the Grafana dashboard "Fleet Workforce — Triage (Fleet 2)" (`fleetd_spend_day`, $2/day cap).
- **The LLM's reasoning quality** beyond the five-dismissal sample.
- **Signals the fleet never sees** (warnings, logs without errors): see `o11y-review`.
