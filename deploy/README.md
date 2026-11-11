# deploy — the Mac mini's deploy of this repo

The mini runs its services in place from this checkout: launchd jobs, the Hub, the alert rules,
fleetd and the fleets. So a deploy is a `git pull` of `main`, checked by gates, and rolled back if
any gate is red.

```bash
# on the mini
bash ~/agentic-ai-homelab/deploy/mini-deploy.sh
# the old entry point does the same:
bash ~/agentic-ai-homelab/signal-fleet/deploy/deploy.sh
```

It prints `pulled : <sha>`, then each hook's result, then one of:
- `DEPLOY PASS (<sha>)`;
- `DEPLOY FAIL: …`, after rolling the checkout back to where it was.

It refuses a dirty checkout and a diverged one.

## What `mini-deploy.sh` does

1. Refuses a dirty checkout, and records the current commit (`PREV`).
2. Runs the **pre-pull** hooks. A failing one is reported and never blocks the deploy.
3. `git pull --ff-only origin main`, giving `NOW`.
4. Runs the **gate** hooks from the pulled code. Any non-zero exit is RED.
5. On RED: `git reset --hard PREV`, then the **rollback** hooks, then `DEPLOY FAIL`.

It runs from a temporary copy of itself, so the pull can replace the script safely. It is written for
the mini's `/bin/bash` 3.2.

## Hooks

Each part of the repo that needs checks or records at deploy time registers a script. Nothing about
any one part is written into `mini-deploy.sh`.

| Directory | When | Contract |
|---|---|---|
| `hooks/pre-pull.d/*.sh` | before the pull | best effort; non-zero is reported, not blocking |
| `hooks/gate.d/*.sh` | after the pull, from the pulled code | exit 0 = green, non-zero = red (rolls back) |
| `hooks/rollback.d/*.sh` | after a rollback | best effort |

Hooks run in name order with `bash`, and get `CHECKOUT`, `PREV` and `NOW` (short shas) in the
environment.

Registered today, all for the triage fleet:
- `pre-pull.d/10-signal-fleet-deploy-log.sh`: installs the post-merge hook that logs every pull to
  `~/signal-fleet/results/deploys.tsv`.
- `rollback.d/10-signal-fleet-deploy-log.sh`: logs the rollback in the same file.

`gate.d/10-signal-fleet.sh` (the fleet's replays of this repo's copy) was removed on 2026-11-11: the
triage fleet runs from [flotilla](https://github.com/chipi/flotilla) since the switch that day, and
its gates run in flotilla's deploy and the fleet session's weekly check. With no gate.d hook, a pull
has no gate. The two deploy-log hooks leave with the fleet too, and this deploy keeps working
unchanged.

## Tests

`deploy/test_mini_deploy.sh` runs `mini-deploy.sh` against a throwaway origin and checkout. It covers:
- a green deploy;
- a red gate and its rollback;
- a dirty checkout, refused;
- no new commits;
- a failing pre-pull hook, which must not block;
- a diverged checkout;
- the temporary copy being cleaned up.

CI runs it on every change under `deploy/`. It also passes under bash 3.2.57 (the `bash:3.2`
image), the mini's version.

```bash
bash deploy/test_mini_deploy.sh deploy/mini-deploy.sh
```
