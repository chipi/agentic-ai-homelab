# Runbook — colima 8→4 vCPU on homelab (Mac mini)

**Status:** prepared, not executed. Pick a low-traffic window and run
attended. Author: investigation session 2026-08-26.

## Why

Host `qemu-system-x86_64` (colima VM, owned by `_dockerhost`) sustains
~4.5–5.7 cores while the 29 containers inside it account for only
~1.5–2 cores. The gap is QEMU idle/virtualization overhead, amplified by
an **8-vCPU SMP guest on a 6-physical-core host** (Intel i7-8700B,
6C/12T) that also runs another agent's iOS-simulator builds.

This is documented QEMU-colima behavior, not a runaway container:
- colima #493 — qemu host process 30–100% while guest reports <5%;
  "hypervisor level, not the VM".
- colima #1543 — usernet networking spikes ~200% with zero containers.

Confirmed NOT the usual amplifiers: **no Kubernetes** (0 k8s containers,
none in cmdline), no restarting/unhealthy container (only a benign
`glitchtip-migrate` exited 0). Lever chosen: reduce SMP count 8→4.
This is the cheap, reversible lever; the deeper cure (migrate
`vmType: qemu → vz`) is a separate volume-backup-first host rebuild —
**not** part of this runbook.

## Exact current config

`/var/_dockerhost/.colima/default/colima.yaml` (colima 0.10.3, readable
as `claude`, no sudo):

```
cpu: 8      ← change target → 4
memory: 20
disk: 100
vmType: qemu
mountType: sshfs
arch: x86_64
kubernetes: (disabled)
```

Live qemu cmdline confirms: `-smp 8,sockets=1,cores=8,threads=1`,
`-m 20480`, `-machine q35,accel=hvf` (hardware virt, not emulation).

## How it's managed (why the restart method matters)

- **launchd daemon `com.homelab.colima.plist`** (root-owned) runs, as
  `_dockerhost`: `exec colima start` — **bare, no `--cpu` flag → reads
  the yaml.** So persisting `cpu: 4` (via `--cpu 4`) is what the next
  boot picks up. Nothing hardcodes 8.
- The colima service has **NO `KeepAlive`** — runs once at boot, forks
  the lima hostagent, exits. A manual `colima stop && start` will NOT be
  fought by launchd (no flapping). **Corollary worst case:** if
  `colima start` fails, launchd will NOT auto-retry — stack stays down
  until a human intervenes.
- **`com.homelab.docker-relay.plist`** = socat `UNIX-LISTEN:/var/run/docker.sock`
  → colima's socket, with **`KeepAlive`**. Self-heals: dies when the VM
  drops, respawns and reconnects once colima's socket returns. No action.
- All 29 containers auto-restart: **8 `always` + 21 `unless-stopped`,
  zero no-policy** → they come back on their own, no manual `compose up`.
- Volumes: **18 named + 1 anonymous**. Untouched by stop/start. Only
  `colima delete` / `compose down -v` destroy them → data-safe change.

## The change (run as `_dockerhost`, mirror the plist env)

`claude` user has no sudo — operator runs this, or authorizes a path.

```bash
sudo -u _dockerhost -H bash -lc \
  'export PATH=/usr/local/bin:$PATH HOME=/var/_dockerhost; colima stop && colima start --cpu 4'
```

`--cpu 4` restarts AND persists `cpu: 4` into the yaml, keeping the next
launchd boot consistent. **Run attended — watch `colima start` live, do
NOT background it.**

## Verify (after start returns)

```bash
# 1. colima up, cpu now 4
sudo -u _dockerhost -H bash -lc 'export PATH=/usr/local/bin:$PATH HOME=/var/_dockerhost; colima status'
grep -E '^cpu:' /var/_dockerhost/.colima/default/colima.yaml          # → cpu: 4
ps -o command= -p "$(pgrep -f qemu-system-x86_64)" | tr ' ' '\n' | grep -A1 smp   # → -smp 4...

# 2. all 29 containers back up
export DOCKER_HOST=unix:///var/run/docker.sock
/usr/local/bin/docker ps -q | wc -l                                    # → 29
/usr/local/bin/docker ps -a --format '{{.Status}} | {{.Names}}' | grep -viE '^Up '   # only glitchtip-migrate (Exited 0)

# 3. the payoff — host qemu %cpu should sit lower; sample 3x
for i in 1 2 3; do ps -o %cpu= -p "$(pgrep -f qemu-system-x86_64)"; sleep 1; done
```

## Rollback (identical line, 8)

```bash
sudo -u _dockerhost -H bash -lc \
  'export PATH=/usr/local/bin:$PATH HOME=/var/_dockerhost; colima stop && colima start --cpu 8'
```

## Expected gap (ESTIMATE — not measured; boot log was already cleared)

| Phase | Est. |
|---|---|
| `colima stop` (graceful qemu shutdown) | ~10–30s |
| `colima start` (lima boots VM, blocks until docker ready; 100GB disk + sshfs) | ~30–90s |
| 29 containers auto-restart → healthy | ~1–3 min |
| **Docker socket usable** | **~1–2 min** |
| **Full stack healthy** | **~2–5 min** |

## Worst case (ranked, worst first)

1. **VM doesn't come back.** `colima start` hangs/errors (open reports on
   recent macOS — you're on 15.7.7; colima #1211, #987). No `KeepAlive`
   → launchd will NOT retry → stack down until human fixes it. Recovery:
   `colima status` → `colima start --verbose` → force-kill stale
   `qemu`/`limactl`, retry → last resort reboot the Mac. **Disk intact →
   downtime risk, NOT data loss.**
2. **`colima stop` hangs → force-kill qemu → unclean shutdown.** Guest FS
   journal-replays; postgres WAL / victoriametrics WAL / minio are
   crash-consistent and recover. Small nonzero risk only for anything
   mid-write (incl. the 1 anonymous volume).
3. **4 vCPU barely helps** — if burn is networking/usernet not SMP count,
   restart bought little; real fix becomes the `vz` migration. Low harm.
4. **Transient docker-socket errors** for other agents / obs push / crons
   during the window — self-heals; ~2–5 min scrape/ingest gap.

## Optional insurance against #2 (likely overkill — change is data-safe)

Quick DB dumps first (sub-5-min rollback if a store comes up dirty):
```bash
export DOCKER_HOST=unix:///var/run/docker.sock
/usr/local/bin/docker exec langfuse-postgres-1 pg_dumpall -U postgres > /tmp/langfuse-$(date +%F).sql
# repeat for glitchtip-postgres-1, umami-db as needed
```

## NOT verified / open items

- Gap timing is an **estimate** — no restart was performed to measure it,
  and the real boot log (`/tmp/colima-boot.log`) was already cleared.
- Did **not** prove *why* qemu burns ~5 cores (SMP idle-spin vs usernet
  vs device I/O) — inference from the host/guest gap, not measured. If
  4 vCPU underperforms, investigate usernet (#1543) before assuming SMP.
- The `vz` migration (the actual cure for QEMU idle burn) is **out of
  scope here** — needs `colima delete` + recreate, which destroys the VM
  disk, so it requires a named-volume backup first. Separate runbook.
