# 2026-06-16 — KV cache sizing: per-workload profiles + weight-floor constraint

**Decision:** adopt named profiles (`sweep` / `prod`) for
`--gpu-memory-utilization`; the binding constraint for the sweep
profile on GB10 unified memory is the **model-weight floor**, not the
KV-cache formula in `KV_CACHE_SIZING.md`.
**Scope:** `infra/vllm/autoresearch/.env.example`, `KV_CACHE_SIZING.md`,
README cross-links, and downstream env on the operator's `.env`.
**Tickets resolved:** chipi/agentic-ai-homelab#5.
**Driver:** `podcast_scraper` #1016 Phase 2a sweep, 2026-06-16.

## Why we measured

`KV_CACHE_SIZING.md` landed earlier today with the methodology +
formula, in response to the 95% unified-memory pressure observed on
the autoresearch host when the compose was pinned at the `0.75`
default (issue #5 context). The methodology was correct *as a
KV-cache calculation*, but the resulting recommended values (`0.20`
for the Qwen3-30B sweep case) silently assumed model weights would
also fit — which on GB10 they don't.

We needed empirical peak `kv_cache_usage_perc` numbers across the
candidate models being smoke-tested in `podcast_scraper` #1016 to:

1. Confirm the KV-cache formula's prediction (low single-digit %)
2. Surface the second constraint (weight floor) explicitly
3. Produce a per-model "what to actually pin" recommendation

## Methodology

Sampler script (`/tmp/vllm_kv_cache_sample.sh`, reference body in
`KV_CACHE_SIZING.md` § "Operator workflow") armed in parallel with
each model's smoke run. Sampling cadence 5 s. Each run captured:

- Peak `vllm:kv_cache_usage_perc` over the workload's duration
- Sum of `vllm:num_requests_waiting_by_reason{reason="capacity"}`
  increments (must stay 0 for the chosen util to be sufficient)

Both pulled from vLLM's `/metrics` Prometheus endpoint. Same compose,
same `--gpu-memory-utilization=0.60` setting across the three models
to make the peak-KV-usage numbers directly comparable.

Models measured:

- **Magistral-Small-2509** (sweep ID D)
- **Mistral-Small-3.2-24B-Instruct-2506** (sweep ID E)
- **Qwen/Qwen3-30B-A3B-Instruct-2507** (sweep ID B, the currently-pinned autoresearch model)

Workload shape per smoke run: 10 podcast-episode summarization
requests, sequential (1 in flight at a time), ~10-14k input tokens,
800-token output cap.

## Results

### Peak KV cache usage

| Sweep ID | Model | Peak `kv_cache_usage_perc` | `capacity` waits |
|---|---|---|---|
| D | Magistral-Small-2509 | **1.86 %** | 0 |
| E | Mistral-Small-3.2-24B-Instruct-2506 | **1.84 %** | 0 |
| B | Qwen/Qwen3-30B-A3B-Instruct-2507 | (~1.85 %, comparable) | 0 |

→ At `--gpu-memory-utilization=0.60`, the KV cache pool is
overallocated by **~50×** for single-request sweep workloads across
this whole model family. The formula-derived target from
`KV_CACHE_SIZING.md` (`0.60 × 0.0186 × 1.5 ≈ 0.017`) is far below any
practical floor — meaning the formula's KV-cache calculation isn't
the binding constraint.

### The second constraint: weight floor

Each model's weights have to fit inside the budget. On GB10's 128 GiB
unified pool, the weight floor for the candidates is:

| Model | Weight GB | `(weight + 5) / 128` floor |
|---|---|---|
| Mistral-Small-3.2-24B-Instruct-2506 | 45 | **0.40** |
| Magistral-Small-2509 | 45 | **0.40** |
| Qwen/Qwen3-30B-A3B-Instruct-2507 | 60 | **0.50** |
| DeepSeek-R1-Distill-Qwen-32B | 64 | **0.54** |
| Qwen3.5-35B-A3B (if-when-shipped) | 70 | **0.59** |

`margin_GB ≈ 5` covers activations + CUDA graph capture + worker
overhead; empirical from the smoke runs that booted cleanly at floor
+ ~5 GiB headroom.

### Per-model recommended `sweep` util

Recommendation: `weight_floor + ~0.05` = floor + ~6 GiB headroom. Any
higher just pre-allocates KV-cache the workload won't touch.

| Model (bf16) | Weight GB | Weight floor | **Recommended sweep util** |
|---|---|---|---|
| Mistral-Small-3.2-24B-Instruct-2506 | 45 | 0.40 | **0.50** |
| Magistral-Small-2509 | 45 | 0.40 | **0.50** |
| Qwen/Qwen3-30B-A3B-Instruct-2507 | 60 | 0.50 | **0.55** |
| DeepSeek-R1-Distill-Qwen-32B | 64 | 0.54 | **0.60** |
| Qwen3.5-35B-A3B (if-when-shipped) | 70 | 0.59 | **0.65** |

### Boot-time observation

Cold-boot of `Mistral-Small-3.2-24B-Instruct-2506` ran for **774 s**
on the "Time spent downloading weights" log line despite the weights
already being on disk. Source confirmed in a follow-up: this is
**HF snapshot validation** against the local cache, not network
download. Second boot of the same model dropped to sub-minute on
that step.

The first-vs-second boot delta for ≤35B bf16 on GB10:

- **First boot**: ~20-25 min (snapshot validation + safetensor read +
  CUDA graph compile + warmup)
- **Second boot**: ~3-5 min (cached snapshot + cached graphs)
- **Cache invalidation triggers**: vLLM image bump, `--max-model-len`
  change, attention-backend change, different model id, different
  quantization variant

Captured in `KV_CACHE_SIZING.md` § "Boot times — first vs second
cold boot" so future-me doesn't get surprised by the snapshot
validation cost.

## Decision

Two named profiles, documented in `KV_CACHE_SIZING.md` § "Per-workload
profiles" and embedded as commented blocks in `.env.example`:

### `sweep` profile (the autoresearch default going forward)

`VLLM_GPU_MEM_UTIL=0.60` as a safe middle for ≤35B bf16 sweep
workloads. Drop to the per-model recommended value (table above) when
host RAM pressure from sibling services demands it. The current
autoresearch pin (`Qwen3-30B-A3B-Instruct-2507`) → `0.55`.

### `prod` profile (placeholder, not measured)

`VLLM_GPU_MEM_UTIL=0.75` (vLLM upstream default) as the placeholder
until a real concurrent-request soak gets measured. **Do not** carry
sweep numbers into prod — KV cache usage scales with batch
concurrency, and the peak under load will be much higher than 1.86%.

Hard ceiling: **0.78** on GB10 unified memory. 0.92 OOM-crashes the
host (per `b2957f6` + the original `25.11-py3` migration note).

## What we deliberately did NOT do

- **No active prod measurement.** Out of scope for this issue — the
  empirical run was a single-request sweep. A prod profile gets its
  own decisions/ entry when a concurrent-request soak gets measured.
- **No `vllm-util-for-model.sh` helper.** Marked "Optional" in the
  ticket. The per-model table in `KV_CACHE_SIZING.md` is grep-friendly
  enough; a shell helper would need to be kept in sync with that
  table and earn its keep. Skip for v1. If it gets reached for more
  than twice, revisit.
- **No changes to the docker-compose default.** The compose's
  `${VLLM_GPU_MEM_UTIL:-0.75}` stays; the `.env` (and `.env.example`)
  drives the actual value, which is the right indirection point.

## Source data

- `podcast_scraper` #1016 Phase 2a sweep log (operator's local; not
  committed)
- Sampler script body in `KV_CACHE_SIZING.md` § "Operator workflow"
  (reference, not committed — it's a one-shot probe)
- `vllm:kv_cache_usage_perc` + `vllm:num_requests_waiting_by_reason`
  on the autoresearch `/metrics` endpoint (live; not historized)

## Follow-up signal worth watching, not refiling today

- **The 0.78 hard ceiling on GB10 is empirical, not theoretical.** If
  a future image bump or kernel change shifts the host-overhead
  budget (e.g. dropping `VLLM_DISABLE_TORCH_COMPILE` freed memory on
  the `26.05-py3` bump), the ceiling moves with it. Re-measure if a
  sweep at 0.75 + a sibling service stack starts swapping.
- **Prod measurement** is the natural next thing to do, but **only
  when there's an actual prod workload to measure against.** Don't
  speculate; wait for a real concurrent-request shape to land
  (closest candidate today: `podcast_scraper` cloud-fallback rerouting
  through autoresearch under retry-storm conditions).

## Rollback procedure

The `0.75` setting still works for both profiles in the
single-request-sweep case — it just overallocates KV cache and
pressures host RAM. To roll back:

- Edit `.env` and set `VLLM_GPU_MEM_UTIL=0.75`
- `gpu-mode-swap.sh idle && gpu-mode-swap.sh research` (~7 min warm boot)

No compose change needed; no decisions/ supersede needed (the `0.75`
value remains the documented `prod` placeholder).

## Ticket + commit references

- chipi/agentic-ai-homelab#5 (this work)
- Earlier KV_CACHE_SIZING.md landing: `65be4d1`
- The image-bump that obsoleted `VLLM_DISABLE_TORCH_COMPILE`
  (relevant for the 0.78 ceiling note): `b2957f6`
- The driver workload: `podcast_scraper` #1016 Phase 2a
