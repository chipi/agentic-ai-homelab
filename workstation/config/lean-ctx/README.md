# LeanCTX — workstation configuration and project-root isolation

`config.toml` here is the operator's global LeanCTX config (symlinked to
`~/.config/lean-ctx/config.toml` by `install.sh`). LeanCTX is a global tooling layer:
one install serves every project and every agent, so no project may become its
"current" project for anybody else.

## Root semantics (what LeanCTX should use, and does after the fix)

For every invocation the project root is derived from **that invocation's own cwd**:
LeanCTX resolves it to the Git top-level (`git rev-parse --show-toplevel`). So:

| Agent cwd | Root |
|---|---|
| `/work/<project>/main` or a directory below it | `/work/<project>/main` |
| `/work/<project>/worktrees/<task>` or below it | that worktree, not `main` |
| two worktrees of the same project | each its own |

Nothing is shared between invocations, so concurrency is safe by construction:
two agents in two projects (or two worktrees) never consult a common "current root".
The jail is unchanged: from one root, another project's or sibling worktree's files
are still refused by LeanCTX's own tools.

## The defect it fixes (2026-10-16)

**Symptom.** An agent in `/work/oceancanvas/main` (or any project other than Orrery,
or any worktree) had plain reads refused:
`path escapes project root: …/README.md (root: /work/orrery/main). Access denied: outside active project`.
The refusal exits 0, so callers saw "success" with an error text.

**Mechanism (reproduced in isolation, see the test).**

1. The Claude Code `PreToolUse` Bash hook (`lean-ctx hook rewrite`) turns native
   `cat`/`head`/`sed -n`/`tail` into `lean-ctx read`, `grep`/`rg` into
   `lean-ctx grep`, and `ls <dir>` into `lean-ctx ls`.
2. Those one-shot CLI calls are by default forwarded to ONE per-user daemon
   (`lean-ctx serve --_foreground-daemon`, socket `~/.local/share/lean-ctx/daemon.sock`),
   auto-started by the first call that needed it.
3. The daemon checks every request against **its own** project root, which is the
   cwd of the call that started it. On the X3 that was `/work/orrery/main` on
   2026-10-02 (the daemon's `/proc/<pid>/cwd`). The caller's cwd, `--root` and
   `LEAN_CTX_PROJECT_ROOT` are all ignored on that path.

Not involved: the MCP `ctx_*` tools (each agent's MCP server is its own process in
the agent's cwd, so `ctx_read` was always correctly rooted, which is why the
symptom looked inconsistent), tmux, Workbench, `lean-ctx-proxy.service` (an API
proxy, unrelated), the config file, Git normalization. Upstream issue
[#1695](https://github.com/yvgude/lean-ctx/issues/1695) reports the same mechanism;
it is closed, but the `lean-ctx read` path still reproduces in 3.10.5 (installed) and
3.11.4 (latest, tested in isolation).

**Fix.** `install.sh` adds one line to `~/.bashrc` (marked block `lean-ctx-root`):

```bash
export __LEAN_CTX_NO_DAEMON=1
```

With it, those one-shot calls run in the calling process and derive the root from
its cwd. Agents started from a shell (tmux panes are login shells; Omarchy's
`~/.bash_profile` sources `~/.bashrc`) inherit it, and so do their hooks and tool
shells. Notes:

- It is an internal LeanCTX variable (double underscore), the same switch upstream's
  own #1695 report uses; LeanCTX tests only that it is **present** (`=0` also
  disables the daemon). `LEAN_CTX_NO_DAEMON` without the underscores does nothing.
  `root-isolation.test.sh` fails if a LeanCTX upgrade stops honoring it.
- Nothing else changes: same config, same jail, same hook decisions (tested), no
  global root, no `extra_roots`/`allow_paths` widening, no project names.
- No restart is needed or useful. Agents already running keep their environment
  (and the old behavior) until they are restarted; restarting the daemon would only
  re-root it to whoever calls next. The daemon keeps running; new agents simply
  stop using it for these calls.
- Cost: the one-shot calls no longer use the daemon's warm process. Measured on the
  X3 (20 one-line reads of the same file): 94 ms median locally vs 32 ms through
  the daemon, so about 60 ms more per rewritten read. MCP `ctx_*` calls are
  unaffected.
- On 3.10.5 a direct `lean-ctx read <path outside the root>` run locally only warns
  instead of refusing (upstream #1903, fixed in 3.11.0). The hook never produces such
  a call: cross-project reads pass through as the native command, before and after
  the fix, so agents' effective access is unchanged.

## If an agent gets the wrong root again

```bash
echo "${__LEAN_CTX_NO_DAEMON-unset}"          # in the agent's shell: must not be 'unset'
tr '\0' '\n' < /proc/<agent-pid>/environ | grep __LEAN_CTX_NO_DAEMON   # a running agent's env
readlink /proc/$(cat ~/.local/share/lean-ctx/daemon.pid)/cwd            # the shared daemon's root
cd <checkout> && lean-ctx read README.md -m lines:1-1                   # via the daemon (unset variable)
cd <checkout> && __LEAN_CTX_NO_DAEMON=1 lean-ctx read README.md -m lines:1-1   # per-invocation
bash workstation/config/lean-ctx/root-isolation.test.sh                 # the whole regression suite
```

If the refusal names a root that is not the agent's checkout and the variable is
unset in that agent, start a new shell/tmux window (or re-run `install.sh` if the
`lean-ctx-root` block is missing from `~/.bashrc`) and restart that agent.

## Relationship to Workbench

Workbench owns the layout (`/work/<project>/main`, `…/worktrees/<task>`) and starts
agents in the right directory; LeanCTX derives everything from that cwd. Workbench
does not pass roots to LeanCTX and does not need to.

## Executable allowlist

`shell_allowlist_extra` adds `wt`, `wb-stream`, `wb-workspace`, `wb-integrate`.
`wb-storage` and `wb-tmux` are deliberately **not** allowlisted: both mix read-only
subcommands (`status`, `verify`, `show`) with state-changing ones (`install-dropins`;
`save`, `restore`), they are operator tools for maintenance windows, and LeanCTX
3.10.5 can only allow a whole executable (subcommand entries such as `"wb-tmux status"`
arrive in 3.11.0). Revisit if agents genuinely need the read-only subcommands.

`setsid` is also not on the allowlist, so `lean-ctx -c 'setsid …'` (what the hook
makes of a `setsid` command typed directly) is refused in every project, while a
`setsid` inside a script run with `bash script.sh` is not checked. That is the
"setsid works in some sessions" observation; it is unrelated to the root defect.
Whether to allow it is a separate decision.

## Tests

`bash workstation/config/lean-ctx/root-isolation.test.sh`: scratch Git projects
(alpha with two worktrees, beta), a scratch LeanCTX state dir with its own daemon,
the real hook. It reproduces the defect, then requires, with the fix: 120
alternating sequential reads and 400 concurrent ones (four contexts at once, plus an
unfixed caller keeping the alpha-rooted daemon busy) all answered from their own
context; worktrees rooted at themselves; identical hook decisions with and without
the fix; the MCP jail still refusing other projects and sibling worktrees; tmux
panes picking the fix up from `~/.bashrc`; the real daemon and tmux server untouched.
