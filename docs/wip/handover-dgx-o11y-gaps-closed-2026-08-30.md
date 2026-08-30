# Handover — DGX instrumentation gaps: 3 closed, 1 impossible (with a better substitute)

**Date:** 2026-08-30 · **From:** homelab agent · **To:** the podcast_scraper session that
filed "close the gaps before prod_dgx_full runs" · **Re:** your GAP 1–4, issue #1886

**Nothing was restarted during your run.** cadvisor and dcgm-exporter were recreated
*before* you started the vLLM; the new GPU exporter is additive (a script + systemd
timer, no container touched). vLLM, pyannote, moss and faster-whisper were never
interrupted by me.

## Verdict per gap

| | verdict | action needed from you |
|---|---|---|
| **GAP 1** VRAM | **Impossible on this hardware** — but fully substituted | rewrite #1886 A2 criterion |
| **GAP 2** throttle | **CLOSED** — collected and live | none |
| **GAP 3** vLLM metrics | **Not a gap** — 2 were renamed | fix 2 metric names in #1886 |
| **GAP 4** co-tenancy | **CLOSED**, container CPU/RAM *and* GPU | none |

---

## GAP 1 — VRAM: not a configuration gap, a hardware fact

`DCGM_FI_DEV_FB_USED`/`FB_FREE` were **already in the enabled counter set**; the device
returns nothing for them. Ground truth: `nvidia-smi -q -d MEMORY` reports
`Total/Reserved/Used/Free = N/A`. In total **12 of the 25 default DCGM fields are
silently dropped** on this GB10 (all `FB_*`, `MEM_CLOCK`, every `DCGM_FI_PROF_*`).
GB10 is unified memory — there is no framebuffer to report. No config change fixes it.

**But you now have something better than FB_USED — per-container GPU memory.**

`nvidia-smi --query-compute-apps` *does* work here, and each PID's cgroup carries its
docker container id. New exporter (`infra/dgx/bin/gpu-process-metrics.sh`, 30s systemd
timer on dgx-llm-1) turns that into real series:

```
dgx_gpu_process_memory_bytes{container="...",process="..."}   per container
dgx_gpu_memory_used_bytes                                     total across GPU processes
dgx_gpu_process_count                                         how many hold GPU memory
```

First live readings, with your stack running:

| container | GPU memory |
|---|---|
| `vllm-autoresearch` | **30.88 GB** |
| `pyannote` | 3.25 GB |
| `moss` | 2.00 GB |
| `faster-whisper` | 0.19 GB |
| **total** | **36.33 GB** |

**Rewrite A2 against these.** Your "VRAM headroom > 20%" GO/NO-GO becomes either
`dgx_gpu_memory_used_bytes` against the GB10 unified pool, or
`node_memory_MemAvailable_bytes{instance="dgx-llm-1"}` (on unified memory, host
headroom *is* GPU headroom). Both are live now.

A dead-man rule (`dgx-gpu-metrics-stale`) fires if the exporter stops, so this can't
go dark unnoticed mid-run.

## GAP 2 — throttle reasons: CLOSED

Not supported by default, but I tested rather than assumed: a throwaway exporter on a
spare port proved the GB10 **does** support it. Added via a custom counter set
(`infra/observability/dcgm-counters.csv`) and deployed.

`DCGM_FI_DEV_CLOCK_THROTTLE_REASONS` is live in VictoriaMetrics — **1 series, currently
`0`** (not throttled). Corroborate with `DCGM_FI_DEV_SM_CLOCK`, also live: a sustained
SM-clock drop at stable load is the observable proxy your A1 needs.

## GAP 3 — vLLM metrics: not a gap, two were renamed in vLLM 0.20

Your stack came up while I was working, so I verified against the running server
(`0.20.1+7124b12a.dev`, serving `NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4` — your
`vllm_verify_served_model` contract passes). All eight metrics exist. Two changed name:

| #1886 says | actual on vLLM 0.20 |
|---|---|
| `vllm:gpu_cache_usage_perc` | **`vllm:kv_cache_usage_perc`** |
| `vllm:time_per_output_token_seconds` | **`vllm:inter_token_latency_seconds`** |

The rest match, including **`vllm:num_requests_waiting`** — your load-bearing A3 metric.
All confirmed reaching the mini (`up{job="vllm-autoresearch"}=1`).

Also visible in `vllm:cache_config_info`: you're running `gpu_memory_utilization="0.25"`
and `num_gpu_blocks="12994"`.

## GAP 4 — co-tenancy: CLOSED, and it was broken worse than you thought

**Container CPU/RAM was NOT being collected.** Your brief assumed cadvisor covered the
siblings; in fact **0 of 120 DGX container series carried a `name` label**. Root cause,
from cadvisor's own startup log:

```
Registration of the docker container factory failed:
client version 1.41 is too old. Minimum supported API version is 1.44
```

cadvisor **v0.49.1** ships a Docker API client below the modern daemon minimum, so its
docker factory never registers and it falls back to raw cgroup scanning — series arrive
as `id="/system.slice/docker-<hash>.scope"` with no name, image or labels, which
silently empties every panel filtering on `name!=""`.

Fixed: **v0.52.1**, proven on a spare port first, then deployed. **97 named series**
where there were 0. `pyannote`, `faster-whisper`, `moss`, `vllm-autoresearch` all
resolve by name now.

**Per-container GPU attribution** — which you assumed needed Kubernetes — is solved by
the new exporter above. You have both halves of co-tenancy: CPU/RAM from cadvisor, GPU
memory from `dgx_gpu_process_memory_bytes`, on the same 30s axis.

> **prod-podcast has the identical cadvisor defect** (66 series, 0 named). The pin is
> committed for it, but my key has no SSH to prod — someone with that key must deploy it.

## Dashboards — both fixed; one was dead and unversioned

**DGX — Services** (`dgx-services`): the "GPU mem used" stat was querying `FB_USED` and
rendering empty. Replaced, and added the rows your run needs: throttle reasons, SM
clock/temp, vLLM KV-cache usage, sibling container memory, and **GPU memory by
container**.

**DGX observability (#943)**: this one was **UI-only, not in git**, and almost entirely
non-functional — three independent breakages:
1. every panel filtered `host="dgx"`, **a label these metrics do not carry** (they use
   `instance="dgx-llm-1"`, `cluster="dgx"`) → all 11 data panels empty;
2. GPU memory and "SM active" queried the unavailable `FB_*`/`PROF_*` fields;
3. the pyannote panels used `service="pyannote-server"`; the real value is `"pyannote"`.

Now exported, fixed, and committed as
`infra/observability/backend/grafana/dashboards/Homelab/dgx-observability-943.json`.
Edit it in git from now on, not the UI.

## Retention — no action

VictoriaMetrics: 6-month retention, `--dedup.minScrapeInterval=15s` matching the scrape
interval, no downsampling. Measured 41 points per 10 min at step=15s — full resolution.
A multi-hour 100-episode run is comfortably covered.

## Corrected verification block

```sh
HL=$(tailscale ip -4 homelab | head -1)
for m in DCGM_FI_DEV_CLOCK_THROTTLE_REASONS DCGM_FI_DEV_SM_CLOCK \
         'vllm:num_requests_waiting' 'vllm:kv_cache_usage_perc' \
         dgx_gpu_memory_used_bytes dgx_gpu_process_memory_bytes; do
  echo -n "$m: "
  curl -s "http://$HL:8428/api/v1/query" --data-urlencode "query=$m" \
    | python3 -c 'import json,sys;r=json.load(sys.stdin)["data"]["result"];print(len(r),"series")'
done
```

All six return ≥1 series with the stack running. **Drop `DCGM_FI_DEV_FB_USED` from your
checks — it will never return data on this hardware.**

## NOT covered / open

- **prod-podcast cadvisor** — same defect, pin committed, needs someone with prod SSH.
- **`DCGM_FI_PROF_*`** (SM active, tensor pipe, PCIe throughput) — unavailable on GB10,
  same class as `FB_*`. If #1886 wanted tensor-pipe utilisation, it can't be had here.
- **vLLM metrics under sustained load** — I verified they exist and flow, but the box was
  idle. Their behaviour during your 10/100-episode runs is what you're about to measure.
- The `#943` dashboard still reports `provisioned: false` in Grafana's metadata even
  though it now serves the file's content; a Grafana restart at a convenient moment
  should settle that flag. Cosmetic.

## Commits

`8161a2a` cadvisor v0.52.1 · `f3599d6` DCGM throttle counter set · `dgx-services` +
`#943` dashboard fixes · per-process GPU exporter + dead-man alert. All on
`origin/main`, mini synced.
