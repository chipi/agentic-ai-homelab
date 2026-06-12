# Pillar 3 — Cloud AI workflow

How I work with cloud LLM APIs (Claude, OpenAI, Gemini) in real projects.

> **Status: v0.2 partial.** Narrative is real; example code lands
> incrementally. The example list is intentionally short — generic
> "router over four providers" patterns rot fast, so this pillar leans
> on concrete reference code (in operator's other projects) over
> aspirational abstractions here.

## Why this shape

Cloud LLM APIs are not interchangeable. They share an OpenAI-shaped
interface and not much else. Practical patterns that matter more than
which provider you pick:

1. **Prompt caching as discipline.** A 5-minute TTL is short enough that
   it shapes how you build agent loops; long enough that getting it right
   shifts both cost and latency by orders of magnitude.
2. **Cost gates.** Soft warnings + hard caps, both in dollars. Without
   these, exploration sessions silently turn into eval sweeps.
3. **The right work for the cloud.** Frontier capability, fresh
   knowledge, long context — yes. Bulk throughput, repetitive prompts,
   private data — no. Pillar 2 covers the no's.

The example code below operationalizes (1). Cost gates (2) are project-
specific guard-rails — patterns documented, not pre-built. The
when-which decision (3) is captured in the table at the bottom.

## Patterns

### Prompt caching as discipline

Anthropic's prompt cache has a 5-minute TTL. That single number drives
three concrete patterns:

- **Stable preambles up front; volatile context at the end.** Cache
  keys are prefix-based — once a prefix is cached, every continuation
  pays only for the suffix. Order matters as much as content.
- **Sleep intervals in agent loops are tuned around the TTL.** Under
  ~5 minutes = stay cached (fast warm reads, ~10% of cost). Over =
  commit to a long wait (one cache miss buys hours). Never pick 5
  minutes exactly — you eat the miss without amortizing it.
- **Cache hit/miss as a first-class metric.** Log `cache_creation_input_tokens`
  and `cache_read_input_tokens` per request; if hit rate is below ~80%
  on a stable workload, prompt structure is wrong.

→ [`examples/claude-api-with-caching/`](https://github.com/chipi/agentic-ai-homelab/tree/main/examples/claude-api-with-caching)

### Multi-provider routing *(reference, not abstracted)*

The right shape conceptually: one interface (chat completion + tool use),
multiple backends (Claude, OpenAI, Gemini, local vLLM). Selection axes:

- **Capability requirement** — long context → Claude; cheap bulk → Gemini;
  zero-egress → local vLLM
- **Cost budget** — cheaper models for non-critical work
- **Latency target** — local for interactive, cloud for thoughtful

Not extracted into `examples/multi-provider-router/`. The honest reference
is operator's `podcast_scraper-infra` provider classes (`cloud_balanced`,
`cloud_thin`, `cloud_with_dgx_*`), where the abstraction has been beaten
on by real work. Genericizing it cleanly is more work than its derived
value here.

### Batch API

Anthropic Batch (and OpenAI's equivalent) at 50% cost for non-interactive
work. When to reach for it:

- Eval sweeps over hundreds of items
- Bulk re-classification / re-summarization
- Anything where 24h turnaround is acceptable

The shape: stage requests into batch jobs, poll for completion, persist
outputs alongside their inputs. Pattern lives inline in the eval-harness
example (below) rather than as its own example dir.

### Eval harness shape

Provider-agnostic harness that takes a dataset + a prompt + a model and
returns scored outputs. The shape that works:

- **Configs in YAML** — one per experiment cell (prompt × model × hyperparams)
- **Outputs to a deterministic path** with config + git SHA stamped in
- **Judges separate from generators** — composable, swappable
- **Adversarial verification** — multiple independent judges; majority
  wins for high-stakes decisions

Reference shape comes from podcast_scraper's `finale_runner.py`.
Genericized form lands in
[`examples/eval-harness/`](https://github.com/chipi/agentic-ai-homelab/tree/main/examples/eval-harness)
once the operator points at the canonical source.

### Cost gates

Soft limit ($X/mo) triggers a warning in CI. Hard limit ($Y/mo) blocks
new experiments. Numbers depend on the project; the *pattern* is having
both, expressed as a single env-driven config:

```
ANTHROPIC_COST_SOFT_USD=50
ANTHROPIC_COST_HARD_USD=200
```

Then a small middleware around your provider client checks
`anthropic_billing_usage_query()` (or equivalent) once per minute and
raises a `CostGateExceeded` exception when crossed. Soft = log + Slack;
hard = exception that aborts the run. Composes with token-side discipline
from [`recipes/token-management-lean-ctx-rtk.md`](recipes/token-management-lean-ctx-rtk.md)
— two layers, different lever.

### MCP — tool exposure

When the agent needs to *do* things (read files, search code, run shell)
rather than just reason about them. FastMCP + project tools wired into
opencode / Claude Code via the MCP server registry pattern in
[`agent-harnesses.md`](agent-harnesses.md#mcp-server-registry-pattern).

→ [`examples/mcp-tool-template/`](https://github.com/chipi/agentic-ai-homelab/tree/main/examples/mcp-tool-template)

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

## See also — provider bake-off

`provider-bakeoff/` at the repo root is a self-contained mini-project
for comparing 10 LLM providers across 4 countries (🇺🇸 US, 🇫🇷 EU, 🇨🇳 CN, 🏠 local)
on the same tasks, with real cost numbers. Picks the "when which" question
out of theoretical-table territory and into "here's what your workload
actually does on each".

```bash
cd provider-bakeoff
cp .env.example .env       # fill in whichever keys you have
make bakeoff               # ~$0.50-$2 for a full sweep
```

Designed to lift into its own GitHub project later — see
`provider-bakeoff/README.md` for the layout and
`provider-bakeoff/AGENTS.md` for the agent-runnable contract.

## Open in v0.2 → v0.3

All Pillar 3 items landed. Future work is judgment-call territory —
e.g., examples for batch API, multi-provider router (still deferred to
podcast_scraper-infra's real reference).

## Inspirations

- Anthropic prompt caching docs — <https://docs.anthropic.com/>
- podcast_scraper `finale_runner.py` — eval harness shape.
- podcast_scraper `cloud_balanced` / `cloud_thin` / `cloud_with_dgx_*`
  profiles — multi-provider routing in practice.
