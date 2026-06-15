# vllm-autoresearch

Sibling stack to [`../coder-next/`](../coder-next/) sharing the same
GB10 GPU. This is **podcast_scraper's** sweep / contention target —
the slot that `gpu-mode-swap.sh research` brings up.

## Why this stack exists

- `coder-next` is the operator's IDE coding agent (off-limits to other
  projects' sweeps).
- `vllm-autoresearch` is the slot for project workloads that need a
  serving vLLM — autoresearch summary/GI sweeps against the #928 Cell C
  baseline, #996 catastrophic-tail characterization, future provider
  comparisons that need `gpu-mode-swap.sh research` to point somewhere
  real.
- The single GB10 GPU can host only one vLLM at a time, hence the
  mode-swap dance.

## First-time setup

```bash
# On the DGX-class host:
cd ~/Projects/agentic-ai-homelab/infra/vllm/autoresearch/

# 1. Secrets
cp .env.example .env
chmod 600 .env
$EDITOR .env              # fill HF_TOKEN; keep VLLM_API_KEY default if you like

# 2. Pin the model — MODEL_PLACEHOLDER must become a real HF repo id
$EDITOR docker-compose.yml
# Replace MODEL_PLACEHOLDER with the chosen Qwen 3.x A3B MoE id.
# See "Model selection" below for the candidates.

# 3. Point gpu-mode-swap.sh at this dir (one-time per host)
echo "GPU_MODE_RESEARCH_DIR=$HOME/Projects/agentic-ai-homelab/infra/vllm/autoresearch" \
  >> ~/.config/gpu-mode.env

# 4. First boot
gpu-mode-swap.sh idle        # clear anything else on the GPU
gpu-mode-swap.sh research    # brings up this compose
gpu-mode-swap.sh status      # confirm vllm-autoresearch is the active mode

# Cold start = 10-30 min depending on model size. The healthcheck's
# start_period: 10m absorbs CUDA-graph compile.
```

## Model selection

**Currently pinned: `Qwen/Qwen3-30B-A3B-Instruct-2507`** (since 2026-06-14).

BF16, MoE, 30 B total / ~3 B active. Closest current canonical HF repo
to the report's "Qwen3.6-35B-A3B" baseline shape: same family, same
A3B (active-3-billion) MoE structure, same quant. Caveat: **30 B vs
35 B total = 5 B smaller than the original eval baseline.** Re-run #928
Cell C against this pin to confirm scoring parity before treating it
as the new canonical autoresearch target.

If parity fails (drift outside scoring noise), the next pin candidate
is whichever Qwen3-32B/35B A3B MoE the team ships after this one — do
NOT pin upward to the 80 B Qwen3-Next variant (different size class,
different latency profile, conclusions don't transfer).

### Vendor watch — when to revisit this pin

Closes chipi/agentic-ai-homelab#3. The 30 B vs 35 B drift from the
original eval baseline is acceptable today; nothing on the horizon
ships in the right size class, so re-pinning would just trade one
drift for another. **Check in occasionally — roughly quarterly, or
when you see a vendor announcement** — for a fresh A3B MoE in the
30-35 B total-param band (same family, same quant). When one shows
up, evaluate it against the criteria above; if it's a good fit,
coordinate with `podcast_scraper` #928 to re-baseline Cell C before
flipping the pin.

Practical signals to watch:
- Qwen team blog / HuggingFace org for a mid-tier MoE between the
  existing 7 B and 80 B tiers
- DeepSeek / Mistral / Cohere occasional A3B-shaped releases in this
  band
- Any community port of an existing 30-35 B dense model into A3B MoE
  form (unlikely but possible)

The current pin stays in place by default — there is no calendar
alarm and no CI check; this is just a "next time you happen to look,
look here too" note.

### Image: `nvcr.io/nvidia/vllm:26.05-py3` (bumped 2026-06-15)

This stack was bumped from `25.11-py3` → `26.05-py3` on 2026-06-15
(chipi/agentic-ai-homelab#2). Result: strictly equal or better on every
dimension measured (cold boot +7%, steady-state −4%, run-1 cold-cache
spike −34%, 256-request 5-min load test 0 errors p99=4.67s, 96% GPU
saturation). The bump also obsoleted chipi/agentic-ai-homelab#1: the
old `fused_moe.py:798` "Using default MoE config" warning no longer
appears, replaced by an on-the-fly `flashinfer + trtllm` runtime
autotuner. There is no static `E=128,N=768,device_name=NVIDIA_GB10.json`
to ship anymore. If the autotuner ever surfaces obviously sub-optimal
kernel choices on GB10, open a fresh ticket for that specific gap —
the original tuning-by-static-JSON approach doesn't apply here.

`coder-next/` remains on `25.11-py3` for now (different stack, different
upgrade decision).

Full eval write-up — methodology, side-by-side numbers, side effects
surfaced, rollback procedure — lives at
[`decisions/2026-06-15-image-bump-25.11-to-26.05.md`](decisions/2026-06-15-image-bump-25.11-to-26.05.md).

## Decision history

`decisions/` is the durable home for autoresearch-stack decisions
(image bumps, model re-pins, scaling moves, contention investigations).
File-per-decision, `YYYY-MM-DD-<slug>.md`, captures methodology +
results + rollback so future-me can answer "why did we make this
choice?" from the repo, not from git log spelunking. Entries are
**append-only**: superseded decisions get a new entry referencing the
old one, not edits in place.

### Historical context for this pin

The podcast_scraper `EVAL_HYBRID_ROUTING_2026_06.md` § Summary refers
to the autoresearch vLLM target as "Qwen3.6-35B-A3B (bf16) on
nvcr.io/nvidia/vllm:26.05-py3." That naming predates the Qwen-Next
rename and **does not have a canonical HF repo of its own** — confirm
with the operator (or with the eval report's contemporaneous compose
file if archived anywhere) which exact upstream snapshot was the
intended target.

**Hard size constraint: stay in the ~30–35 B total-parameter class.**
The original eval baseline was 35 B; jumping to 70-80 B is *not* a like-for-
like substitution (≈2× VRAM at the same quant, very different latency
profile, and the contention-test conclusions wouldn't transfer). The
exact upstream snapshot needs operator confirmation before pinning —
candidates to ASK ABOUT, not blindly substitute:

| Class | What to look for | Notes |
| --- | --- | --- |
| **MoE in the ~30 B total range** | A Qwen 3.x MoE checkpoint with total params ≈ 30–35 B (active ~3 B). The Qwen team has shipped 30 B-class A3B MoEs; verify the current canonical repo id at boot time. | Closest shape match to the report's "Qwen3.6-35B-A3B" baseline. **Do not substitute the 80 B Qwen3-Next variant** — different size class. |
| **Dense 32 B fallback** | `Qwen/Qwen2.5-32B-Instruct` | Stable, well-known. Dense not MoE, so the inference profile differs from the original A3B baseline — note this caveat in any eval report. |
| **Smaller dense (only if the 32 B class is unavailable)** | `Qwen/Qwen2.5-14B-Instruct` or similar | Last-resort fallback. Half the parameters; expect different quality + much faster inference. Re-baseline before publishing comparisons. |

**Recommendation:** confirm the exact intended HF repo id with the
operator before first boot. Do NOT pick a checkpoint outside the
30–35 B total-parameter class without an explicit re-baseline. If the
operator can dig up the contemporaneous compose file from the original
#928 Cell C measurement, that's the gold-standard pin. Once chosen,
update `MODEL_PLACEHOLDER` in `docker-compose.yml` and run #928 Cell C
to confirm parity (tie within scoring noise) before treating it as the
new canonical autoresearch baseline.

## GPU contention rules

- Don't boot this while `coder-next` is up. `gpu-mode-swap.sh research`
  switches cleanly; manual `docker compose up` does not.
- Don't boot this while DGX whisper or pyannote is mid-request — see
  `podcast_scraper/docs/guides/PROD_RUNBOOK.md` § "Provider model
  selection — DGX vs cloud per stage" for the "idle vLLM before
  transcription windows" rule and the #963 / #996 evidence behind it.
- The 0.75 GPU memory cap is shared with coder-next for the same
  reason: 0.92 OOM-crashes the host on the GB10 unified pool.

## Telemetry hooks (when applicable)

The podcast_scraper-side `compose/grafana-agent.yaml` does NOT scrape
this stack today — the existing DGX observability config (#943) only
includes node/cAdvisor/DCGM/pyannote-app. If you want autoresearch
vLLM telemetry, add a `dgx-vllm-autoresearch` scrape job pointing at
`dgx-llm-1.tail6d0ed4.ts.net:8003/metrics` — vLLM exposes
Prometheus-format metrics at `/metrics` natively, no instrumentor
needed. Cardinality: ~30 series at the default config; well within
the existing budget.

## Related

- [`../coder-next/`](../coder-next/) — sibling stack, operator's IDE.
- [`../template/`](../template/) — canonical starter compose; this dir
  was forked from it.
- `gpu-mode-swap.sh` — the GPU-ownership contract.
- `podcast_scraper/docs/guides/PROD_RUNBOOK.md` — operator rules.
- `podcast_scraper` issues: #927 (DGX-vs-cloud epic), #963 (contention),
  #996 (catastrophic-tail characterization, blocked on this stack
  being live).
