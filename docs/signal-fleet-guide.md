# Triage fleet (Fleet 2) — how it works and why

This guide explains the triage fleet (`signal-fleet`, Fleet 2): its parts, one signal's path through it, the two ledgers that hold its memory, and the reasoning behind each rule. It is the "why" for the next agent who has to change it.

- **How to install, run, review and improve it:** [Triage fleet runbook](recipes/signal-fleet-runbook.md).
- **The full design history:** RFC-0003 and [`SIGNALS.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/signal-fleet/SIGNALS.md).
- **How this fleet fits with the others:** [Fleet architecture](fleet-architecture.md).

State as of 2026-10-17 (checked against the running system): live on the Mac mini at stage **`propose`**, code at `69f88f1` or later. It files, comments on and reopens GitHub issues in `chipi/podcast_scraper`, `chipi/orrery` and `chipi/agentic-ai-homelab`, and mirrors the operator's GitHub closes onto the GlitchTip issues it filed (the sync, below).

## What it is, and what it is not

The fleet watches production signals (Grafana alerts and GlitchTip errors) and decides, for each one, whether a human or another fleet needs to act. The result is a GitHub issue, a comment on an existing issue, or a recorded decision to do nothing.

It **never** touches production, never changes code, and never closes a GitHub issue. Closing is the operator's call (fleet-architecture invariant 6); the sync only copies that call onto GlitchTip. Fixing belongs to Fleet 1 (bug-fix) and Fleet 3 (remediation).

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
       ├─ 6. GitHub → GlitchTip sync (#100, SF_GLITCHTIP_SYNC=1): mirror the operator's closes
       └─ 7. spend file      cycle cost → fleetd's daily budget guard ($2/day)
```

| Part | Where | Role |
|---|---|---|
| `fleetd` | [`fleetd/`](https://github.com/chipi/agentic-ai-homelab/tree/main/fleetd), binary at `~/fleetd/fleetd` | runs each fleet's cycle on its interval. Owns the stage, timeout (process group killed on timeout), budget, STOP flag and its own metrics. |
| cycle code | [`signal-fleet/mvp/`](https://github.com/chipi/agentic-ai-homelab/tree/main/signal-fleet/mvp), run **from the git checkout** | `orchestrator.py` (cycle), `sources.py` (read Grafana/GlitchTip), `correlate.py` (probe evidence: logs, metrics, traces), `triage.py` (decide), `actions.py` (dispositions ledger), `filing.py` (GitHub + filed ledger), `glitchtip_sync.py` (GitHub → GlitchTip), `stale.py`, `inbox.py`, `observ.py` (metrics, Langfuse) |
| state | `~/signal-fleet/` on the host, never in git | `results/dispositions.tsv`, `results/filed.tsv`, small state files, `queue/`, `fleet-gateway.env` |
| LLM | the homelab LiteLLM gateway, model alias `fleet-triage-pro` | investigation and the file/escalate decision. Never dedup, never routing. |
| surfaces | Grafana "Fleet Workforce — Triage (Fleet 2)" (incl. the sync's panels), "Triage — Operator Inbox"; alerts `fleetd-cycle-failing`, `fleetd-silent`, `glitchtip-sync-failing`; Langfuse project "agents" | how the operator and the next agent see it |

The code is stateless between cycles. Everything the fleet "remembers" is in the two ledgers and the GitHub issues themselves.

## One signal's path

### 1. Normalize

`sources.to_signal` (Grafana) and `sources.to_error_signal` (GlitchTip) turn each item into a signal with two identities:

- **`fingerprint`** — the same problem across time. Grafana: the alert's label-set fingerprint. GlitchTip: `glitchtip:<SHORTID>`, e.g. `glitchtip:PODCAST-PIPELINE-5E`.
- **`occurrence_id`** — one episode of it: fingerprint + `startsAt` (Grafana) or `firstSeen` (GlitchTip). The cycle is idempotent on this key.
- **The host-wide OOM alert is split per container** (2026-10-27, `sources.to_signals` + `guards.oom_episodes`). "Kernel OOM killer fired" fires per host, so while evals-inspector was OOM-killed every ~5 min the alert never stopped, and player-api's kills (10-26 13:46, 10-27 07:13) produced no new occurrence. The fleet now reads the kernel's `oom-kill:` lines (VictoriaLogs), maps each docker cgroup to its container (cadvisor), and emits one signal per container: fingerprint `<alert>:oom:<container>`, occurrence = the container's kill *episode* (kills under 30 min apart; an episode that began with the firing is keyed on the firing's start), so a crash loop stays one occurrence and a later kill is a new one. A failed lookup keeps the host-wide signal. Replay: `eval_oom_edge_replay.py`.

Test and synthetic signals are suppressed at this stage.

### 2. Seen before?

`orchestrator.run_grafana` / `run_glitchtip`:

- **Same occurrence already decided:** skip. A GlitchTip error whose event count rose since its last triage gets a `recurrence` row: one per count change, not one per cycle (fix `b3c4c5f`). It is re-triaged in full only after `SF_RETRIAGE_HOURS` (24 h).
- **Exception — promote at once** (2026-10-17, `orchestrator._promote_now`): when the last decision was `file` but the low-signal gate folded the error into a rollup, its first recurrence re-triages immediately, so filing promotes it to its own issue. Before this, 6 fingerprints (12 count changes, incl. the fatal PLAYER-1I) stayed rollup lines for good.
- **A new Grafana firing of a known fingerprint inside 24 h:** a `recurrence` row, no new triage.

### 3. Triage: deterministic gates before the LLM

`triage.triage()`:

1. **Operational states → `dismiss`, no LLM** (`OPERATIONAL_MARKERS`):
    - cost cap;
    - provider budget / HTTP 402;
    - failed fallbacks;
    - upstream shared-pool rate limits (`upstream-rate-limit`: OpenRouter 429 with `limit_source=upstream_provider_shared_pool`, operator call on homelab #17).

    These are states, not bugs, and they hold even while the triager is down.

2. **Investigation by the LLM:** up to `SF_MAX_PROBES` (3) probes — logs, metrics, traces, source state, occurrence history — then one terminal decision. A GlitchTip error's trace is looked up by the OTel id the apps stamp as `tags.trace_id` (fix `06c07e0`; the SDK's own `contexts.trace.trace_id` never exists in VictoriaTraces). Each triage is **one Langfuse trace** (project "agents"): the fleet mints the trace id, and the gateway adds its costed generations to it as `triage-turn-N` (`e4e396f`). The decision:
    - `file`: a real problem; becomes an issue with `work_type` `bug` or `config-enhancement`;
    - `dismiss`: benign, **with independent probe evidence** (the intent gate). An **edge-5xx burst** is never dismissed when a container on the edge's host started or was OOM-killed within 10 min before to 5 min after it (`triage._edge_gate`, 2026-10-27): probes run after the restart look healthy because the container is back (the 10-26 13:46:30 burst was dismissed exactly so). It escalates naming the container; a failed lookup escalates too;
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

### 5. Mirror onto GlitchTip: the sync (#100)

GitHub is where the operator decides; GlitchTip used to never hear about it (2026-10-15: 312 of 363 filed GitHub issues were closed, their GlitchTip issues still unresolved). At the end of each cycle `glitchtip_sync.run` reads, for every GlitchTip fingerprint in the filed ledger, its GitHub issue and copies the decision:

| GitHub | GlitchTip |
|---|---|
| closed as fixed | resolved "in next release": a later recurrence counts as a regression |
| closed as not planned | resolved |
| closed as duplicate of #M | follows #M: merged into #M's GlitchTip issue only if it is the **same error** (same project, same fleet skeleton), then takes #M's state; otherwise resolved when #M is closed |
| open / reopened | untouched |

Every mapped issue gets one `Tracked in GitHub: <url>` comment. A row whose short id was reused by a newer issue is skipped (`reused_short_id`). Nothing is lost by resolving: a recurrence reopens the GlitchTip issue, triage runs before the sync in the same cycle, and filing reopens (< 7 days) or files a regression.

- **Switch:** `SF_GLITCHTIP_SYNC=1` in `fleet-gateway.env`, token `GLITCHTIP_WRITE_TOKEN` (`event:write`). Writes only when the cycle writes (not in `shadow`).
- **o11y:** metric `signal_fleet_glitchtip_sync{kind=mapped|merged|resolved|commented|errors}` every run; alert `glitchtip-sync-failing` (errors in every run for 25 min); one VictoriaLogs line per write, `{fleet="triage", event="glitchtip_sync"}` (the audit trail).
- **By hand:** `python3 glitchtip_sync.py` is a dry run (counts and samples); `--apply` writes.

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

**Low-signal:** a GlitchTip error with ≤ 1 event, 0 users and no code location. It goes to a per-project rollup issue (`[low-signal] aggregate — <project>`) as one line, instead of an issue of its own. A **fatal** event (a crash, a watchdog kill) is never low-signal: it gets its own issue on its first hit (2026-10-17: PLAYER-I, PLAYER-L and PLAYER-1I had been buried in rollup #2000).

**GitHub state is read at filing time** (`issue_state`): the operator's close, label or comment *is* the acknowledgement. The local ledger never overrides GitHub.

**Retired rows:** `glitchtip-retired:<SLUG>-<n>`. These belong to a deleted GlitchTip project. A project recreated under the same slug restarts its short ids, and its new errors would match the dead project's rows (2026-10-01: a rate limit reopened an unrelated issue). `filing.py --retire-glitchtip-project SLUG BEFORE` moves them out of the matching namespace. The runbook has the procedure.

**Reused short ids are ignored automatically** (2026-10-17): a ledger row filed *before* the GlitchTip issue now holding its short id was first seen belongs to another, older issue. Filing (`ledger_lookup`, GlitchTip signals only) and the GitHub → GlitchTip sync both ignore such a row (`reused_short_id`). Before this, a recreated `orrery-dev` gave the probe ORRERY-DEV-1 the August decision on orrery#429, and the sync resolved it; 7 rows were affected. Retiring rows is still tidy, but no longer required.

### Other state files

| File | Purpose |
|---|---|
| `results/.deferred.json` | per-signal count of transient triager failures (#11); absent when nothing is deferred |
| `results/.stale_last_run` | UTC day of the last stale pass |
| `results/.inbox_seen` | operator-inbox bookkeeping |
| `results/.last_cycle_spend` | cycle cost in USD, read by fleetd's budget guard |
| `results/probes/` | per-decision capture (`capture.py`), **off unless `SF_CAPTURE_PROBES=1`** in `fleet-gateway.env`: one JSON per decision (mode 600) with the signal, every probe answer the model got (raw and the trimmed text it read) and, with `SF_CAPTURE_EAGER=1` (default), the rest of the probe menu at default args, so `triage.investigate(signal, probe_table=item["probes"])` replays the decision exactly. About 12 KB each. Real production data: keep on the host, `scrub.py` before sharing |
| `queue/` | proposals the fleet may not act on alone (`cleanup`, `config-enhancement`; everything in `shadow`) as `*.json`; handled ones renamed `.filed` / `.resolved`. The operator triages them with the `triage-fleet-review` skill's `proposals.py` (54 had piled up by 2026-10-17); `queue/archive/` holds batches set aside |

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
10. **A GlitchTip short id is not an identity on its own.** A recreated project restarts the counter, so a ledger row counts only if it was filed after the issue now holding that id was first seen. A manual retire step was forgotten for four projects; the rule needs no step.
11. **A crash is never a rollup line.** Fatal events skip the low-signal gate, and a signal the fleet decided to file is promoted on its first recurrence. The rollup exists to quiet one-off noise, not to hold bugs the fleet already recognised.
12. **GitHub decides, GlitchTip follows.** The sync copies the operator's call and never makes one; a merge needs the same error, not just a duplicate link, because an umbrella issue can hold several errors.

## Known gaps (as of 2026-10-17)

| Gap | Effect | Status |
|---|---|---|
| **Warnings never reach the fleet** | systematic warnings (e.g. speaker-attribution loss in 26 of 28 runs on 2026-10-01) are invisible to it | by design today: the sources are GlitchTip errors and Grafana alerts |
| A one-event GlitchTip error with no culprit is **low-signal by rule** | a real bug can be buried as one line in the rollup (2026-10-01: `[Errno 36] File name too long` → podcast_scraper #1871) | open for non-fatal errors; fatal events get their own issue since 2026-10-17 |
| GlitchTip project **recreated under the same slug** | fingerprint collisions with retired rows | fixed 2026-10-17: a row filed before its issue's first event is ignored (`reused_short_id`). Rows keep their short-id fingerprint. |
| **One cause, several GlitchTip issues** | a provider-auth failure is logged by each layer it passes through: 4 issues in 31 minutes on 2026-10-16 | fixed for provider auth 2026-10-17 (`PROJECT_GROUP_RULES`, one group per project). Other cause classes still fan out until a rule names them. |
| GlitchTip pass reads the **10 most recently seen** issues | a recurrence missed because more than 10 issues had events in one cycle would be re-resolved by the sync before triage sees it | not seen: the busiest 10-minute window in the 14 days to 2026-10-17 had 6 issues |
| **Cycle output is not kept** | fleetd logs one summary line per cycle (`fleetd.log`, VictoriaLogs `service:fleetd`); what a cycle printed is gone | the sync's writes are in VictoriaLogs; for anything else, rerun the step by hand |
| `.deferred.json` entries **never expire** | an occurrence that deferred once and never came back keeps a count of 1 (two from 2026-10-08) | harmless; pruning needs a last-deferred time per entry, which the file does not store |
| `eval_recurrence_replay.py` takes about 6 min on the mini | every deploy is that much slower | accepted for now (operator call 2026-10-01) |
| Homelab filesystem series are **pushed twice** to VictoriaMetrics | double storage; hidden by `min by` in rules | not investigated |
| `~/signal-fleet/fleet.env` | a stale duplicate of `fleet-gateway.env`; fleetd does not load it | delete when convenient |
| **No way to mute a fragmenting bug** | a bug whose fingerprint keeps changing files new issues; `triage-fleet/muted` only silences one fingerprint, and fuzzy matches never inherit a mute | needs a `muted-class` label (2026-08-28 design, never built) |
| **Chained-exception ordering is spec-only** | the cause-chain handling (2026-08-27 enhancement #5) was built against the spec; no real chained exception has passed through it yet | re-check when the first real chain appears |
