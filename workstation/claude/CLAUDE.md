# Global operator rules — source of truth

The canonical, harness-neutral operator ruleset ("how I work, what I expect")
lives in **AGENTS.md** and is imported below. Everything else in this CLAUDE.md
only *layers* Claude-specific tooling (lean-ctx, RTK) on top — it never
duplicates or overrides AGENTS.md. opencode reads the exact same file via
`~/.config/opencode/AGENTS.md` (symlink → the path below).

@/Users/markodragoljevic/.config/AGENTS.md

@RTK.md

<!-- lean-ctx -->
<!-- lean-ctx-claude-v3 -->
## lean-ctx — Context Runtime

Always prefer lean-ctx MCP tools over native equivalents:
- `ctx_read` instead of `Read` / `cat` (cached, 10 modes, re-reads ~13 tokens)
- `ctx_shell` instead of `bash` / `Shell` (95+ compression patterns)
- `ctx_search` instead of `Grep` / `rg` (compact results)
- `ctx_tree` instead of `ls` / `find` (compact directory maps)
- Native Edit/StrReplace stay unchanged. If Edit requires Read and Read is unavailable, use `ctx_edit(path, old_string, new_string)` instead.
- Write, Delete, Glob — use normally.

Read modes: full (edit), map (overview), signatures (API), diff (post-edit), lines:N-M (range), auto.
Details live in the `lean-ctx` skill (loads on demand — keep this file lean).
<!-- /lean-ctx -->
