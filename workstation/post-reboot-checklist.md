# Post-reboot checklist — this laptop (`markos-macbook-pro-1`)

**When to use:** after a full **restart** (not sleep). Sleep is fine — cmux
reconnects and everything resumes; nothing to check. A restart kills every live
process, so this is the path that needs validating (~every 2 weeks for you).

**Scope:** this laptop only. The homelab services (Grafana, VictoriaMetrics,
GlitchTip, Langfuse, Umami, LiteLLM, the `homelab-home` page) run on the **mini**
and **DGX** — a laptop restart does **not** touch them. Only check those if you
rebooted *that* box (separate concern).

---

## TL;DR — paste this after login, read the PASS/CHECK lines

```sh
U=$(id -u)
echo "1. awake-keeper:   $(launchctl print gui/$U/com.homelab.caffeinate 2>/dev/null | grep -q 'state = running' && echo PASS || echo 'FAIL — see fix 1')"
echo "   system sleep:   $(pmset -g | grep -q 'sleep.*prevented by caffeinate' && echo 'held (good)' || echo 'CHECK — nothing holding it')"
echo "2. display free:    $(pmset -g | grep -q 'displaysleep.*prevented by caffeinate' && echo 'FAIL — caffeinate is forcing display on (see fix 2)' || echo 'PASS — screen can sleep')"
echo "3. cmux-login job:  $(launchctl print gui/$U/com.homelab.cmux-login >/dev/null 2>&1 && echo 'loaded' || echo 'FAIL — see fix 3')"
echo "   cmux running:    $(pgrep -x cmux >/dev/null && echo PASS || echo 'FAIL — see fix 3')"
echo "   claude sessions: $(pgrep -f '/opt/homebrew/bin/claude' 2>/dev/null | wc -l | tr -d ' ') resumed"
echo "4. ollama:          $(pgrep -x ollama >/dev/null && echo PASS || echo 'FAIL — see fix 4')"
echo "5. tailscale→mini:  $(tailscale status 2>/dev/null | grep -q '^100.87.33.61.*homelab' && echo PASS || echo 'FAIL — see fix 5')"
```

Then eyeball cmux itself: **workspaces are back and the Claude agents resumed**
(that's `terminal.autoResumeAgentSessions = true`, pinned in
`~/.config/cmux/cmux.json`). Want the screen off? `pmset displaysleepnow`.

---

## The checklist

- [ ] **1. Machine stays awake.** `com.homelab.caffeinate` LaunchAgent is
      `running`, and `pmset -g` shows system sleep "prevented by caffeinate".
      This is what keeps the Claude sessions alive when you walk away.
- [ ] **2. Screen can still turn off.** `pmset -g` displaysleep line is **not**
      "prevented by caffeinate" (a transient `NotificationCenter` hold is fine —
      it clears on its own). If it's held by caffeinate, a stale `-d` snuck back.
- [ ] **3. cmux reopened with its workspaces + resumed agents.** The
      `com.homelab.cmux-login` job runs `open -a cmux` at login; cmux restores
      workspaces and re-resumes the Claude sessions. Confirm the workspaces and
      agents are actually back on screen, not just that the app launched.
- [ ] **4. ollama is up** (brew service, local LLM on `:11434`).
- [ ] **5. Tailscale is connected** and `homelab` (the mini, `100.87.33.61`) is
      reachable — that's your path to every remote service.

---

## Fixes if something's red

**Fix 1 — awake-keeper not running:**
```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.homelab.caffeinate.plist
```

**Fix 2 — caffeinate forcing the display on:** find the offender and check its
flags — a keeper should be `caffeinate -i -s` (no `-d`):
```sh
ps aux | grep '[c]affeinate'          # anything with -d asserts the display
pmset -g assertions | grep Display    # who holds PreventUserIdleDisplaySleep
```
Kill any stray `-d` caffeinate by PID; the launchd keeper (`-i -s`) is correct.

**Fix 3 — cmux didn't reopen:**
```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.homelab.cmux-login.plist
open -a cmux
# sessions not resuming? confirm the setting is still pinned:
~/.agents/skills/cmux-settings/scripts/cmux-settings get terminal.autoResumeAgentSessions   # want: true
```

**Fix 4 — ollama down:**
```sh
brew services start ollama
```

**Fix 5 — tailscale not up / mini unreachable:**
```sh
tailscale status | head        # is the node up at all?
tailscale ping homelab         # path to the mini
# GUI: open the Tailscale menu-bar app and reconnect if logged out
```

---

## Known gap (not yet automated)

The two `com.homelab.*` LaunchAgents are **not yet tracked by
`workstation/install.sh`** — they were created live. A fresh-machine restore
(`install.sh`) will *not* recreate them. Follow-up: add both plists to the
workstation restore set so a clean Mac gets the awake-keeper + cmux-login for
free. Until then, if you wipe/restore this laptop, recreate them by hand.
