---
name: ci-step-local
description: Test a GitHub workflow or composite-action step locally before pushing — extract one `run:` step, run it under bash (never zsh) the way the runner does, with a fresh HOME/RUNNER_TEMP/GITHUB_ENV/GITHUB_OUTPUT and every `${{ … }}` supplied explicitly, as named pass AND fail cases. Plus `verify_units.sh`, which checks systemd unit files on the host they are for without installing them. Use when changing a workflow step, a composite action, an ssh/scp/known_hosts flag, or a systemd unit, when asked "test the workflow change locally", "does this step still work", or before pushing anything under .github/.
---

# ci-step-local

A workflow change used to be tested by pushing it and waiting for a real run. Two changes on
2026-10-17 were proven locally instead, by hand:

- SSH host-key pinning across 23 workflows: the composite action's script was extracted and run
  against prod with the right key, a wrong key and a garbage key.
- A systemd timer: `systemd-analyze verify` on the box.

The hand-rolled versions kept hitting zsh word-splitting (`"File name too long"`,
`zsh: ==== not found`) and needed `bash -c` wrappers. This makes it one command, under bash. For
a one-off remote command (not a step), use `host-run`.

## Run a step

```bash
R=~/.claude/skills/ci-step-local/scripts/run_step.py   # needs PyYAML: pyenv python3, not /usr/bin/python3
python3 $R .github/actions/prod-ssh-key/action.yml --step 0 \
  --sub 'inputs.ssh_private_key=dummy-pem' --sub 'inputs.identity_env_name=SSH_PROD_IDENTITY' \
  --sub "inputs.pinned_host_key=ssh-ed25519 AAAA…" --case right-key --expect-exit 0
python3 $R .github/actions/prod-ssh-key/action.yml --step 0 … \
  --sub 'inputs.pinned_host_key=not-a-key' --case garbage --expect-exit 1
python3 $R .github/workflows/deploy-config.yml --job deploy --step "Stage + deploy config for the surface" --env DRY_RUN=true …
```

- `--step`: the step's `id`, `name`, or index among all steps.
- Every `${{ … }}` in the script or the step's `env` must be given with `--sub`. An unresolved one
  refuses (exit 4) instead of running with an empty string, which is how a guard gets proven by
  accident.
- The step runs in your working directory, with your PATH and network: a step that ssh's to prod
  reaches prod. Run only steps that are read-only or DRY_RUN there, unless the operator said go.
- Always pair a passing case with a case that must fail.

## Check systemd units on their host

```bash
~/.claude/skills/ci-step-local/scripts/verify_units.sh -i ~/.ssh/podcast_prod_operator deploy@prod-podcast \
  infra/systemd/prod-ops-health.service infra/systemd/prod-ops-health.timer
```

It copies the files to a temp dir on the host, runs `systemd-analyze verify` there, prints each
timer's next run, and removes the copies. Nothing is installed. It also prints warnings from the
host's existing drop-ins: on 2026-10-17 that is how Caddy's unquoted `CADDY_BIND_ADDRS` (IPv6 bind
dropped) was found. Read every line, not only your unit's.

## Tested 2026-10-17

- `run_step.py` on `prod-ssh-key/action.yml`:
  - unresolved inputs → REFUSED (exit 4);
  - right key → exit 0, `SSH_PROD_IDENTITY` in the temp GITHUB_ENV, written in the temp HOME, not
    yours;
  - garbage key → exit 1 with the action's own `::error::`.
- `verify_units.sh` on prod with the #1877 units: reported the wrapper missing from the box checkout
  (expected before deploy), the timer's next run, and the Caddy drop-in warning. Temp dir removed.

## Not covered

- `uses:` steps (marketplace actions such as checkout or tailscale) are not run. Supply their outputs
  with `--env` / `--sub`.
- `shell:` other than bash, `working-directory:`, and step `if:` conditions are not interpreted.
- Matrix and reusable-workflow `with:` values: pass them as `--sub` yourself.
