# Right-sizing `--gpu-memory-utilization` for vLLM on GB10

A short note on how to pick the right value for `--gpu-memory-utilization`
instead of leaving it at the upstream default. Written 2026-06-16 after
hitting 95% unified-memory pressure on the GB10 during a downstream
sweep (`podcast_scraper` #1016 Phase 2a) where the compose was pinned at
the 0.75 default.

This applies to **any** vLLM stack on a unified-memory host (GB10 / Jetson
Orin) where "GPU memory" and "system RAM" are the same physical pool —
so over-allocating KV cache directly pushes the rest of the system into
swap.

## The problem

vLLM's `--gpu-memory-utilization` flag is a *budget*, not a tax. With
`0.75` set, vLLM **pre-allocates** ~75% of GPU memory into a KV-cache
pool at startup, sized to maximize batch throughput. That allocation
happens whether or not you actually batch — a single-request workload
that never uses more than 5% of the pool still pays for the full
budget upfront.

On GB10 specifically (128 GB unified memory):

- Model weights at bf16 for a ~30B-A3B MoE: **~67 GiB**
- KV cache pre-alloc at 0.75 util: **~25-30 GiB**
- CUDA graph + activations + worker overhead: **~5-10 GiB**
- **Total resident: ~95-100 GiB**

For a host that also runs faster-whisper (~3 GiB) + pyannote (~3 GiB) +
observability stack (~1 GiB) + Linux page cache, that lands at
**~95% unified-memory pressure** and pushes ~10 GiB into swap. The host
gets sluggish; a fresh vLLM swap dance has a real chance of OOM-failing
on cold boot.

## The signals you need to right-size

vLLM exposes everything on `/metrics` (Prometheus format). Three metrics
are load-bearing:

| Metric | Read | Decision rule |
|---|---|---|
| `vllm:kv_cache_usage_perc` | Instantaneous % of KV cache pool currently in use (0.0 - 1.0) | Peak over a realistic workload → how much KV cache the workload *actually* needs |
| `vllm:num_requests_waiting_by_reason{reason="capacity"}` | Counter; increments when a request stalls because KV cache is full | **Must stay 0** post-rightsizing. > 0 means you under-allocated and requests are queueing on KV-cache pressure (latency hit) |
| `vllm:num_requests_running` | Concurrent in-flight batch size | Tells you whether the workload is single-request (sweep / eval) or batched (production serving) |

There are more metrics (`vllm:gpu_prefix_cache_hit_rate`,
`vllm:num_preemptions_total`, etc.) — for sizing, those three are
enough.

## Methodology

1. **Boot vLLM at the upstream default** (`--gpu-memory-utilization=0.75`).
2. **Run the realistic workload** end-to-end. For a sweep / eval, that's
   the actual prediction script across the actual dataset. For
   production serving, a representative concurrent-request soak.
3. **Sample `/metrics` every 5 s** during the workload. Capture peak
   `kv_cache_usage_perc` and the total `capacity` waits.
4. **Apply the formula:**

   ```
   new_util = current_util × peak_kv_cache_usage_perc × safety_factor
   ```

   Recommended safety factor: **1.5** (50% margin). Lower if you're
   confident in workload stability; higher if you batch unpredictably.
5. **Cold-boot vLLM at the new value.** Re-run a smoke and confirm
   `capacity` waits stay at 0 and `kv_cache_usage_perc` peaks at roughly
   `1 / safety_factor` of the new budget (so ~67% peak for a 1.5×
   margin).
6. **If `capacity` waits > 0 at the new value** → step back up
   incrementally (0.05 at a time). The right value is the smallest
   utilization that keeps `capacity` waits at 0 under your workload.

## The math example that drove this note

`podcast_scraper` autoresearch sweep, 2026-06-16:

- Model: `Qwen/Qwen3-30B-A3B-Instruct-2507` bf16
- Workload: 10 episodes, sequential (1 request at a time), ~10-14K
  input tokens per episode, 800-token cap on output
- KV needed per request: ~15K tokens × 1 = **~937 blocks** at the
  cache's 16-token block size
- Total KV pool at 0.75 util: **24,426 blocks** (`cache_config_info{num_gpu_blocks="24426"}`)
- Predicted peak usage: 937 / 24,426 = **~3.8%**

Right-size formula: `0.75 × 0.038 × 1.5 = 0.043`. That's below vLLM's
sane-default floor for KV scheduling, so the formula's theoretical
minimum lands at **`--gpu-memory-utilization=0.20-0.25`** for this
workload purely on KV-cache grounds.

**BUT — that's not the binding constraint.** See the floor below.

For a production serving role (multi-request batched), the same model
would size very differently — peak `kv_cache_usage_perc` under load
would be much higher and the right value might genuinely be 0.65-0.75.
**The number depends on the workload, not the model.** Right-size
per-stack, not per-model.

## Floor constraint — model weights have to fit too

The right-size formula above tells you **how much KV cache the workload
actually needs.** It does NOT tell you whether the resulting budget is
big enough to hold the **model weights**.

`--gpu-memory-utilization` is a single budget split across:

```
total_budget = weights + activations + CUDA graphs + KV cache pool
```

If you pin the budget so low that weights + activations don't fit, the
model fails to load (cold-boot crash) or evicts pages into swap (host
death spiral).

The **weight floor** is roughly:

```
weight_floor_util = (weight_GB + margin_GB) / total_unified_memory_GB
```

with `margin_GB ≈ 5` for activations + CUDA graphs + worker overhead.

For GB10 (128 GiB unified):

- Qwen3-30B-A3B-Instruct-2507 (bf16, 60 GB weights):
  `(60 + 5) / 128 = 0.508` → can't go below **~0.50**
- Mistral-Small-3.2-24B (bf16, 45 GB):
  `(45 + 5) / 128 = 0.391` → can't go below **~0.40**

**The right value is `max(KV_formula_output, weight_floor)`.** For
sweep workloads on GB10 the weight floor dominates — the formula's
KV-only answer (0.20-0.25 for this workload) sits below the weight
floor (0.50), so 0.50 wins. Tighter quants (FP8, NVFP4, INT8) drop the
weight floor proportionally and let you go lower.

The math example above gave the KV-only answer; the actual right value
for that workload is the weight floor (~0.50) plus the recommended
margin (see profile table below).

## Per-workload profiles

Two named profiles. Real workloads always fall into one of these
buckets; the right `--gpu-memory-utilization` depends on **which
bucket**, not on the model.

### Profile: `sweep` (single-request, isolated)

The autoresearch / eval / benchmark shape. One request in flight at a
time, predictable input length, predictable output length. KV cache
peaks at single-digit percent of the pool. The binding constraint is
the weight floor, not the KV cache.

Per-model recommendations on GB10 bf16, derived from the 2026-06-16
sweep (Magistral-Small-2509 D + Mistral-Small-3.2-24B-Instruct-2506 E +
Qwen3-30B-A3B-Instruct-2507 B all measured at peak
`kv_cache_usage_perc ≈ 1.86%`):

| Model                                          | Quant | Weight GB | Weight floor | **Recommended sweep util** |
|------------------------------------------------|-------|-----------|--------------|----------------------------|
| **NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4** (current pin) | **NVFP4** | **18** | **0.18** | **0.25** |
| Mistral-Small-3.2-24B-Instruct-2506            | bf16  | 45        | 0.40         | **0.50**                   |
| Magistral-Small-2509                           | bf16  | 45        | 0.40         | **0.50**                   |
| Qwen/Qwen3-30B-A3B-Instruct-2507 (BF16 baseline) | bf16 | 60        | 0.50         | **0.55**                   |
| DeepSeek-R1-Distill-Qwen-32B                   | bf16  | 64        | 0.54         | **0.60**                   |
| Qwen3.5-35B-A3B (if-when-shipped)              | bf16  | 70        | 0.59         | **0.65**                   |

**Recommended = floor + ~0.05** (≈ 6 GiB headroom over the weight
floor). Anything more is wasted on a single-request sweep; the KV cache
pool will never see ~2% peak utilization.

**On the NVFP4 row:** 18 GB weights drops the weight floor to 0.18.
The `.env.example` profile default (`sweep` = 0.60 from 2026-06-16) is
now over-allocated by ~2.4× the recommended value for this model —
**fine for correctness** (host has memory to spare), but if a sibling
service is competing for unified memory, dropping to 0.25 frees
~45 GiB. The profile default stays at 0.60 as a "safe middle" that
works for any model in the table; right-size per-deploy when memory
pressure justifies it.

Source data + measurement methodology:
- BF16 rows: [`decisions/2026-06-16-kv-cache-per-workload-profiles.md`](decisions/2026-06-16-kv-cache-per-workload-profiles.md)
- NVFP4 row: [`decisions/2026-06-19-nvfp4-quant-swap.md`](decisions/2026-06-19-nvfp4-quant-swap.md)

### Profile: `prod` (concurrent / batched serving)

The serving-many-clients shape. Multiple concurrent requests, variable
input length, variable output length. KV cache peaks at much higher
percentages because vLLM packs multiple in-flight requests into the
pool.

**Not measured on this homelab yet.** Don't carry the sweep numbers
into a prod role without a real measurement run. The vLLM upstream
default (`0.75`) is the right placeholder until you have a measured
peak; bump or drop from there per the methodology above.

When a prod measurement lands, add a sibling
`decisions/YYYY-MM-DD-kv-cache-prod-profile.md` capturing the run.

## Boot times — first vs second cold boot

Cold-boot wall-clock on a fresh `gpu-mode-swap.sh research` is
dominated by **whether the weights + CUDA graphs are already cached
locally.** The vLLM "Time spent downloading weights" log line is a bit
misleading — when weights are already on disk it's measuring **HF
snapshot validation against the cache**, not network download.

### First boot (cold cache)

```
HF snapshot fetch + checksum validation:  ~5-10 min (network-dependent for first pull)
Safetensor read from disk into memory:    ~3-5 min
CUDA graph compile + capture:             ~2-3 min (no flashinfer autotuner) to ~5 min (with autotuner)
Warmup pass:                              ~30-60 s
TOTAL (≤35B bf16 on GB10):                ~20-25 min
```

Today's empirical: 774 s (~12.9 min) of "Time spent downloading
weights" for `Mistral-Small-3.2-24B` even though weights were on disk
— that's the snapshot validation step, not network. Confirmed by
re-booting the same model right after; the second boot dropped to
sub-minute on that step because the validated snapshot path was
remembered.

### Second boot (warm cache)

```
HF snapshot cache hit:                    ~30 s
Safetensor read:                          ~2-3 min
CUDA graph compile:                       ~30-60 s (cached if same shape)
Warmup pass:                              ~30 s
TOTAL (≤35B bf16 on GB10):                ~3-5 min
```

### Cache invalidation triggers (force back to first-boot cost)

Any of these wipe the second-boot speed advantage:

| Trigger | Why it invalidates |
|---|---|
| vLLM image bump (e.g. 25.11 → 26.05) | `VLLM_CACHE_ROOT` schemas can change between vLLM versions; CUDA graphs are re-captured |
| `--max-model-len` change | KV cache pool shape changes → block table + CUDA graph re-capture |
| Attention backend change (flash-attn → flashinfer, etc.) | Different kernel selection → graph re-capture |
| Different model id (even within the same family) | Fresh snapshot validation + read |
| Quantized variant of same model (FP8 / NVFP4 / INT8) | Different HF repo id → fresh snapshot + safetensor read |

The second-boot speedup is robust to **container restart** (no compose
change), not to **compose change**.

## Operator workflow

The sampler script lives at `/tmp/vllm_kv_cache_sample.sh` on the
operator's laptop (not committed — it's a one-shot probe, not infra).
Reference body:

```bash
#!/bin/bash
DURATION="${1:-300}"
ENDPOINT="http://<vllm-host>:8003/metrics"
peak_perc=0.0; total_capacity_waits=0
end=$(($(date +%s) + DURATION))
while [ $(date +%s) -lt $end ]; do
  payload=$(curl -s --max-time 4 "$ENDPOINT")
  perc=$(echo "$payload" | awk '/^vllm:kv_cache_usage_perc{/{print $2}' | head -1)
  capacity=$(echo "$payload" | awk '/^vllm:num_requests_waiting_by_reason{.*capacity/{print $2}' | head -1)
  echo "$(date +%H:%M:%S) kv=$perc capacity=$capacity"
  if awk -v a="$perc" -v b="$peak_perc" 'BEGIN{exit !(a>b)}'; then peak_perc="$perc"; fi
  total_capacity_waits=$(awk -v a="$total_capacity_waits" -v b="$capacity" 'BEGIN{print a+b}')
  sleep 5
done
echo "peak=$peak_perc capacity_waits=$total_capacity_waits"
```

Arm it in another terminal while the workload runs. Final block prints
the peak and capacity-wait total → apply the formula → cold-boot vLLM.

## Decisions/ entries that should land alongside a re-pin

If a sweep determines that the autoresearch stack's real workload wants
a non-default `--gpu-memory-utilization`, drop a sibling decisions/
entry capturing:

- The workload that drove the number (sweep id, request shape, dataset
  size).
- Peak `kv_cache_usage_perc` observed.
- Whether `capacity` waits stayed at 0.
- The new value, with the formula applied.
- Re-evaluation trigger: when the workload shape changes (e.g. moving
  from single-request sweep to batched serving), re-sample.

The pin lives in `docker-compose.yml` (`VLLM_GPU_MEM_UTIL`); the
*reason* the pin is what it is lives in `decisions/`.

## Not in scope

- Production batched serving — this note covers the right-sizing
  methodology; the right value for a multi-tenant serving role is its
  own measurement run.
- `--max-model-len` tuning — independent lever, also affects KV-cache
  block count. Tune it after `--gpu-memory-utilization` is set; same
  measurement methodology (peak observed input length × safety margin).
- Multi-vLLM-on-one-GPU — gpu-mode-swap.sh enforces "one at a time" on
  this host, so the budget calculation assumes single-tenant. Don't
  carry these numbers over to a future shared-GPU setup without
  re-measuring.
