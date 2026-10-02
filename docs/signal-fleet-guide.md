# Triage fleet (Fleet 2) — how it works and why

This guide explains the triage fleet (`signal-fleet`, Fleet 2): its parts, one signal's path through it, the two ledgers that hold its memory, and the reasoning behind each rule. It is the "why" for the next agent who has to change it.

- **How to install, run, review and improve it:** [Triage fleet runbook](recipes/signal-fleet-runbook.md).
- **The full design history:** RFC-0003 and [`SIGNALS.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/signal-fleet/SIGNALS.md).
- **How this fleet fits with the others:** [Fleet architecture](fleet-architecture.md).

State as of 2026-10-02: live on the Mac mini at stage **`propose`**. It files, comments on and reopens GitHub issues in `chipi/podcast_scraper`, `chipi/orrery` and `chipi/agentic-ai-homelab`.

## What it is, and what it is not

The fleet watches production signals (Grafana alerts and GlitchTip errors) and decides, for each one, whether a human or another fleet needs to act. The result is a GitHub issue, a comment on an existing issue, or a recorded decision to do nothing.

It **never** touches production, never changes code, and never closes an issue. Closing is the operator's call (fleet-architecture invariant 6). Fixing belongs to Fleet 1 (bug-fix) and Fleet 3 (remediation).

## The moving parts

```text
fleetd (Go supervisor, macOS LaunchDaemon com.homelab.fleetd)
  └─ every 10 min: python3 orchestrator.py --cycle --limit 10 --no-dry-run
       env: ~/signal-fleet/fleet-gateway.env + FLEETD_STAGE + FLEETD_CYCLE_ID
       cwd: <checkout>/signal-fleet/mvp
       │
       ├─ 1. Grafana pass    firing, non-meta alerts        (sources.firing_alerts)
       ├─ 2. GlitchTip pass  10 most recently seen unresolved errors (sources.glitchtip_unresolved)
       │       each signal → triage → act → file (below)
       ├─ 3. triager-down    if the LLM is down: ONE aggregate issue, never one per signal
       ├─ 4. inbox push      operator-inbox metrics for Grafana
       ├─ 5. stale pass      once per UTC day: nudge open issues whose signal went quiet
       └─ 6. spend file      cycle cost → fleetd's daily budget guard ($2/day)
```

| Part | Where | Role |
|---|---|---|
| `fleetd` | [`fleetd/`](https://github.com/chipi/agentic-ai-homelab/tree/main/fleetd), binary at `~/fleetd/fleetd` | runs each fleet's cycle on its interval. Owns the stage, timeout (process group killed on timeout), budget, STOP flag and its own metrics. |
| cycle code | [`signal-fleet/mvp/`](https://github.com/chipi/agentic-ai-homelab/tree/main/signal-fleet/mvp), run **from the git checkout** | `orchestrator.py` (cycle), `sources.py` (read Grafana/GlitchTip), `triage.py` (decide), `actions.py` (dispositions ledger), `filing.py` (GitHub + filed ledger), `stale.py`, `inbox.py`, `observ.py` (metrics, Langfuse) |
| state | `~/signal-fleet/` on the host, never in git | `results/dispositions.tsv`, `results/filed.tsv`, small state files, `queue/`, `fleet-gateway.env` |
| LLM | the homelab LiteLLM gateway, model alias `fleet-triage-pro` | investigation and the file/escalate decision. Never dedup, never routing. |
| surfaces | Grafana "Fleet Workforce — Triage (Fleet 2)", "Triage — Operator Inbox"; alerts `fleetd-cycle-failing`, `fleetd-silent` | how the operator and the next agent see it |

The code is stateless between cycles. Everything the fleet "remembers" is in the two ledgers and the GitHub issues themselves.

## One signal's path

### 1. Normalize

`sources.to_signal` (Grafana) and `sources.to_error_signal` (GlitchTip) turn each item into a signal with two identities:

- **`fingerprint`** — the same problem across time. Grafana: the alert's label-set fingerprint. GlitchTip: `glitchtip:<SHORTID>`, e.g. `glitchtip:PODCAST-PIPELINE-5E`.
- **`occurrence_id`** — one episode of it: fingerprint + `startsAt` (Grafana) or `firstSeen` (GlitchTip). The cycle is idempotent on this key.

Test and synthetic signals are suppressed at this stage.

### 2. Seen before?

`orchestrator.run_grafana` / `run_glitchtip`:

- **Same occurrence already decided:** skip. A GlitchTip error whose event count rose since its last triage gets a `recurrence` row: one per count change, not one per cycle (fix `b3c4c5f`). It is re-triaged in full only after `SF_RETRIAGE_HOURS` (24 h).
- **A new Grafana firing of a known fingerprint inside 24 h:** a `recurrence` row, no new triage.

### 3. Triage: deterministic gates before the LLM

`triage.triage()`:

1. **Operational states → `dismiss`, no LLM** (`OPERATIONAL_MARKERS`):
    - cost cap;
    - provider budget / HTTP 402;
    - failed fallbacks;
    - upstream shared-pool rate limits (`upstream-rate-limit`: OpenRouter 429 with `limit_source=upstream_provider_shared_pool`, operator call on homelab #17).

    These are states, not bugs, and they hold even while the triager is down.

2. **Investigation by the LLM:** up to `SF_MAX_PROBES` (3) probes — logs, metrics, traces, source state, occurrence history — then one terminal decision:
    - `file`: a real problem; becomes an issue with `work_type` `bug` or `config-enhancement`;
    - `dismiss`: benign, **with independent probe evidence** (the intent gate);
    - `cleanup`: test or synthetic noise;
    - `escalate`: a specific question only a human can answer.

3. **Triager failures:**
    - a 401/402/403 means the triager is down: one aggregate issue for the fleet, not one per signal;
    - a timeout or 5xx defers the signal to the next cycle (`.deferred.json`, at most 6 deferrals, then escalate);
    - a cycle where every call deferred counts as triager-down (#11).

### 4. Act and file

`actions.act` writes the disposition row; `filing.file_or_update` decides what happens on GitHub (the decision tree under "The filed ledger"). The stage gates the writes:

- **`shadow`:** nothing external.
- **`propose`:** issues, comments and reopens on GitHub. Cleanup stays queued.
- **`live`:** everything.

## The two ledgers

Both are tab-separated files under `~/signal-fleet/results/`. **They are the fleet's memory**: lose them and it forgets every decision and re-files old problems. Back them up before any edit, and carry them to any new host.

### `dispositions.tsv` — every decision, append-only

One row per decision or recurrence. Columns:

```text
ts  occurrence_id  fingerprint  source  alertname  disposition  work_type  followup
model  prompt_ver  prompt_sha  gates  n_probes  certainty  reason  signal_count
cycle_id  stage
```

- **`disposition`:** `file | dismiss | escalate | cleanup | recurrence`.
- **`signal_count`:** the source's event count at decision time. Recurrence rows compare against it.
- **`gates`:** which gates passed, e.g. `operational:upstream-rate-limit`.
- **`cycle_id`:** joins a row to fleetd's log line for that cycle.

It answers "what did the fleet decide, and why?" and feeds:

- the dispositions dashboard (metric `signal_fleet_disposition{disposition=...}`);
- the stale check (when a signal was last seen);
- every replay eval.

As of 2026-10-02 it held about 13,000 rows. 10,764 of those are repeated recurrence rows written before fix `b3c4c5f`; they are harmless and left in place.

### `filed.tsv` — which GitHub issue each signal maps to

One row per fingerprint that reached GitHub. Columns:

```text
fingerprint  repo  issue  group_key  filed_at  last_comment_day  norm_key  alert_key
```

It is upserted by fingerprint, so a fingerprint has exactly one row.

#### The four matching keys, strongest first

| Key | Built from | Matches |
|---|---|---|
| `fingerprint` | the source's own identity | the same alert or error again |
| `group_key` | curated storm rules (`GROUP_RULES`) and the low-signal rollup (`low-signal:<project>`) | members of one incident / one rollup bucket |
| `norm_key` (`v1:`) | the message with volatile parts masked: run ids, timestamps, UUIDs, hex ids, paths, dollar amounts, numbers of 4+ digits, `[n]` counters | the same bug under a new fingerprint |
| `alert_key` (`a2:`) | repo + source + alert name with counters/measurements masked | the same alert, coarsest; **open issues only** |

#### The lookup: `filing.ledger_lookup`

1. Exact `fingerprint` → that row.
2. `group_key` → newest row.
3. `norm_key` → the newest row **whose issue is open and is not a rollup bucket**. If none is open, the newest row (reopen / regression path) (fix `1282374`).
4. `alert_key` → the newest row whose issue is open.

#### The filing decision: `filing.file_or_update`

| Prior match | Fleet does |
|---|---|
| issue has label `triage-fleet/muted` and the match is exact (fingerprint/group) | nothing, forever |
| muted, but the match is fuzzy (norm/alert key) | ignores the mute and files fresh: a fuzzy match must never bury a different bug |
| issue closed **as a duplicate** | follows GitHub's `duplicateOf` (up to 3 hops) to the canonical issue, then applies the rows below to *that* issue; the ledger row is remapped to it |
| issue **open** | one comment per day: `Recurred <date>… (matched on <key>)` |
| issue closed **< 7 days** (`REOPEN_WINDOW_DAYS`) | reopens it with a comment |
| issue closed **≥ 7 days** | files a new issue linking the old one (regression) |
| no match | files a new issue, labelled `triage-fleet/filed` |
| prior is a low-signal rollup, signal is no longer low-signal | promotes: a new issue of its own |

**Low-signal:** a GlitchTip error with ≤ 1 event, 0 users and no code location. It goes to a per-project rollup issue (`[low-signal] aggregate — <project>`) as one line, instead of an issue of its own.

**GitHub state is read at filing time** (`issue_state`): the operator's close, label or comment *is* the acknowledgement. The local ledger never overrides GitHub.

**Retired rows:** `glitchtip-retired:<SLUG>-<n>`. These belong to a deleted GlitchTip project. A project recreated under the same slug restarts its short ids, and its new errors would match the dead project's rows (2026-10-01: a rate limit reopened an unrelated issue). `filing.py --retire-glitchtip-project SLUG BEFORE` moves them out of the matching namespace. The runbook has the procedure.

### Other state files

| File | Purpose |
|---|---|
| `results/.deferred.json` | per-signal count of transient triager failures (#11); absent when nothing is deferred |
| `results/.stale_last_run` | UTC day of the last stale pass |
| `results/.inbox_seen` | operator-inbox bookkeeping |
| `results/.last_cycle_spend` | cycle cost in USD, read by fleetd's budget guard |
| `queue/` | drafts that were not sent (shadow stage, cleanup dispositions) |

## The operator's interface: GitHub labels

| Label | Set by | Meaning |
|---|---|---|
| `triage-fleet/filed` | fleet | the fleet filed this issue |
| `triage-fleet/escalated` | fleet | the fleet needs a human answer |
| `triage-fleet/actionable` | fleet | machine-fixable candidate for Fleet 1 |
| `triage-fleet/low-signal` | fleet | a rollup bucket issue |
| `triage-fleet/stale-candidate` | fleet | the signal has been quiet 7 days with no human comment ("looks resolved?") |
| `triage-fleet/substrate` | fleet | the fleet's own infrastructure (e.g. triager down) |
| `triage-fleet/routed:bugfix` | operator | dispatch to Fleet 1 |
| `triage-fleet/muted` | operator | never act on this signal again (exact matches only) |

Closing an issue is the operator's dismissal; a recurrence inside 7 days reopens it. A comment from the operator is reporter input on the next triage.

## Why it is built this way

These rules came from incidents. Keep them unless the evidence changes.

1. **Deterministic before the LLM.** Dedup, routing, operational states, recurrence and low-signal are code, not prompts. They are cheap, testable, and they don't drift. The LLM only investigates and decides file vs. escalate.
2. **Fail closed, in one place.** When the triager is down, the fleet files one aggregate issue, not one per signal. The August 2026 flood turned a 401 into about 90 escalation issues.
3. **GitHub is the source of truth for state.** The fleet reads issue state at filing time and never acts on a cached copy.
4. **A fuzzy match never inherits a mute.** Muting is exact (fingerprint / group key). Otherwise one mute could silence a different bug forever.
5. **Prefer the bug's open issue, through the precise key only.** Norm-key matches prefer an open issue; alert-key matches don't override them. Tried on 2026-10-02: the alert key's moves mostly re-derived GitHub's duplicate links, and where they differed the link was more exact (#2037 → #1958 by alert key; its `duplicateOf` is #2040). Explicit links beat inferred ones, so duplicates are followed directly (rule 6).
6. **A duplicate is not the bug's issue; its canonical is.** When the operator closes an issue as a duplicate, a recurrence goes to the issue it duplicates. The link comes from GitHub (GraphQL `ClosedEvent.duplicateOf`; REST only carries the reason). Before this, one disk alert reopened four duplicates of #43.
7. **A rollup bucket is not a bug's issue.** Never route a specific bug's recurrence to `[low-signal] aggregate`.
8. **One condition, one alert.** Fan-out has to be fixed at the source rule, not deduplicated afterwards. Example: per-mountpoint disk alerts gave six issues for one disk; the fix groups by disk (`0702aee`).
9. **Every behaviour change is proven on real history before it ships.** The runbook's improvement loop requires a replay against a frozen corpus, a baseline-reproduces-history check, and a mutation check.

## Known gaps (as of 2026-10-02)

| Gap | Effect | Status |
|---|---|---|
| **Warnings never reach the fleet** | systematic warnings (e.g. speaker-attribution loss in 26 of 28 runs on 2026-10-01) are invisible to it | by design today: the sources are GlitchTip errors and Grafana alerts |
| A one-event GlitchTip error with no culprit is **low-signal by rule** | a real bug can be buried as one line in the rollup (2026-10-01: `[Errno 36] File name too long` → podcast_scraper #1871) | open |
| GlitchTip project **recreated under the same slug** | fingerprint collisions with retired rows | procedure in the runbook. A permanent fix would key GlitchTip fingerprints on the project id. |
| `eval_recurrence_replay.py` takes about 6 min on the mini | every deploy is that much slower | accepted for now (operator call 2026-10-01) |
| Homelab filesystem series are **pushed twice** to VictoriaMetrics | double storage; hidden by `min by` in rules | not investigated |
| `~/signal-fleet/fleet.env` | a stale duplicate of `fleet-gateway.env`; fleetd does not load it | delete when convenient |
