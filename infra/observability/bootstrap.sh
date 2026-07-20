#!/usr/bin/env bash
# bootstrap.sh — stand up the self-hosted observability platform on a host.
# Decrypts sops secrets, assembles each stack's .env with this host's tailnet
# IP, brings the stacks up, verifies health, and prints the ACL ports to grant.
#
# Idempotent: re-running rewrites the .env files and `compose up -d` reconciles.
# Runs the BACKEND (VictoriaMetrics/Logs/Traces + Grafana) + GlitchTip + Langfuse.
# Does NOT run the Alloy collector (Linux/GPU-specific; stays on the DGX).
#
# Prereqs: docker (OrbStack on macOS) running, tailscale up, sops + age installed,
# an age key at $SOPS_AGE_KEY_FILE (default ~/.config/sops/age/keys.txt), and an
# encrypted infra/observability/secrets.sops.env (see secrets.sops.env.example).
#
# Usage:  ./infra/observability/bootstrap.sh [--dry-run]
set -euo pipefail

DRY=0; [[ "${1:-}" == "--dry-run" ]] && DRY=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OBS="$REPO/infra/observability"
SECRETS_ENC="$OBS/secrets.sops.env"
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"

say() { printf '\033[1;36m[bootstrap]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[bootstrap] ✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ── preflight ────────────────────────────────────────────────────────────
say "preflight"
command -v docker  >/dev/null || die "docker not found (install OrbStack on macOS)"
docker info >/dev/null 2>&1   || die "docker daemon not running (start OrbStack)"
command -v sops    >/dev/null || die "sops not found (brew install sops)"
command -v tailscale >/dev/null || die "tailscale not found"
[[ -f "$SECRETS_ENC" ]] || die "missing $SECRETS_ENC (see secrets.sops.env.example)"
[[ -f "$SOPS_AGE_KEY_FILE" ]] || die "missing age key at $SOPS_AGE_KEY_FILE"

IP="$(tailscale ip -4 2>/dev/null | head -1)"
[[ "$IP" =~ ^100\. ]] || die "could not read tailnet IP (tailscale up?) — got '$IP'"
say "tailnet IP: $IP"

# Bind address for published ports. Default = the tailnet IP (locks ports to the
# tailnet). On Docker-for-Mac, publishing to the utun tailnet IP can silently
# fail — if a port is healthy locally but tailnet peers time out, re-run with
# BIND=0.0.0.0 (also exposes to the LAN; rely on macOS firewall + the tailnet ACL).
BIND="${BIND:-$IP}"
say "bind address: $BIND${BIND:+ $([[ "$BIND" == 0.0.0.0 ]] && echo '(all interfaces — LAN-exposed)')}"

# ── soft checks (warn, don't block) ──────────────────────────────────────
case "$(uname -s)" in
  Darwin)
    say "macOS $(sw_vers -productVersion 2>/dev/null) — OrbStack needs 13+ (Ventura)"
    MEMGB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) ;;
  Linux) MEMGB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1048576 )) ;;
  *) MEMGB=0 ;;
esac
if (( MEMGB >= 12 )); then say "RAM ${MEMGB}GB — ample for the full stack"
elif (( MEMGB > 0 )); then say "⚠ RAM ${MEMGB}GB — full stack wants ~12GB+; consider deferring Langfuse"; fi

# ── decrypt secrets into this shell (never written to disk) ──────────────
say "decrypting secrets"
# shellcheck disable=SC1090
set -a; eval "$(sops -d "$SECRETS_ENC")"; set +a

# ── assemble per-stack .env (secrets + host IP + static config) ──────────
write_env() { # $1=path ; stdin=contents
    if (( DRY )); then say "DRY: would write $1"; return; fi
    umask 077; cat > "$1"; chmod 600 "$1"; say "wrote $1"
}

write_env "$OBS/backend/.env" <<EOF
VM_LISTEN=$BIND
VLOGS_LISTEN=$BIND
VTRACES_LISTEN=$BIND
GRAFANA_LISTEN=$BIND
VM_RETENTION=6
VLOGS_RETENTION=30d
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$GRAFANA_ADMIN_PASSWORD
EOF

write_env "$REPO/infra/glitchtip/.env" <<EOF
GLITCHTIP_LISTEN=$BIND
GLITCHTIP_PORT=8090
GLITCHTIP_DOMAIN=http://$IP:8090
POSTGRES_PASSWORD=$GLITCHTIP_POSTGRES_PASSWORD
SECRET_KEY=$GLITCHTIP_SECRET_KEY
DJANGO_SUPERUSER_EMAIL=admin@homelab.local
DJANGO_SUPERUSER_PASSWORD=$GLITCHTIP_SUPERUSER_PASSWORD
ENABLE_OPEN_USER_REGISTRATION=false
DEFAULT_FROM_EMAIL=glitchtip@homelab.local
EOF

write_env "$REPO/infra/langfuse/.env" <<EOF
LANGFUSE_LISTEN=$BIND
LANGFUSE_PORT=4000
NEXTAUTH_URL=http://$IP:4000
SALT=$LANGFUSE_SALT
ENCRYPTION_KEY=$LANGFUSE_ENCRYPTION_KEY
NEXTAUTH_SECRET=$LANGFUSE_NEXTAUTH_SECRET
POSTGRES_PASSWORD=$LANGFUSE_POSTGRES_PASSWORD
DATABASE_URL=postgresql://postgres:$LANGFUSE_POSTGRES_PASSWORD@postgres:5432/postgres
CLICKHOUSE_PASSWORD=$LANGFUSE_CLICKHOUSE_PASSWORD
REDIS_AUTH=$LANGFUSE_REDIS_AUTH
MINIO_ROOT_PASSWORD=$LANGFUSE_MINIO_ROOT_PASSWORD
LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY=$LANGFUSE_MINIO_ROOT_PASSWORD
LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY=$LANGFUSE_MINIO_ROOT_PASSWORD
LANGFUSE_INIT_ORG_ID=homelab
LANGFUSE_INIT_ORG_NAME=homelab
LANGFUSE_INIT_PROJECT_ID=agents
LANGFUSE_INIT_PROJECT_NAME=agents
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=$LANGFUSE_INIT_PROJECT_PUBLIC_KEY
LANGFUSE_INIT_PROJECT_SECRET_KEY=$LANGFUSE_INIT_PROJECT_SECRET_KEY
LANGFUSE_INIT_USER_EMAIL=admin@homelab.local
LANGFUSE_INIT_USER_NAME=admin
LANGFUSE_INIT_USER_PASSWORD=$LANGFUSE_INIT_USER_PASSWORD
TELEMETRY_ENABLED=false
EOF

if (( DRY )); then say "dry-run done — no containers started"; exit 0; fi

# ── bring up ─────────────────────────────────────────────────────────────
say "starting stacks (pulls images on first run)"
docker compose -f "$OBS/backend/docker-compose.yml"  up -d
docker compose -f "$REPO/infra/glitchtip/docker-compose.yml" up -d
docker compose -f "$REPO/infra/langfuse/docker-compose.yml"  up -d

# ── verify ───────────────────────────────────────────────────────────────
say "verifying health (waiting up to ~2min each)"
check() { # name url
    for _ in $(seq 1 40); do
        [[ "$(curl -s -o /dev/null -w '%{http_code}' "$2" 2>/dev/null)" == "200" ]] \
            && { say "✓ $1"; return 0; }
        sleep 3
    done
    printf '\033[1;31m[bootstrap] ✗ %s not healthy at %s\033[0m\n' "$1" "$2" >&2
}
check "VictoriaMetrics" "http://$IP:8428/health"
check "VictoriaLogs"    "http://$IP:9428/health"
check "VictoriaTraces"  "http://$IP:10428/health"
check "Grafana"         "http://$IP:3000/api/health"
check "GlitchTip"       "http://$IP:8090/_health/"
check "Langfuse"        "http://$IP:4000/api/public/health"

cat <<EOF

$(say "done — grant these ports to this host's tag in the Tailscale ACL:")
   3000 (Grafana)  8428 (metrics)  9428 (logs)  10428 (traces)
   8090 (GlitchTip)  4000 (Langfuse)
Then repoint senders (DGX collector REMOTE_WRITE_URL/LOGS_WRITE_URL, app DSNs,
OTLP endpoint) at $IP — or flip the MagicDNS obs name to this host.
EOF
