---
name: host-run
description: Run a multi-line, quoted or JSON-bearing command on a homelab host (the Mac mini, the DGX, the prod VPS) from a script file instead of inline over ssh — it copies the file, runs it with bash or python3, streams the output, returns the remote exit code and deletes the copy. Use whenever a remote command has more than one line, quotes inside quotes, JSON, a heredoc or inline Python, before writing `ssh host '...'` by hand.
---

# host-run

Inline commands over `ssh` break in ways that look like real failures:
- zsh on the laptop expands `=word` (`echo =====` → `zsh: ==== not found`);
- nested quotes corrupt JSON bodies silently (`Invalid JSON`);
- inline Python f-strings can't contain backslashes;
- non-interactive shells on the mini lack `/usr/local/bin`, so `docker` isn't found.

All of these hit this repo's sessions repeatedly (2026-10-16/17). A script file has none of
them.

## Run

```bash
# write the commands to a file in your scratchpad, then:
~/.claude/skills/host-run/scripts/run.sh <host> <file.sh|file.py> [args...]
```

| Host | Reaches |
|---|---|
| `homelab` (or `mini`) | the Mac mini, operator account (`ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab`) |
| `homelab-claude` | the mini's `claude` account (`ssh homelab-claude`) |
| `dgx` | `dgx-llm-1` |
| `prod` | `deploy@prod-podcast` |

- `.py` files run with `python3`, anything else with `bash`.
- `/usr/local/bin` and `/opt/homebrew/bin` are put on `PATH`, so `docker` works on the mini.
- Arguments are passed literally (each one `%q`-quoted).
- The exit status is the remote script's: 2 means bad usage, 3 means the host is unreachable.
- The remote copy lives in `/tmp/host-run.XXXXXX` (mode 700) and is removed on exit.

## Rules

- **Secrets never go in the file or the arguments.** The script loads them on the host
  (`set -a; . ~/…/.env; set +a`), the way the handbook's recipes do.
- Read-only by default. A script that writes (deletes, restarts, mints) needs the same approval
  as running those commands by hand.
- Keep the file in your scratchpad, not in a repo.

## Verified

2026-10-17 on `homelab` and `dgx`:
- arguments `"arg one" '$HOME' '=x'` arrived literally;
- JSON with spaces round-tripped;
- `echo =====` printed;
- an f-string with a backslash ran;
- `docker` resolved;
- `exit 7` came back as 7, and an unknown host exited 2;
- no `/tmp/host-run.*` files were left on either host.

## Not covered

- Interactive commands (`sudo` with a password, TUI tools).
- Copying files back; use `scp` for that.
- Long-running jobs; the script runs in the foreground of the ssh session.
