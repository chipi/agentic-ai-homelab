# RFC-0005 — Fleet 3 v1: `remediation-fleet`, unattended recovery of prod after a reboot

**Status:** Proposed (2026-09-30)
**Runs on:** the `homelab` Mac mini, as one fleet under `fleetd` (RFC-0004).
**Acts on:** the podcast_scraper production VPS (`prod-podcast`), only through one GitHub Actions
workflow in the public `chipi/podcast_scraper` repo.
**Relates to:** RFC-0003 (Fleet 2 hands remediation to Fleet 3), RFC-0004 (`fleetd`),
[fleet architecture](../fleet-architecture.md) (Fleet 3 = the config/runtime lever).
**Relates to (podcast_scraper):** ADR-115 (prod secrets live in RAM only),
`docs/guides/DEPLOY_GOTCHAS.md` §1 / §1b, `.github/workflows/restage-prod-secrets.yml`,
`scripts/ops/restage_prod_recreate.sh`.

This is the first Fleet 3 member. It owns exactly one lever. Nothing in it is an LLM.

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
fully recovers prod after a reboot. **What is missing is something that makes that call, and
approves it, without a human.**

## Proposal

### Scope — one lever, forever for v1

| in scope | out of scope (v1) |
| --- | --- |
| Detect "prod is up but needs its secrets restaged / containers recreated" | Box unreachable (VPS down): nothing to do until it is back; the existing "prod dark" alert covers it |
| Dispatch `restage-prod-secrets.yml` with fixed inputs | Any other workflow, deploy, image change, rollback |
| Approve the `prod` deployment of **that run only** | Approving anything else, ever |
| Verify the result and report | Restarting `alloy`, fixing the boot unit, any host change |

The fleet never holds a prod secret, never SSHes to prod with write capability, and never changes
code or config.

### Placement — same shape as the existing fleets

- **Directory:** `remediation-fleet/` at the repo root, a sibling of `bugfix-fleet/`.
- **Language:** stdlib-only Python 3 (`/usr/bin/python3`), like `infra/ci-ops-poller/poll.py`,
  which already calls the GitHub Actions API. No dependencies.
- **Supervisor:** a block in `fleetd.json`. `fleetd` gives us the scheduler, the STOP-file kill
  switch, the no-overlap rule, the cycle timeout, the `stage` ladder, and the `fleetd-silent`
  pattern for free. **No new LaunchDaemon plist** and no change to `infra/mini-setup.sh`.

```text
remediation-fleet/
  README.md            what it does, install, drill, how to stop it
  .env.example         names only (see "Credentials")
  cycle.py             one cycle: check → decide → act → verify → report (exit code = outcome)
  state.json           gitignored; cooldown / attempt ledger / latch
  tests/               unittest, stdlib; GitHub + SSH faked
```

`fleetd.json` block (paths are placeholders):

```json
{
  "name": "remediation",
  "enabled": true,
  "interval": "5m",
  "cycle_cmd": "/usr/bin/python3 /Users/operator/agentic-ai-homelab/remediation-fleet/cycle.py",
  "workdir": "/Users/operator/agentic-ai-homelab/remediation-fleet",
  "env_file": "/Users/operator/agentic-ai-homelab/remediation-fleet/.env",
  "stop_flag": "/Users/operator/agentic-ai-homelab/remediation-fleet/STOP",
  "budget_day_usd": 0,
  "stage": "shadow",
  "cycle_timeout": "30m"
}
```

`cycle_timeout` must exceed one workflow run: the 2026-09-30 restage took 1m30s, and a cold image
pull can take several minutes. 30m leaves room for the verify step. `fleetd` never overlaps cycles,
so a long cycle simply skips ticks.

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

**What the check reports** (all read-only):

| field | how | "needs recovery" when |
| --- | --- | --- |
| `secrets_dirs` | `test -d /dev/shm/{podcast,operator,player}-secrets` and file count | any dir missing or empty |
| `down_containers` | `docker ps -a` per compose project `compose`, `operator`, `player`; status `Exited*` / `Restarting*` / `Created*` | non-empty |
| `keyless_control_plane` | `docker inspect compose-api-1` Mounts has no `/run/secrets/*` destination | true |
| `boot_time` | `/proc/stat` `btime` | informational (lets the fleet say "rebooted at …") |
| `alloy_running` | `docker ps --filter name=^alloy$` | informational in v1 (not fixed by this lever) |
| `deploy_in_progress` | informational; the real guard is GitHub-side (below) | — |

Example output:

```json
{"schema":"prod_recovery_check/v1","boot_time":1790740980,
 "secrets_dirs":{"podcast":0,"operator":0,"player":0},
 "down_containers":["player-api-1","operator-api-1","player-learning-app-1","operator-viewer-1"],
 "keyless_control_plane":true,"alloy_running":false,"needs_recovery":true}
```

`needs_recovery` is computed on the box, by the same rules `restage_prod_recreate.sh` uses to
decide what to recreate, so detection and action cannot disagree. The fleet re-checks it
independently from the fields and refuses to act if the two differ.

**If SSH fails** (timeout, refused, host key mismatch): the fleet records `prod_reachable=0` and does
nothing. A host-key **mismatch** is a hard error (alert, latch), never auto-accepted — a rebuilt VPS
gets a new host key, and accepting it is an operator decision.

### The action — dispatch, find, approve exactly one run

1. **Pre-flight guards** (any failure → do nothing this cycle, report why):
   - `stage` is `live` (in `shadow` the fleet logs "would act" and stops here);
   - not latched, not inside the cooldown, under the daily cap (see Guardrails);
   - no run of `deploy-all-prod.yml`, `deploy-prod.yml`, `deploy-player.yml`,
     `deploy-operator.yml` or `restage-prod-secrets.yml` is `queued` / `in_progress` / `waiting`.
     They share the `deploy-prod` concurrency group, so a dispatch would only queue behind them —
     and a deploy that is running will restage anyway.
2. **Dispatch** `POST /repos/chipi/podcast_scraper/actions/workflows/restage-prod-secrets.yml/dispatches`
   with `ref: main` and inputs `confirm=RESTAGE_SECRETS`, `surfaces=all`, `recreate=true`,
   `request_id=<uuid4>`.
3. **Find the run.** The dispatch API does not return a run id. **Prereq in podcast_scraper:** add
   an optional `request_id` input and `run-name: "Restage prod tmpfs secrets ${{ inputs.request_id }}"`
   to the workflow. The fleet polls `GET …/actions/workflows/restage-prod-secrets.yml/runs?event=workflow_dispatch&branch=main`
   (every 5 s, up to 2 min) for the run whose `display_title` contains its `request_id`. Not found →
   report and stop. It **never** guesses by time or picks "the newest run".
4. **Approve that run only.**
   - `GET …/actions/runs/{run_id}/pending_deployments`.
   - Approve only if **all** of these hold:
     - `run.path == ".github/workflows/restage-prod-secrets.yml"`;
     - `run.head_branch == "main"` and `run.event == "workflow_dispatch"`;
     - `display_title` contains this cycle's `request_id`;
     - exactly one pending environment, named `prod`.
   - Then `POST …/actions/runs/{run_id}/pending_deployments` with
     `{"environment_ids":[<id>],"state":"approved","comment":"remediation-fleet <request_id>: <check summary>"}`.
   - Any mismatch → do not approve, alert, latch.
5. **Wait** for the run to complete (poll every 15 s, up to 20 min). Record the conclusion and the
   run URL.
6. **Verify.** Run the check again. **Success** means the run concluded `success` **and** the fresh
   check reports `needs_recovery=false`. Anything else counts as a failed attempt.

### Guardrails

| guard | value | why |
| --- | --- | --- |
| Allowlist | exactly one workflow path, one ref, one environment | the token can do more; the code must not |
| Cooldown | 15 min between attempts | a restage takes ~2 min; a second try inside 15 min means the first did not work |
| Daily cap | 3 failed attempts per rolling 24 h → **latch** | a loop that keeps "fixing" is worse than an outage we know about |
| Latch | `state.json` `latched=true`; cleared only by the operator (`cycle.py --unlatch`) | autonomy is revocable and does not re-grant itself |
| Kill switch | `fleetd` STOP flag | the standard fleet off switch |
| Stages | `shadow` → `live` | `shadow` detects and reports "would act", and approves nothing |
| No overlap | `fleetd` never runs two cycles at once | one attempt in flight, ever |
| No LLM | none | invariant 1 of the fleet architecture |

### Credentials

Two credentials, both on the mini only, both in the fleet's gitignored `.env` (mode `0600`), the
same pattern as the other daemons. A LaunchDaemon has no login Keychain, so Keychain is not an
option.

1. **SSH key** `~/.ssh/remediation_fleet_prod` (ed25519, no passphrase). Its only power is running
   the check script, via the forced command. `.env`: `PROD_CHECK_SSH_KEY`, `PROD_CHECK_SSH_TARGET`
   (`deploy@prod-podcast`), `PROD_CHECK_KNOWN_HOSTS` (a pinned `known_hosts` file).
2. **GitHub fine-grained personal access token**, `.env`: `GITHUB_TOKEN`.
   - Resource owner: `chipi`. Repository access: **only** `chipi/podcast_scraper`.
   - Permissions: **Actions: read and write** (dispatch, read runs), **Deployments: read and write**
     (approve the pending deployment), **Metadata: read** (mandatory). Nothing else.
   - Expiry: the maximum the org allows. The fleet reads the `github-authentication-token-expiration`
     response header and pushes `remediation_github_token_expiry_days`. An alert fires below 14 days.

**Why a personal token, not a GitHub App.** The `prod` environment's required reviewer is the
operator's user account. An approval has to come from a required reviewer, so the token has to act
as that user. As far as I know GitHub Apps cannot be added as required reviewers — **verify this
before implementing**; an App would be preferable if it can.

**Self-review.** The same user both dispatches and approves. This works today because the `prod`
environment has `prevent_self_review: false` (checked 2026-09-30). If that setting is ever turned
on, approvals fail with 4xx. The fleet must treat that as "latch + alert", never as "retry".

**Accepted risk, stated plainly.** Whoever holds this token can approve **any** pending `prod`
deployment in the repo, not only restages. The allowlist is enforced by the fleet's code, not by
GitHub. Mitigations:

- the mini's disk is FileVault-encrypted and physically at home;
- `.env` is `0600`;
- the mini is reachable only over the tailnet;
- every approval carries a `remediation-fleet <request_id>` comment, so the GitHub audit log shows
  which approvals the fleet made.

The operator accepted this trade on 2026-09-30, over duplicating the prod secrets into a second,
reviewer-less environment.

### Reporting

Same channels as the other daemons.

- **VictoriaMetrics** (`:8428/api/v1/import/prometheus`), pushed at the end of every cycle:
  - `remediation_last_cycle_timestamp{fleet="remediation"}` — pushed **last**, only if the cycle
    itself ran cleanly (the dead-man pattern);
  - `remediation_prod_reachable`, `remediation_prod_needs_recovery`, `remediation_alloy_running`;
  - `remediation_actions_total{result="success|failed|skipped_guard|shadow"}`;
  - `remediation_latched`, `remediation_github_token_expiry_days`.
- **VictoriaLogs** (`:9428/insert/jsonline`): one `ops_event/v1` line per cycle that did more than
  "all fine" — the check JSON, the decision, `request_id`, run URL, conclusion and verify result.
- **Grafana rules** in `infra/observability/backend/grafana/provisioning/alerting/rules.yaml`:

  | rule | condition | severity |
  | --- | --- | --- |
  | `remediation-silent` | no `remediation_last_cycle_timestamp` for 15 m (NoData → Alerting, like `fleetd-silent`) | warning |
  | `remediation-acted` | `increase(remediation_actions_total{result="success"}[10m]) > 0` | info (email) — so the operator sees in the morning that prod was fixed overnight |
  | `remediation-failed` | `increase(remediation_actions_total{result="failed"}[30m]) > 0` | critical |
  | `remediation-latched` | `remediation_latched == 1` | critical |
  | `remediation-token-expiring` | `remediation_github_token_expiry_days < 14` | warning |
  | `prod-alloy-down` | `remediation_alloy_running == 0` for 15 m while `remediation_prod_reachable == 1` | warning — separates "box down" from "box up, not shipping", which the dark alerts cannot |

### Rollout

1. **Prereqs in podcast_scraper** (one PR):
   - `scripts/ops/prod_recovery_check.sh` plus unit tests (stub `docker`, same style as
     `test_restage_prod_recreate.py`);
   - the `request_id` input and `run-name` on `restage-prod-secrets.yml`;
   - the forced-command `authorized_keys` entry in `infra/cloud-init/prod.user-data`, and the same
     entry applied once to the live box (operator-approved host change);
   - a DEPLOY_GOTCHAS §1b note that recovery is now automatic, and how to stop it.
2. **Fleet code** in this repo, with unit tests faking SSH and the GitHub API. Cover:
   - a clean box does nothing;
   - a broken box dispatches, finds the run by `request_id`, and approves;
   - a run with the wrong workflow, branch or environment is **not** approved;
   - cooldown, daily cap and latch;
   - a host-key mismatch latches;
   - an unreachable prod does nothing;
   - a failed verify counts as a failed attempt.
3. **Shadow week.** `stage: "shadow"`. Check that the fleet reports "clean" on a healthy box and
   never "would act" without a reason.
4. **Drill, in a quiet window, operator present.** On prod: `rm -rf /dev/shm/player-secrets`.
   - This breaks nothing that is running: containers keep their mounted copies.
   - The check sees `secrets_dirs.player == 0`.
   - With `stage: "live"`, the fleet dispatches and approves. The workflow restages; the recreate
     finds nothing down and recreates nothing.
   - Verify reports clean, and `remediation-acted` fires.

   This exercises every step end to end without an outage.
5. **Live.** `stage: "live"`. Record the promotion in `docs/history/0002-decisions.md`.

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

1. **Why did Docker not start `alloy` at boot?** It is `unless-stopped`; its `StartedAt` stayed at
   2026-09-16; the daemon log shows only "Removing stale sandbox". Until this is understood, the
   fleet only **reports** `alloy_running`. Restarting it could be a second lever, and that needs its
   own decision.
2. **Should `podcast-scraper.service` stop recreating the control plane keyless at boot?** Today the
   fleet's recreate fixes it within minutes. A boot unit that leaves the old container alone, or
   waits for secrets, would remove the keyless window entirely. That is a podcast_scraper decision.
3. **GitHub App as a required reviewer** — confirm that it is not possible (see Credentials). If it
   is, switch the approval to an App and drop the personal token.
4. **GitHub outage during a reboot.** Recovery waits for GitHub. This is accepted for v1; the
   secrets' only source of truth is GitHub.
5. **Notification channel for `remediation-acted`.** Email is the default contact point. Decide
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
  operator. It means entering secrets twice and keeping them in sync. It would have avoided a token
  that can approve prod deployments. The environment was created during the discussion, never
  used, and deleted the same day.
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
