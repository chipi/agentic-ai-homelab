# Examples

Small concrete code samples. Each subdir is a self-contained example for
ONE pattern.

> **Status: v0.1 placeholder.** Content lands in v0.3 per
> `docs/wip/NEXT_STEPS.md`. The patterns are described in
> `docs/cloud-ai-workflow.md`.

## Planned examples (v0.3)

- `claude-api-with-caching/` — Python skeleton showing prompt cache
  hit/miss telemetry, model-version migration pattern.
- `multi-provider-router/` — generic shape: same interface over Claude /
  OpenAI / Gemini / local vLLM.
- `mcp-tool-template/` — minimal FastMCP server example.
- `eval-harness/` — provider-agnostic harness derived from
  podcast_scraper's `finale_runner.py`.

## Convention for new examples

Each example dir contains:
- `README.md` — what the example shows, when you'd use it, what it
  *doesn't* show.
- The minimum viable code (≤200 lines if possible).
- `requirements.txt` or `package.json` — pinned dependencies.
- `.env.example` if it needs API keys.

Examples are NOT meant to be installed / run from this repo. They're
reference patterns to copy-and-adapt.
