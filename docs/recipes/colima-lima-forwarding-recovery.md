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
| `mini_container_cpu_percent` / `container_uptime_seconds{box="mini"}` | stale / absent (host mini-metrics collectors are dead) |
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
(the false alert clears), and `mini_container_cpu_percent` fresh again.

---

## Make it more resilient

Ranked by value. The first two remove the failure modes that actually hurt; the
rest reduce frequency or improve the signal.

1. **Scrape the critical exporters VM-internally, not via `host.docker.internal`.** — ✅ **DONE (2026-08-18)**
   *(highest value — kills the false-alert failure mode entirely)*
   alloy-homelab runs *inside* the VM but used to scrape the LiteLLM postgres
   exporter and the delivery workers by bouncing out to the Mac host's forwarded
   ports (`host.docker.internal:9189`, `:9110-9112`) — so a forward break vanished
   those metrics and false-fired the gateway-down alert. Now alloy joins
   `litellm_default` + `delivery_default` and scrapes the **containers directly by
   name** (`litellm-postgres-exporter:9187`,
   `delivery-{email,push,events}:{9110,9111,9112}`), immune to any host-forward
   break. (node_exporter stays on `host.docker.internal:9100` — it's a *native* Mac
   process, not a container.) Config:
   `infra/observability/hosts/homelab/{config.alloy,docker-compose.yml}`.

2. **A forward-health watchdog.** — 2a ✅ **DONE (2026-08-18)** · 2b opt-in
   - **2a (notify-first — DONE):** `infra/mini-metrics/forward-watchdog.sh` (launchd
     `com.homelab.forward-watchdog`) proves `docker ps` every 30s and heart-beats
     `mini_forward_up=1` over the *forwarded* `:8428`. Because the heartbeat rides
     the same forward, it stops the instant the forward breaks → the
     `mini-forward-down` alert fires (#3). Detect-only; it does **not** restart.
     **Auto-capture (added 2026-09-03):** on the FIRST failed probe of a break it
     dumps `/tmp/forward-break-<ts>.txt` — `ha.stderr.log` tail, `serial.log`
     OOM/panic grep, relay-log tail, `colima status`, and guest zombie census /
     top / dockerd / container list — **before** any recovery. The recovery
     itself (`colima restart`) recreates `ha.stderr.log`, which is exactly why
     the trigger was unidentifiable after *both* the 2026-08-18 and 2026-09-03
     breaks. Captures once per break (marker file, cleared when the forward
     returns); every guest probe is timeout-bounded so a wedged guest cannot
     stall the heartbeat loop.
   - **2b (auto-restart — opt-in, NOT enabled):** upgrade the watchdog to run
     `colima restart` itself when the socket is dead > 5 min **and** the VM is up,
     with a cooldown so a flapping network can't restart-loop, logging each action.
     Left opt-in because auto-running a container-bouncing restart on shared infra
     is a standing pre-authorization of a disruptive action — enable only once 2a's
     signal has proven trustworthy in practice.

3. **Alert on the break itself, not on its shadow.** — ✅ **DONE (2026-08-18)**
   `mini-forward-down` in `infra/observability/backend/grafana/provisioning/alerting/rules.yaml`
   is a dead-man's switch (same pattern as `dgx-silent`): fires `warning` when
   `mini_forward_up` has no samples for 5m — `kind:infra`, routed to the operator
   email surface. Replaces the misleading false "LiteLLM down" alert with a signal
   that names the real cause and links this runbook.

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

- **2026-09-03** — **Second occurrence, ~5 h** (04:03 -> 09:07), recovered by a
  graceful `colima restart`. **Trigger still unidentified** (see below).

  **Timeline (from `/tmp/docker-relay.log`):**
  `04:00:40` first socat `Broken pipe` — the mux half-opens and established
  forwards start failing mid-write; three more at `04:01:43`, `04:02:08`,
  `04:02:35`; `04:03:16` flips to `Connection refused` — the forwarded socket
  stops accepting entirely; `04:04` last `instance="homelab"` metric sample;
  `~04:08` `mini-forward-down` fires.

  **Blast radius, measured — a host control-plane outage, NOT a service outage.**
  Broke: the host `docker` CLI; every host loopback port
  (`:3000/:8428/:8090/:3001/:4000/:4001/:9428/:10428/:8888`); the host collectors
  (mini-metrics, dgx-scrape, forward-watchdog); the socat relay's upstream.
  Kept serving throughout: `dockerd` `active` with all 28 containers `Up`; every
  caddy tsnet node (all 9 Caddyfile upstreams are *container names*, so the
  consumer path never touches the host forward); DGX + prod-podcast telemetry
  ingest (continuous, zero gap 03:50-04:20 and beyond). Caddy's 502 rate was
  **lower** during the outage (11 in 5 h = 2.2/h) than in the 2.8 h before it
  (11 = 3.9/h) — i.e. no consumer-visible degradation.
  *Diagnostic trap:* probing from the Mac host measures the exact plane that is
  broken and makes a host-plane break look like a total outage. **Verify service
  health from another tailnet node** (e.g. the DGX) before concluding anything.

  **Detection worked as designed.** `mini-forward-down` fired within ~5 min and
  named the right cause; the 5 h was *response* time, not detection time. 2a's
  signal has now proven accurate on a real event — the precondition item **2b**
  was gated on.

  **The 2026-08-18 trigger did not reproduce.** No sustained network outage:
  `dgx-llm-1` (LAN) and `prod-podcast` (internet) both reported into
  VictoriaMetrics continuously across the break while only `instance="homelab"`
  stopped. Note also the mux is `ssh -p 50866 127.0.0.1` — host loopback into
  QEMU — which an external network transition does not traverse. A sub-minute
  blip stays possible (2 min metric resolution); operator context: laptop closed
  ~02:15, phone left the tailnet ~04:00 (time-correlates).
  Also **ruled out**: `db-backup` (runs 04:30, *after* the break); container /
  port-forward churn (`mini_docker_total` flat at **30** every 5 min,
  02:30-04:05) despite two other agents running Docker e2e tests on the box;
  guest resource exhaustion (guest disk 24 %, 13.5 G available, swap 0).

  **Guest state at diagnosis:** `lima-guestagent` pinned at **96.9 % CPU** with
  **109 zombies**; guest load 44 at 43.8 % idle; dockerd looping
  `"Could not send KILL signal to container process ... process already finished"`
  (health-probe `exec` reaping failing). After restart: **1 zombie**,
  guest-agent 11 %, load 3.1, host load 49 -> 8.

  **Open question — is the guest-agent livelock the *cause* or another symptom?**
  Unresolvable here: `ha.stderr.log` was recreated by the restart, so lima's own
  view of 04:00-04:03 is gone. **Capture it BEFORE restarting next time** — that
  is the one artifact that would settle the trigger.

  **Relay-noise note (for anyone reading `/tmp/docker-relay.log` in a panic):**
  the refusal storm (~2.75/s; ~50 k today, ~140 k on 2026-08-18) is simply
  *outage duration x normal polling rate* — mini-metrics (~9 docker calls per
  20 s loop), forward-watchdog (1 per 30 s), plus hub regen / langfuse-check /
  agent tooling, each failing instead of succeeding. socat logs only failures,
  so the ~3 k/day baseline is the same polling with a >98 % success rate. It is a
  **symptom, not a load problem** — a refused UNIX-socket connect costs
  microseconds and did not contribute to the qemu CPU. The real cost is that the
  log has no rotation (28 MB, ~10 MB per outage).

## Related

- [Mac mini → observability host](mac-mini-observability.md)
- [Observability dependency & blast-radius map](../observability-dependency-map.md)
- [Consuming homelab services](consuming-homelab-services.md)
- Collector: `infra/mini-metrics/` · Self-monitor: `infra/observability/hosts/homelab/`
