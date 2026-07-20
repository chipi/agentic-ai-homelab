# Runbook — empty Mac mini → running observability platform

Provision a fresh Mac mini as the permanent observability host (VictoriaMetrics/
Logs/Traces + Grafana + GlitchTip + Langfuse), replacing the DGX stopgap.
Decision + rationale: [ADR-0006](../adr/ADR-0006-mac-mini-observability-provisioning.md).

**What runs here:** the backend + GlitchTip + Langfuse.
**What does NOT:** the Alloy collector (Linux/GPU-specific — stays on the DGX).
**Data:** fresh start (no migration).

> ⚠️ **Mac-specific bits to validate on first boot** (untested until the mini
> exists): publishing container ports to the `utun` tailnet IP — if a port is
> healthy locally but tailnet peers time out, re-run bootstrap with
> **`BIND=0.0.0.0 ./infra/observability/bootstrap.sh`** (binds all interfaces —
> also LAN-exposed; rely on macOS firewall + the tailnet ACL). Also confirm
> OrbStack is set to start at login and restart containers after reboot.
>
> **Sizing:** the 2018 i7 mini with **32 GB** runs the full stack comfortably
> (~8–10 GB working set) — no staging needed. `bootstrap.sh` warns if RAM < 12 GB.

## 0. Prereqs (install once)

```sh
# Docker runtime — OrbStack (lighter/faster than Docker Desktop)
brew install orbstack           # then launch it once; enable "start at login"
brew install tailscale sops age git
```
- `tailscale up` — note the mini's tailnet IP (`tailscale ip -4`) and give it a
  memorable MagicDNS name (e.g. `obs`) in the Tailscale admin console.

## 1. Age key + secrets (once)

```sh
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt      # prints the age PUBLIC key (age1…)
```
- Back up `keys.txt` to your password manager — **without it the secrets can't be
  decrypted**.
- Put the public key into `.sops.yaml` (repo root, the `age:` field), commit.

```sh
git clone <repo> ~/agentic-ai-homelab && cd ~/agentic-ai-homelab
cp infra/observability/secrets.sops.env.example infra/observability/secrets.sops.env
$EDITOR infra/observability/secrets.sops.env    # fill every value (fresh + strong)
sops -e -i infra/observability/secrets.sops.env # encrypt in place
git add infra/observability/secrets.sops.env && git commit -m "secrets: mac mini obs (encrypted)"
```
Generators: passwords `openssl rand -hex 16`; keys `openssl rand -hex 32`
(`ENCRYPTION_KEY` = exactly 64 hex); Langfuse keys `pk-lf-$(uuidgen|tr A-Z a-z)`
/ `sk-lf-…`.

## 2. Bootstrap (repeatable)

```sh
./infra/observability/bootstrap.sh --dry-run    # writes .env files only, no containers
./infra/observability/bootstrap.sh              # decrypt → .env → compose up → verify
```
It decrypts the secrets, writes each stack's `.env` with this host's tailnet IP,
brings the three stacks up, health-checks them, and prints the ACL ports to grant.

## 3. Grant ACL ports

In the Tailscale admin console, grant to this host's tag:
`3000` (Grafana) · `8428` (metrics) · `9428` (logs) · `10428` (traces) ·
`8090` (GlitchTip) · `4000` (Langfuse). Verify each from your laptop:
`curl -m5 -o /dev/null -w '%{http_code}\n' http://<mini-ip>:3000/api/health`.

## 4. Post-bootstrap (fresh-start setup)

- **GlitchTip:** the org/team/project are NOT auto-created (mobile UI hangs on
  org creation) — recreate them server-side like before:
  `docs/wip/glitchtip-vps-error-tracking-handover.md` has the Django-shell
  snippet; grab the new DSN.
- **Langfuse:** `LANGFUSE_INIT_*` bootstraps org `homelab` + project `agents` +
  keys automatically — nothing to do; log in with the init user.
- **Grafana:** datasources + dashboards provision from git automatically.

## 5. Cutover senders DGX → mini

Repoint everything that sends at the mini's IP (or flip the MagicDNS `obs` name):

| Sender | Change |
|---|---|
| DGX Alloy collector | `REMOTE_WRITE_URL` + `LOGS_WRITE_URL` → `http://<mini>:8428/…` / `:9428/…`, then `docker compose up -d` |
| podcast app (traces) | `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` → `http://<mini>:10428/insert/opentelemetry/v1/traces` |
| podcast app (errors) | new GlitchTip `GLITCHTIP_DSN` (from step 4) |
| any Langfuse sender | Langfuse host → `http://<mini>:4000` + new project keys |

Adopting a stable MagicDNS `obs` name up front collapses this to "give the mini
the `obs` name" — senders that target `obs.<tailnet>.ts.net` don't change.

## 6. Decommission the DGX backend (once the mini is verified)

On the DGX: `docker compose -f infra/observability/backend/... down`, same for
glitchtip + langfuse. Keep the DGX **collector** running. The DGX is then
collector-only, as intended.

## Rollback

The mini is additive until step 5. If something's wrong, don't cut over — the
DGX keeps serving. `bootstrap.sh` is re-runnable; `docker compose down -v` per
stack wipes a bad start (destructive — fresh volumes).
