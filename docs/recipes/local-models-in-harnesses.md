# Local models in coding harnesses

## Why this exists

The homelab runs local models (the X3's Ollama, the DGX's vLLM). Coding harnesses (Claude Code,
opencode) can point at them as an external model. These notes record what works, what doesn't and
why, from real runs, so each harness and model is tried once and the result is kept. Add a section
per harness or model as it is tried; keep the numbers.

## Quick reference

| What | Value |
|---|---|
| Endpoint | the X3's Ollama, `http://100.92.54.65:11435` (user unit `ollama`; reachable from the X3 and the mini only, `infra/x3/README.md`) |
| APIs it speaks | Anthropic Messages (`/v1/messages`, tool use included), OpenAI (`/v1/chat/completions`), Ollama's own (`/api/*`) |
| Model kept loaded | `qwen3:30b-a3b-instruct-2507-q4_K_M` (30.5B MoE, ~3B active), 65,536-token context, 25.4 GB of GPU memory |
| Cost | $0; it shares the GPU with the hub's morning briefing (06:00 UTC), which waits behind a long session |
| Other models | 14 more in `~/.ollama/models` (up to 120B class); asking for one swaps the loaded model out (`OLLAMA_MAX_LOADED_MODELS=1`), and over ~35 GB is the operator's call (`infra/x3/AGENTS.md`) |

## Claude Code (tried 2026-11-19, Claude Code on the X3, Ollama 0.40.13)

### How to run it

On the X3, in the project folder:

```bash
M=qwen3:30b-a3b-instruct-2507-q4_K_M
mkdir -p ~/.claude-local-ollama
ANTHROPIC_BASE_URL=http://100.92.54.65:11435 ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_MODEL=$M \
ANTHROPIC_DEFAULT_OPUS_MODEL=$M ANTHROPIC_DEFAULT_SONNET_MODEL=$M ANTHROPIC_DEFAULT_HAIKU_MODEL=$M \
CLAUDE_CODE_SUBAGENT_MODEL=$M CLAUDE_CODE_MAX_CONTEXT_TOKENS=65536 \
CLAUDE_CONFIG_DIR=~/.claude-local-ollama claude --strict-mcp-config
```

Each line is there for a reason found in the runs:

- **`ANTHROPIC_DEFAULT_*_MODEL` and `CLAUDE_CODE_SUBAGENT_MODEL`:** the operator's settings send
  subagents to `sonnet` and side calls to `haiku`; Ollama has no model by those names.
- **`CLAUDE_CODE_MAX_CONTEXT_TOKENS=65536`:** Claude Code does not know the model and otherwise
  assumes a 200k window, so auto-compact would never fire before Ollama runs out.
- **`--strict-mcp-config`:** with the operator's MCP servers loaded, every request fails before the
  model sees it: `API Error: 400 Unable to generate parser for this template. Automatic parser
  generation failed: JSON schema error at #: properties must be an object`. Ollama builds a grammar
  from the tool schemas and one MCP tool's schema breaks it. Which server's tool is not known yet.
- **`CLAUDE_CONFIG_DIR` (an empty folder):** with MCP off but the operator's own config loaded (global
  CLAUDE.md, lean-ctx hooks that deny native tools), the model answered that a file in the folder did
  not exist, ran no command, and talked about a `ctx_search` tool it did not have. A small model
  follows those instructions literally. The empty folder also means no login: the token is the dummy.

Messages you will see and can ignore: "connectors are disabled" (claude.ai connectors need the
login), "isn't described by this version's model catalog", and an auto-mode billing notice for
non-Anthropic endpoints.

### Results: three Haiku-sized tasks

Headless (`claude -p`), the clean setup above, each checked against the files, not the model's report:

| Task | Time | Result |
|---|---|---|
| Rename a function across 2 files, run the program to check | 87 s | **Pass.** Four edits, 0 old names left, output unchanged |
| List the ERROR and WARN lines of a 300-line worker log, the repeated failure, the line count | 55 s | **Partly right.** All 4 lines with batch and time, the repeated batch named; the line count wrong (301, real 300) |
| Start a 10 s job in the background, wait, report its last line and whether it succeeded | 124 s | **Fail.** Said it succeeded and gave `[exited with code 0]` (Claude Code's own background-task text) as the job's last line; the job was still at `step 5/5` when it answered, the real last line `DONE rc=0` came after |

### Verdict

- **Use it for:** mechanical edits whose result a command or a diff checks (renames, moving code,
  formatting, small mechanical refactors).
- **With care:** read-only questions over logs and files; treat counts and other small facts as
  unverified until checked.
- **Don't use it for:** watching background jobs, or anything where it decides on its own that
  something finished or succeeded; it reported success early and misread the output.
- **Speed:** 1–2 minutes per small task.

## opencode

Not tried yet. It takes an OpenAI-compatible provider: `http://100.92.54.65:11435/v1` with the
model name above.

## Open questions

- Which MCP server's tool schema Ollama rejects, and whether the fix belongs in that server or in
  Ollama (a newer Ollama than 0.40.13 is the operator's call).
- Whether a larger local model (the 120B class in `~/.ollama/models`) does the background-job task
  right, at what speed, with the assistant's model swapped out meanwhile.
- The same three tasks through opencode.
- The same tasks against the DGX's vLLM through LiteLLM (alias `fleet-triage-local`): whether LiteLLM's
  Anthropic-format endpoint serves that alias to Claude Code is not checked.

## Verification (repeating the test)

The runs used three scratch folders and a script that runs `claude -p "<task>"` in each with the
environment above, `--allowedTools=<only what the task needs>` (written `--allowedTools=…`: the
option takes several values and swallows a prompt placed after it) and `< /dev/null`, then checks
the result independently:

1. **Rename:** `util.py` defines `calc_total`, `calc_tax` calls it, `app.py` imports both and prints
   `total 20.0`, `tax 4.2`. Check: `grep -c calc_total` is 0 in both and the output is unchanged.
2. **Log:** 300 INFO lines with ERROR on batch 87 (twice, 10:14Z), batch 251 (10:41Z) and WARN on
   batch 203 (10:33Z). Check against `grep -E 'ERROR|WARN'` and `wc -l`.
3. **Background job:** `job.sh` prints `step 1/5` … `step 5/5` two seconds apart, then `DONE rc=0`.
   Check `job.out` when the model answers.

`claude` must be on the lean-ctx shell allowlist (`workstation/config/lean-ctx/config.toml`, added
2026-11-19) for an agent to run this.

## Troubleshooting

- **`400 Unable to generate parser for this template`:** MCP tools are loaded; add
  `--strict-mcp-config`.
- **`Error: Input must be provided either through stdin or as a prompt argument`:** the prompt came
  after `--allowedTools <list>`; put it first or write `--allowedTools=<list>`.
- **The model ignores the tools you allowed, or names tools it doesn't have:** the operator's config
  is loaded; set `CLAUDE_CONFIG_DIR` to an empty folder.
- **Slow first answer:** the model is being loaded (another model was asked for); `curl -s
  http://100.92.54.65:11435/api/ps` shows what is loaded.
