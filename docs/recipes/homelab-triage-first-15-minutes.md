# Homelab triage — the first 15 minutes

**Start here** when something on the homelab looks broken and you are picking it
up cold. Read this before you investigate anything.

## Why this exists

On **2026-09-03** the mini had a 5-hour incident. Diagnosing it took ~5 hours of
analysis. It should have taken minutes: a runbook already existed
([colima/lima forwarding](colima-lima-forwarding-recovery.md)), the alert fired
correctly within 5 minutes and named the cause, and a watchdog was already
deployed for it.

The time went to four avoidable mistakes, all made before any real analysis
started. Every one is cheap to avoid and expensive to make. They are listed
first, deliberately.

---

## The four traps

### 1. You are probably on a stale checkout

```
cd ~/agentic-ai-homelab; git fetch; git log --oneline HEAD..origin/main | wc -l
```

On 2026-09-03 the responder worked **56 commits behind**, and therefore:
concluded "there is no alert rule for the docker engine — none" (there was, and
it had already fired); reported "nothing changed in the last 17 days" (work
landed 4 days earlier); and told the operator their own recollection of recent
changes was wrong. **It was not.**

A stale checkout does not produce errors. It produces confident, wrong answers.

### 2. Never diagnose the mini *from* the mini

The most common homelab failure — the host↔VM forward break — kills **exactly
the plane you are probing from**: the host `docker` CLI, every host loopback
port, and the host collectors. Probe from the mini and a healthy stack looks
like a total outage.

```
ssh -o StrictHostKeyChecking=accept-new ops@dgx-llm-1 \
  'for n in grafana glitchtip umami vm hub; do printf "%-10s " "$n"; \
   curl -sk -o /dev/null -m 10 -w "%{http_code}\n" "https://$n.tail6d0ed4.ts.net/"; done'
```

**Service health is only meaningful from another tailnet node.** On 2026-09-03
the mini reported every service dead; from the DGX all nine were serving
normally the entire time.

This applies to name resolution too: the per-service nodes are tagged
`tag:homelab-svc`, and ACL visibility means they may not resolve *from the mini*
even while perfectly healthy. `NO RESOLVE` on the mini is not evidence.

### 3. Check for an existing runbook before investigating

```
ls docs/recipes/
```

Ten recipes exist. The 2026-09-03 failure was fully documented — mechanism,
symptom table, recovery, and prior incident — and was still rediscovered from
scratch.

### 4. A scoped or zero-result command is not a fact

Known liars on this box:

| Command | What it actually tells you |
|---|---|
| `lsof -iTCP -sTCP:LISTEN` | **only your own user's** sockets. Not "nothing is listening" |
| `/tmp/docker-relay.log` | socat logs **failures only** — it says nothing about the success rate |
| `mini_docker_total` | 5-minute resolution; **cannot** see sub-5-minute container churn |
| `colima status` | process-level only — reports `running` throughout a total outage |
| `mini_forward_up` present | proves *a* watchdog runs, **not** which version |
| curl to a `.ts.net` name | depends on the caller's ACL visibility, not on service health |

**Always establish a baseline before calling something anomalous.** On
2026-09-03 four `Broken pipe` lines were read as "3 minutes of degradation"; the
chronic rate is ~92/hour, every hour, for weeks. The real signal was a single
clean edge one minute later.

---

## Quick reference — the four commands, in order

```
# 1. Am I current?
cd ~/agentic-ai-homelab; git fetch; git log --oneline HEAD..origin/main | wc -l

# 2. Are services actually down?  (from the DGX, NOT the mini)
ssh ops@dgx-llm-1 'curl -sk -o /dev/null -w "%{http_code}\n" https://grafana.tail6d0ed4.ts.net/'

# 3. Is it the host↔VM forward?  (200 above + failure below == yes)
docker ps -q >/dev/null 2>&1; echo "docker rc=$?"; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/api/health

# 4. Did the watchdog already capture it?
ls -lt /tmp/forward-break-*.txt 2>/dev/null | head -3
```

**If 2 returns 200 while 3 fails → it is a host control-plane break, not a
service outage.** Stop here and go to
[colima/lima forwarding — break & recovery](colima-lima-forwarding-recovery.md).
Consumers are unaffected; do not panic-restart.

---

## Evidence sources — what survives recovery

The recovery action (`colima restart`) **destroys the most important evidence**.
Two incidents were lost that way before this was understood. Capture first.

| Source | Location | Survives `colima restart`? | Readable without sudo? |
|---|---|---|---|
| **Guest journal** | `/var/log/journal` *inside the VM* | **YES** — back to VM creation | **yes**, see below |
| `ha.stderr.log` | `_lima/colima/` | **NO — recreated** | no (root) |
| `ha.stdout.log` | `_lima/colima/` | **NO — recreated** | no (root) |
| `docker events` | in-memory in dockerd | **NO** | via `colima ssh` |
| Auto-capture dumps | `/tmp/forward-break-*.txt` | yes | yes |
| Master-PID transitions | `/tmp/forward-master-pid.log` | yes | yes |
| socat relay log | `/tmp/docker-relay.log` | yes | yes |
| macOS unified log | `log show` | yes, but **rolls** — grab early | needs sudo |
| VictoriaMetrics history | `http://127.0.0.1:8428` | yes | yes |

**The guest journal is the highest-value source and was overlooked for two
incidents.** It is what finally showed that the SSH master was closed cleanly
rather than breaking.

### Reading the guest journal without sudo

The VM's journal can be mounted into a container, so no `_dockerhost` access is
needed:

```
docker run --rm -v /var/log/journal:/var/log/journal:ro ubuntu:24.04 bash -c \
  'apt-get update -qq && apt-get install -y -qq --no-install-recommends systemd && \
   journalctl -D /var/log/journal -b -1 -t sshd --no-pager -o short-iso | tail -40'
```

`-b -1` is the previous boot, `-b -2` the one before. Requires container network
egress; if `apt-get` is blocked, ask the operator to run `journalctl` via
`colima ssh` instead.

---

## Access map — know what you can do before saying "I can't"

| As | sudo | Can read | Cannot read |
|---|---|---|---|
| `claude` | **no** (`sudo -n` fails) | `/tmp/*`, the repo, VictoriaMetrics, `docker`, `ssh ops@dgx-llm-1` | `/var/_dockerhost/**`, `/Users/markodragoljevic/**` |
| `markodragoljevic` | **yes**, passwordless | everything | — |

Before declaring a gap, exhaust the access you have — the DGX is reachable
keylessly over Tailscale SSH and is the correct vantage point for service checks.

## Handing commands to the operator

- **No `!` prefix.** `!` is Claude Code's prompt syntax. In the operator's bash
  it is the **logical NOT** operator: `! cd x && git pull` inverts `cd`'s success
  and **silently skips everything after `&&`**. This cost a whole deploy cycle on
  2026-09-03 — the pull never ran and the "verified" deploy had not happened.
- **Use `;` not `&&`** so one failing step cannot silently skip the rest.
- **Verify the effect, not the exit code.** A process start time, a file's
  content, a version marker. `rc=0` proved nothing when the file on disk was
  unchanged.

---

## Verification

You have triaged correctly when you can answer all four:

1. Am I on current `origin/main`?
2. Do services respond **from another tailnet node**?
3. Does the symptom match an existing recipe in `docs/recipes/`?
4. Have I captured the restart-destroyed evidence *before* recovering?

## Troubleshooting

- **"Everything is down"** — re-check from the DGX before believing it. A host
  control-plane break presents exactly this way and is not a service outage.
- **A `.ts.net` name will not resolve** — check from another node first; ACL
  visibility, not service health.
- **A metric "disappeared"** — ask whether its *write path* rides the lima
  forward before concluding the source is dead.
- **The docs build fails on an untouched file** — check whether it is red on
  `origin/main` too before attributing it to your change.
