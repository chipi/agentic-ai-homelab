# DGX terminal dashboard — tmux + mosh + custom panes

**Date:** 2026-06-12
**Status:** v0.1 — live, in daily use
**Reach:** Tailscale + mosh + tmux (no public exposure)

A 4-pane tmux dashboard for the DGX that gives a complete "what's the box
doing right now" view in one window. Built over mosh so it survives laptop
sleep and network changes. Reached over the tailnet, no public exposure.

This doc is the rebuild recipe + cheat sheet. Everything below is what's
currently live (as of the Date above) in the operator's homelab.

> **Placeholder legend.** Throughout this doc, `<angle-bracketed>` tokens
> mark per-operator values — substitute consistently with your own:
>
> | Placeholder | What it stands for |
> |---|---|
> | `<operator>` | Your local username (Mac + DGX) |
> | `<dgx-host>` | DGX hostname on the tailnet (e.g. `dgx-llm-1`) |
> | `<your-tailnet>` | Your Tailscale tailnet name (the `tailXXXX` prefix) |
> | `<your-key>` | SSH private key filename you use to reach the DGX |
> | `<dgx-tailnet-ip>` | The DGX's tailnet IP (only appears in one troubleshooting example) |
> | `<dgx-tag>` | Tailscale ACL tag you've assigned to the DGX node |
> | `<laptop>` | Your laptop's tailnet name (only in the optional 5th-pane idea) |

---

## Connection chain

```
Mac (cmux / Ghostty)
  └─ mosh <dgx-host>.<your-tailnet>.ts.net -- tmux attach -t dgx
       └─ SSH over tailnet (auth) → mosh-server spawn → UDP 60000-61000 (transport)
            └─ DGX tmux server (session "dgx")
                 └─ window "watch", 2x2 panes:
                      .1 nvitop  .2 btop  .3 llm-status  .4 ctop
                       (positions can vary by render order)
```

Each layer's role:

- **cmux/Ghostty** — Mac-side terminal multiplexer; uses Cmd-based shortcuts so `Ctrl-b` passes straight through to inner tmux.
- **mosh** — survives sleep / network change / IP change. Same UX as ssh, just resumes after a yellow `[network connection lost]` indicator.
- **tailnet** — encrypted transport, ACL'd. UDP 60000-61000 explicitly opened for mosh.
- **tmux on DGX** — persistent session; programs keep running when you detach.

---

## Daily command

```bash
mosh <dgx-host>.<your-tailnet>.ts.net -- tmux attach -t dgx
```

Or via shell alias (suggested in `~/.zshrc`):

```bash
alias dgx="mosh <dgx-host>.<your-tailnet>.ts.net -- tmux attach -t dgx"
```

Then `dgx` ⏎ from anywhere = instant dashboard.

To **start fresh** instead of attaching (kills any existing session, rebuilds layout):

```bash
mosh <dgx-host>.<your-tailnet>.ts.net -- ~/dgx-dash.sh
```

---

## Files installed

### On DGX (`/home/<operator>/`)

| Path | Purpose |
|------|---------|
| `~/.config/tmux/tmux.conf` | tmux preferences (mouse, history, status bar, bindings) |
| `~/dgx-dash.sh` | dashboard launcher — builds session + 4 panes |
| `~/dgx-dash.sh.bak` | backup of original 13-line script (pre-polish) |
| `~/llm-status.sh` | custom one-screen LLM-stack health summary |
| `/usr/local/bin/ctop` | container-metrics TUI (manual install, ARM64 binary v0.7.7) |

### On Mac (`/Users/<operator>/`)

| Path | Change |
|------|--------|
| `~/.ssh/config` | Added keepalive for `<dgx-host>` + convenience host block |
| `~/.tmux.conf` | Pre-existing (Ctrl-a prefix, mouse, split-with-pipe). Unchanged. |
| `/opt/homebrew/bin/mosh` | Installed via `brew install mosh` (v1.4.0). |

### Tailscale ACL (admin console: <https://login.tailscale.com/admin/acls/file>)

One rule added to allow UDP 60000-61000 from operator → DGX:

```json
{
  "action": "accept",
  "src":    ["<operator>@example.com"],
  "dst":    ["tag:<dgx-tag>:60000-61000"],
  "proto":  "udp"
}
```

---

## File contents (verbatim, for rebuild)

### `~/.config/tmux/tmux.conf` (DGX)

```bash
# ─── general ────────────────────────────────────────────────
set -g mouse on                       # click to focus, scroll panes, drag borders
set -g history-limit 10000            # 10k lines of scrollback per pane
set -g base-index 1                   # windows start at 1, not 0
setw -g pane-base-index 1             # panes too — first pane in a window is .1
set -g renumber-windows on            # close a window → re-tighten numbering
set -g default-terminal "tmux-256color"
set -g repeat-time 1000               # 1s window for repeating prefix actions (arrows)

# ─── pane navigation without the prefix ─────────────────────
# Alt+arrow jumps panes instantly. If your terminal sends Esc instead of Alt,
# enable "Option as Meta" in cmux/Ghostty, or just delete these four lines.
bind -n M-Left  select-pane -L
bind -n M-Right select-pane -R
bind -n M-Up    select-pane -U
bind -n M-Down  select-pane -D

# ─── status bar (keep tmux default green) ───────────────────
# Adds a right-side readout so you can see at a glance what machine/session you're on.
set -g status-right ' #[bold]#S#[default] @ #H  %H:%M '
set -g status-right-length 60

# ─── reload this config without restarting tmux ─────────────
bind r source-file ~/.config/tmux/tmux.conf \; display "reloaded ~/.config/tmux/tmux.conf"
```

### `~/dgx-dash.sh` (DGX)

```bash
#!/bin/bash
# 4-pane DGX monitoring dashboard.
# Layout (2x2 — physical positions can vary by tmux split order):
#   ┌──────────────────┬──────────────────┐
#   │ .1  nvitop       │ .2  btop         │
#   ├──────────────────┼──────────────────┤
#   │ .4  ctop         │ .3  llm-status   │
#   └──────────────────┴──────────────────┘
# General tmux settings live in ~/.config/tmux/tmux.conf (auto-loaded by tmux).
set -euo pipefail

SESSION=dgx
WINDOW=watch

tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" -n "$WINDOW"

# 2x2 grid (pane-base-index=1 from tmux.conf → first pane is .1)
tmux split-window -h -t "$SESSION:$WINDOW"
tmux split-window -v -t "$SESSION:$WINDOW.2"
tmux split-window -v -t "$SESSION:$WINDOW.1"

tmux send-keys -t "$SESSION:$WINDOW.1" 'nvitop' C-m
tmux send-keys -t "$SESSION:$WINDOW.2" 'btop' C-m
tmux send-keys -t "$SESSION:$WINDOW.3" 'watch -n 2 -t -c ~/llm-status.sh' C-m
tmux send-keys -t "$SESSION:$WINDOW.4" 'ctop' C-m

tmux select-pane -t "$SESSION:$WINDOW.1"
tmux attach -t "$SESSION"
```

### `~/llm-status.sh` (DGX)

```bash
#!/bin/bash
# llm-status.sh — one-screen "what's the LLM stack doing right now" summary.
# Designed to be called by `watch -n 2 -t -c ~/llm-status.sh`.
set +e

C_HDR='\033[1;36m'; C_OK='\033[32m'; C_BAD='\033[31m'; C_DIM='\033[2m'; C_RST='\033[0m'

printf "${C_HDR}═══ LLM stack @ $(date '+%H:%M:%S')  uptime $(uptime -p | sed 's/^up //') ═══${C_RST}\n\n"

# ── Service health ──
printf "${C_HDR}Service:${C_RST}  "
state=$(systemctl is-active ollama 2>/dev/null)
[ "$state" = active ] && printf "ollama ${C_OK}●${C_RST}  " || printf "ollama ${C_BAD}● $state${C_RST}  "
ss -lntH 2>/dev/null | awk '$4 ~ /:(11434|800[0-9]|8010)$/ {sub(/.*:/, "", $4); print $4}' | sort -un | while read p; do
    printf ":$p ${C_OK}●${C_RST}  "
done
printf '\n\n'

# ── Loaded models ──
printf "${C_HDR}Loaded models:${C_RST}\n"
models=$(curl -fsS --max-time 1 localhost:11434/api/ps 2>/dev/null)
if [ -n "$models" ]; then
    n=$(echo "$models" | jq -r '.models | length' 2>/dev/null)
    if [ "$n" -gt 0 ] 2>/dev/null; then
        echo "$models" | jq -r '.models[] |
            "  \(.name)\t\((.size_vram/1024/1024/1024) | floor)GiB VRAM\t\(.details.parameter_size)\texpires \(.expires_at | sub("\\..*"; "") | sub("T"; " "))"' \
            | column -t -s $'\t'
    else
        printf "  ${C_DIM}(none warm — ollama is cold)${C_RST}\n"
    fi
else
    printf "  ${C_BAD}(ollama API unreachable)${C_RST}\n"
fi
printf '\n'

# ── Recent traffic (last 60s) ──
printf "${C_HDR}Ollama traffic (last 60s):${C_RST}\n"
log60=$(journalctl -u ollama --since "60 seconds ago" --no-pager 2>/dev/null)
total=$(printf '%s\n' "$log60" | grep -c '\[GIN\]')
if [ "$total" -gt 0 ]; then
    rps=$(echo "scale=2; $total/60" | bc -l)
    printf "  ${C_OK}%s${C_RST} requests  (%s req/s)\n" "$total" "$rps"
    printf '%s\n' "$log60" | awk '
        /\[GIN\]/ {
            n = split($0, parts, "|")
            tail = parts[n]
            if (match(tail, /([A-Z]+)[[:space:]]+"([^"]+)"/, m)) {
                print m[1] " " m[2]
            }
        }
    ' | sort | uniq -c | sort -rn | head -3 | awk -v dim="$(printf "$C_DIM")" -v rst="$(printf "$C_RST")" '{printf "  %s%4d%s  %s %s\n", dim, $1, rst, $2, $3}'
    errs=$(printf '%s\n' "$log60" | grep -cE '\| 5[0-9]{2} \|')
    [ "$errs" -gt 0 ] && printf "  ${C_BAD}%s errors (5xx)${C_RST}\n" "$errs"
else
    printf "  ${C_DIM}idle${C_RST}\n"
fi
printf '\n'

# ── GPU memory by process ──
printf "${C_HDR}GPU memory by process:${C_RST}\n"
nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader 2>/dev/null \
    | awk -F', ' '{printf "  pid %-8s %10s  %s\n", $1, $2, $3}' \
    | head -6
```

### `~/.ssh/config` additions (Mac)

```sshconfig
# Keep SSH connections alive over flaky networks / brief naps.
# Sends a keepalive every 30s; gives up if 4 in a row miss (= 2 min dead → disconnect).
# Doesn't fix laptop-sleep (no packets while asleep) — that's what mosh is for.
Host <dgx-host> *.<your-tailnet>.ts.net
    ServerAliveInterval 30
    ServerAliveCountMax 4
    TCPKeepAlive yes

# Convenience: connect with just `ssh <dgx-host>` or `mosh <dgx-host>.<your-tailnet>.ts.net`
# — no -u, no -i needed.
Host <dgx-host> <dgx-host>.<your-tailnet>.ts.net
    User <operator>
    IdentityFile ~/.ssh/<your-key>
    IdentitiesOnly yes
```

---

## tmux cheat sheet — what I actually press

Prefix is **`Ctrl-b`** (default — kept stock on DGX). Press prefix, release, then the action key. Upstream tmux has many more bindings; this is the working set for this dashboard.

| Key | Action |
|---|---|
| `Ctrl-b d` | **Detach** — leave session running, back to plain shell |
| `Ctrl-b r` | Reload `~/.config/tmux/tmux.conf` (custom binding) |
| `Ctrl-b [` | **Copy/scroll mode** — arrows / PgUp to navigate; `q` exits |
| `Ctrl-b z` | **Zoom** active pane fullscreen (toggle) — look for `Z` in status bar |
| `Ctrl-b ← → ↑ ↓` | Move focus to neighbor pane (1s repeat window) |
| `Alt + ← → ↑ ↓` | Same, no prefix needed (requires Option-as-Meta in terminal) |
| Click pane / drag border | Focus + resize (mouse mode on) |

Anything else (splits, new windows, sessions list, kill pane): see `Ctrl-b ?` or upstream `man tmux`.

---

## Pane tools — keys I actually use

### nvitop (.1 — GPU monitor)

| Key | Action |
|---|---|
| `a` | **Cycle display modes** (full / compact / auto — the move) |
| `Tab` | Switch focus between GPU panel and Process panel |
| `↑` `↓` + `Enter` | Select process / inspect |
| `/` | Filter processes by name |
| `t` / `k` | Terminate / kill selected process |
| `q` | Quit |

### btop (.2 — host CPU/mem/net)

| Key | Action |
|---|---|
| `1`-`4` | Toggle each box (CPU / mem / net / proc) |
| `m` | Cycle process sort columns |
| `Enter` | Inspect selected process |
| `q` | Quit |

### ctop (.4 — container metrics)

| Key | Action |
|---|---|
| `Enter` on a container | Open detail view |
| **`q`** in detail view | **Back to overview** (NOT exit ctop) |
| `q` from overview | Exit ctop |
| `l` (on focused container) | Live log view |

### llm-status (.3 — custom LLM monitor)

No keybindings — read-only `watch` view. Refreshes every 2 seconds.
Shows: service health, listening ports, loaded Ollama models with VRAM
+ keep-alive expiry, request rate (last 60s), top endpoints, GPU memory
by process.

---

## Mac side — cmux / mouse / keyboard quirks

### cmux nesting

- cmux uses Cmd-based shortcuts; `Ctrl-b` passes through cleanly to DGX tmux. No prefix conflict.
- Tab cycling **within** a cmux workspace: `Cmd+Shift+]` / `Cmd+Shift+[`
- Workspace cycling: try `Cmd+Ctrl+Shift+]` or `Cmd+Shift+<number>` (not yet confirmed)
- Open cmux's `Cmd+K` command palette if it has one — best way to discover bindings.

### Mouse in inner tmux over SSH (broken)

When using plain SSH (not mosh), inner-tmux mouse clicks required Cmd+double-click — the first click was eaten by cmux/Ghostty's own pane focus.

### Mouse in inner tmux over mosh (works)

After switching to mosh, single-click pane focus, trackpad scroll, drag-resize all work as expected. **Use mosh.**

### Text selection (tmux mouse on)

Holding **Option while dragging** lets the terminal natively select text (for Cmd+C). Without it, tmux owns the mouse and drag-to-select doesn't behave like a native terminal.

Alternative: tmux's copy mode (`Ctrl-b [` → navigate → `Space` to mark start → move → `Enter` to yank). Yank goes to tmux's clipboard. With OSC52 it can flow to Mac clipboard — future polish.

---

## Troubleshooting recipes

### Laptop slept → console prints weird characters

Happens with plain SSH; doesn't happen with mosh. If you're still on SSH:

```bash
# Drop the broken connection, open a fresh cmux tab, then:
ssh <dgx-host>.<your-tailnet>.ts.net
# If the shell looks scrambled before tmux attach:
reset
tmux attach -t dgx
```

The DGX-side tmux state is preserved; you're only reconnecting a viewer. **Long-term fix: use mosh.**

### `mosh: Nothing received from server on UDP port 60001`

Tailscale ACL is blocking UDP. Verify the ACL rule exists (see the JSON above), then sanity-test UDP path:

```bash
# DGX: listen
ssh <dgx-host>.<your-tailnet>.ts.net 'timeout 5 python3 -c "
import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind((\"0.0.0.0\", 60050)); s.settimeout(4)
print(\"listening\"); print(s.recvfrom(64))" ' &
sleep 1
# Mac: send
python3 -c "
import socket
socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'ping', ('<dgx-host>.<your-tailnet>.ts.net', 60050))"
wait
```

Should print `listening` then `(b'ping', ('<dgx-tailnet-ip>', ...))`. If you don't see the second line, ACL still blocks.

### Stray mosh-server holding a port

Kill them and reconnect:

```bash
ssh <dgx-host>.<your-tailnet>.ts.net 'pkill -u <operator> mosh-server'
mosh <dgx-host>.<your-tailnet>.ts.net -- tmux attach -t dgx
```

### Reload tmux config without losing the session

Inside tmux: `Ctrl-b r` (or `Ctrl-b :` then `source-file ~/.config/tmux/tmux.conf`). All panes / programs / scrollback preserved.

### Rebuild dashboard from scratch

```bash
# Inside tmux:
Ctrl-b d                # detach
~/dgx-dash.sh           # kills "dgx" session, builds fresh layout, attaches
```

---

## Future improvements (not done)

- **OSC52 clipboard** — let tmux-copied text land in Mac clipboard automatically (one tmux.conf line).
- **systemd-user auto-start** — boot DGX → dashboard ready, no manual `dgx-dash.sh`.
- **`tmux-resurrect` / `tmux-continuum`** — save full session state across DGX reboots.
- **Add vLLM pane / extend llm-status** — when vLLM lands (homelab v0.2), the port-auto-detect in `llm-status.sh` will surface it automatically; add a "vLLM /metrics" section if Prometheus endpoint exposed.
- **Tailnet RTT pane** — `ping <laptop>` in a 5th pane for link sanity. Probably unneeded if mosh feels healthy.

---

## Quick reference card

```
Connect:           mosh <dgx-host>.<your-tailnet>.ts.net -- tmux attach -t dgx
Detach:            Ctrl-b d
Reload tmux conf:  Ctrl-b r
Rebuild layout:    Ctrl-b d  →  ~/dgx-dash.sh
Zoom a pane:       Ctrl-b z   (toggle)
Pane navigation:   Ctrl-b ← → ↑ ↓   (or Alt+arrow)
Scroll history:    Ctrl-b [   →  arrows / PgUp  →  q
ctop detail back:  q  (only quits ctop from overview)
nvitop layout:     a  (cycle compact / full)
```
