# RFC-0005 — Fleet 3 v1: `remediation-fleet`, unattended recovery of prod after a reboot

**Status:** Proposed (2026-09-30)
**Runs on:** the `homelab` Mac mini, as one fleet under `fleetd` (RFC-0004).
**Acts on:** the podcast_scraper production VPS (`prod-podcast`), only through one GitHub Actions
workflow in the public `chipi/podcast_scraper` repo.
**Relates to:** RFC-0003 (Fleet 2 hands remediation to Fleet 3), RFC-0004 (`fleetd`),
[fleet architecture](../fleet-architecture.md) (Fleet 3 = the config/runtime lever).
**Relates to (podcast_scraper):** ADR-115 (prod secrets live in RAM only),
`docs/guides/DEPLOY_GOTCHAS.md` §1 / §1b, `.github/workflows/restage-prod-secrets.yml`,
`scripts/ops/restage_prod_recreate.sh`, and — built for this RFC in `b9c07ff8f` —
`scripts/ops/prod_recovery_check.sh` and `scripts/ops/prod_health_lib.sh`.

This is the first Fleet 3 member. It owns exactly one lever — the first entry in the
[prod-lever registry](../fleet-architecture.md#prod-levers-how-a-fleet-may-act-on-prod) that
invariant 6 was amended to create (2026-09-30). Nothing in it is an LLM.

## Motivation

### The incident (2026-09-30)

All times UTC.

| time | what happened |
| --- | --- |
| 01:35 → 02:17 | Last jobs of an overnight corpus-repair queue ran and finished. |
| 03:26 | The VPS went down hard. The journal just stops, with no clean shutdown. |
| 03:36 / 03:42 | Grafana fired `prod-podcast dark (no samples 10m)` and `prod logs dark (no lines 15m)`. Detection worked. |
| 04:03 | The VPS came back up. |
| 04:03 → 06:00 | The public player and operator APIs were **down for ~2 hours**. Nobody was awake. |
| ~06:00 | Recovered by hand, which needed the operator's approval of a prod deployment gate. |

What the box looked like after the reboot:

- `player-api-1` and `operator-api-1` were `Exited (127)`, with **no application logs**. `runc` failed
  the bind mount before any process started:
  `open /dev/shm/player-secrets/podcast_sentry_dsn_api: no such file or directory`.
- `player-learning-app-1` and `operator-viewer-1` (nginx) were crash-looping with
  `host not found in upstream "api"`, one layer downstream of the dead APIs.
- `compose-api-1` (the control plane) was **Up and healthy, with no provider keys**.
  `podcast-scraper.service` runs `docker compose up` at boot without the secrets overlay, so it
  recreated the container with no `/run/secrets` at all. Any pipeline job started from it would have
  run without model keys.
- The host log shipper (`alloy`) was not started by Docker at boot, although it is set to
  `unless-stopped`. Prod metrics and logs were therefore dark for the whole outage. **Unexplained** —
  see Open questions.

### Why a reboot breaks prod

ADR-115 keeps every prod runtime secret in `/dev/shm` — RAM, never disk. That property is deliberate
and is **not** up for change here. Its consequence: after any reboot the secrets are gone, and they
exist again only when GitHub Actions stages them from GitHub's secret store. Before this RFC the only
way to trigger that was a human dispatching `restage-prod-secrets.yml` and approving its `prod`
environment gate. At 4 a.m. that means the product is down until someone wakes up.

### Already fixed on the prod side (podcast_scraper, 2026-09-30)

These are **prerequisites this RFC builds on**, not part of it:

- **Secrets no longer vanish on logout.** logind's default `RemoveIPC=yes` deleted the `deploy`
  user's `/dev/shm` files at the end of every deploy SSH session. Running containers kept their
  copies, but any later restart failed exactly like a reboot. `RemoveIPC=no` is now live on prod
  (`/etc/systemd/logind.conf.d/10-keep-deploy-shm.conf`) and in `infra/cloud-init/prod.user-data`.
  The secrets now last until the next reboot.
- **The recovery workflow actually recovers** (commit `f68b4388f`). Its first real run went green
  while recovering one surface of three:
  - `printf %q` escaped the surface list, so `podcast` and `operator` were skipped as "unknown";
  - the image tag was read off a sibling container, which moved `player-api` to an untested image;
  - the keyless control plane was never recreated, because it looked healthy.

  Each of these is fixed and covered by `tests/unit/scripts/ops/test_restage_prod_recreate.py`.

So after those fixes, one call to `restage-prod-secrets.yml` (`surfaces: all`, `recreate: true`)
is expected to fully recover prod after a reboot. **What is missing is something that makes that
call, and approves it, without a human.**

**The fixed workflow has not run in production yet.** Its only run ever is
[`36675886130`](https://github.com/chipi/podcast_scraper/actions/runs/36675886130) (05:58 UTC,
head `9949699df`) — the partially-successful run above, *before* the fix. `f68b4388f` landed at
06:38. "Fully recovers" therefore rests on the unit tests, not on a real reboot. The class-A drill
(deleting one secret dir) does not close that gap either; the class-B runs in the propose stage do —
on the drill box if it can reproduce the failure, then a controlled prod reboot (see Rollout, Stage C2).

## Proposal

### Scope — one lever, forever for v1

| in scope | out of scope (v1) |
| --- | --- |
| Detect "prod is up but needs its secrets restaged / containers recreated" | Box unreachable (VPS down): nothing to do until it is back; the existing "prod dark" alert covers it |
| Dispatch `restage-prod-secrets.yml` with fixed inputs | Any deploy, image change, rollback |
| Approve the `lever-restage` deployment of **that run only**, as the bot identity (see "The lever environment") | Approving anything else, ever — and the bot is a reviewer nowhere else, so GitHub refuses it too |
| Dispatch the read-only `prod-ops-health.yml` to verify (never approved — it has no gate) | Dispatching any other workflow |
| Verify the outcome through observability, and report | Restarting `alloy`, fixing the boot unit, any host change |

The fleet never holds a prod secret, never SSHes to prod with write capability, and never changes
code or config.

### Fit with the fleet architecture — a registered lever, and one departure

**1. Invariant 6 — amended into a lever model; this is lever #1.** Invariant 6 used to read *"The
operator gates irreversibles: merges, deletes, prod state. Permanently, not provisionally."* This
fleet approves a prod deployment without the operator — the whole point of the RFC — so it could not
be designed around. Rather than a one-off exception for this RFC, the invariant was amended on
2026-09-30 (decided by the operator) into a rule that future prod-acting fleets can use too:

> The operator gates every irreversible and every change to prod — per run, or by approving a named
> lever. [...] A lever not in the registry does not exist, and the never-list can never be a lever.

The full rule — the three tiers of prod action (never a lever / lever-eligible / everything else),
the lever contract, containment outside the fleet, and the registry — lives in
[fleet-architecture.md → Prod levers](../fleet-architecture.md#prod-levers-how-a-fleet-may-act-on-prod).
Why it is shaped that way: more prod actions will appear as prod runs (adding capacity under load is
the obvious next one), and a pile of exceptions stops being an exception. So the bar is on
**admission** — a never-list, a contract, GitHub-enforced containment — not on the count.

**Why this action is lever-eligible.** It returns prod to a **known prior state**: the secrets GitHub
already holds, onto the image each container was already running (`f68b4388f` reads the tag off the
container itself). It deploys nothing new, changes no code or config, and its inputs are fixed. It is
on no part of the never-list.

**The lever contract, filled in:**

| field | this lever |
| --- | --- |
| trigger | `prod_recovery_check/v1` over a forced-command SSH key: `needs_recovery=true`, re-derived by the fleet from the fields (see "The signal") |
| preconditions | stage allows it; not latched; outside cooldown; under the caps; no prod-mutating workflow queued or running (step 1) |
| action | `restage-prod-secrets.yml` on `main`, inputs fixed: `confirm=RESTAGE_SECRETS`, `surfaces=all`, `recreate=true`, plus a `request_id` |
| blast radius | writes the secrets GitHub already holds into prod's `/dev/shm`, and recreates the containers the shared rules library reports broken, on their current image. Touches no code, config, data or image version |
| verify | layered outcome verify, step 6: structure, user-facing probes, secret-dependent `prod-ops-health` checks, observability |
| on failure | latch and page (critical); never retry past a guard |
| rate cap | 15 min cooldown; 3 failed attempts per 24 h → latch; a cap on successes is Open question 9 |
| environment + identity | `lever-restage`, approved by the bot machine account, which is a reviewer on no other environment (see "The lever environment") |
| stages | shadow → propose → live, classes A and B promoted separately on `reference-remediation/` (see "Eval", "Rollout") |
| owner | this RFC |

**2. It is not the Fleet 3 pipeline the architecture sketched.** The architecture's Fleet 3 row
reads `config-enhancement` label → lever menu → verify-after-apply → **auto-rollback**. This v1:

- is triggered by a direct check on prod, **not** by the `config-enhancement` label from Fleet 2 —
  there is no typed-label seam yet, so Fleet 2 and Fleet 3 do not compose in v1;
- has a menu of exactly one lever;
- has **no rollback**. A restage cannot meaningfully be undone, and it only restores what was there.
  "Verify-after-apply" is kept (step 6); a failed verify latches instead of rolling back.

Both are deliberate for v1. The Fleet 3 row in `fleet-architecture.md` now points at this RFC and
the lever registry.

**Everything else follows the existing fleets.** The goal for this first Fleet 3 member is to be built
and run exactly like Fleets 1 and 2, so a reviewer can check it line by line:

| invariant / pattern | Fleets 1 and 2 | this RFC |
| --- | --- | --- |
| 1 · no LLM decides control flow | deterministic orchestrators; models are leaf calls | no model at all |
| 2 · invention cannot reach action | every action cites evidence (intent gate, dismissal evidence) | every action cites its check JSON, stored in the ledger and referenced from the approval comment |
| 3 · asking beats guessing | needs-info / escalate are first-class terminals | latch + alert is the terminal; the fleet never retries its way past a guard |
| 4 · autonomy earned per class on frozen replay | Fleet 2's bar on `reference-hardening/` | `eval_decisions.py` over `reference-remediation/`; classes A and B promoted separately (see "Eval") |
| 5 · fail safe and loud, append-only ledger | `dispositions.tsv` stamped with model + prompt sha | `actions.tsv` stamped with code sha + check schema (see "Ledger") |
| 6 · operator gates irreversibles and prod changes | merges, deletes, prod state — per run | the operator approved **the lever** (this RFC), not each run; lever #1 in the registry, contract above, contained by `lever-restage` + the bot |
| 7 · never triage its own substrate | `meta: "true"` on fleet-health rules | same (see Reporting) |
| supervisor | a `fleetd` block, Python core (ADR-0008) | same |
| code vs state | code in the checkout; state + secrets in `~/signal-fleet/`, `~/.bugfix-fleet/` | code in the checkout; state + secrets in `~/remediation-fleet/` |
| deploy | `signal-fleet/deploy/deploy.sh`: pull, run the gates, auto-rollback | `remediation-fleet/deploy/deploy.sh`, same shape |
| stage ladder | shadow → propose → live, operator-gated, per class | same (see Rollout) |
| metrics | `signal_fleet_*`, `bugfix_fleet_*` | `remediation_fleet_*` |
| operator surfaces | home page fleet rows; Fleet Workforce dashboards | a Remediation row and dashboard (Gate to MVP) |

### Placement — same shape as the existing fleets

- **Directory:** `remediation-fleet/` at the repo root, a sibling of `signal-fleet/` and
  `bugfix-fleet/`.
- **Language:** stdlib-only Python 3 (`/usr/bin/python3`, 3.9.6 on the mini), like the Fleet 2 core
  and `infra/ci-ops-poller/poll.py`, which already calls the GitHub Actions API. No dependencies.
  This is ADR-0008's split: `fleetd` (Go) supervises, the fleet's logic stays Python.
- **Supervisor:** a block in `fleetd.json`. `fleetd` gives us the scheduler, the STOP-file kill
  switch, the no-overlap rule, the cycle timeout, the `stage` ladder and its own
  `fleetd_cycle{fleet=…}` metric. It does **not** give a per-fleet dead-man (see Reporting). **No new
  LaunchDaemon plist** and no change to `infra/mini-setup.sh`.
- **Code vs state — the Fleet 1/2 split.** Code runs from the git checkout; state and secrets live
  outside it, in `~/remediation-fleet/`, never inside the repo directory. Fleet 2 does exactly this
  (`~/signal-fleet/{results,queue,logs}` + its `.env`, all paths absolute and env-overridable as
  `SF_*`); Fleet 1 keeps its ledger in `~/.bugfix-fleet/`. Deploy is then a `git pull` that cannot
  touch state or credentials. Paths are overridable as `RF_*` so tests run against a temp dir.

```text
remediation-fleet/                   (in the repo — code only)
  README.md            "Current state — read first", install, drill, how to stop it
  EVAL.md              the decision eval and its bar (see "Eval")
  .env.example         names only (see "Credentials")
  cycle.py             one cycle: check → decide → act → verify → report (exit code = outcome)
  decide.py            pure decision function: check JSON + ledger state → action; no I/O
  eval_decisions.py    frozen-replay eval over reference-remediation/ (deterministic, no network)
  test_units.py        unit tests; GitHub + SSH faked
  deploy/deploy.sh     git pull + run the gates + auto-rollback if red (as signal-fleet/deploy/)
  reference-remediation/
    cases.json         versioned check outputs, starting with the 2026-09-30 incident

~/remediation-fleet/                 (on the mini — state + secrets, gitignored by location)
  .env                 0600; see "Credentials"
  known_hosts          pinned prod host key
  STOP                 kill switch (fleetd stop_flag)
  results/actions.tsv  append-only decision ledger (see "Ledger")
  results/state.json   cooldown, attempt counters, latch — derived, rebuildable from the ledger
```

`fleetd.json` block:

```json
{
  "name": "remediation",
  "enabled": true,
  "interval": "5m",
  "cycle_cmd": "/usr/bin/python3 cycle.py",
  "workdir": "/Users/markodragoljevic/agentic-ai-homelab/remediation-fleet",
  "env_file": "/Users/markodragoljevic/remediation-fleet/.env",
  "stop_flag": "/Users/markodragoljevic/remediation-fleet/STOP",
  "budget_day_usd": 0,
  "stage": "shadow",
  "cycle_timeout": "40m"
}
```

(Same shape as the live triage block in `~/fleetd/fleetd.json`: `workdir` is the checkout,
`env_file` and `stop_flag` sit in the fleet's state directory.)

`cycle_timeout` must exceed the longest legitimate cycle: dispatch and approve (≈ 1 min) + wait for
the restage (≤ 25 min, see step 5) + verify (step 6: the SSH check, up to 3 min of user-facing
probes, and a `prod-ops-health` run, measured at 33–59 s but allowed 5 min with queueing) ≈ 35 min.
The 2026-09-30 restage job itself took 1m30s (05:59:12 → 06:00:42), but its `timeout-minutes` is 20
and a cold image pull is slow. 40m covers the worst case with margin. `fleetd` never overlaps cycles, so a long cycle simply skips ticks.

`budget_day_usd: 0` disables the budget guard (`fleetd` only enforces it when `> 0`); this fleet
spends nothing. `fleetd` passes the stage to the cycle as the environment variable `FLEETD_STAGE` —
that, not a field in `.env`, is what `cycle.py` reads to decide between `shadow` and `live`.

### The signal — a read-only check on prod, over SSH

**Why not metrics.** In the incident, prod metrics were dark for the whole outage because `alloy`
did not start. A metrics-based trigger would have seen "no data" — indistinguishable from "box
down". The check has to look at the box directly.

**How.** A new read-only script in podcast_scraper, `scripts/ops/prod_recovery_check.sh`, runs on
prod and prints one JSON object. The fleet reaches it with a **dedicated SSH key whose
`authorized_keys` entry pins it to that one command**:

```text
restrict,command="/srv/podcast-scraper/scripts/ops/prod_recovery_check.sh" ssh-ed25519 AAAA… remediation-fleet
```

`restrict` disables port, agent and X11 forwarding and the pty. `command=` ignores whatever the
client asks to run. So the key can do nothing but produce the check's output. It is installed for
the `deploy` user (already in the `docker` group, so it can run `docker ps` / `docker inspect`
without sudo). The entry lives in `infra/cloud-init/prod.user-data` and is applied to the live box
once.

**Network:** already allowed. The tailnet policy grants `tag:homelab-host → tag:prod:22`.

**What the check reports** — built as `scripts/ops/prod_recovery_check.sh` in podcast_scraper
`b9c07ff8f` (2026-09-30), schema `prod_recovery_check/v1`, one JSON line, exit 0 whenever the check
itself ran. All read-only:

| field | how | sets `needs_recovery` when |
| --- | --- | --- |
| `secrets_dirs` | count of **non-empty** files in `/dev/shm/{podcast,operator,player}-secrets` (`prod_secret_file_count`) | any count is 0 — dir missing or empty |
| `down_containers` | `prod_broken_containers`: status `Exited*` / `Restarting*` / `Created*` in the `compose`, `operator`, `player` projects, **plus** `compose-api-1` when it is Up but has no `/run/secrets/*` mount | non-empty |
| `keyless_control_plane` | that `compose` `api` container is Up with no secrets mounts (`prod_has_secret_mounts`) | true (it is also listed in `down_containers`) |
| `boot_time` | `/proc/stat` `btime` | never — informational (lets the fleet say "rebooted at …") |
| `alloy_running` | `docker ps --filter name=^alloy$ --filter status=running` | **never** — a restage does not start `alloy`, so it must not trigger one |

There is **no** `deploy_in_progress` field: whether a deploy is running is a GitHub fact, and the
guard for it stays on the GitHub side (the pre-flight check, step 1).

Real output from prod on the morning of 2026-09-30 (read-only run):

```json
{"schema":"prod_recovery_check/v1","boot_time":1790740976,"secrets_dirs":{"podcast":0,"operator":0,"player":0},"down_containers":[],"keyless_control_plane":false,"alloy_running":true,"needs_recovery":true}
```

The secret dirs had been deleted at 06:14 UTC — by logind's `RemoveIPC`, before `RemoveIPC=no` was
applied — while every container kept running on its mounted copies. Nothing was down, yet any restart
would have failed. That is exactly **class A** (see "Eval"), caught by the check before it could turn
into an outage; the next deploy restages the dirs. It is also the first real fixture for the eval.

For comparison, the 2026-09-30 reboot itself would have read (reconstructed from the incident facts,
not captured — the check did not exist yet):

```json
{"schema":"prod_recovery_check/v1","boot_time":1790740976,"secrets_dirs":{"podcast":0,"operator":0,"player":0},"down_containers":["compose-api-1","operator-api-1","operator-viewer-1","player-api-1","player-learning-app-1"],"keyless_control_plane":true,"alloy_running":false,"needs_recovery":true}
```

**Detection and action cannot disagree — built, and tested.** Both `prod_recovery_check.sh` (the
fleet's signal) and `restage_prod_recreate.sh` (the recovery) source one library,
`scripts/ops/prod_health_lib.sh`, instead of each carrying its own copy of the rules. A parity test,
`test_the_check_reports_exactly_what_the_recovery_recreates` in
`tests/unit/scripts/ops/test_prod_recovery_check.py`, runs both against the same fake box and asserts
that `down_containers` equals the set of containers the recovery recreates. The fleet still re-checks
`needs_recovery` independently from the fields and refuses to act if the two differ.

**Where the script lives on prod.** The forced command runs
`/srv/podcast-scraper/scripts/ops/prod_recovery_check.sh`. `/srv/podcast-scraper` is a git checkout,
owned by `deploy`, that the control-plane deploy resets to the deployed sha — so the script exists on
the box only **after a deploy that includes `b9c07ff8f`**. Until then the key would run a missing file.

**If SSH fails** (timeout, refused, host key mismatch): the fleet records `prod_reachable=0` and does
nothing. A host-key **mismatch** is a hard error (alert, latch), never auto-accepted — a rebuilt VPS
gets a new host key, and accepting it is an operator decision.

### The action — dispatch, find, approve exactly one run

1. **Pre-flight guards** (any failure → do nothing this cycle, report why):
   - the stage allows it: in `shadow` the fleet logs "would act" and stops here; in `propose`, and in
     `live` for a class not listed in `RF_LIVE_CLASSES`, it dispatches (step 2) but never approves
     (step 4 is skipped) and still waits and verifies once the operator approves;
   - not latched, not inside the cooldown, under the daily cap (see Guardrails);
   - no run of `deploy-all-prod.yml`, `deploy-prod.yml`, `deploy-player.yml`,
     `deploy-operator.yml` or `restage-prod-secrets.yml` is `queued` / `in_progress` / `waiting`.
     A deploy that is running will restage anyway.

     **Until the single concurrency group lands, this guard is the only thing preventing a restage
     from racing a deploy.** Only
     `deploy-prod.yml` shares the restage's `deploy-prod` concurrency group. The others each have
     their own — `deploy-all-prod`, `deploy-player`, `deploy-operator` (checked 2026-09-30) — and
     `deploy-all-prod` calls the player and operator deploys as reusable workflows. So a restage
     dispatched during a player or operator deploy would **not** queue behind it; both would act on
     the box at once. The guard is also check-then-act: a deploy started between the check and the
     dispatch is not caught. Putting every prod-mutating workflow in one concurrency group closes both
     holes at the GitHub level — decided, and now a Gate-to-MVP prereq (Open question 2). The guard
     stays afterwards as belt-and-braces.
2. **Dispatch** `POST /repos/chipi/podcast_scraper/actions/workflows/restage-prod-secrets.yml/dispatches`
   with `ref: main`, inputs `confirm=RESTAGE_SECRETS`, `surfaces=all`, `recreate=true`,
   `request_id=<uuid4>`, and `return_run_details: true`.
3. **Find the run — by `request_id`, cross-checked by run id.** Built in podcast_scraper `b9c07ff8f`:
   the workflow has an optional `request_id` input and
   `run-name: Restage prod tmpfs secrets ${{ inputs.request_id }}` (empty for a human dispatch). The
   fleet polls `GET …/actions/workflows/restage-prod-secrets.yml/runs?event=workflow_dispatch&branch=main`
   (every 5 s, up to 2 min) for the run whose `display_title` contains its `request_id`. Not found →
   report and stop. It **never** guesses by time or picks "the newest run".

   Cross-check: since
   [2026-02-19](https://github.blog/changelog/2026-02-19-workflow-dispatch-api-now-returns-run-ids/)
   the dispatch endpoint can return `200` with `workflow_run_id` when `return_run_details: true` is
   sent (otherwise `204 No Content`). When the fleet gets an id back, it must equal the run found by
   `request_id`; a mismatch → do not approve, alert, latch. A `204` is not an error — the
   `request_id` lookup alone is enough. (GitHub's REST reference and changelog describe that opt-in
   slightly differently, which is why `request_id` is the primary mechanism, not the response.)
4. **Approve that run only.**
   - `GET …/actions/runs/{run_id}/pending_deployments`.
   - Approve only if **all** of these hold, re-read from `GET …/actions/runs/{run_id}` rather than
     trusted from the dispatch response:
     - `display_title` contains this cycle's `request_id`, and `run.id` equals the dispatch's
       `workflow_run_id` when one was returned;
     - `run.path == ".github/workflows/restage-prod-secrets.yml"`;
     - `run.head_branch == "main"` and `run.event == "workflow_dispatch"`;
     - exactly one pending environment, named `lever-restage`.
   - Then `POST …/actions/runs/{run_id}/pending_deployments` **with the bot's approval token** (never
     the dispatch token) and
     `{"environment_ids":[<id>],"state":"approved","comment":"remediation-fleet <request_id>: <check summary>"}`.
     GitHub records the approval as the bot account.
   - Any mismatch → do not approve, alert, latch. These checks are layer 1 of containment; GitHub
     refusing the bot anywhere but `lever-restage` is layer 3 (see "The lever environment").
5. **Wait** for the run to complete (poll every 15 s, up to 25 min). Record the conclusion and the
   run URL. The wait must exceed the job's own `timeout-minutes: 20`, because it also covers queueing
   and the time from dispatch to approval; a 20-minute wait could abandon a slow run that was about to
   succeed and count it as a failure.
6. **Verify that the product works — closing the loop through observability.** "The workflow went
   green" is not the outcome that matters; on 2026-09-30 a green run recovered one surface of three.
   The fleet proves recovery the way a user and the observability stack would see it, in layers, and
   only **all required layers green** counts as success:

   | layer | how | required? |
   | --- | --- | --- |
   | a. structure | re-run the SSH check: `needs_recovery=false` | yes |
   | b. user-facing | from the mini, `GET https://prod-podcast.tail6d0ed4.ts.net/api/health` → `200`, plus the player and operator surfaces' health endpoints (the exact URLs to be taken from the deploy workflows' own post-deploy probes — not yet identified here), retried for up to 3 min (the first request after a recreate took ~70 s on 2026-09-30). Reachable today: `tag:homelab-host → tag:prod:443` is granted, and the probe returned `200` on 2026-09-30. | yes |
   | c. secret-dependent paths | dispatch `prod-ops-health.yml` (no approval: its `prod-ops-health` environment has no protection rules by design), wait for it, then read the **fresh** `prod_ops_health_check{check=…}` from VictoriaMetrics — `last_run_timestamp` newer than the recovery. Its `gateway` check exercises the provider keys through the LLM gateway; `o11y_glitchtip` exercises the Sentry DSN. Those are exactly the paths a missing secret breaks. Runs took 33–59 s (12/12 green, 2026-09-18 → 29). | `gateway`, `o11y_glitchtip`: yes |
   | d. observability flowing | `o11y_metrics` / `o11y_logs` / `o11y_traces` from the same run, plus fresh `node_*{instance="prod-podcast"}` samples in VictoriaMetrics | reported, not required |

   Layer d is reported rather than required because it depends on `alloy`, which this lever does not
   fix (Open question 5). Failing it after a/b/c pass is a distinct outcome — **"product recovered,
   observability dark"** — recorded in the ledger and raised by `prod-alloy-down`, not counted as a
   failed attempt that would trigger a retry the retry cannot fix.

   Anything short of a + b + c green counts as a failed attempt → latch + critical alert, so the
   operator is woken exactly when automation did not work. **This is how the recreate path gets proven
   in production:** not only by a one-off drill, but on every real recovery, by the outcome, with a human
   paged the first time it does not hold (see Rollout, and Open question 3).

### Guardrails

| guard | value | why |
| --- | --- | --- |
| Allowlist | two workflow paths, one ref: `restage-prod-secrets.yml` (dispatch + approve its `lever-restage` run) and `prod-ops-health.yml` (dispatch only; nothing to approve). One environment ever approved: `lever-restage` | the dispatch token can do more than this (see Credentials); the code must not. Approval is additionally bounded by GitHub, not only by this code |
| Cooldown | 15 min between attempts | a restage takes ~2 min; a second try inside 15 min means the first did not work |
| Daily cap | 3 failed attempts per rolling 24 h → **latch** | a loop that keeps "fixing" is worse than an outage we know about |
| Latch | `state.json` `latched=true`; cleared only by the operator (`cycle.py --unlatch`) | autonomy is revocable and does not re-grant itself |
| Kill switch | `fleetd` STOP flag | the standard fleet off switch |
| Stages | `shadow` → `propose` → `live` per class | `shadow` detects and reports "would act"; `propose` dispatches but leaves the approval to the operator; `live` approves, one class at a time — the ladder every fleet climbs |
| No overlap | `fleetd` never runs two cycles at once | one attempt in flight, ever |
| No LLM | none | invariant 1 of the fleet architecture |

### Ledger — append-only, like the other fleets

Invariant 5 asks every fleet for an append-only ledger that stamps what decided each action. Fleet 2
writes `~/signal-fleet/results/dispositions.tsv` (one row per decision, stamped `model`,
`prompt_sha`, `gates`, `cycle_id`, `stage`); Fleet 1 keeps its ledger in `~/.bugfix-fleet/`. This
fleet writes `~/remediation-fleet/results/actions.tsv`, one row per cycle that did more than "all
fine":

`ts · cycle_id · stage · code_version · check_schema · class · decision · reason · gates ·
request_id · run_id · run_url · conclusion · verify_a · verify_b · verify_c · verify_d · outcome`

There is no model or prompt to stamp (no LLM), so `code_version` (the checkout's git sha) and
`check_schema` (`prod_recovery_check/v1`) take that role: they say which logic made the call. The
full check JSON is kept with the row — it is the evidence invariant 2 asks every action to cite, and
the approval comment on GitHub points back to it by `request_id`.

`results/state.json` (cooldown, counters, latch) is a **derived cache**, rebuildable from the ledger.
If they disagree, the ledger wins.

### Eval — autonomy earned on frozen replay

Invariant 4: *"Autonomy is earned per class on frozen replay (the eval bars), never granted per
fleet."* Fleet 2 earned its seat on `eval_hardening.py` over `reference-hardening/` — a versioned set
of real, scrubbed signals. This fleet does the same with its decision function:

- `reference-remediation/cases.json` holds versioned `prod_recovery_check` outputs, each labelled with
  the expected decision. *Incidents become fixtures*: case #1 is the **2026-09-30 reboot**,
  reconstructed from the facts in Motivation (class B); case #2 is the **real output captured on prod
  that morning** after `RemoveIPC` emptied the secret dirs with every container still up (class A — see
  "The signal"). The set must also cover: a healthy box; secrets missing but
  nothing down; containers down; keyless control plane only; `alloy` down only (must **not** act); a
  deploy in flight; SSH unreachable; a host-key mismatch; a check whose `needs_recovery` disagrees with
  its fields; and each "wrong run" shape the approval step must refuse.
- `eval_decisions.py` replays them through `decide.py` (pure, no I/O) and enforces the bar:
  **0 actions on any must-not-act case, every must-act case acted on, 0 approvals of a mismatched
  run.** One run suffices: the logic is deterministic, so Fleet 2's k≥3 (which exists to average out
  LLM variance) does not apply.
- `deploy/deploy.sh` runs `eval_decisions.py` and `test_units.py` on every deploy and rolls the
  checkout back if either is red — the same gate-then-rollback shape as `signal-fleet/deploy/deploy.sh`.
- Every real incident the fleet sees (or misses) becomes a new case before the logic changes.

**Classes.** Autonomy is promoted per class, not for the whole fleet:

- **Class A — secrets missing, nothing down.** Restage only; the recreate finds nothing to do. Lowest
  risk. It is what the drill produces.
- **Class B — containers down or control plane keyless.** Restage **and** recreate. This is what a real
  reboot produces, and it runs the recreate code that has not yet run in production.

### The lever environment — `lever-restage`, approved by a bot

This is containment layer 3 from the lever model: GitHub itself, not the fleet's code, limits what the
fleet can approve. Decided by the operator on 2026-09-30.

**Why an environment, and why a bot.** A GitHub token cannot be scoped to one workflow; an environment
can. If the fleet approved in `prod` — whose reviewer is the operator, `chipi` — any credential able to
approve there could approve all **20** dispatchable workflows gated by `prod` (listed via the workflows
API on 2026-09-30), including `infra-apply.yml`, `prod-restore-corpus.yml` and
`mint-prod-gateway-key.yml`. So:

- `restage-prod-secrets.yml` deploys to a new environment, **`lever-restage`**, instead of `prod`.
- `lever-restage` has two required reviewers: the **bot machine account** and the operator (`chipi`).
  GitHub: *"Only one of the required reviewers needs to approve the job for it to proceed"* — so the bot
  alone can approve at `live`, and the operator can approve in `propose` or by hand.
- The bot is a reviewer on **no other environment**, and a **read-only** collaborator on the repo. A
  stolen bot token can therefore approve a waiting `lever-restage` run and nothing else. It cannot
  dispatch, push, or approve in `prod`.
- Deployment branches: protected branches only, like `prod`.
- A CI check in podcast_scraper asserts that **exactly one workflow file** names `lever-restage`. Without
  it, a later workflow could quietly declare that environment and inherit the bot's approval. Any such
  workflow still has to be merged to `main` by the operator; the check makes the change visible and red.

**Why a machine account and not a GitHub App.** Approving a required-reviewer gate needs a user or team
(*"up to six users or teams"*). An App can gate a deployment only as a custom deployment protection
rule, which is webhook-driven, so the mini would need an endpoint reachable from the internet. GitHub's
terms allow one free machine account beside a personal account, *"used exclusively for performing
automated tasks"*. See Alternatives.

**The secrets it needs — and the trap.** `prod` holds **10** environment-scoped secrets; everything else
the restage uses (SSH key, Tailscale OAuth, several app secrets) is repo-level and reaches any
environment unchanged. Of those 10, the restage reads **6**:

- `PROD_OPENAI_API_KEY`, `PROD_GEMINI_API_KEY`, `LITELLM_PROJ_PODCAST_PROD_KEY` — environment-level only;
- `PROD_DEEPSEEK_API_KEY`, `PROD_SENTRY_DSN_API`, `PROD_SENTRY_DSN_PIPELINE` — defined at **both**
  environment and repo level.

The last three are the trap. If one is left out of `lever-restage`, the run does not fail. The workflow
receives the **repo-level** value instead, which may not be the one prod runs on. (Which level wins when
both exist was not confirmed in GitHub's docs here. The design does not depend on it: `lever-restage`
must define all six.) Two guards:

- **A drift check.** For each of the six, the `updated_at` metadata in `lever-restage` must be no older
  than in `prod`. Secret values are write-only in GitHub and can never be compared or copied, so rotating
  a prod key means setting it in both environments, from the operator's source. Which credential runs
  this check is still open. It must **not** be one of the fleet's tokens: listing secret metadata needs
  a permission neither token has.
- **Verify layer c catches a wrong provider key** after the fact: the `prod-ops-health` `gateway` check
  exercises the keys. A wrong Sentry DSN surfaces only through `o11y_glitchtip`.

**Self-review.** In `propose` the operator (`chipi`) approves runs that were dispatched with the
operator's own token, so `prevent_self_review` must stay **off** on `lever-restage`. It stays off on
`prod` too, where the operator dispatches and approves their own deploys. At `live`, dispatcher
(`chipi`) and approver (bot) differ anyway.

### Credentials

Three credentials, all on the mini only, all in the fleet's gitignored `.env` (mode `0600`), the
same pattern as the other daemons. A LaunchDaemon has no login Keychain, so Keychain is not an
option. The rule behind the split: **each credential gets the power its stage needs, no earlier.**

1. **SSH key** `~/.ssh/remediation_fleet_prod` (ed25519, no passphrase). Its only power is running
   the check script, via the forced command. `.env`: `PROD_CHECK_SSH_KEY`, `PROD_CHECK_SSH_TARGET`
   (`deploy@prod-podcast`), `PROD_CHECK_KNOWN_HOSTS` (a pinned `known_hosts` file).
2. **Dispatch token** — the operator's fine-grained personal access token, `.env`:
   `GITHUB_DISPATCH_TOKEN`. Used from `shadow` on (in shadow only for the per-cycle token check).
   - Resource owner: `chipi`. Repository access: **only** `chipi/podcast_scraper`.
   - Permissions: **Actions: read and write** (dispatch, read runs), **Metadata: read** (mandatory).
     **No Deployments permission, at any stage** — this token never approves anything.
3. **Approval token** — the bot machine account's token, `.env`: `GITHUB_APPROVE_TOKEN`. Present
   **only from `live`**; in `shadow` and `propose` the variable is unset and the approve code path
   refuses to run.
   - A **classic** token: fine-grained tokens do not work for a collaborator on another user's personal
     repository. The endpoint needs the `repo` scope for classic tokens. What bounds this token is
     the bot's **read-only collaborator role** plus its reviewer seat on `lever-restage` alone, not the
     scope.

**Both GitHub tokens, the same hygiene:**

- **An explicit expiry, never "No expiration" — 90 days.** `chipi` is a personal account, so no org
  policy caps the lifetime, and personal tokens may be created with no expiry at all. A non-expiring
  token sends no `GitHub-Authentication-Token-Expiration` header, so the expiry alert would silently
  never fire. The 90-day renewal is also the lever registry's review point: renewing the approval token
  is when the operator re-confirms the lever.
- **Checked every cycle, not only when acting.** On a healthy box the cycle would otherwise never call
  GitHub, so a revoked or expired token would first be discovered at 4 a.m., in the middle of the outage
  it was meant to fix. Every cycle makes one cheap authenticated read per token (e.g.
  `GET /repos/chipi/podcast_scraper`), pushes `remediation_fleet_github_token_ok{token="dispatch|approve"}`
  (1/0), and parses the expiry header into
  `remediation_fleet_github_token_expiry_days{token=…}`. An absent header, or one in the past, means
  "unknown" and sets `…_token_ok=0`, never "0 days left". (That header has misbehaved before: for a
  period in 2025 it returned the current server time for fine-grained tokens, see google/go-github#3708,
  fixed server-side around 2025-09-12.) The approval token is checked only once it exists (`live`).
  Daily use also keeps both tokens out of GitHub's automatic removal of tokens unused for a year.

**Blast radius, stated plainly** (checked 2026-09-30 against all 60 workflow files and the environments
API):

- **Dispatch token, all stages.** It can start any `workflow_dispatch` workflow. Of those:
  - the **prod-gated** ones — including `restage-prod-secrets.yml` once it moves to `lever-restage` —
    then **wait for a reviewer** (the operator; the bot is a reviewer only on `lever-restage`);
  - these **ungated** ones run **immediately**:
    - `stop-prod-pipeline.yml` — kills running prod pipeline containers. It is the emergency brake, left
      ungated on purpose; the typed `STOP` is its only guard;
    - `backup-corpus-prod.yml`, `backup-operator-appdata-prod.yml`, `backup-player-appdata-prod.yml` —
      SSH to prod with the repo-level `PROD_SSH_PRIVATE_KEY`; their environment `prod-backup` has no
      protection rules;
    - `prod-ops-health.yml` — read-only.
  - Worst case for a leaked dispatch token: interrupt prod batch work, run backups. It **cannot change
    prod state or code** — no Contents permission, and every workflow that writes prod state waits for a
    reviewer.
- **Approval token, `live` only.** It can approve a waiting `lever-restage` run, which only ever
  restages and recreates onto current images. It cannot dispatch, so it can approve only runs something
  else started. Worst case for a leaked approval token plus a leaked dispatch token: extra restages of
  prod. That is the lever's own blast radius, by construction.

**Where the tokens sit** — mitigations as they actually stand (checked on the mini 2026-09-30):

- the mini is physically at home;
- `.env` is `0600`;
- each token is scoped to one repository and the minimum its role needs;
- every approval shows as the **bot** in GitHub's UI and audit log, with a
  `remediation-fleet <request_id>` comment pointing to the ledger row.

Two things a reviewer might assume are **not** true:

- **The disk is not encrypted.** `fdesetup status` → `FileVault is Off`. That was a deliberate
  trade-off to let the mini boot without a login (see `docs/wip/mac-mini-headless-server.md`). Anyone
  with physical access to the mini has the tokens, and so does any process running as
  `markodragoljevic` on it, agent sessions included.
- **The mini is not tailnet-only.** `sshd` listens on `*:22`, the macOS application firewall is
  disabled, and the mini has a LAN address. Anyone on the home network can reach its SSH port (key
  auth still applies). Restricting `sshd` to the tailnet interface is a cheap hardening the operator
  may take separately.

The operator re-confirmed the trade on these corrected facts on 2026-09-30, with the staged split
(dispatch-only until `live`; approval only as the contained bot) as the condition.

### Reporting

Same channels as the other daemons.

- **VictoriaMetrics** (`:8428/api/v1/import/prometheus`), pushed at the end of every cycle:
  - `remediation_fleet_last_cycle_timestamp{fleet="remediation"}` — pushed **last**, only if the cycle
    itself ran cleanly (the dead-man pattern);
  - `remediation_fleet_prod_reachable`, `remediation_fleet_prod_needs_recovery`, `remediation_fleet_alloy_running`;
  - `remediation_fleet_actions_total{result="success|success_o11y_dark|failed|skipped_guard|shadow|proposed"}`;
  - `remediation_fleet_latched`, `remediation_fleet_github_token_ok{token="dispatch|approve"}`,
    `remediation_fleet_github_token_expiry_days{token=…}`.

  `fleetd` also pushes its own `fleetd_cycle{fleet="remediation",outcome=…}` every cycle. That is
  not a substitute for `remediation_fleet_last_cycle_timestamp`: `fleetd_cycle` is pushed whatever the
  outcome, while the timestamp is pushed only when the cycle ran cleanly. And the existing
  `fleetd-silent` rule cannot cover this fleet — it alerts on `sum(count_over_time(fleetd_cycle[35m]))`
  across **all** fleets, so a stalled remediation fleet would stay hidden behind a healthy triage
  fleet. A per-fleet dead-man is required.
- **VictoriaLogs** (`:9428/insert/jsonline`): one `ops_event/v1` line per cycle that did more than
  "all fine" — the check JSON, the decision, `request_id`, run URL, conclusion and verify result.
- **Grafana rules** in `infra/observability/backend/grafana/provisioning/alerting/rules.yaml`:

  | rule | condition | NoData | severity | labels |
  | --- | --- | --- | --- | --- |
  | `remediation-silent` | `remediation_fleet_last_cycle_timestamp` older than **50 m** | Alerting (dead-man) | warning | `meta: "true"` |
  | `remediation-acted` | `increase(remediation_fleet_actions_total{result=~"success\|success_o11y_dark"}[10m]) > 0` | OK | info — so the operator sees in the morning that prod was fixed overnight | `meta: "true"` |
  | `remediation-proposed` | `increase(remediation_fleet_actions_total{result="proposed"}[10m]) > 0` | OK | info — propose stage: a restage is waiting for the operator's approval in GitHub | `meta: "true"` |
  | `remediation-failed` | `increase(remediation_fleet_actions_total{result="failed"}[30m]) > 0` | OK | critical | `meta: "true"` |
  | `remediation-latched` | `remediation_fleet_latched == 1` | OK | critical | `meta: "true"` |
  | `remediation-token-invalid` | `remediation_fleet_github_token_ok == 0` for 15 m, per `token` | OK | critical | `meta: "true"` |
  | `remediation-token-expiring` | `remediation_fleet_github_token_expiry_days < 14`, per `token` | OK | warning | `meta: "true"` |
  | `prod-alloy-down` | `remediation_fleet_alloy_running == 0` for 15 m while `remediation_fleet_prod_reachable == 1` | OK | warning — separates "box down" from "box up, not shipping", which the dark alerts cannot | `service`, `environment: prod` |

  Why these settings, which an earlier draft left out or got wrong:

  - **50 m, not 15 m, for `remediation-silent`.** A legitimate recovery cycle runs up to 40 m
    (`cycle_timeout`) and pushes its timestamp only at the end, so the gap between two timestamps can
    reach ~45 m (40 m + the 5 m interval). A 15 m threshold would fire on **every real recovery**.
    For comparison, `fleetd-silent` uses 35 m for 10-minute fleets.
  - **`meta: "true"` on the fleet's own rules** — invariant 7 of the fleet architecture: *"the fleet
    never triages its own substrate."* Fleet 2's Grafana pass polls firing alerts and skips only
    `meta`-labelled ones, so without the label Fleet 2 would triage Fleet 3's health. The notification
    policy also routes `meta` alerts to the operator only. `prod-alloy-down` is the exception: it is a
    genuine prod symptom, so it is fleet-consumable and must follow the "truthful symptom" contract
    (stable `alertname`, `service` + `environment` labels, a symptom-stating summary).
  - **`noDataState: OK` on the counter and gauge rules.** `remediation_fleet_actions_total{result="failed"}`
    does not exist until the first failure, so absence is the healthy state; the architecture records
    6 days of false `DatasourceNoData` from exactly this mistake on `fleetd`. Only the dead-man rule
    treats absence as an alarm.
  - **`severity: info` is new.** No existing rule uses it (the rules file has 18 `critical`, 30
    `warning`), and no policy route matches it, so it lands on the default receiver (email) like
    `warning`, and the homelab home page's alert banner shows any non-critical alert as a yellow
    warning. That matches the intent — but it is a new severity value, and worth a line in the
    alerting README when the rule lands.

### Rollout — the same ladder as Fleets 1 and 2

The operator gates every stage transition, as for the other fleets
([`fleet-rollout-plan.md`](../wip/fleet-rollout-plan.md)). On acceptance this section becomes
**Track C** in that plan. `fleetd` holds one `stage` per fleet; per-class promotion lives in the fleet's
own config (`RF_LIVE_CLASSES` in `.env`) — a class not listed there behaves as `propose` even when
`FLEETD_STAGE=live`.

**Gate to MVP** (start shadow when all are ticked):

- **Prereqs in podcast_scraper** — status from the prod-side session, 2026-09-30:
  - [x] shared rules library `scripts/ops/prod_health_lib.sh`, sourced by both the check and
    `restage_prod_recreate.sh`, with the parity test (`b9c07ff8f`);
  - [x] `scripts/ops/prod_recovery_check.sh` plus `tests/unit/scripts/ops/test_prod_recovery_check.py`
    (`b9c07ff8f`);
  - [x] `request_id` input and `run-name` on `restage-prod-secrets.yml`; the workflow copies
    `prod_health_lib.sh` to `/tmp` beside the recreate script (`b9c07ff8f`);
  - [ ] CI green on `b9c07ff8f` (partly still running on 2026-09-30), and **a deploy that includes it
    reaches prod** — until then `/srv/podcast-scraper/scripts/ops/prod_recovery_check.sh` does not
    exist on the box;
  - [ ] **one concurrency group for every prod-mutating workflow** — `restage-prod-secrets`,
    `deploy-prod`, `deploy-player`, `deploy-operator`, `deploy-all-prod` (decided 2026-09-30, see Open
    question 2);
  - [ ] the forced-command `authorized_keys` entry for `deploy`, in `infra/cloud-init/prod.user-data`
    **and** applied once to the live box (operator-approved host change). The public key is generated on
    the mini, so this step follows key creation there;
  - [ ] **the `lever-restage` environment** (see "The lever environment"): required reviewers = the bot
    machine account + `chipi`, `prevent_self_review` off, protected branches only, the six
    environment-scoped secrets set from the operator's source; `restage-prod-secrets.yml` switched from
    `environment: prod` to `environment: lever-restage`; the CI check that exactly one workflow names
    `lever-restage`; the secret drift check, with its credential chosen. Done before shadow, so that
    `propose` already exercises the real environment (with the operator approving there);
  - [ ] a DEPLOY_GOTCHAS §1b note that recovery is automatic and how to stop it — once the fleet is live.
- [ ] **The bot machine account** created, added as a **read-only** collaborator on
  `chipi/podcast_scraper` and as a reviewer on `lever-restage` only. Its token is **not** issued yet —
  that happens at Stage C3.
- [ ] **Fleet code** with `test_units.py` faking SSH and the GitHub API. Cover:
  - a clean box does nothing, but still verifies the GitHub token;
  - a broken box dispatches, finds its run by `request_id`, and approves (live) or stops at the
    approval (propose);
  - a dispatch that returns `204` still proceeds via the `request_id` lookup; a returned
    `workflow_run_id` that differs from the `request_id` run does **not** approve, and latches;
  - no run with its `request_id` within 2 min → report and stop, never "the newest run";
  - a run with the wrong id, workflow, branch or environment is **not** approved;
  - cooldown, daily cap and latch;
  - a host-key mismatch latches;
  - an unreachable prod does nothing;
  - each verify layer failing (a, b, c) counts as a failed attempt; layer d alone failing records
    "product recovered, observability dark" and is **not** a failed attempt;
  - a run still in progress at 25 min counts as failed, and is not re-dispatched inside the cooldown;
  - an invalid token, or a missing / past-dated expiry header, sets
    `remediation_fleet_github_token_ok=0`;
  - an approval rejected with 4xx (e.g. `prevent_self_review` turned on) latches instead of retrying;
  - the approve path refuses to run when `GITHUB_APPROVE_TOKEN` is unset, and never sends an approval
    with the dispatch token;
  - a pending environment other than `lever-restage` (e.g. `prod`) is never approved.
- [ ] **Eval bar green**: `eval_decisions.py` over `reference-remediation/`, including the 2026-09-30
  incident case (see "Eval").
- [ ] **`deploy/deploy.sh`** wired to run the eval and the unit tests, with auto-rollback.
- [ ] **Surfaces, like Fleets 1 and 2**: alert rules provisioned (see Reporting); a Remediation fleet row
  on the homelab home page next to "Triage fleet" and "Bug-fix fleet"; a Fleet Workforce dashboard
  alongside `signal-fleet-disp` and `bugfix-fleet-work`.

**Stage C1 — Shadow (1–2 weeks).** `stage: "shadow"`. The fleet detects, decides, checks the token and
writes "would act" rows to the ledger; it dispatches nothing and approves nothing. Weekly ritual, as for
Fleet 2: review the ledger — zero "would act" on a healthy box, and every "would act" has a reason
traceable to its check JSON.

**Stage C2 — Propose.** `stage: "propose"`. The fleet detects and **dispatches** the restage, then
**stops at the approval**: the run waits in GitHub for the required reviewer, as it does today — except
that detection and dispatch have already happened, so the operator's part shrinks to one tap. When the
operator approves, the fleet waits, runs the full verify (step 6) and records the outcome.

- Notification: GitHub notifies required reviewers of a waiting deployment; whether that reaches the
  operator's phone depends on their GitHub notification settings (not verified here). A
  `remediation-proposed` rule (info) covers it independently.
- Drill for **class A**, in a quiet window: on prod, `rm -rf /dev/shm/player-secrets`. It breaks nothing
  running — containers keep their mounted copies. The check sees `secrets_dirs.player == 0`; the fleet
  dispatches; the operator approves; the recreate finds nothing to do; verify passes.
- **Class B: first on the drill box, then a controlled reboot of prod** (decided 2026-09-30, Open
  question 3):
  1. **The DR drill box first**, if podcast_scraper extends the drill to reproduce the failure (what is
     missing today is listed under Open question 3). The fleet points at the drill host instead of prod.
     It detects the reboot, dispatches the drill-parameterised restage, and verifies. No prod impact,
     and it can repeat on every weekly drill.
  2. **Then a controlled, operator-attended reboot of prod**, in a window when prod is not busy, done
     in any case. With the operator approving in `lever-restage` and the full outcome verify running,
     this is the first time the recreate code fixed in `f68b4388f` runs in production. It also observes
     two things nothing else can: whether `alloy` starts at boot (Open question 5), and the keyless boot
     unit (Open question 6).

**Stage C3 — Live, per class.** `stage: "live"` with `RF_LIVE_CLASSES` listing the promoted classes.
Promotion to `live` is when the bot's approval token is issued (90-day expiry) and set as
`GITHUB_APPROVE_TOKEN`. The first bot approval is a **supervised class-A drill**, with the operator
watching. It proves, on the real system, the two mechanics this RFC takes from the docs: that a classic
token of a read-only collaborator can call the approve endpoint, and that the bot's approval alone
releases the run. Promote class A after one verified propose-stage success plus that supervised bot
approval; class B after its verified propose-stage success in production (the controlled prod
reboot above). The registry row in `fleet-architecture.md` moves to `live` for the promoted class in
the same change. Each promotion is operator-gated, reversible (drop the class, or set the stage
back), and recorded in `docs/history/0002-decisions.md` — as are the invariant-6 amendment and the
credential acceptance (Open question 1).

### Recovery time

- Worst case for a reboot:
  - prod back → next tick: ≤ 5 min;
  - dispatch → run starts: seconds to ~1 min, depending on the GitHub queue;
  - restage + recreate: ~1.5–3 min, longer on a cold image pull.
- **Expected total: about 5–10 minutes after the box is back**, instead of "when the operator wakes
  up".
- The first request to the operator API after a recreate took ~70 s on 2026-09-30 (a cold cache).
  That is a separate, known issue.

## Open questions

Questions 1–4 were settled with the operator on 2026-09-30 (recorded below and in Discussion). The
rest can be settled during implementation.

1. **Invariant 6 and the credential trade — decided.**
   - *Invariant:* amended into the lever model, rather than a one-off exception for this RFC. Other
     prod-acting fleets are expected, so the bar sits on admission: a never-list, a lever contract,
     GitHub-enforced containment, and a registry in which this RFC is lever #1. Landed in
     [fleet-architecture.md](../fleet-architecture.md#prod-levers-how-a-fleet-may-act-on-prod) with
     this RFC. See "Fit with the fleet architecture".
   - *Credentials:* re-confirmed on the corrected facts (FileVault off, LAN-reachable `sshd`, and the
     real blast radius: 20 `prod`-gated workflows plus 4 ungated ones that touch prod). The condition is
     the staged split. The operator's personal token only ever dispatches and never holds a Deployments
     permission. Approval happens only at `live`, as the bot, in `lever-restage`. See "Credentials" and
     "The lever environment".
   - *Accepted cost:* a second environment holding six duplicated secrets, with a drift check. This
     reverses the earlier rejection of a separate environment (see Alternatives). The difference: this
     one has a bot reviewer and a CI-enforced single workflow, where the rejected one was reviewer-less.
2. **One concurrency group for every prod-mutating workflow — decided: yes.** The operator, 2026-09-30:
   a post-reboot restage is a special case; nothing else should run while it does, and it should wait
   for anything already running. All five workflows (`restage-prod-secrets`, `deploy-prod`,
   `deploy-player`, `deploy-operator`, `deploy-all-prod`) move into one group — now a Gate-to-MVP
   prereq. Accepted cost: player and operator deploys, which may run in parallel today, serialise. The
   fleet's pre-flight guard stays as belt-and-braces; it is no longer the only protection.
3. **How is the recreate path proven? — decided: by outcome on every run, first on the drill box, then
   by a controlled reboot of prod.** Every run proves itself through step 6's layered verify (the
   operator: close the loop through observability). For class B's *first* run, the operator chose, in
   order: (D) the DR drill box, then (B) an operator-attended reboot of prod when it is not busy. B
   happens in any case; D goes first **if the drill can be made to reproduce the failure**.
   **Today it cannot** (read from `drill-deploy.yml` and `drill-exercise.yml`, 2026-09-30):
   - **no tmpfs secrets.** The drill stages only a static `.env` (paths and profiles); in the
     workflow's words, *"Missing LLM/Sentry/Grafana keys fall through to compose `${VAR:-}` defaults"*.
     Nothing is written to `/dev/shm/*-secrets`, so there is nothing for a reboot to lose.
   - **no player or operator surfaces.** The drill workflows deploy the control-plane stack (`api`,
     `viewer`, `pipeline-llm` images) and never mention `player` or `operator`. Those surfaces are the
     ones that went down on 2026-09-30.
   - **the restage workflow targets prod only.** It is hard-wired to `environment: prod`,
     `PROD_SSH_PRIVATE_KEY` and `PROD_TAILNET_FQDN`, with no drill counterpart, the way
     `drill-deploy.yml` parameterises `deploy-prod.yml`.
   - **the box is ephemeral.** `drill-exercise.yml` builds it on Wednesdays 02:00 UTC and always
     destroys it at the end of the run. No drill host was on the tailnet when checked.

   Making D real is podcast_scraper work: drill-scoped secrets staged the ADR-115 way, the player and
   operator surfaces deployed, a drill-parameterised restage, the check script and a forced-command key
   on the drill host, and a reboot step in the exercise. What D can prove: the whole mechanism (secrets
   vanish, detect, restage, recreate on the right image, fix the keyless control plane, verify
   structure and user-facing probes). What it cannot: the `lever-restage` approval (the `drill`
   environment has no reviewers) and real provider keys, so verify layer c is prod-only. Once built,
   it could re-prove recovery on every weekly drill rather than once. Whether podcast_scraper builds
   this is that repo's decision; B stands either way.
4. **A bot identity that approves as itself — decided: the machine account, from the start.** It is the
   containment for the lever (see "The lever environment"), so it is set up in the Gate to MVP and
   holds the only approval credential from `live` on. The operator's personal token is never an approval
   credential. GitHub shows the **approval** as the bot. The **dispatch** still shows as `chipi`, the
   token's owner; the run name carries the `request_id`, and the approval comment points to the ledger.
   *Still open:* making the dispatch show as a bot too. A GitHub App installed with **Actions: write**
   could dispatch as `<app>[bot]` without the webhook that ruled Apps out for approval. Not verified
   here. Having the machine account dispatch instead would need a write collaborator, and so a classic
   token that can push; that is rejected.
5. **Why did Docker not start `alloy` at boot?** It is `unless-stopped`; its `StartedAt` stayed at
   2026-09-16; the daemon log shows only "Removing stale sandbox". Until this is understood, the
   fleet only **reports** `alloy_running`. Restarting it could be a second lever, and that needs its
   own decision.
6. **Should `podcast-scraper.service` stop recreating the control plane keyless at boot?** Today the
   fleet's recreate fixes it within minutes. A boot unit that leaves the old container alone, or
   waits for secrets, would remove the keyless window entirely. That is a podcast_scraper decision.
7. **The mini is a single point of failure — for both the recovery and the alert about it.** The
   fleet runs on the mini, and so do the VictoriaMetrics and Grafana that would raise
   `remediation-silent`. If the mini is down when prod reboots, there is no recovery **and** no alert
   saying so. This is not theoretical: on 2026-09-08 the mini lost power and stayed off the tailnet for
   30 hours (fixed since 2026-09-10 by `infra/tailscale/tailscale-up.sh`, which rejoins at boot without
   a login — but a power cut still stops everything). Options: accept it for v1; or add an external
   dead-man that expects a periodic ping from the mini.
8. **GitHub outage during a reboot.** Recovery waits for GitHub. This is accepted for v1; the
   secrets' only source of truth is GitHub.
9. **Should successful attempts be capped too?** The daily cap counts only *failed* attempts. A box
   that reboots repeatedly would be restaged every time, each one an unattended `prod` approval,
   visible only as repeated `remediation-acted` emails. A cap on total approvals per 24 h (e.g. 5) would
   turn a reboot loop into a latch and a page.
10. **Notification channel for `remediation-acted`.** Email is the default contact point. Decide
    whether it should reach a phone.

## Alternatives considered

- **Secrets on prod's disk, loaded at boot** — rejected. It contradicts ADR-115, whose point is that
  secrets are never on the VPS disk. Encrypting them does not help when the key sits on the same
  disk.
- **GitHub as the watchdog** (a scheduled workflow probing prod every 5 min) — rejected. GitHub is
  CI, and may be replaced one day; it should not be the thing watching production.
- **A boot-time trigger on prod** (a unit that dispatches the workflow with a token) — rejected. It
  puts a credential on the prod box, which is exactly what ADR-115 avoids.
- **Duplicate the prod secrets into a reviewer-less `prod-restage` environment** — rejected by the
  operator. It means entering secrets twice and keeping them in sync. The environment was created
  during the discussion, never used, and deleted the same day. **Partly reversed later that day:** the
  lever model needs a per-lever environment as its containment, so `lever-restage` accepts the same
  duplication cost, with two differences. It **has** a reviewer (the bot, plus the operator), and it is
  held to one workflow by a CI check. A reviewer-less environment would have let any workflow naming
  it deploy with no approval at all.
- **Approve in `prod` with the operator's personal token** (the first draft) — replaced. That token
  could approve any of the 20 `prod`-gated workflows, including `infra-apply.yml` and
  `prod-restore-corpus.yml`, with only the fleet's own code saying no.
- **A GitHub App as a custom deployment protection rule**, so approvals show as `<app>[bot]` —
  rejected for now. GitHub drives it by webhook, so the mini would need an endpoint reachable from the
  internet (e.g. Tailscale Funnel), and how it combines with a required-reviewer rule was not
  confirmed. The machine account gives the same attribution with neither.
- **The mini keeps a copy of the secrets and pushes them to prod** — rejected. It adds a second
  secrets store to keep in sync with GitHub.
- **Trigger from the Grafana "prod dark" alert via webhook** — not for v1. In the incident the dark
  alert could not tell "box down" from "box up, shipper dead". It may become a faster trigger later,
  with the SSH check still deciding.

## Discussion

- **2026-09-30** — Written after the incident above, from a working session with the operator. The
  prod-side fixes (`RemoveIPC=no`, the three recovery-workflow bugs) shipped the same day in
  podcast_scraper. Decisions taken in the session:
  - use the existing `prod` environment and let the fleet approve its own run, with no secret
    duplication;
  - check every 5 minutes, not every minute;
  - GitHub stays CI only;
  - the fleet runs on the homelab mini as the first Fleet 3 member.
- **2026-09-30 (later)** — Fact-check pass before external review. Every claim that could be checked
  was checked against the live system: the mini (`fdesetup`, `lsof`, `launchctl`), prod's metrics in
  VictoriaMetrics, the GitHub API for `chipi/podcast_scraper` (workflows, environments, run history),
  and GitHub's docs. Corrected:
  - *Wrong facts:* FileVault is **off** on the mini, and the mini is **not** tailnet-only — both had
    been listed as mitigations for the token risk. Only `deploy-prod.yml` shares the restage's
    concurrency group; the other three deploy workflows do not, which makes the pre-flight guard
    load-bearing rather than a nicety. `chipi` is a user, so "the maximum the org allows" was not a
    real token expiry. "Fully recovers" was stated as proven; the fixed workflow has never run in
    production.
  - *Outdated premise:* the dispatch API has returned a run id (opt-in, `return_run_details`) since
    2026-02-19, so the `request_id` / `run-name` / polling prereq is dropped.
  - *Internal inconsistencies:* a 15 m `remediation-silent` threshold would fire on every real
    recovery (a legitimate cycle runs up to 35 m) — now 45 m; the 20 m wait equalled the job's own
    20 m timeout — now 25 m, with `cycle_timeout` 35 m.
  - *Gaps:* invariant 6 conflict and the departure from the architecture's Fleet 3 pipeline are now
    stated; invariant 7 `meta` labels and `noDataState: OK` specified for the alerts; the GitHub token
    is exercised every cycle instead of only when acting; detection and recreate now share one rules
    library instead of two copies; drill coverage stated honestly; five new open questions (invariant
    6, concurrency, proving the recreate path, the mini as single point of failure, capping successes).
  - *Confirmed as written:* the incident timeline (prod metrics gap 03:26:07 → 06:06:07 UTC; prod boot
    time 04:02:56; the restage job 05:59:12 → 06:00:42 = 1m30s); every podcast_scraper path, ADR-115,
    commit `f68b4388f`, DEPLOY_GOTCHAS §1/§1b, `RemoveIPC=no` in cloud-init, the `deploy` user in the
    `docker` group; the tailnet grant `tag:homelab-host → tag:prod:22` and live reachability from the
    mini; `prod` requiring reviewer `chipi` with `prevent_self_review: false`; `prod-restage` deleted;
    the token permissions (Actions read/write, Deployments write) per GitHub's per-endpoint table;
    `fleetd` accepting every field of the proposed block, with `budget_day_usd: 0` meaning "no cap";
    `fleetd` running as a system LaunchDaemon, so the no-Keychain reasoning holds.
- **2026-09-30 (review with the operator)** — Goal and decisions stated by the operator, and folded in:
  - *Goal:* full automation. The mini reacts to the signal, dispatches the restage and — because the
    operator may be asleep — approves it. The concept is deliberately extended so that automation can
    approve a prod workflow. Invariant 6 is to be amended accordingly (Open question 1).
  - *Identity:* "the app" means the fleet on the mini running under the operator's personal token —
    for now. Long term the operator wants GitHub to show that **a bot** approved, not the operator,
    with no impersonation; routes in Open question 4.
  - *Concurrency:* one group for every prod-mutating workflow — decided (Open question 2).
  - *Proof:* close the loop through observability — the fleet validates, after acting, that the product
    works. Step 6 is now a layered outcome verify (user-facing probes, the secret-dependent
    `prod-ops-health` checks, observability flowing), which also answers Open question 3.
  - *Fleet-pattern compliance:* this first Fleet 3 member is built and run like Fleets 1 and 2 — state
    and secrets outside the checkout, an append-only ledger, a frozen-replay eval with a bar and
    per-class promotion, a gated `deploy.sh`, the shadow → propose → live ladder, `remediation_fleet_*`
    metrics, and the same operator surfaces. See the table under "Fit with the fleet architecture".
- **2026-09-30 (prod-side handover, podcast_scraper `b9c07ff8f`)** — The prerequisites were built and
  pushed to `main` by the session doing the prod-side work; the RFC now matches them:
  - the shared library is `scripts/ops/prod_health_lib.sh` (not the `lib/prod_containers.sh` this
    document had proposed), with a parity test proving the check reports exactly what the recovery
    recreates;
  - the check's real fields: non-empty file counts per secret dir; `compose-api-1` counted as down when
    keyless; `alloy_running` never sets `needs_recovery`; **no** `deploy_in_progress` field — that
    guard stays GitHub-side;
  - `request_id` + `run-name` **were built**, so they are the primary way the fleet finds its run. This
    supersedes the earlier entry above that called them dropped; the dispatch response's run id (opt-in
    since 2026-02-19) is kept as a cross-check;
  - the check exists on prod only after a deploy that includes `b9c07ff8f`; the forced-command
    `authorized_keys` entry and the DEPLOY_GOTCHAS note are still to do;
  - a real read-only run that morning returned `needs_recovery=true` with nothing down — `RemoveIPC` had
    emptied the secret dirs at 06:14 UTC, before `RemoveIPC=no` was applied. That is class A, now eval
    case #2.
  - Verified against GitHub by this session: `b9c07ff8f` is `main`'s head; the three files and the
    parity test exist; the workflow carries `run-name` and `request_id`; `lib/prod_containers.sh` does
    not exist.
- **2026-09-30 (decisions on the open questions)** — Decided with the operator:
  - *Invariant 6:* amended into a **lever model** instead of a one-off exception, because more
    prod-acting fleets are expected (adding capacity under load was the operator's example), and
    "if suddenly things become a rule then it's not really an exception anymore". The operator's
    containment requirement, verbatim in substance: things that act on prod "can only do really things
    they said they can do, nothing more". Hence the never-list, the lever contract, containment
    enforced by GitHub rather than the fleet's code, and a registry. Landed in
    `fleet-architecture.md`, with this RFC as lever #1 (status: proposed, not in force).
  - *Containment:* a per-lever environment, `lever-restage`, approved by a bot machine account that is a
    reviewer nowhere else. This accepts the secret duplication the operator had rejected earlier in the
    day; the operator called it a good compromise to make the lever system work.
  - *Credentials:* staged — dispatch-only personal token from shadow, approval token (bot) only at
    `live`, both 90-day expiry. A correction during this discussion: an earlier answer claimed that
    dispatch alone was harmless because every prod run waits for approval. That was wrong. Four
    dispatchable workflows that touch prod run ungated (`stop-prod-pipeline.yml` and three backups);
    they are now listed under Credentials.
  - *Bot identity:* the machine account from the start, not after a personal-token v1. Once the bot is
    the containment, there is no reason to approve with the personal token first.
  - *Proving the recreate path:* class B's first run goes to the drill box first, if it can be made to
    reproduce the failure — today it stages no tmpfs secrets, deploys no player/operator surfaces and
    has no drill restage. Then comes a controlled prod reboot when prod is not busy, done in any case.
