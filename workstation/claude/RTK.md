# RTK - Rust Token Killer

**Usage**: Token-optimized CLI proxy (60-90% savings on dev operations)

## Meta Commands (always use rtk directly)

```bash
rtk gain              # Show token savings analytics
rtk gain --history    # Show command usage history with savings
rtk discover          # Analyze Claude Code history for missed opportunities
rtk proxy <cmd>       # Execute raw command without filtering (for debugging)
```

## Installation Verification

```bash
rtk --version         # Should show: rtk X.Y.Z
rtk gain              # Should work (not "command not found")
which rtk             # Verify correct binary
```

⚠️ **Name collision**: If `rtk gain` fails, you may have reachingforthejack/rtk (Rust Type Kit) installed instead.

## Manual usage — no auto-hook (as of 2026-07-01)

The Claude Code auto-rewrite hook was removed — `lean-ctx` owns Bash-command
rewriting now (the two competed on every command). Invoke rtk explicitly when you
want its tuned per-tool output; the analytics run standalone.

```bash
rtk git status        # compact git
rtk docker ps         # compact docker output
rtk err <cmd>         # run cmd, show only errors/warnings
rtk test <cmd>        # run tests, show only failures
```

Refer to CLAUDE.md for the full command reference.
