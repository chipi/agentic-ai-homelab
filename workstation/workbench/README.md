# workbench — persistent tmux session for phone/SSH access

A always-on tmux session named `main`, one window per project, so a phone SSH
client can attach and drive an agent without rebuilding anything.

| File | Installed to | Purpose |
|---|---|---|
| `wb` | `~/bin/wb` | Rebuild the session if needed, then attach. The only command you type. |
| `wb-session.sh` | `~/bin/wb-session.sh` | Create session `main` with one window per project, detached. Idempotent. |
| `tmux.conf` | `~/.tmux.conf` | Phone-friendly: mouse on, status bar doubles as the key-chord cheatsheet, OSC 52 clipboard. |
| `com.chipi.workbench.plist` | `~/Library/LaunchAgents/` | Runs `wb-session.sh` on session start so the windows are already there. |

Install via `workstation/install.sh` (symlinks all four). Then:

    launchctl bootstrap user/$(id -u) ~/Library/LaunchAgents/com.chipi.workbench.plist

Adding a project is one line in `wb-session.sh` — `new-window -t $S -n <name> -c <path>`.

## Two things that are easy to get wrong

**`LimitLoadToSessionType` must include `Background`.** A LaunchAgent defaults to
the `Aqua` session type. Reaching this box over SSH puts you in a `Background`
launchd domain (confirm with `launchctl managername`), and bootstrapping an
Aqua-only agent there fails with the near-useless `Bootstrap failed: 5:
Input/output error`. The plist lists both types.

**A LaunchAgent is not a boot job.** It runs when its user gets a login session.
If the SSH account is not the console user and no `autoLoginUser` is set, a plain
reboot never starts that user's session, so the agent does not fire until someone
SSHes in. Check with:

    stat -f "%Su" /dev/console
    defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser

If the session must exist before any login, this has to be a LaunchDaemon in
`/Library/LaunchDaemons` with `<key>UserName</key>` set to the target account,
which needs root. The agent here does not cover that case.

## Socket note

tmux honours `TMUX_TMPDIR` (or `-L`), not `TMPDIR`, so the server lands on a
path like `/private/tmp/tmux-<uid>/default` that is identical across Aqua,
Background, and SSH sessions of the same uid. That is why an agent-started
server is still reachable from an interactive `tmux attach`.
