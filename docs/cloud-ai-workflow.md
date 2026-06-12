# Pillar 3 — Cloud AI workflow

How I work with cloud LLM APIs (Claude, OpenAI, Gemini) in real projects.

> **Status: v0.1 placeholder.** Content lands in v0.3 per
> `docs/wip/NEXT_STEPS.md`. Intentionally last because cloud-LLM workflow
> patterns benefit from longer real-use observation before being
> documented as "the way".

## What goes here (target state)

### Prompt caching as discipline

The 5-minute TTL on Anthropic's prompt cache changes how you design
agents. Patterns:
- Stable preambles go up front; volatile context goes at the end.
- Sleep intervals in agent loops are tuned around the TTL (under 5
  minutes = stay cached; over 5 minutes = commit to a long wait).
- Telemetry exposes cache hit/miss so you can prove the discipline holds.

→ `examples/claude-api-with-caching/`

### Multi-provider routing

The right shape: one interface (chat completion + tool use), multiple
backends (Claude, OpenAI, Gemini, local vLLM). Provider selection by:
- Capability requirement (long context → Claude; cheap bulk → Gemini;
  zero-egress → local)
- Cost budget (cheaper models for non-critical work)
- Latency target (local for interactive, cloud for thoughtful)

→ `examples/multi-provider-router/`

### Batch API

Anthropic batch (and OpenAI's equivalent) at 50% cost for non-interactive
work. When to reach for it:
- Eval sweeps over hundreds of items
- Bulk re-classification / re-summarization
- Anything where 24h turnaround is acceptable

→ `examples/batch-pattern/` (if/when written)

### Eval harness shape

Provider-agnostic harness that takes a dataset + a prompt + a model and
returns scored outputs. The shape that works:
- Configs in YAML (one per experiment cell)
- Outputs go to a deterministic path with config + git SHA stamped in
- Judges are separate from generators (composable)
- Adversarial verification (multiple independent judges; majority wins)
  for high-stakes decisions

Reference shape comes from podcast_scraper's `finale_runner.py`. Genericized
form lands in `examples/eval-harness/` (v0.3).

### Cost gates

Soft limit ($X/mo) triggers a warning in CI. Hard limit ($Y/mo) blocks
new experiments. Numbers depend on the project; the *pattern* is having
both.

### MCP — tool exposure

When the agent needs to *do* things (read files, search code, run shell)
rather than just reason about them. FastMCP + my project tools wired
into opencode / Claude Code.

→ `examples/mcp-tool-template/`

## Cloud vs local — when which

| If you need... | Reach for | Why |
|---|---|---|
| Best agentic capability today | Claude (Opus tier) | Tool use + long context + reasoning, all reliable |
| Highest output speed for chat | local vLLM (Qwen3-Coder-Next-FP8) | On GB10: faster than cloud round-trip after first token |
| Predictable cost for bulk work | local (Ollama or vLLM) | Pay once for hardware, then unlimited tok/s |
| Privacy / no egress | local | Self-hosted, no third-party logging |
| Latest frontier model | cloud (Claude or GPT-5 tier) | Always ahead of openweights by ~6-12 months |
| Cheap eval sweeps | Anthropic / OpenAI batch | 50% discount, 24h turnaround |
| Tool calls + structured output | Claude or vLLM with tool parser | Most reliable across models |

## Open in v0.1

- [ ] Every example dir referenced above (see `docs/wip/NEXT_STEPS.md`).
- [ ] Concrete cost-gate sample config.
- [ ] One canonical "Claude with prompt caching" Python skeleton.
- [ ] Concrete multi-provider router code (not just the abstract shape).

## Inspirations

- Anthropic prompt caching docs — `https://docs.anthropic.com/`
- podcast_scraper `finale_runner.py` — eval harness shape.
- podcast_scraper `cloud_balanced` / `cloud_thin` / `cloud_with_dgx_*`
  profiles — multi-provider routing in practice.
