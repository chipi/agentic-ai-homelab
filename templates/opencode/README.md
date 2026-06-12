# opencode — global config drop-in

Copy these files into `~/.config/opencode/` to bootstrap opencode with the
same rules and conventions as this repo.

## Files

- `AGENTS.md` — the 34-rule global agent rules. Same file as the repo
  root `AGENTS.md`. Loaded by opencode on every session, every directory.
- `rules/lean-ctx.md` — lean-ctx MCP usage rules. Loaded the same way.
- `opencode.json.example` — provider + MCP config template.

## Quick start

```bash
mkdir -p ~/.config/opencode/rules

cp AGENTS.md             ~/.config/opencode/AGENTS.md
cp rules/lean-ctx.md     ~/.config/opencode/rules/lean-ctx.md
cp opencode.json.example ~/.config/opencode/opencode.json

# Substitute placeholders in the config:
sed -i '' \
  -e 's|<dgx-host>|dgx-llm-1|g' \
  -e 's|<your-tailnet>|your-tailnet-name|g' \
  -e 's|<vllm-api-key>|your-actual-key|g' \
  ~/.config/opencode/opencode.json
```

Verify opencode picks them up: start an opencode session in any
directory. The AGENTS.md content should govern behavior immediately;
`opencode models` should list `vllm/Qwen/Qwen3-Coder-Next-FP8`.

## Per-project overlays

Per-project `AGENTS.md` files at a repo's root *layer on top* of these
globals. Project rules take precedence when they contradict the globals
(and if they do, that's a signal to reconcile — see global rule "What
overrides this file").

## Lean-ctx MCP setup

`rules/lean-ctx.md` assumes the lean-ctx MCP server is installed at
`/opt/homebrew/bin/lean-ctx`. The `mcp` block in `opencode.json.example`
points there.

Install:

```bash
brew install lean-ctx
which lean-ctx                           # → /opt/homebrew/bin/lean-ctx
```

Verify in opencode: `mcp` slash command should list `lean-ctx` as
connected.

## Add more providers

The template ships with the local vLLM only. To add cloud providers,
extend the `provider` block. The shapes:

### Anthropic / Claude

```json
"anthropic": {
  "npm": "@ai-sdk/anthropic",
  "name": "Claude",
  "options": {
    "apiKey": "{env:ANTHROPIC_API_KEY}"
  },
  "models": {
    "claude-sonnet-4-6":  { "name": "Claude Sonnet 4.6", "tools": true },
    "claude-opus-4-7":    { "name": "Claude Opus 4.7",   "tools": true },
    "claude-haiku-4-5":   { "name": "Claude Haiku 4.5",  "tools": true }
  }
}
```

### OpenAI

```json
"openai": {
  "npm": "@ai-sdk/openai",
  "name": "OpenAI",
  "options": {
    "apiKey": "{env:OPENAI_API_KEY}"
  },
  "models": {
    "gpt-5":      { "name": "GPT-5",      "tools": true },
    "gpt-5-mini": { "name": "GPT-5 mini", "tools": true }
  }
}
```

### Google / Gemini

```json
"google": {
  "npm": "@ai-sdk/google",
  "name": "Gemini",
  "options": {
    "apiKey": "{env:GOOGLE_API_KEY}"
  },
  "models": {
    "gemini-2.5-pro":   { "name": "Gemini 2.5 Pro",   "tools": true },
    "gemini-2.5-flash": { "name": "Gemini 2.5 Flash", "tools": true }
  }
}
```

> `{env:NAME}` resolves at session start. Export the keys in your shell
> rc — opencode never persists them.

## Add more MCP servers

The `mcp` block ships with `lean-ctx` only. Add per the same shape:

```json
"mcp": {
  "lean-ctx": { ... },
  "chrome-devtools": {
    "type": "local",
    "command": ["npx", "-y", "chrome-devtools-mcp@latest", "--headless", "--isolated"],
    "enabled": true
  }
}
```

See [`recipes/chrome-devtools-mcp-agent-loop.md`](../../docs/recipes/chrome-devtools-mcp-agent-loop.md)
for the headless-isolated vs visible-persistent trade-off and use
patterns.

## `model` vs `small_model`

The top-level `model` field is opencode's default for normal turns. The
`small_model` field is what opencode reaches for on cheap auxiliary work
(commit messages, quick summaries, single-shot completions).

| Use case | `model` | `small_model` |
|---|---|---|
| Local-only setup | `vllm/...-Coder-Next-FP8` | Same | One model, no swap cost |
| Cost-sensitive cloud | `anthropic/claude-sonnet-4-6` | `anthropic/claude-haiku-4-5` | Big for real work, small for chores |
| Local + cloud mix | `vllm/...-Coder-Next-FP8` | `anthropic/claude-haiku-4-5` | Local for sessions, cloud Haiku for fast cheap auxiliaries |

Default in `opencode.json.example`: both point at the local vLLM —
zero cloud spend, single model to think about.
