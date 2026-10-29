# FastContext — Mac (Ollama) serving config

Microsoft FastContext-1.0-4B-RL behind a local Ollama OpenAI-compatible
endpoint, with the **template patch** required to make tool-calling
actually work on Ollama 0.30.x.

## Why this Modelfile exists

The default `mradermacher/FastContext-1.0-4B-RL-i1-GGUF` template
unconditionally prepends `<think>` to every assistant turn. Ollama's
parser sees that and classifies the model as "thinking-capable," which
in 0.30.x triggers two cascading bugs:

1. With `tools` defs in the request → all output is routed to the
   `reasoning` field; `content` and `tool_calls` come back empty
   (matches ollama/ollama#10976, #15288, #14601, #14745, #12203).
2. `reasoning_effort: "none"` partially unblocks (content populates)
   but Ollama *still* won't extract `<tool_call>...</tool_call>`
   markers into the OpenAI `tool_calls` array from a thinking-flavored
   template.

This Modelfile rebuilds the template with the `<think>` prefix
**removed**. Result: clean tool-calling, parallel calls, populated
`tool_calls` array, empty `content`, `finish_reason: "tool_calls"` —
the FastContext-expected shape.

## Build

```bash
ollama pull hf.co/mradermacher/FastContext-1.0-4B-RL-i1-GGUF:latest
ollama create fastcontext-clean -f infra/fastcontext/Modelfile
```

## Smoke test

```bash
curl -s -X POST http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"fastcontext-clean",
       "messages":[
         {"role":"system","content":"Use Grep/Glob/Read. Final answer in <final_answer>file:line</final_answer>."},
         {"role":"user","content":"Find files mentioning gpu mode swap"}],
       "tools":[{"type":"function","function":{"name":"Grep","description":"Search","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"}},"required":["pattern"]}}}],
       "max_tokens":200,"temperature":0}' | python3 -m json.tool
```

**Expected:** `content: ""`, populated `tool_calls`, `finish_reason: "tool_calls"`.

## CLI usage

```bash
BASE_URL="http://localhost:11434/v1" \
MODEL="fastcontext-clean" \
API_KEY="ollama" \
fastcontext --query "<question>" --max-turns 6 --citation
```

## Known patches outside this directory

FastContext's `src/fastcontext/agent/tool/grep.py` hardcodes
`/usr/bin/rg`. On Apple Silicon, ripgrep installs at
`/opt/homebrew/bin/rg`. Patch the constant locally after `uv tool
install`, or symlink `/usr/bin/rg` → `/opt/homebrew/bin/rg`.

## Versions verified

- Ollama daemon: 0.30.10
- FastContext CLI: 0.1.0 (microsoft/fastcontext @ 2026-06-15 release)
- GGUF: `hf.co/mradermacher/FastContext-1.0-4B-RL-i1-GGUF:latest`
- macOS: Darwin 24.x, Apple Silicon

## Why FastContext, and where it stands

FastContext is a 4B Qwen3 finetune trained for one job: code recon. Given a question about a
repo it greps and reads live (READ / GLOB / GREP tool calls in its own loop, no index) and
returns the files and line ranges that matter, so the exploration tokens stay out of the
calling agent's context. Things to know before wiring it anywhere:

- **Tool-call parsing is make-or-break.** It only works if the runtime parses its tool calls
  instead of printing them as text; that is what the Modelfile patch above fixes on Ollama.
- **Wire it as a service, not a `model`.** It carries its own tools and loop; set as a
  subagent's model, the host feeds it the host's tool names and it misfires.
- **Measure net tokens per passing task,** not main-agent savings: it spends its own tokens.
  This was never measured.
- **Concurrency:** one local 4B serves a few parallel callers, not a fleet.

**Status (2026-06-24, unchanged since):** active for Pi through `~/.pi/rules/fastcontext.md`;
**parked for opencode**. Three subagent models (DeepSeek-V4-Flash, Kimi K2.6, Qwen 3.6 Plus)
all bypassed the wrapped CLI, no published opencode integration exists, and opencode's
architecture blocks it (sst/opencode #4096: subagents get the full repo context; #7296: task
permissions hard-disabled). With the "off-the-shelf only" constraint (no custom MCP wrapper)
there was no path left; opencode's `agent.explore` is `disable: true` with its config kept.
The binary, the `fastcontext-clean` Ollama model and the Pi rule are intact.
