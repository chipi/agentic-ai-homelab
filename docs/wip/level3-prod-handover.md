# Level 3 — Prod handover (homelab exposure migration)

**To:** the prod agent (has prod VPS access + the deploy pipeline).
**From:** the homelab agent (mini + shared repos; **no prod VPS access**).
**Context:** we moved homelab observability off plaintext raw ports onto per-service
**caddy-tailscale nodes** with real Tailscale certs — `vm./vlogs./grafana./litellm./
langfuse./umami./glitchtip./vtraces./hub.tail6d0ed4.ts.net`. Levels 0–2 done (homelab
dashboards + DGX telemetry migrated + verified). **Level 3 = move prod's telemetry the
same way, then retire the raw ports.** Full history: `docs/wip/mac-mini-headless-server.md`.

This doc splits **what I already did / can do** from **what only you can do on prod**,
and specifies the GitOps workflow to build. It is written to be handed off verbatim.

---

## The split

### ✅ Done by me (homelab side — no prod touch, non-breaking)
- **Nodes ready to receive every prod ingest type** — verified they route through Caddy:
  - `vm.tail6d0ed4.ts.net/api/v1/import/prometheus` (and `/api/v1/write`) → **204**
  - `vlogs.tail6d0ed4.ts.net/insert/loki/api/v1/push` → **204**
  - `glitchtip.tail6d0ed4.ts.net/api/1/envelope/` → **403** (reached GlitchTip auth, not a 404)
  - `umami.tail6d0ed4.ts.net/api/send` → **400** (reached Umami, not a 404)
- **ACL grant PR is open: chipi/podcast_scraper#1665** — adds `tag:prod` to the
  `tag:homelab-svc:443` grant. Additive/non-breaking. **You merge it as step 1** (it also
  gives prod netmap visibility so MagicDNS resolves the node names — they're NXDOMAIN on a
  box until the grant applies; that's ACL-gated, confirmed on the DGX).

### 🔓 Only you can do (prod VPS box-side — I have no prod SSH key)
The prod push endpoints are **box-only bootstrap values**, not in the GitOps config layer:
- **Alloy** `REMOTE_WRITE_URL` / `LOGS_WRITE_URL` live in `/opt/vps-observability/.env`
  (`BOOTSTRAP_PREREQUISITES.md` line ~77; `deploy-prod.yml` comment: *"the
  /opt/vps-observability Alloy container owns REMOTE_WRITE_URL/LOGS_WRITE_URL; nothing staged
  into .env here"*). `deploy-config.yml` deploys `config.d/*.alloy` **drop-ins**, not this `.env`.
- **GlitchTip/Umami ingest** flows app → prod Caddy telemetry/analytics vhosts →
  `GLITCHTIP_UPSTREAM` (box-side Caddy env) → homelab (ADR-129). Same class of box-only value.

**⚠ Verify my analysis** — I cannot see the prod box. Confirm the actual contents of
`/opt/vps-observability/.env` and whether a deploy path I couldn't see already manages it.

---

## Prod agent tasks (ordered)

### 1. Merge ACL PR #1665
`acl` check will pass; snyk is the quota-red (not a real fail). Merge → GitOps apply. After
apply, confirm from prod: `getent hosts vm.tail6d0ed4.ts.net` resolves, and
`curl -s -o /dev/null -w '%{http_code} %{ssl_verify_result}' --data-binary 'p 1' https://vm.tail6d0ed4.ts.net/api/v1/import/prometheus` → `204 0`.

### 2. Build the GitOps workflow for the vps-observability `.env` (the operator wants this)
Make the Alloy endpoints GitOps-managed instead of bootstrap-manual. **Design:**
- Add a repo-tracked, **non-secret** values file, e.g. `infra/observability/vps-observability.endpoints.env`:
  ```
  REMOTE_WRITE_URL=https://vm.tail6d0ed4.ts.net/api/v1/write
  LOGS_WRITE_URL=https://vlogs.tail6d0ed4.ts.net/insert/loki/api/v1/push
  ```
- Add a `workflow_dispatch` workflow (or extend `deploy-config.yml`) that, using
  `secrets.PROD_SSH_PRIVATE_KEY`, **surgically upserts those keys** into
  `/opt/vps-observability/.env` (don't overwrite the whole file — it has other bootstrap
  values), then **recreates the alloy container**. Skeleton:
  ```yaml
  # .github/workflows/deploy-vps-observability-env.yml
  on: { workflow_dispatch: { inputs: { dry_run: { type: boolean, default: true } } } }
  jobs:
    deploy:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: ./.github/actions/prod-ssh-key
          with: { ssh_private_key: ${{ secrets.PROD_SSH_PRIVATE_KEY }} }
        - run: |
            scp -i "$SSH_PROD_IDENTITY" -o IdentitiesOnly=yes \
              infra/observability/vps-observability.endpoints.env "$SSH_TARGET":/tmp/obs.env
            ssh -i "$SSH_PROD_IDENTITY" -o IdentitiesOnly=yes "$SSH_TARGET" '
              set -e; F=/opt/vps-observability/.env; cp "$F" "$F.bak-$(date +%s)"
              while IFS="=" read -r k v; do [ -z "$k" ] && continue
                if grep -q "^$k=" "$F"; then sed -i "s#^$k=.*#$k=$v#" "$F"; else echo "$k=$v" >> "$F"; fi
              done < /tmp/obs.env
              cd /opt/vps-observability && docker compose up -d alloy'   # RECREATE, not HUP
  ```
- **CRITICAL:** the endpoint is an **env var** → a running Alloy will NOT pick it up on
  `docker kill -s HUP alloy` (HUP reloads config files, not `env_file`). You must **recreate**
  the container (`docker compose up -d alloy` / `docker restart` won't reload env either on
  some setups — use `up -d`). This is how I repointed the DGX. `deploy-config.yml`'s HUP is
  fine for drop-ins but NOT for this `.env` change.

### 3. Repoint prod Alloy → TLS nodes
Set in `/opt/vps-observability/.env` (via the workflow above, or by hand first to de-risk):
- `REMOTE_WRITE_URL=https://vm.tail6d0ed4.ts.net/api/v1/write`
- `LOGS_WRITE_URL=https://vlogs.tail6d0ed4.ts.net/insert/loki/api/v1/push`
Then recreate alloy. (Back up the old `.env` first — `cp .env .env.bak-*`.)

### 4. (Coordinated with me) GlitchTip / Umami ingest → nodes
Prod-side: repoint the Caddy telemetry/analytics upstreams (`GLITCHTIP_UPSTREAM` and the
Umami upstream) from the raw homelab endpoint to `glitchtip.tail6d0ed4.ts.net` /
`umami.tail6d0ed4.ts.net`. **This is coupled to a homelab-side change I must make in sync**
(GlitchTip's `GLITCHTIP_DOMAIN` on the mini drives CSRF/ALLOWED_HOSTS + the DSN, so the new
Host must be allowed). **Do NOT do GlitchTip alone** — ping me and we flip both together, or
we sequence it as its own mini-step. (Umami has no server-side host binding, lower risk.)

**✅ HOMELAB SIDE DONE (2026-08-16):** on the mini I set `GLITCHTIP_DOMAIN=https://glitchtip.tail6d0ed4.ts.net`
and wired `CSRF_TRUSTED_ORIGINS=https://glitchtip.tail6d0ed4.ts.net,https://homelab.tail6d0ed4.ts.net:8445`
(new node + old serve port, so UI login works on both during the flip), recreated web+worker.
Verified: UI `GET / → 200` (real cert, `ssl_verify=0`); ingest `POST /api/1/envelope/ → 403
{"detail":"Denied"}` = DSN-auth reject, **host accepted** (not DisallowedHost). `ALLOWED_HOSTS`
defaults to `["*"]` so the current raw `:8090` path keeps working until you flip — **no breakage
window.** Prod agent: flip `GLITCHTIP_UPSTREAM` → `https://glitchtip.tail6d0ed4.ts.net` (the node
speaks TLS, so `reverse_proxy https://glitchtip.tail6d0ed4.ts.net` — no `header_up Host` needed,
`ALLOWED_HOSTS=*`), `systemctl restart caddy`. Umami flips independently (no host binding).

### 5. Verify prod telemetry lands on the nodes (same as I did for DGX)
From anywhere on the tailnet:
```
curl -s "https://vm.tail6d0ed4.ts.net/api/v1/query?query=count({instance=\"<prod-instance>\"})"
curl -s "https://vlogs.tail6d0ed4.ts.net/select/logsql/query?query={cluster=\"prod\"}&limit=1&start=2m"
```
Fresh timestamps (age < 90s) = flowing. Check prod Alloy logs for no remote_write/TLS errors.

---

## After prod is migrated — cleanup (I own this, on the mini)
Only once BOTH DGX (done) and prod push to the nodes:
1. Retire the old `tailscale serve` path/port rules (443 paths + 8443/8444/8445/10000) + the
   `--tcp=9443` passthrough.
2. Close the raw `0.0.0.0` ports — set `*_LISTEN=127.0.0.1` in the mini stacks' `.env` and
   recreate (VM/VLogs/VTraces/Umami/GlitchTip/Langfuse/Grafana). This is what shrinks the
   plaintext attack surface — **the whole point of the migration.**
3. ACL trims: remove the temporary `9443` grant; trim the now-unused ports from the
   `tag:homelab-host` grant.
4. Revoke the caddy-tailscale auth key (`tag:homelab-svc`) — nodes keep running (state
   persisted); operator does this in the Tailscale admin console.

**Do NOT close the raw ports before prod is migrated — it would drop prod telemetry.**

---

## Rollback (per prod change)
- Alloy: restore `/opt/vps-observability/.env.bak-*` + recreate alloy. Old raw endpoint stays
  valid the whole time (raw ports not closed until cleanup), so revert is instant + lossless.
- ACL #1665: additive; revert = drop the `tag:prod` src from the grant (another PR).
- GlitchTip/Umami upstream: restore the prior Caddy env value + reload.

## SEPARATE prod bug — LiteLLM→Langfuse tracing is very likely also dead
Not part of the TLS migration, but prod-side + urgent. The colima migration reseeded the
homelab Langfuse with fresh volumes → only the `agents` project survived (the homelab
LiteLLM was silently 401'ing for 3h; I fixed it by syncing its keys to Langfuse's seeded
`LANGFUSE_INIT_PROJECT_*` pair). **Prod's LiteLLM targets a `litellm-vps` Langfuse project
(`deploy-litellm.sh`) that no longer exists** → prod's keys point at a dead project → prod
LLM tracing is almost certainly silently 401'ing too (LiteLLM logs nothing).

**Fix (your call on the model):**
- **Consolidate (simplest):** point prod's LiteLLM `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` at the
  live `agents` pair (`infra/langfuse/.env` `LANGFUSE_INIT_PROJECT_PUBLIC_KEY`/`SECRET_KEY`)
  and redeploy litellm. Prod + homelab traces share one project (tag per gateway if you want
  them split in the UI).
- **Separate project:** recreate a `litellm-vps` project in Langfuse (UI, or the admin API
  with `LANGFUSE_INIT_USER_*` creds) + new keys → set them on prod → redeploy.
- Verify: `curl -u $PK:$SK http://homelab:4000/api/public/projects` → 200, then a call
  through the prod gateway lands a trace.

**✅ DONE (2026-08-15):** `infra/langfuse-check/prod.env` is written and
`langfuse_export_up{gateway="prod"}=1` is verified live in VictoriaMetrics — i.e. prod's
Langfuse keys are valid, so **prod LiteLLM→Langfuse tracing is already working** and now
alerted. No further action on this item.

**(Reference — how it was wired:)** drop prod's Langfuse keys
into the mini's `infra/langfuse-check/prod.env` (gitignored):
```
PROD_LF_PUBLIC_KEY=pk-lf-...
PROD_LF_SECRET_KEY=sk-lf-...
```
The `com.homelab.langfuse-check` daemon then also emits `langfuse_export_up{gateway="prod"}`
and the `langfuse-export-down` alert covers prod too. (Send me the keys and I'll place the
file — or you drop it on the mini.)

## Open questions for you to confirm (I couldn't, no prod access)
1. Full contents of `/opt/vps-observability/.env` — anything besides the two URLs? (affects
   surgical-upsert vs template).
2. Exact env var names for the Caddy telemetry/analytics upstreams (`GLITCHTIP_UPSTREAM` +
   the Umami one) and where they're set on the box.
3. Whether the prod Alloy is `docker compose`-managed at `/opt/vps-observability` (assumed) so
   `docker compose up -d alloy` is the right recreate command.
