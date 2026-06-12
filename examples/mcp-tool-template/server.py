"""Example FastMCP server — three tools demonstrating the common shapes.

Run standalone:
    python server.py

Or wire into Claude Code / opencode (see README for the JSON snippets).
"""

from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("example-tools")


@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name. Pure-function shape — args in, value out."""
    return f"Hello, {name}!"


@mcp.tool()
def word_stats(text: str) -> dict:
    """Count words and characters in `text`.

    Returns a structured dict. This is the shape most real tools take —
    typed args, dict response, no side effects.
    """
    words = text.split()
    return {
        "word_count": len(words),
        "char_count": len(text),
        "longest_word": max(words, key=len) if words else "",
    }


@mcp.tool()
def read_lines(path: str, n: int = 20) -> dict:
    """Read the first `n` lines of a file.

    Demonstrates the filesystem-touching shape + how to handle errors
    cleanly. Returns either {"lines": [...], "truncated": bool} on success
    or {"error": "..."} on failure — never raises through to the MCP
    transport.

    Default truncation (20 lines) keeps the response cheap. The agent can
    re-call with a larger `n` if it needs more.
    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            return {"error": f"not a file: {p}"}

        with p.open("r", encoding="utf-8", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= n:
                    return {"lines": lines, "truncated": True}
                lines.append(line.rstrip("\n"))
            return {"lines": lines, "truncated": False}

    except (OSError, PermissionError) as e:
        return {"error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    mcp.run()
