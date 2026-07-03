# Global operator rules — source of truth

The canonical, harness-neutral operator ruleset ("how I work, what I expect")
lives in **AGENTS.md** and is imported below. Everything else in this CLAUDE.md
only *layers* Claude-specific tooling (lean-ctx) on top — it never
duplicates or overrides AGENTS.md. opencode reads the exact same file via
`~/.config/opencode/AGENTS.md` (symlink → the path below).

@/Users/markodragoljevic/.config/AGENTS.md

<!-- lean-ctx -->
<!-- lean-ctx-claude-v3 -->
## lean-ctx — Context Runtime

Prefer lean-ctx `ctx_*` for READING/exploring (their real strength):
- `ctx_read` instead of `Read` / `cat` (cached, 10 modes, re-reads ~13 tokens)
- `ctx_shell` instead of `bash` / `Shell` (95+ compression patterns)
- `ctx_search` instead of `Grep` / `rg` (compact results)
- `ctx_tree` instead of `ls` / `find` (compact directory maps)
- **Editing: use native `Read` then `Edit`.** `ctx_read` does NOT register for native Edit ("File has not been read yet") — read edit-targets natively. (`ctx_patch` works but is fiddly + in-repo only; skip it.)
- **Scope:** lean-ctx is project-only — for `~/.claude`/`~/.config` and other out-of-repo paths, use native tools (`ctx_read` refuses them).
- Write, Delete, Glob — use normally.

Read modes: full (edit), map (overview), signatures (API), diff (post-edit), lines:N-M (range), auto.
Details live in the `lean-ctx` skill (loads on demand — keep this file lean).
<!-- /lean-ctx -->
