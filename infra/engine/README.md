# `infra/engine/` — the Docker engine layer (layer 0)

The pieces that make `docker` work at all on the Mac mini, as code. Everything
else under `infra/` assumes this layer already exists.

Installed by [`../mini-engine-setup.sh`](../mini-engine-setup.sh) — run it
**first**, before `bootstrap.sh` (containers) and `mini-setup.sh` (collectors).

## Why this directory exists

Until 2026-09-03 this layer lived **only on the box** and as prose in
[`docs/wip/mac-mini-headless-server.md`](../../docs/wip/mac-mini-headless-server.md).
An audit that day found a from-scratch rebuild would have reached "brew
installed, Tailscale up, age key restored" and then stopped: nothing created the
service account, the VM spec, the boot daemon or the socket relay. The
`socat` dependency wasn't even in the Brewfile.

## What's here

| File | Installs to | Purpose |
|---|---|---|
| `colima.yaml` | `/var/_dockerhost/.colima/default/colima.yaml` | VM spec — 8 cpu / 20 GB / 100 GB, qemu, sshfs `/Users` |
| `com.homelab.colima.plist` | `/Library/LaunchDaemons/` | Boots the VM at system start as `_dockerhost`, no login needed |
| `com.homelab.docker-relay.plist` | `/Library/LaunchDaemons/` | `socat` relay publishing the socket at `/var/run/docker.sock`, `root:admin` 0660 (operator + root only) |

Plus, done by the script rather than a file: the **`_dockerhost` service
account** (uid 504, gid 20 staff, home `/var/_dockerhost`, `IsHidden`), and
removing any global `DOCKER_HOST` from `/etc/zshenv`: it overrode other
accounts' docker contexts and sent them to this production engine (2026-10-09).

## How the pieces fit

```
  launchd ──> com.homelab.colima ──> colima start (as _dockerhost)
                                        └─> QEMU VM ──> dockerd
                                              └─ lima forwards the guest socket
                                                 over an SSH ControlMaster to
                                                 /var/_dockerhost/.colima/default/docker.sock  (0600)
  launchd ──> com.homelab.docker-relay ──> socat ──> /var/run/docker.sock       (root:admin 0660)
                                                        ↑
            the operator account + root talk here; development (any
            account) uses the separate dev engine below
```

## The dev engine (`dev/`)

A second, separate engine for development, off unless someone starts it
([ADR-0009](../../docs/adr/ADR-0009-on-demand-dev-docker-engine.md)): `_dockerdev`,
vz + virtiofs, 4 CPU / 6 GiB, socket `/var/run/docker-dev.sock` (`root:staff`).
Installed by [`../mini-dev-engine-setup.sh`](../mini-dev-engine-setup.sh), never by
this directory's setup. Usage and the agents' contract:
[dev Docker engine](../../docs/recipes/dev-docker-engine.md).

## Known fragilities — read before changing anything

- **The SSH ControlMaster is a single point of failure.** Both the docker socket
  *and* every published container port *and* the sshfs `/Users` mount ride it.
  When it goes away the host loses all three while the VM and containers keep
  running perfectly. Twice so far (2026-08-17, 2026-09-03). Detection is
  [`../mini-metrics/forward-watchdog.sh`](../mini-metrics/forward-watchdog.sh);
  the recovery and the full analysis are in
  [the recovery runbook](../../docs/recipes/colima-lima-forwarding-recovery.md).
- **`vmType: qemu` is the current choice, not a hardware limit.** An earlier note
  said vz is Apple-Silicon-only; that is false — the `claude` account's colima
  runs `vmType: vz`, `mountType: virtiofs` on this Intel mini (since 2026-10-08).
  Moving the production VM to vz is untested.
- **No `KeepAlive` on the colima daemon** — `colima start` is one-shot, so
  KeepAlive would restart-loop it. Nothing supervises the engine afterwards.
- **The VM is oversubscribed** — a 20 GB guest on a 32 GB host that also runs dev
  workloads. Revisit `memory:` once dev moves off the box.

## Not covered here

OS-level prerequisites that no script can create: Xcode Command Line Tools,
Homebrew, the age key, FileVault-off, and the `pmset` power settings. (Tailscale
is installed manually, but keeping it UP with no login session is handled by
[`../tailscale/`](../tailscale/README.md) — see that README for why a LaunchAgent
was not enough.) See the Prerequisites table in
[`../README.md`](../README.md).
