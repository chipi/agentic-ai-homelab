# Chrome DevTools MCP — agent feedback loop for UI work

**Date:** 2026-06-12
**Status:** v0.1 — in daily use on orrery (SvelteKit) and podcast_scraper
**Reach:** local Chrome / Chromium; per-project MCP server

The single highest-leverage MCP server for any project with a browser-
visible surface. The agent gets a Chrome it can drive: navigate, click,
type, screenshot, run JavaScript, watch the network, read console errors.
That closes the inner-loop on UI work — instead of asking "did my CSS
change work?", the agent inspects the rendered page and answers itself.

> **Placeholder legend.**
>
> | Placeholder | What it stands for |
> |---|---|
> | `<project-dir>` | Project root where the MCP is registered |
> | `<dev-server-url>` | URL of the local dev server, e.g. `http://localhost:5173` |

---

## Why this exists

Without the MCP, the agent-on-UI-task loop is:

```
1. Agent edits Svelte component / CSS / template.
2. Agent: "I think this should work — please reload and check."
3. Operator: reloads, looks, screenshots, reports back.
4. Goto 1 until correct.
```

Operator-in-the-loop on every iteration is the bottleneck. The Chrome
DevTools MCP collapses that:

```
1. Agent edits.
2. Agent navigates the live page, takes a screenshot, reads console.
3. Agent verifies — or sees the bug and iterates without asking.
4. Agent only surfaces to operator when:
     - Stuck (hits a question only operator can answer)
     - Done (visual + console verified clean)
```

The win isn't speed alone — it's that the agent develops better
verification habits. "Done" requires *observed* correctness, not
*hoped-for* correctness.

---

## What the MCP gives the agent

A subset of Chrome DevTools Protocol exposed as MCP tools. The
operationally important ones:

| Tool | What it does |
|---|---|
| `navigate_page` | Open a URL in the controlled browser |
| `take_screenshot` | PNG of the page (or a specific element) — returns to agent as an image |
| `take_snapshot` | Accessibility tree of the page (cheaper than screenshot, text-only) |
| `evaluate_script` | Run JS in the page, return the result |
| `click_element` / `type_text` / `fill_form` | Drive interactions |
| `list_console_messages` | Read errors / warnings / logs |
| `list_network_requests` | Inspect fetch / XHR traffic |
| `wait_for` | Wait for a selector / network-idle / a JS predicate |
| `emulate_cpu_throttling` / `emulate_network` | Simulate slow CPU / slow net |

The agent sees screenshot output natively (multimodal) — it doesn't have
to OCR a saved file. Same for the snapshot (accessibility tree is
structured, dirt-cheap on tokens).

---

## Two install modes — pick the right one

### A. Headless + isolated  *(fast, ephemeral)*

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "chrome-devtools-mcp@latest",
        "--headless",
        "--isolated"
      ],
      "env": {}
    }
  }
}
```

- **No visible browser window.**
- **Fresh browser context per MCP-server start** (no cookies, no
  localStorage carry-over).
- Use for: CI-shaped tasks, anything where you want zero side effects,
  Claude Code sessions over cron / scheduled agents.

### B. Visible + persistent  *(debuggable, sticky)*

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "chrome-devtools-mcp@latest"
      ],
      "env": {}
    }
  }
}
```

- **Real Chrome window opens** when the agent calls `navigate_page` —
  you watch the agent work in real time.
- **Persistent profile**: stays logged in across sessions; useful when
  the page under test needs auth (orrery's admin dashboard, etc.).
- Use for: live UI iteration with operator watching, anything that
  needs an authenticated session.

The operator's working setup uses **(A)** for podcast_scraper-style
work (data pipelines that emit dashboards) and **(B)** for orrery (rich
Svelte UI you want to *see* the agent driving).

---

## Install

### 1. Pick the mode (A or B above), paste the JSON

Per-project: `<project-dir>/.mcp.json` (or under
`~/.claude.json` → `projects.<project-dir>.mcpServers`).

Global (every project): top-level `mcpServers` in `~/.claude.json`.
Generally a bad idea — chrome-devtools is per-project by nature.

### 2. Confirm Chrome is available

The MCP spawns a Chrome / Chromium binary via Puppeteer's bundled
download (no separate install needed). If you've already got Chrome on
the Mac, it'll be reused.

```bash
# Optional sanity check:
npx -y chrome-devtools-mcp@latest --version
```

### 3. Restart Claude Code, verify

```
/mcp
```

Should list `chrome-devtools` as connected. First invocation will pull
the npm package + (if needed) the Chromium binary — can take 30-60s.
Subsequent starts are fast.

---

## Daily use — three loop patterns

### Loop 1: visual change verification

Task: "make the Nav component sticky on scroll".

Agent runs:

```
1. Edit  src/lib/components/Nav.svelte.
2. ctx_shell: pnpm dev          (or rely on existing dev server)
3. navigate_page("<dev-server-url>")
4. evaluate_script: window.scrollTo(0, 500)
5. take_screenshot               → confirm Nav still pinned
6. list_console_messages         → confirm no Svelte runtime errors
7. If wrong: edit, goto 4.
8. If right: report done.
```

This is the canonical loop. Operator sees a Slack-message-shaped report
("nav is sticky, no console errors") instead of iterating Reload-Screenshot-
Describe.

### Loop 2: network behavior check

Task: "the /api/launches endpoint is being called twice on page load —
fix the duplicate".

Agent runs:

```
1. navigate_page("<dev-server-url>/launches")
2. list_network_requests filter=launches → confirm 2 calls
3. Read the offending component, identify the dup.
4. Edit.
5. navigate_page again (force reload).
6. list_network_requests → confirm 1 call.
```

### Loop 3: console-error triage

Task: "users report a flicker on mobile viewport — figure out why".

Agent runs:

```
1. emulate_cpu_throttling x4
2. emulate_network "Slow 3G"
3. navigate_page("<dev-server-url>")
4. take_screenshot interval=200ms × 10
5. list_console_messages
6. Trace any warnings to the source component.
```

Three loops, all close without operator intervention until the agent
has a finding.

---

## "Definition of done" pattern

In project-local `AGENTS.md`, codify what "done" means for UI work:

```markdown
## UI work — done means

Before marking a UI task complete, the agent must:

1. `navigate_page` to the affected route.
2. `take_screenshot` at desktop AND mobile viewport.
3. `list_console_messages` shows zero errors or warnings.
4. If the task is interactive: `click_element` + `take_screenshot`
   showing the post-interaction state.
5. The PR description includes the screenshots inline.

"It compiles" is not done. "It works visually + no console errors" is done.
```

This is operator-level discipline encoded in the project AGENTS.md so
every session enforces it without re-asking.

---

## Common operations cheat sheet

### Open a page and screenshot

```
navigate_page("<dev-server-url>/foo")
take_screenshot
```

### Click a thing, screenshot the result

```
navigate_page("<dev-server-url>/foo")
click_element selector=".cta-button"
wait_for selector=".success-toast"
take_screenshot
```

### Read errors from a broken page

```
navigate_page("<dev-server-url>/broken-route")
list_console_messages   # errors, warnings, info
```

### Inspect a network call

```
navigate_page("<dev-server-url>/foo")
list_network_requests filter="api/"
get_network_request id=<id>   # full headers + body
```

### Run arbitrary JS in the page

```
evaluate_script "document.querySelectorAll('.card').length"
evaluate_script "window.__APP_STATE__"   # peek at exposed state
```

### Mobile viewport check

```
evaluate_script "matchMedia('(max-width: 768px)').matches"
# Or set viewport explicitly (varies by MCP version — check tools list)
```

---

## Troubleshooting

### `npx -y chrome-devtools-mcp@latest` hangs on first run

Usually downloading the Chromium binary. Let it finish (~30-60s first
time, ~10s thereafter). Run:

```bash
npx -y chrome-devtools-mcp@latest --version 2>&1 | head
```

If still hung past 2 minutes, network may be blocking the Puppeteer
download. Set `PUPPETEER_DOWNLOAD_HOST` if behind a proxy.

### "Connection refused" when navigating to localhost

The dev server isn't running, or it's on a different port. Verify:

```bash
curl -fsS <dev-server-url>/ | head -1
```

If headless+isolated mode, also check: `--isolated` runs in a
profile that may not have `localhost` allowed by the network stack.
Usually a non-issue but flagged here.

### Chrome zombies after a session crash

```bash
pgrep -fl chrome | head
pkill -f 'chrome-devtools-mcp'
```

`--headless` runs hide more readily than visible runs; if you've
accumulated several, the OS may also report low memory.

### Screenshots come back blank

Usually one of:
- The page hasn't loaded yet → add `wait_for "networkidle"` before
  the screenshot.
- The viewport is too small → set a larger viewport or use
  `fullPage: true` on the screenshot call.
- The page renders via WebGL / Canvas and headless Chrome's GPU support
  is degraded → switch to visible mode (B) for diagnosis.

### `evaluate_script` errors with "Execution context destroyed"

Page navigated or reloaded during the call. Wrap the eval in a
`wait_for` of a stable selector first.

### Authenticated pages forget the login (mode A)

Expected — `--isolated` discards the profile each restart. Switch to
mode B (no `--isolated`) for auth-heavy work; the profile persists across
sessions.

---

## Token discipline

The Chrome DevTools MCP can be a token firehose if used naively.
Guidelines:

- **Prefer `take_snapshot` over `take_screenshot`** when you only need to
  know what's on the page, not how it looks. Snapshots are accessibility
  trees — structured text, cheap.
- **Don't screenshot in a loop** — agents sometimes get carried away with
  "screenshot, check, screenshot" cycles. Screenshot once after a
  meaningful change, not after every action.
- **Filter `list_network_requests`** by URL pattern — full request lists
  on a busy SPA are huge.
- **`list_console_messages` is cheap** — read it often, costs little.

This composes well with [`token-management-lean-ctx-rtk.md`](token-management-lean-ctx-rtk.md)
— lean-ctx doesn't touch MCP traffic, so Chrome DevTools is the
domain where the agent's own discipline matters most.

---

## Future improvements (not done)

- **PR check** — wire a GitHub Action that fails if a UI-touching PR
  doesn't include the screenshot evidence in its description.
- **Visual regression** — store a baseline screenshot per route; compare
  on each PR. Tools like `playwright-visual-regression` already exist;
  integrating one as an MCP-driven check would close the loop further.
- **Shared profile across projects** — Mode B persistence is per-MCP-
  invocation right now; a shared profile across multiple projects
  would let one auth session serve several.
- **Trace recording** — Chrome DevTools Protocol supports trace capture
  (`Tracing.start`/`Tracing.end`). Useful for "agent profiles this slow
  page" workflows; not yet exposed by chrome-devtools-mcp at time of
  writing.

---

## References

- chrome-devtools-mcp on npm:
  <https://www.npmjs.com/package/chrome-devtools-mcp>
- Companion recipe (token discipline):
  [`token-management-lean-ctx-rtk.md`](token-management-lean-ctx-rtk.md)
- AGENTS.md pattern for "definition of done" — see global rules
  ([`AGENTS.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/AGENTS.md)
  in this repo), specifically the operating-discipline section.

---

## Quick reference card

```
Install (per-project), mode A — fast/ephemeral:
  ".mcp.json" or per-project mcpServers in ~/.claude.json:
    "chrome-devtools": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--headless", "--isolated"]
    }

Install mode B — visible/persistent:
  Same JSON, drop "--headless" and "--isolated".

Verify:                /mcp                  (in Claude Code)
First-run cost:        ~30-60s (Chromium download)
Per-page baseline:     navigate_page → take_snapshot → list_console_messages
Visual proof:          take_screenshot (after wait_for "networkidle")
Inspect network:       list_network_requests filter="..."
Kill zombies:          pkill -f 'chrome-devtools-mcp'
```
