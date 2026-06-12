# MCP tool template — FastMCP server skeleton

Minimal Python skeleton for writing your own MCP server. Exposes a handful
of small tools to demonstrate the three shapes that cover most real cases:

1. **Pure-function tool** — args in, value out, no side effects.
2. **Structured tool** — typed args, structured response (dict / list).
3. **Filesystem-touching tool** — reads from disk; demonstrates the
   "real work" shape.

When to write your own MCP server (vs reusing an existing one):

- You have project-specific data the agent needs to query (a metrics
  dashboard, a CSV catalog, a private API).
- You want a structured tool surface instead of the agent inventing
  bash commands every time.
- An existing MCP server *almost* does what you want but its output
  shape is wrong — wrap it in a thin facade.

When NOT to:

- You can solve it with a shell command. Don't wrap `ls` in an MCP server.
- You can solve it with a one-line CLI. Same reasoning — bash + the
  agent's existing tools are enough.

## Run it standalone

```bash
cd examples/mcp-tool-template
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python server.py
# → "FastMCP server 'example-tools' running on stdio"
```

Stdio mode is what MCP clients (Claude Code, opencode) connect to. The
server stays running until the client disconnects.

## Wire into Claude Code (per-project)

Add to `.mcp.json` at your project root, or to
`~/.claude.json` under `projects.<your-path>.mcpServers`:

```json
{
  "mcpServers": {
    "example-tools": {
      "type": "stdio",
      "command": "python",
      "args": ["/abs/path/to/examples/mcp-tool-template/server.py"],
      "env": {}
    }
  }
}
```

Restart Claude Code → `/mcp` should list `example-tools` as connected.

## Wire into opencode

Add to `~/.config/opencode/opencode.json` under `mcp`:

```json
{
  "mcp": {
    "example-tools": {
      "type": "local",
      "command": ["python", "/abs/path/to/examples/mcp-tool-template/server.py"],
      "enabled": true
    }
  }
}
```

## What's in server.py

Three tools, each annotated:

| Tool | Shape | Why include it |
|---|---|---|
| `greet(name)` | pure function | Confirms the wiring works at all |
| `word_stats(text)` | typed args, structured response | Most useful real shape |
| `read_lines(path, n)` | filesystem access | Demonstrates the "side effect" shape + how to handle errors |

Copy one of these as your starting point. Each is ~10 lines.

## Token discipline for MCP authors

Every tool's return value is sent to the agent's context. Keep returns
tight:

- **Return structured data, not prose.** A dict the agent can index is
  cheaper than a sentence it has to parse.
- **Truncate proactively.** If a tool *could* return a 10MB file,
  default to the first N lines and let the agent ask for more.
- **Don't return success messages.** `{"ok": true}` is fine. `"Successfully
  completed the operation with parameters X, Y, Z."` is a waste.

See [`docs/recipes/token-management-lean-ctx-rtk.md`](../../docs/recipes/token-management-lean-ctx-rtk.md)
for the broader token-discipline context.

## See also

- [FastMCP docs](https://gofastmcp.com/) — official reference.
- [`docs/agent-harnesses.md`](../../docs/agent-harnesses.md) — MCP server
  registry pattern (when global vs per-project).
- [`docs/recipes/chrome-devtools-mcp-agent-loop.md`](../../docs/recipes/chrome-devtools-mcp-agent-loop.md)
  — a richer example of MCP-as-feedback-loop.
