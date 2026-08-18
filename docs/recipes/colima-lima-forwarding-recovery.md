# colima / lima host↔VM forwarding — why it breaks, how to recover

**Applies to:** the Mac mini (`homelab`), which runs the whole observability +
LLM-gateway stack as Docker containers inside a **colima** VM.

**TL;DR:** After a network transition (internet outage, link flap, sleep/wake)
the Mac host can lose its connection *into* the VM — the `docker` CLI, all
published loopback ports, and the metrics collectors go dead — **while every
container keeps running and every tailnet TLS node stays up for real
consumers.** The reliable fix is a **graceful `colima restart`**. The durable
fix is to stop depending on the host forward for anything that matters (see
[Make it more resilient](#make-it-more-resilient)).

---

## What colima and lima actually are

macOS cannot run Linux containers natively, so:

- **colima** ("Containers on Lima") runs Docker inside a **Linux VM** on the Mac.
- **lima** ("Linux Machines") is the layer colima sits on. It manages the QEMU
  VM *and* the bridge between the Mac host and the guest VM.
- On this box the VM runs under the **`_dockerhost`** service account; the docker
  socket lives at `/var/_dockerhost/.colima/default/docker.sock`, and a root
  **socat relay** (`com.homelab.docker-relay`) republishes it at the standard
  `/var/run/docker.sock` so tooling finds it.

### The fragile part: the host↔VM bridge rides on SSH

lima forwards two kinds of things **from the guest VM to the Mac host over an
SSH connection** (an SSH `ControlMaster` mux held open by the lima *hostagent*):

1. **The docker socket** — guest `/var/run/docker.sock` →
   host `/var/_dockerhost/.colima/default/docker.sock`. This is how the host
   `docker` CLI (and the socat relay) talk to the VM's dockerd.
2. **Every published container port** — a container publishing `127.0.0.1:4001`
   is reachable on the *Mac host's* `127.0.0.1:4001` only because lima forwards
   it. Same for `:8428` (VM), `:3000` (Grafana), `:9189` (the LiteLLM postgres
   exporter), `:9110-9112` (delivery workers), etc.

That SSH connection runs over QEMU's usermode network. **Any network transition
can drop or half-open it:** an internet outage, a Wi-Fi/Ethernet flap, a VPN
change, or a sleep/wake. When the TCP half-opens (the OS still thinks it's
alive), the hostagent keeps reusing the dead mux; new forward commands silently
fail and existing forwards stop relaying. **The VM and containers are
unaffected — they live entirely inside QEMU — but the host loses its window into
them.** In practice the hostagent does **not** reliably rebuild the forwards on
its own after a half-open break (confirmed 2026-08-18: cycling the SSH master +
`colima ssh` reconcile did **not** restore them; only a restart did).

---

## Symptoms — how to recognise this specific failure

The tell is **"the containers are fine but the host can't see them,"** and
crucially **real consumers are unaffected**:

| Signal | State when this breaks |
|---|---|
| `sudo -u _dockerhost … docker ps` (host CLI) | `Cannot connect to the Docker daemon at …/docker.sock` |
| Host loopback ports (`127.0.0.1:4001/:8428/:3000/:9189`) | `HTTP 000` (connection refused / timeout) |
| **`up{job="litellm-postgres"}` in VM** | **absent → "LiteLLM gateway down" alert FALSE-fires** |
| `container_cpu_percent{box="mini"}` / `container_uptime_seconds{box="mini"}` | stale / absent (host mini-metrics collectors are dead) |
| Delivery-worker board | stale (scraped via forwarded `:9110-9112`) |
| **`colima status` (as `_dockerhost`)** | **"colima is running"** — the VM is fine |
| **dockerd inside the VM** | **`active`, all containers `Up`** |
| **TLS nodes from another device** (`https://litellm.tail…ts.net/…`) | **`200` — consumers never noticed** |

> The false **"LiteLLM gateway down"** alert is the classic mis-read. The alert
> watches `up{job="litellm-postgres"}` as a dead-man's switch, and alloy scrapes
> that exporter via `host.docker.internal:9189` — a *forwarded* port. The forward
> dies → the metric vanishes → the alert fires, **even though LiteLLM is healthy
> and serving.** Always confirm litellm from a *different* tailnet device before
> believing it's down.

### Why the TLS nodes survive (and consumers don't notice)

The per-service `*.tail6d0ed4.ts.net` nodes are **caddy-tailscale (tsnet)**
endpoints running *inside* the caddy container. Each joins the tailnet directly
over WireGuard — external traffic reaches them **without touching the Mac host's
lima forwards**. So litellm/grafana/glitchtip/vm stay reachable for the fleet,
prod telemetry, and apps throughout the outage. (Note: from the mini *host
itself*, curling its own `*.ts.net` node can return `000` due to tailnet
hairpin routing — that is **not** a reliable health signal. Test from the DGX or
another device.)

---

## Diagnose (copy-paste, run from your Mac)

```sh
ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab '
  export PATH=/usr/local/bin:$PATH
  DHENV="sudo -u _dockerhost env HOME=/var/_dockerhost PATH=$PATH"
  echo "-- VM alive? --";        $DHENV colima status
  echo "-- dockerd inside VM --"; $DHENV colima ssh -- sh -c "sudo systemctl is-active docker; sudo docker ps -q | wc -l"
  echo "-- host CLI (this is what breaks) --"; $DHENV docker ps >/dev/null 2>&1 && echo OK || echo "HOST SOCKET DEAD"
  echo "-- forwarded loopback ports --"
  for p in 4001 8428 3000 9189; do
    echo "  :$p -> HTTP $(curl -s -m4 -o /dev/null -w "%{http_code}" http://127.0.0.1:$p/ 2>/dev/null)"
  done'
# consumer reality check — from ANOTHER tailnet device (not the mini):
ssh ops@dgx-llm-1 'curl -s -m8 -o /dev/null -w "litellm TLS: %{http_code}\n" https://litellm.tail6d0ed4.ts.net/health/liveliness'
```

If the VM + dockerd are up, the host socket is dead, loopback ports are `000`,
**but** the DGX sees litellm `200` → this is the lima-forwarding break. Recover:

## Recover — graceful `colima restart`

The nudge (cycling the SSH master) is worth ~10s but usually fails. The reliable
fix is a restart. Use **`colima restart`, never `launchctl kickstart -k`** — the
`-k` SIGKILLs QEMU, which is an unclean power-off and **risks postgres/clickhouse
corruption**. `colima restart` does a graceful guest shutdown (QMP
`system_powerdown`, containers get SIGTERM) then boots and re-establishes every
forward.

```sh
ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab '
  export PATH=/usr/local/bin:$PATH
  sudo -u _dockerhost env HOME=/var/_dockerhost PATH=$PATH colima restart'
```

- **~1.5 min end to end.** Bounces all containers → a brief blip and some lost
  in-flight prod telemetry (glitchtip / vm / umami) during the window. This is a
  **shared-state action — get operator approval per instance.**
- The `com.homelab.colima` launchd job is `RunAtLoad` only (no `KeepAlive`), so a
  manual `colima restart` does **not** race launchd.
- **Boot order:** `vm:8428` and the exporters come back in seconds; **litellm and
  grafana take ~30-60s more** to listen — a transient `000` on `:4001`/`:3000`
  right after restart is normal, keep polling.

### Post-restart validation

```sh
ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab '
  export PATH=/usr/local/bin:$PATH
  DHENV="sudo -u _dockerhost env HOME=/var/_dockerhost PATH=$PATH"
  $DHENV docker ps --format "{{.Names}}" | wc -l          # expect ~29
  curl -s -m5 -o /dev/null -w "litellm :4001 %{http_code}\n" http://127.0.0.1:4001/health/liveliness
  pgrep -f "mini-metrics/push.sh" >/dev/null && echo "mini-metrics collector: up"'
# from the DGX: consumers + the dead-man's switch recovered
ssh ops@dgx-llm-1 '
  curl -s -m8 -o /dev/null -w "litellm TLS %{http_code}\n" https://litellm.tail6d0ed4.ts.net/health/liveliness
  curl -s -m8 "https://vm.tail6d0ed4.ts.net/api/v1/query" --data-urlencode "query=up{job=\"litellm-postgres\"}"'
```

Green = litellm `200` from the DGX, `up{job="litellm-postgres"}` back to `1`
(the false alert clears), and `container_cpu_percent{box="mini"}` fresh again.

---

## Make it more resilient

Ranked by value. The first two remove the failure modes that actually hurt; the
rest reduce frequency or improve the signal.

1. **Scrape the critical exporters VM-internally, not via `host.docker.internal`.**
   *(highest value — kills the false-alert failure mode entirely)*
   alloy-homelab runs *inside* the VM, yet it scrapes the LiteLLM postgres
   exporter and the delivery workers by bouncing out to the Mac host's forwarded
   ports (`host.docker.internal:9189`, `:9110-9112`). Point it at the exporter
   **containers directly over the docker network** (by container name) so the
   dead-man's switch and delivery metrics survive any host-forward break. Config:
   `infra/observability/hosts/homelab/config.alloy`.

2. **A forward-health watchdog that auto-recovers.**
   A small launchd/cron probe on the mini: if the host docker socket is dead
   **but** `colima status` says the VM is up, run `colima restart` (optionally
   only after it's been dead > N minutes). Turns a manual, hours-later fix into
   an automatic, minutes-later one. Bounces containers, but only when already
   broken.

3. **Alert on the break itself, not on its shadow.**
   Add an alert for "host docker socket / forwarded ports unreachable while the
   VM is up." Today the *only* signal is a **false** "LiteLLM down" alert, which
   points at the wrong thing. A dedicated signal names the real cause.

4. **Reduce the triggering transitions.**
   Wired Ethernet over Wi-Fi, a stable uplink, and keeping the Mac awake
   (`caffeinate` — already holding sleep off) cut how often the SSH mux flaps.
   Doesn't eliminate internet outages, but lowers the rate. Ties into the
   headless-server work (`docs/wip/mac-mini-headless-server.md`).

5. **No clean lighter recovery exists today.**
   lima has no supported "re-forward without restarting the VM"; cycling the SSH
   master did not rebuild the forwards (tested 2026-08-18). Until that changes,
   `colima restart` is the recovery. (vz/virtiofs is more robust than
   qemu+sshfs, but vz is Apple-Silicon-only — this mini is Intel x86_64, so QEMU
   is the only path here.)

---

## Incident of record

- **2026-08-18** — A ~1-hour internet outage half-opened the lima SSH mux; the
  host↔VM forwards died and did not self-heal. Presented as a **"LiteLLM gateway
  down"** alert. LiteLLM was healthy the whole time (`200` via its TLS node from
  the DGX); the real breakage was the vanished `up{job="litellm-postgres"}`
  dead-man's-switch metric plus a dead host docker CLI, dead loopback ports, and
  stalled mini-metrics collectors. Sleep was ruled out (`caffeinate` had held
  sleep off for 97 h). A non-disruptive SSH-master nudge failed; a graceful
  `colima restart` restored everything in ~1.5 min.

## Related

- [Mac mini → observability host](mac-mini-observability.md)
- [Observability dependency & blast-radius map](../observability-dependency-map.md)
- [Consuming homelab services](consuming-homelab-services.md)
- Collector: `infra/mini-metrics/` · Self-monitor: `infra/observability/hosts/homelab/`
