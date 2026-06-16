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

Right-size: `0.75 × 0.038 × 1.5 = 0.043`. That's below vLLM's sane-default
floor for KV scheduling, so the realistic minimum lands at
**`--gpu-memory-utilization=0.20-0.25`** for this workload — frees
~50-60 GiB of unified memory vs. the 0.75 default.

For a production serving role (multi-request batched), the same model
would size very differently — peak `kv_cache_usage_perc` under load
would be much higher and the right value might genuinely be 0.65-0.75.
**The number depends on the workload, not the model.** Right-size
per-stack, not per-model.

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
