# FastContext for Recon — Install & Wire-up Guide

A small, practical guide to standing up **Microsoft FastContext** as the engine behind your
recon/scout seat in Claude Code, OpenCode, and Pi. Starts with *why*, then *how it works*,
then the decisions to make, then per-tool setup and a test step.

---

## 1. Why — what it is and what it solves

The expensive, low-value part of most agent runs is **exploration**: an agent greps, opens
twenty files, traces a flow — just to figure out *where* the work is. That exploration is
~46% of a main agent's tokens and the majority of its tool turns. Every one of those tokens
sits in the main agent's context, crowding out reasoning and inflating cost.

**FastContext** is a small (4B / 30B) model Microsoft trained specifically to do that recon
and nothing else. You ask it a question about the codebase; it returns the **exact files and
line ranges** the agent needs, plus a short brief. It's read-only — it can READ / GLOB / GREP,
not edit.

What it solves, concretely: it moves exploration **out of your expensive agent's context**.
Your orchestrator/builder gets a three-paragraph answer with file:line citations instead of
the twenty files someone had to read to produce it. Reported main-agent token cut: up to ~60%.

It is **not** an index, a RAG store, or a chat model. It's a live, trained explorer you call.

---

## 2. How it works (and why it saves tokens)

Two stacked mechanisms:

1. **Context isolation (the pattern).** FastContext runs as a *subagent* — it does the heavy
   reading in its **own throwaway context window**, then returns only the brief. The parent
   never carries the raw exploration. This part works with *any* cheap model in the recon
   seat; FastContext just does it better.
2. **Trained efficiency (the model).** It's fine-tuned to localize in fewer tokens and emit
   tight `file:line` citations rather than dumping file bodies.

Underneath it's a **vanilla Qwen3-4B finetune** (MIT, Qwen/ChatML template), so it runs
anywhere Qwen3 runs. It issues structured **READ/GLOB/GREP tool calls in a loop** — which is
the single most important fact for wiring it (see §4).

It does **not** build a persistent index — it greps live on every call. Consequence: nothing
to keep in sync (great for parallel worktrees — just point each call at that worktree's root),
but nothing is amortized either, so on truly millions-of-LOC repos the live scan starts to
drag (that's when you'd add a coarse retrieval layer underneath).

---

## 3. Key things to think about *before* you install

A short decision checklist — get these right and the rest is mechanical:

1. **Serving runtime.** On Apple Silicon, use **Ollama or MLX**, not SGLang/vLLM (those are
   CUDA-oriented and painful on Mac). On an NVIDIA box, SGLang is what Microsoft's own docs use.
2. **GGUF choice.** It's a stock Qwen3-4B, so a normal `Q4_K_M` / `Q6_K` / `Q8` GGUF works.
   **Avoid the community ROCmFP4 GGUF** — it's AMD-Strix-only and won't load in stock Ollama /
   llama.cpp / LM Studio. If no clean GGUF exists yet, convert from the MIT weights.
3. **Tool-call parsing — the make-or-break.** FastContext only works if the runtime *parses*
   its READ/GLOB/GREP calls instead of printing them as text. SGLang has `--tool-call-parser
   qwen`; Ollama supports tool-calling for Qwen3 but is less battle-tested for this loop —
   so the one thing you must verify is **parsing vs printing** (see §6).
4. **Service vs model wiring.** FastContext carries its *own* tools + loop. If you naively set
   it as a subagent's `model`, the host feeds it the host's tools (wrong names) and it
   misfires. Decide: expose it as a **service** (one `explore` call — recommended) or as a
   **model** the host feeds compatible tools to. See §4.
5. **The recon seat differs per tool.** Pi → `scout`; OpenCode → **`explore`** (NOT `scout` —
   that's dependency research); Claude Code → an explore agent you author.
6. **Net tokens, not main-agent reduction.** FastContext spends its *own* tokens. A scout that
   saves the orchestrator 10k but burns 12k itself is a net loss "60% main-agent reduction"
   hides. Measure **net total tokens per passing task** — so have per-agent telemetry (virtual
   key / proxy) in place to attribute it.
7. **Concurrency.** A parallel fleet fires several scouts at once; one local 4B serves limited
   concurrency. On an M4 Pro / 48GB it's fine for a few, but size for it before fanning out.
8. **Language priors.** It's trained on mainstream modern repos; older/niche code (legacy,
   uncommon languages) is where its citations fray. Test on your *weakest* language first.

---

## 4. The wiring decision: service vs model

**Service (recommended).** Run FastContext behind one call: `explore(query) → file:line`.
Its loop runs internally; each host just registers a single external tool. Uniform across all
tools, and its own tools can't misfire because the host never sees them.
- Simplest: its **CLI** — `fastcontext explore "<query>" --root <path>` (confirm exact flags
  in the repo).
- Cleaner: a thin **MCP wrapper** exposing an `explore` tool — more discoverable, structured
  output, same registration story everywhere.

**Model.** Point the recon subagent's `model:` at the FastContext endpoint — only if you've
confirmed the host feeds it READ/GLOB/GREP-shaped tools matching its training. Possible in
Pi / OpenCode / Claude Code / Codex; not in Cursor (MCP/shell only there).

Start with **service** — it sidesteps the tool-mismatch failure mode entirely.

---

## 5. Serve it (Mac, Ollama)

The stock GGUF templates ship a `<think>` prefix on every assistant turn that breaks
tool-calling on Ollama 0.30.x (see `infra/fastcontext/README.md` for the bug detail and
linked Ollama issues). You **must** wrap the GGUF in a custom Modelfile that strips that
prefix — otherwise `tool_calls` always comes back empty.

```bash
ollama pull hf.co/mradermacher/FastContext-1.0-4B-RL-i1-GGUF:latest
ollama create fastcontext-clean -f infra/fastcontext/Modelfile

# OpenAI-compatible endpoint already running at http://localhost:11434/v1
```

After build, smoke-test with the curl in `infra/fastcontext/README.md` — confirm
`finish_reason: "tool_calls"` and a populated `tool_calls` array. If `content` carries
JSON text instead, the template wasn't applied — rebuild.

Two extra Apple-Silicon fixes you'll trip on:
- FastContext's `tool/grep.py` hardcodes `/usr/bin/rg`. Patch to `/opt/homebrew/bin/rg`
  after `uv tool install`, or symlink it. Without the fix every Grep call returns
  `[Errno 2] No such file or directory: '/usr/bin/rg'`.
- The `fastcontext` binary lands at `~/.local/bin/fastcontext`. Make sure that's on PATH
  (the `uv tool install` step adds it via `~/.zshenv` automatically; restart the shell
  if not).

MLX is the alternative on Apple Silicon if you want tighter memory/perf control. Either way,
the output is an OpenAI-compatible endpoint your harness/MCP wrapper calls.

---

## 6. Wire it per tool

The recon **seat** differs; the wiring shape (register a service / instruct the agent to call
it) is the same.

### Claude Code
- Author `.claude/agents/scout.md` (an explore agent), and either:
  - **Shell route:** instruct it to run `fastcontext explore "<query>" --root .` via Bash and
    read the returned ranges — don't grep itself.
  - **MCP route:** `claude mcp add fastcontext <wrapper>` (or `.mcp.json`) exposing `explore`;
    instruct the agent to use it for code location.

### OpenCode  (seat = **explore**, not scout)
- Add the MCP wrapper in `opencode.json` (`mcp` block), or instruct via `AGENTS.md`.
- Point the **explore** subagent at it. Remember OpenCode's built-in `scout` is *dependency
  research* — don't put FastContext there.

```jsonc
// opencode.json (shape)
{
  "mcp": { "fastcontext": { "command": "<wrapper-cmd>", "args": ["..."] } },
  "agent": {
    "explore": { "mode": "subagent",
      "description": "Locate code in the repo. Use fastcontext.explore; return file:line.",
      "tools": { "fastcontext_explore": true } }
  }
}
```

### Pi  (seat = built-in **scout**)
- Give the built-in `scout` a tool/MCP that calls FastContext, or instruct via `AGENTS.md`
  to shell out to the CLI. Pi's scout becomes the front-end, FastContext the engine.
- **Model route option:** register the local endpoint in `~/.pi/agent/models.json` as a
  provider and set scout's model to it — only after confirming Pi feeds it compatible tools.

```jsonc
// ~/.pi/agent/models.json (model-route option)
{ "providers": { "local": {
  "baseUrl": "http://localhost:11434/v1", "api": "openai-completions",
  "apiKey": "ollama", "models": [{ "id": "fastcontext-4b" }] } } }
```

---

## 7. Test it (the one verify step that matters)

Before trusting it, run a single exploration and confirm **two** things:

1. **Parsing, not printing.** The agent's transcript shows FastContext's tool calls being
   *executed* (READ/GLOB/GREP run, results returned) — not the raw tool-call JSON printed as
   text. Printing = the runtime isn't parsing the Qwen tool format; fix the parser/template.
2. **Correct citations.** The returned `file:line` ranges actually contain the relevant code.
   A token saving that points the agent at the wrong lines is *negative* value — it thrashes.

Test on your **weakest language / oldest code**, not the part FastContext handles easily — if
it's accurate on the TS UI but garbage on the Python/legacy side, that's your real signal.

---

## 8. Measure the win (don't skip this)

The whole point is tokens, so instrument it:
- Capture **net total tokens per task** (every agent summed), via your LiteLLM proxy / per-agent
  virtual key into Langfuse — not just the main-agent drop.
- Compare **with vs without** FastContext on the same handful of real tasks.
- Watch **exploration-token share** fall, and confirm the **pass rate holds** — a recon setup
  that cuts tokens but drops quality is a regression.

If the net delta is small on *your* repo, FastContext isn't earning its setup — fall back to a
plain cheap-model scout (which still gives you the isolation win for free).

---

## Open items to confirm against the repo
- ~~Exact CLI command + flags (`explore`, `--root`, output format) — github.com/microsoft/fastcontext.~~
  — *done (2026-06-24): no `explore` subcommand; the canonical invocation is
  `fastcontext --query "..." --max-turns N --traj path.jsonl [--citation]`.
  Root = cwd at invocation time. See `infra/fastcontext/README.md`.*
- ~~The clean (non-ROCmFP4) GGUF repo/tag, or convert from MIT weights.~~
  — *done (2026-06-24): `hf.co/mradermacher/FastContext-1.0-4B-RL-i1-GGUF:latest`
  (i1-imatrix) works; wrap it with `infra/fastcontext/Modelfile`.*
- ~~Ollama tool-call reliability for this model — the parsing smoke-test (§7) is the gate.~~
  — *done (2026-06-24): stock template breaks tool-calling on Ollama 0.30.x;
  custom Modelfile stripping `<think>` prefix is required. Root cause traced to
  ollama#10976, #15288, #14601, #14745, #12203. See `infra/fastcontext/README.md`.*
- Whether a prebuilt MCP wrapper already exists (vs. writing the thin one).
  — *partial (2026-06-24): no usable wrapper found; community `fast-context-mcp` is
  unreliable. Writing the thin one is the path forward when ready.*
