# Observability boot — Grafana Alloy stack live on DGX → Grafana Cloud

**Date:** 2026-06-12
**Status:** v0.1 — recipe drafted; first live boot pending operator
**Reach:** runs on DGX; pushes outbound to Grafana Cloud over HTTPS

Bring the templated Alloy + DCGM + cAdvisor + Ollama-metrics stack from
`infra/observability/` up live on the DGX and verify metrics land in
Grafana Cloud Explore. Closes NEXT_STEPS open-thread #3 from genesis.

The config layer is already validated. This recipe is the operational
walk-through: credentials, copy-and-boot, verify, troubleshoot.

> **Placeholder legend.**
>
> | Placeholder | What it stands for |
> |---|---|
> | `<your-org>` | Your Grafana Cloud organization slug |
> | `<stack-name>` | Your Grafana Cloud stack name |
> | `<dgx-host>` | DGX hostname on tailnet (e.g. `dgx-llm-1`) |
> | `<your-tailnet>` | Tailscale tailnet name |

---

## Prereqs

On the DGX:
- Docker + NVIDIA Container Toolkit installed (verify: `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`)
- `~/docker-compose/` exists (or your equivalent base dir for composes)
- This repo cloned somewhere accessible (e.g. `~/agentic-ai-homelab/`)

In Grafana Cloud:
- An active Grafana Cloud account (free tier is enough — ~10k series fits
  this stack comfortably)
- A stack with **Prometheus** enabled

If you don't have an account: <https://grafana.com/auth/sign-up/create-user>.
Free tier doesn't require a payment method.

---

## Step 1 — Get the three Grafana Cloud values

In the Grafana Cloud UI:

1. Left sidebar → **Connections** → **Add new connection**
2. Search for **Hosted Prometheus metrics** → open the connection page
3. The page shows the remote-write endpoint, username (instance ID), and
   an API token. Either reuse an existing token (if you have one saved)
   or generate a new one — generating invalidates the prior token.

You need three values (`.env.example` documents them too):

| Value | Looks like | Maps to |
|---|---|---|
| Remote Write Endpoint | `https://prometheus-prod-XX-prod-XX-XXXX.grafana.net/api/prom/push` | `GRAFANA_CLOUD_PROM_URL` |
| Username / Instance ID | `000000` (a number) | `GRAFANA_CLOUD_PROM_USERNAME` |
| API token | `glc_...` (long) | `GRAFANA_CLOUD_PROM_API_KEY` |

Treat the token like a password. **Never commit it.** `.env` is in
`.gitignore`; keep it that way.

---

## Step 2 — Configure on DGX (run from repo in place)

The compose runs from the repo directly — no copy-out. `.env` is
gitignored and lives next to the compose file.

```bash
# On the DGX (via mosh / ssh):
mosh <dgx-host>.<your-tailnet>.ts.net -- bash

# Work inside the repo's observability dir:
cd ~/agentic-ai-homelab/infra/observability

# Create the .env from the example:
cp .env.example .env
$EDITOR .env   # paste the three values from step 1
chmod 600 .env # operator-only read; defensive habit
```

Sanity-check the config layer before booting:

```bash
sudo docker compose config > /dev/null && echo "compose OK"
grep -E '^[A-Z_]+=' .env | wc -l   # should print 3
```

---

## Step 3 — Boot the stack

```bash
sudo docker compose up -d
sudo docker compose ps
```

Expect four containers `running`:

```
NAME            STATUS
alloy           Up X seconds
cadvisor        Up X seconds
dcgm-exporter   Up X seconds
ollama-metrics  Up X seconds
```

Watch Alloy specifically for remote_write health:

```bash
sudo docker compose logs alloy --tail=200 | grep -iE 'remote_write|error|warn'
```

A healthy boot shows lines like:
```
component_id=prometheus.remote_write.default ... msg="components started"
```

Common first-boot warnings:
- `error sending request ... 401` → token wrong, regenerate
- `error sending request ... 403` → username (instance ID) wrong
- `dns lookup ... no such host` → URL wrong (region mismatch)

---

## Step 4 — Verify in Grafana Cloud Explore

In Grafana Cloud → **Explore** → datasource = your Prometheus → query box:

```promql
up{instance="<dgx-host>"}
```

Expected rows (1 = up, 0 = down — both are signal):

| job | meaning |
|---|---|
| `node` | Alloy's built-in host metrics — base health |
| `dcgm` | NVIDIA GPU metrics — GB10 visibility |
| `cadvisor` | Per-container forensics |
| `vllm` | Will be 0 if vLLM is down (expected per gpu-mode `idle`) |
| `ollama` | 1 if `ollama-metrics` sidecar started cleanly |

If you see five rows (or four with `vllm`=0), the stack is healthy.
If you see zero rows: data hasn't arrived yet (wait ~30s for first
scrape interval); if still zero after 2 min, see troubleshooting.

---

## Step 5 — Import dashboards

From Grafana Cloud → **Dashboards** → **New** → **Import** — paste each
ID, pick your Prometheus datasource:

| ID | Dashboard | What you get |
|---|---|---|
| 1860 | Node Exporter Full | host CPU/mem/disk/net/load |
| 12239 | NVIDIA DCGM Exporter | GPU utilization, VRAM, power, temp |
| 17296 | vLLM | tok/s, queue depth, KV cache, TTFT per model |
| 893 | Docker (cAdvisor) | per-container CPU/mem/restarts |

The vLLM dashboard panels will be empty until vLLM is up (see
[`gpu-mode-swap.md`](gpu-mode-swap.md) → `gpu-mode code`).

---

## Step 6 — Pin the image tags

Per genesis NEXT_STEPS #4: composes currently use `:latest` for fast v0.1
iteration. After the first successful boot, freeze the working versions:

```bash
sudo docker compose ps --format json | jq -r '.[] | "\(.Service)  \(.Image)"'
```

Note each image's SHA or pinned tag. Then edit the compose file in the
repo (`infra/observability/docker-compose.yml`):

```yaml
# Before:
image: grafana/alloy:latest
# After (example):
image: grafana/alloy:v1.5.1
```

Repeat for dcgm-exporter, cadvisor, ollama-metrics. Re-run
`docker compose up -d` to validate, then commit the pinned tags.

---

## Troubleshooting

### Containers up, but no data in Explore

Check Alloy's remote_write specifically:

```bash
sudo docker exec alloy curl -fsS localhost:12345/-/healthy
# Should print: All Alloy components are healthy.

sudo docker compose logs alloy --since 5m | grep -iE 'remote_write.*err'
```

If healthy but no metrics: confirm clock skew on DGX. Grafana Cloud
rejects samples >10min in the future or past.

```bash
timedatectl status
sudo timedatectl set-ntp true   # if NTP is off
```

### DCGM exporter restarts repeatedly

Usually a CUDA driver / NVIDIA Container Toolkit version mismatch on
fresh box installs. Test the runtime:

```bash
sudo docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

If that fails, fix the runtime first — DCGM won't work without it.

### `ollama-metrics` shows `ollama` = 0

Either Ollama isn't running on `:11434`, or the sidecar can't reach
localhost. Verify:

```bash
curl -fsS localhost:11434/api/tags | jq '.models | length'
sudo docker exec ollama-metrics wget -qO- http://localhost:11434/api/tags >/dev/null && echo OK
```

### cAdvisor consuming high CPU

cAdvisor on a busy box can chew 5-10% of one core. If that's not
acceptable, raise its scrape interval in `config.alloy` from 30s → 60s.

### Want to verify push throughput

```promql
rate(prometheus_remote_storage_samples_in_total[5m])
```

Run that in Explore. Should be > 0 if scrapes are reaching remote_write.

---

## Tear-down (clean removal)

```bash
cd ~/agentic-ai-homelab/infra/observability/
sudo docker compose down                   # stops + removes containers
sudo docker compose down -v                # + removes named volumes (none used here, but defensive)
```

The Grafana Cloud account is untouched — series will simply stop
arriving. Old series are retained per your stack's retention policy
(15 days on free tier).

---

## Cross-references

- Config-layer docs: [`../local-ai-infra.md`](../local-ai-infra.md) →
  "infra/observability/ — Grafana Alloy stack".
- Compose template + config: `infra/observability/` in this repo.
- The Ollama-observability Level-1/2/3 decision: see
  [`infra/observability/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/observability/README.md)
  on GitHub → "The Ollama observability decision".
- Mode-swap (when running vLLM observability matters):
  [`gpu-mode-swap.md`](gpu-mode-swap.md).

---

## Quick reference card

```
First boot (run from the repo in place):
  cd ~/agentic-ai-homelab/infra/observability
  cp .env.example .env  &&  $EDITOR .env  &&  chmod 600 .env
  sudo docker compose up -d
  sudo docker compose ps

Verify in Grafana:
  up{instance="<dgx-host>"}   # expect 4-5 rows

Watch Alloy health:
  sudo docker compose logs alloy --tail=200 | grep -iE 'remote_write|error'

Pin tags:
  sudo docker compose ps --format json | jq -r '.[] | "\(.Service)  \(.Image)"'
```
