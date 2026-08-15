# Mac mini → headless, login-less Docker server (WIP)

**Goal (operator, verbatim intent):** make the homelab Intel Mac mini a *truly
headless, login-less server* — **nobody logs in for Docker services to start**.
Docker must be a **centralized engine available to ALL users** (marko, the
`claude` workbench user, future users), not bound to any personal account.
Data is throwaway; only configs must survive.

Status date: 2026-08-14. Box: Intel Mac mini, tailnet `100.87.33.61`
(`homelab.tail6d0ed4.ts.net`), LAN `192.168.0.120` / `Mac-mini.local`,
brew prefix `/usr/local`.

---

## ⏭ RESUME NEXT SESSION (2026-08-14 EOD)

1. **Reverse-proxy migration — Phase 1 push is the immediate next action.**
   ACL edit is DONE but UNPUSHED: `~/Projects/podcast_scraper-infra/tailscale/
   policy.hujson` on branch `production` adds `9443` to the
   `autogroup:admin → tag:homelab-host` grant (see its diff). Needs operator
   go/no-go to push + PR → **merge to main auto-applies to the live tailnet**
   (`.github/workflows/tailscale-acl.yml`). After it applies: re-add
   `tailscale serve --bg --tcp=9443 tcp://127.0.0.1:8446`, then validate each
   service through Caddy over the tailnet via
   `curl -sk --resolve NAME.home:9443:100.87.33.61 https://NAME.home:9443/`
   (names/ports table under Phase 0). Then Phases 2–4.
2. **Tailscale headless swap — still paused.** Needs a fresh auth key + operator
   deletes old `homelab` node. Do the exposure migration FIRST (cheaper swap).
3. **Uncommitted / ungitted (need push approval):** `infra/reverse-proxy/`
   (Caddy stack — on mini + local repo, not committed), and the
   `infra/homelab-home/docker-compose.yml` tailnet-port edit.

## DONE + verified (this session)

### Docker engine: OrbStack → colima under a service account
- **OrbStack fully uninstalled**: app, `dev.orbstack.OrbStack.privhelper`
  LaunchDaemon, per-user data, and the hijacked `/usr/local/bin/docker`,
  `docker-compose`, `docker-buildx` symlinks all removed. (One SIP-protected
  leftover that even root can't delete without Full Disk Access:
  `~/Library/Group Containers/HUAQ24HBR6.dev.orbstack` — inert, not touching
  docker.)
- **Engine = colima (qemu backend) owned by a dedicated hidden service account
  `_dockerhost`** (UID ~460, home `/var/_dockerhost`, `IsHidden`). Nothing
  bound to marko. Started with `--vm-type qemu --cpu 8 --memory 20 --disk 100`
  and `--mount <repo>:w --mount /Users/markodragoljevic/umami:w`.
  **Later widened to one `/Users` (writable) mount** in
  `/var/_dockerhost/.colima/default/colima.yaml` (backup `.bak`) so bind-mounts
  from ANY user reach the VM — fixed the `claude` user's `run-local-stack.sh`
  serving an empty `/corpus` (`/api/corpus/feeds` → `[]`); a container now sees
  the 9-feed corpus. Persists across restart/boot (colima re-reads the yaml).
- **Centralized shared socket**: `socat` relay LaunchDaemon publishes
  `/var/run/docker.sock` at mode `0666` → colima socket
  `/var/_dockerhost/.colima/default/docker.sock`. `DOCKER_HOST` set globally in
  `/etc/zshenv`. **Verified: marko AND claude both see all 28 containers**
  through the shared socket (`docker ps -q | wc -l` = 28 for each).
- **Docker CLI toolchain restored to brew** (OrbStack had hijacked it):
  `docker` 29.7.2, compose 5.4.0, buildx 0.36.1. Compose + buildx linked as
  **global** cli-plugins at `/usr/local/lib/docker/cli-plugins/` so every user
  (incl. `_dockerhost`) resolves `docker compose`. (Had to remove a dangling
  `cli-plugins -> /Applications/Docker.app/...` symlink first.)
- `_dockerhost` docker config stripped of `credsStore: osxkeychain` (dangling
  OrbStack helper; all images are public/local so no cred helper needed).
- `_dockerhost` granted recursive read ACL on the repo + umami so it can read
  the mode-600 `.env` files and bind-mounted configs.
- **All 8 stacks up (28 containers)**: observability/backend, glitchtip,
  langfuse, litellm, observability/hosts/homelab, homelab-home, delivery, umami.
  Health spot-checks: grafana `200`, homelab-home `401` (auth), litellm serves.

### Boot daemons + power (headless survival)
- `/Library/LaunchDaemons/com.homelab.colima.plist` — RunAtLoad, runs
  `colima start` as `_dockerhost`, `AbandonProcessGroup`. **Registered.**
- `/Library/LaunchDaemons/com.homelab.docker-relay.plist` — socat relay,
  RunAtLoad + KeepAlive. **Registered + running** (pid live, socket 0666).
- Containers use `restart: unless-stopped` → auto-up when the engine starts.
- **FileVault: DISABLED** (`fdesetup status` → Off) — was the hard blocker to
  login-less boot (it forced a disk-unlock password at every boot). Operator
  approved the security tradeoff (disk no longer encrypted at rest).
- Power: `pmset -a autorestart 1 sleep 0 disksleep 0 powernap 0` — auto-restart
  after power loss, never sleep.

### Access setup
- **Passwordless sudo for marko**: `/etc/sudoers.d/99-marko-nopasswd`
  (`markodragoljevic ALL=(ALL) NOPASSWD: ALL`) — operator installed it so the
  agent can run root ops over SSH. Revoke: `sudo rm /etc/sudoers.d/99-marko-nopasswd`.
- SSH from agent: `ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab`
  (bare-key selection avoids "Too many authentication failures").

---

## NOT DONE — the one open item: Tailscale is still login-dependent

**Problem:** the tunnel that provides remote reach (`100.87.33.61`) is up ONLY
because marko is logged in. Tailscale on the box is the **macsys** variant
(`/Applications/Tailscale.app`, `io.tailscale.ipn.macsys.network-extension`,
v1.98.9) driven by the GUI app under marko's login. **No boot LaunchDaemon, no
privileged helper** → on a login-less reboot the tunnel does NOT come up, and
with `autorestart 1` an unplanned power blip would bring the box back
**unreachable over the tailnet** (SSH/Remote Login itself survives; only the
tailnet path dies). LAN `192.168.0.120` is the operator's on-site fallback only.

**Why this is delicate:** it's the agent's only remote path in, and the operator
is often away — a bad swap could brick remote access until physical access.

### Two ways to make it headless (operator to decide later)

1. **"Run unattended" on the existing macsys app** — reuses the current node,
   IP, serve config, keychain identity; zero reset, no key. BUT it's a GUI menu
   toggle with **no reliable headless command** — operator must click it at the
   Mac (or via screen share). Lowest blast radius.

2. **Swap to standalone brew `tailscaled` boot daemon** (brew tailscale 1.102.2
   already installed, incl. `tailscaled` + a LaunchDaemon plist). True headless
   daemon. Operator picked this path in-session, then paused. Consequences:
   - The node identity is **keychain-locked** to the app (System Keychain items
     `tailscale-machinekey`, `tailscale-id-profile-3609`, `-current-profile`,
     `-profiles`; on-disk `/Library/Tailscale/profile-data/3609/` holds only a
     netmap cache). NOT portable → the new daemon must **re-auth with a fresh
     auth key** (mint at login.tailscale.com → Settings → Keys).
   - New node ⇒ **new tailnet IP** and **`tailscale serve` config resets**. If
     the operator **deletes the old `homelab` node** when minting the key, the
     new daemon reclaims the name `homelab` → **service URLs
     (`homelab.tail6d0ed4.ts.net/...`) stay identical** and the agent reconnects
     via MagicDNS FQDN regardless of IP.
   - The `serve` map must be re-applied after (full backup embedded below).

### Planned safe execution for option 2 (when resumed)
Detached **commit-or-rollback** script (nohup+caffeinate so an SSH drop doesn't
abort), needs: **(a) a fresh reusable auth key**, **(b) operator deletes old
`homelab` node** in the admin console. Steps:
1. Snapshot old IP; quit macsys app (`osascript quit app "Tailscale"` +
   `pkill /Applications/Tailscale.app`).
2. Write `/Library/LaunchDaemons/com.homelab.tailscaled.plist` (root, RunAtLoad,
   KeepAlive) → `tailscaled --state=/var/lib/tailscale/tailscaled.state
   --statedir=/var/lib/tailscale --socket=/var/run/tailscaled.socket`; bootstrap.
3. `tailscale --socket=... up --authkey=KEY --hostname=homelab --timeout=90s`.
4. Poll ≤90s for a `100.x` IP. **If none → ROLLBACK**: bootout the daemon,
   `open -a Tailscale` (marko is logged in) to restore the app/tunnel.
5. Re-apply serve (see backup). Reconnect via `homelab.tail6d0ed4.ts.net`.

Open risk if option 2: brew (open-source) `tailscaled` on macOS drives a utun as
root — inbound tailnet SSH works, but verify exit-node/subnet features if ever
needed. `tailscale serve` re-apply syntax (v1.102) is fiddly; mis-apply only
loses HTTPS exposure (re-runnable), not the tunnel.

### `tailscale serve` config backup (exact restore source)
Human-readable:
```
:443   /vm→8428  /home→8888  /vlogs→9428  /vtraces→10428  /grafana→3000  /litellm→4001  /glitchtip→8090
:10000 /→4001    :8443 /→4000   :8444 /→3001   :8445 /→8090
```
JSON (`tailscale serve status --json`):
```json
{
  "TCP": { "10000": {"HTTPS": true}, "443": {"HTTPS": true}, "8443": {"HTTPS": true}, "8444": {"HTTPS": true}, "8445": {"HTTPS": true} },
  "Web": {
    "homelab.tail6d0ed4.ts.net:10000": { "Handlers": { "/": {"Proxy": "http://127.0.0.1:4001"} } },
    "homelab.tail6d0ed4.ts.net:443":   { "Handlers": {
        "/glitchtip": {"Proxy": "http://127.0.0.1:8090"},
        "/grafana":   {"Proxy": "http://127.0.0.1:3000"},
        "/home":      {"Proxy": "http://127.0.0.1:8888"},
        "/litellm":   {"Proxy": "http://127.0.0.1:4001"},
        "/vlogs":     {"Proxy": "http://127.0.0.1:9428"},
        "/vm":        {"Proxy": "http://127.0.0.1:8428"},
        "/vtraces":   {"Proxy": "http://127.0.0.1:10428"} } },
    "homelab.tail6d0ed4.ts.net:8443":  { "Handlers": { "/": {"Proxy": "http://127.0.0.1:4000"} } },
    "homelab.tail6d0ed4.ts.net:8444":  { "Handlers": { "/": {"Proxy": "http://127.0.0.1:3001"} } },
    "homelab.tail6d0ed4.ts.net:8445":  { "Handlers": { "/": {"Proxy": "http://127.0.0.1:8090"} } }
  }
}
```

---

## Ideas to think about later (operator, 2026-08-14)

### Local DNS
Operator floated running local DNS. What it does / doesn't solve:
- **LAN-by-name already works today** via Bonjour/mDNS: `Mac-mini.local` →
  `192.168.0.120`, no setup. So on-site name resolution isn't the gap.
- A real **local DNS server** (dnsmasq / Pi-hole / Unbound / CoreDNS on the
  mini) buys: stable homelab service names (e.g. `grafana.home`,
  `litellm.home`) independent of any node IP, ad-blocking, split-horizon, and
  decoupling service URLs from Tailscale's `*.ts.net`.
- **Does NOT solve the agent's remote reconnection** — the agent is off-LAN, so
  local DNS is unreachable to it. Remote-by-name is what Tailscale **MagicDNS**
  (`homelab.tail6d0ed4.ts.net`) already provides, following the node across IP
  changes. Local DNS is *orthogonal* to the Tailscale-headless problem.

### "Update services to something more durable" (durable service exposure)
Operator's point: the current exposure via **`tailscale serve` is bound to the
node identity** — swap the node and it resets (see backup above). More durable
alternatives to consider so exposure survives node/IP churn:
- **Local reverse proxy** (Caddy / Traefik / nginx) on the mini terminating a
  stable local hostname → the 127.0.0.1:PORT services. Then `tailscale serve`
  (or Funnel) points at ONE upstream (the proxy) instead of 12 per-service
  rules — far less to re-apply on any node change, and it also works over LAN +
  local DNS without Tailscale.
- Pair with **local DNS** above: `*.home` names → proxy → services. Tailscale
  then just carries the tunnel; the proxy owns routing/TLS.
- Net: decouple "what's exposed" (durable, in a proxy config in git) from "how
  it's reached" (tunnel/DNS, swappable). Makes the pending Tailscale swap much
  cheaper (no 12-rule serve re-apply).

These are **exploration notes, not decisions** — revisit with the paused
Tailscale-headless work.

## PLAN — durable service exposure (parallel-run, service-by-service)

**Decision (operator 2026-08-14):** homelab is **Tailscale-only** (like the rest
of the fleet) — no public domain / no LAN-without-Tailscale need. So option 2
(public domain + Let's Encrypt) is out. In scope: **option 1** (per-service
subdomains via Tailscale **split DNS** + Caddy host-routing + internal-CA TLS)
as the end-state, reached via **option 3 mechanics** first (Caddy behind the
existing `tailscale serve`, nothing breaks) then cut over per service.

**Components (recommended):**
- **Caddy** reverse proxy — new compose stack `infra/reverse-proxy/`, Caddyfile
  **in git**. Owns all routing + internal-CA TLS. (Caddy > Traefik/nginx here:
  simplest config, auto internal CA.)
- **dnsmasq** (lightweight; Pi-hole only if you want an ad-block GUI) — answers
  `*.home` → mini's tailnet IP.
- **Tailscale split DNS** — admin console: route domain `home` → mini tailnet IP
  (the dnsmasq resolver). Makes `*.home` resolve for ALL tailnet clients.

**Backends (from serve backup):** grafana 3000, litellm 4001, vm 8428,
vlogs 9428, vtraces 10428, home(landing) 8888, glitchtip 8090, langfuse 4000,
umami 3001. The Next.js apps (langfuse/umami/glitchtip) + litellm currently need
**dedicated root TLS ports** (8443/8444/8445/10000) because they break under a
path prefix — **subdomain routing eliminates that hack entirely** (each gets a
clean root at `X.home`).

### Phases (each independently valuable + reversible; old path untouched until proven)

- **Phase 0 — Caddy in parallel, no cutover. ✅ DONE 2026-08-14.**
  `infra/reverse-proxy/` (compose + Caddyfile) added; Caddy host-routes every
  backend container-to-container over the stacks' docker networks (`backend_`,
  `litellm_`, `langfuse_`, `umami_`, `glitchtip_default`). Internal ports:
  grafana:3000, litellm:4000, victoriametrics:8428, victorialogs:9428,
  victoriatraces:10428, homelab-home:80, **glitchtip-web-1:8080** (not 8000),
  langfuse-langfuse-web-1:3000, umami:3000. Test ports `127.0.0.1:8081/8446`.
  Internal-CA root persisted in `caddy_data`. **Gate PASSED**: all 9 route
  through Caddy (302/200/401, zero 502) via `curl --resolve X.home:8446`. Old
  `tailscale serve` untouched (11 rules live); 29 containers total.
  NOT yet committed to git (files on mini's checkout + local repo; needs push
  approval). `.home` names not yet resolvable over the tailnet — that's Phase 2.
- **Phase 1 — expose Caddy over Tailscale. ⛔ BLOCKED by tailnet ACL (2026-08-14).**
  Two architecture facts locked in during this phase:
  - **colima only forwards published ports to the Mac's `127.0.0.1`** (can't bind
    the tailnet interface — same reason `100.87.33.61:8888` failed earlier). So a
    containerized Caddy MUST be bridged to the tailnet by `tailscale serve`; it
    can't listen on the tailnet directly. Chosen bridge = `tailscale serve
    --tcp=<port>` **TLS passthrough** → Caddy's HTTPS (Caddy keeps its internal-CA
    TLS + host-routing).
  - **The tailnet ACL only allows the existing serve ports.** Verified from
    markos-macbook-pro: `nc` → 443 OPEN, **9443 BLOCKED**; existing serve works
    (grafana 302, langfuse 200). Added a `--tcp=9443` passthrough, it was
    unreachable, removed it (serve back to 11 rules). Policy lives at
    `~/Projects/podcast_scraper-infra/tailscale/policy.hujson` (NOT edited — prod
    tailnet policy = operator per-instance approval; no TS API cred found to apply).
  - **Consequence for the plan:** true per-service *tailnet* parallelism needs
    ONE new ACL port. Without it, the tailnet cutover is a single reversible
    **:443 flip** (path-serve → Caddy passthrough) after split DNS is set —
    because 443 is already ACL-allowed and split-DNS `*.home → mini:443` lands on
    Caddy. Routing itself is already proven (Phase 0), so this is not a
    correctness risk, only a "how incremental" choice. **Awaiting operator fork
    (see below).**
- **Phase 2 — local DNS + split DNS + CA trust.** Stand up dnsmasq (`*.home` →
  mini tailnet IP); set Tailscale split DNS `home` → mini; export Caddy's root
  CA and trust it on your devices (laptop/phone). Gate: `grafana.home` resolves
  + serves through Caddy over the tailnet with a trusted cert.
- **Phase 3 — cut over service by service.** For each service: prove `X.home`
  works, THEN remove that service's old `tailscale serve` rule. One at a time.
  Suggested order: grafana first (low risk) → vm/vlogs/vtraces → home → litellm
  → langfuse/umami/glitchtip last (these shed their dedicated-port hacks).
- **Phase 4 — close the old way.** Only once ALL services are proven on
  `*.home`: remove remaining serve rules + the 8443/8444/8445/10000 dedicated
  ports. Exposure now = Caddy (git'd) + dnsmasq + split DNS.

**Rollback:** old serve rule for a service stays until that service is proven on
the new path; revert = re-add the one rule (full backup above). Phases 0–2 add
only; nothing is removed before Phase 3.

**Bonus — de-risks the paused Tailscale headless swap:** after this, a node swap
needs only *(a)* update the split-DNS nameserver IP (one place) — **no 12-rule
serve re-apply**. So do this exposure migration FIRST, then the headless
`tailscaled` swap becomes cheap + low-risk.

## ✅ EXPOSURE REDESIGNED → caddy-tailscale per-service nodes (2026-08-15)

Operator rejected both the `*.home`+internal-CA path (root-cert export) and any
public domain (homelab is general-purpose — orrery etc. — and tailnet-only). Final
design: **each service is its own tailnet node `<name>.tail6d0ed4.ts.net` via the
`caddy-tailscale` plugin, serving its own real Tailscale-issued cert.** No domain,
no internal CA, no split DNS, no dnsmasq — tailnet-only, works for anyone on the
tailnet. This supersedes the whole `*.home`/internal-CA/9443-passthrough plan.

**DONE + verified:**
- `infra/reverse-proxy/`: custom `Dockerfile` (xcaddy + caddy-tailscale),
  `Caddyfile` (9 `bind tailscale/<name>` sites), compose (no host ports; TS_AUTHKEY
  from `.env`, git-ignored). Image `caddy-tailscale:local`.
- ACL: `tag:homelab-svc` + `autogroup:admin → tag:homelab-svc:443` merged (PR #1663,
  applied). 9443 grant (PR #1662) now obsolete — trim later.
- Auth key (reusable, `tag:homelab-svc`) in mini `reverse-proxy/.env`. Node tsnet
  state persists in the `caddy_config` volume → survives restart without re-auth.
- **9 nodes live w/ real trusted certs** (`tls_verify=0`): grafana.ts.net 302,
  vm/vlogs/vtraces/litellm/langfuse/umami/glitchtip 200, hub 401. First hit per
  name is slow (on-demand cert mint), cached after.

**Remaining Level-1:**
- Rewrite homepage (`homelab-home` / hub) link inventory → `*.tail6d0ed4.ts.net`.
- Set UI-only app base URLs: Grafana `GF_SERVER_ROOT_URL=https://grafana.tail6d0ed4.ts.net`
  (serve_from_sub_path already false); vm/vlogs/vtraces/litellm serve at root (minimal).
- HOLD langfuse/umami/glitchtip base-URL changes for Level 3 — their URL setting is
  shared UI+ingest, so moving them moves ingest too.

**Cleanup owed (at cutover):** old `tailscale serve` path/port rules on
tag:homelab-host (443 paths + 8443/8444/8445/10000) + the `--tcp=9443` passthrough +
the 9443 ACL grant. Old access still live in parallel until each service is cut over.
Auth key can be revoked once nodes proven stable (state persisted).

## Committed to origin/main (2026-08-15, "commit everything minus secrets")

Repo is now the reproducible inventory — `git clone` + per-box `.env` restores a box:
- Caddy reverse-proxy stack + `.env.example`, homepage `gen.sh` (per-service URLs),
  workstation edits, homelab-home colima port fix, this doc.
- **delivery**: podcast tenant outbox synced to the deployed prod value
  (`100.124.111.115:8099`); **podcast-dev tenant added + ACTIVE** — a twin that
  drains the local dev player-api outbox (`127.0.0.1:8092`) alongside prod so dev +
  prod deliver simultaneously. Reuses podcast's `PODCAST_*` secrets + templates +
  schema (symlinks `delivery/templates/podcast-dev` and `schema/podcast-dev` →
  podcast). Delivery config is BAKED into the image (Dockerfile COPYs tenants.yaml +
  delivery/), read from `/app/tenants.yaml` — so activating needed an **image
  rebuild**, not a bind-mount edit. Rebuilt + recreated on the mini; both workers
  live. When `:8092` is down the podcast-dev worker logs a caught connection-refused
  each poll (VLogs noise only — no alert: `delivery-worker-down` watches
  `up{job=delivery}` per channel; liveness is process-based; no error metric).

Note: `.env` (secrets) stays gitignored on each box. Delivery templates ARE in git
(`delivery/delivery/templates/`), earlier "not in git" was a wrong-dir read.

## Other open items (non-blocking)
- **Reboot test NOT performed** (operator declined). It's the only way to *prove*
  headless survival — but pointless/risky until Tailscale option is resolved,
  since a login-less reboot today loses the tailnet path.
- **git**: `infra/homelab-home/docker-compose.yml` has an uncommitted edit
  (commented out the `100.87.33.61:8888:80` tailnet-IP port bind — colima can't
  bind arbitrary host IPs; kept `127.0.0.1:8888:80`). Needs commit + push
  approval.
