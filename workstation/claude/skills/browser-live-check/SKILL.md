---
name: browser-live-check
description: Run a function from the project's own TS/JS code inside a real headless Chromium (real decoder, real fetch, real CORS) and get its result as JSON — bundled with the project's bundler, served on an ephemeral port, torn down afterwards. Use when a unit test's fakes cannot answer the question, when asked to "check it in a real browser", "run this against the live host", or "measure it for real", or before claiming browser behaviour you have only reasoned about.
---

# browser-live-check

Unit tests fake the browser: a `decodeAudioData` stub, a fetch mock, no CORS. Some answers only
exist in a real browser against a real host: which headers a cross-origin page can read, what a
real MP3 decodes to, how many bytes a sync actually downloads. This skill is the committed
harness for those checks. It was rebuilt from a transcript twice before it was committed
(podcast_scraper RFC-129, 2026-10-16).

## Run

```bash
~/.claude/skills/browser-live-check/scripts/live_check.sh \
  <project_dir> <entry.ts> <window_fn> [args.json] [--timeout-s 300]
```

- **`<entry.ts>`** puts one async function on `window` and imports the code under test with
  paths relative to `<project_dir>`:

  ```ts
  import { AudioSync, browserStreamAccess } from './src/player/audioSync'
  ;(window as any).runCheck = async (ref: unknown, url: string) => {
    let bytes = 0
    // ...wrap the real thing, count what you need to measure...
    return { bytes }
  }
  ```

- **`args.json`** is a JSON array, spread into the call.
- **stdout** is one line: the function's return value as JSON. Console and page errors go to
  stderr.
- **Exit codes:** 0 ok; 1 the function threw (or the page errored); 2 setup failed (no bundler,
  no Playwright, bundle error).

## What it does, and the traps it already handles

| Step | Detail |
| --- | --- |
| Bundle | The project's own `node_modules/.bin/rolldown`, else `esbuild`, as an IIFE. Never `npx` to install one: a missing bundler is a setup failure to report. Runs with `NODE_OPTIONS` unset, which some repos set for other tools. |
| Imports | The entry is copied into `<project_dir>` as `.live-check-entry-<pid>.ts` (an entry outside the project could not resolve the project's modules). Removed on exit, always. |
| Serve | `python3 -m http.server 0` on 127.0.0.1. The OS picks the port, so parallel runs and other worktrees never collide. |
| Browser | The project's own Playwright (`playwright` or `@playwright/test`), headless Chromium. |
| Teardown | A `trap` kills only the server PID this run started, and deletes the temp dir and entry copy. |

## Measuring against a live host

- **Count at the boundary you care about.** Wrap the access layer (range requests, fetch) in the
  entry and return the counts; `{ bytes, requests, ms }` is the pattern.
- **Compare with ground truth from a different method.** Example: the sync's map against a
  full offline alignment of the same file, or each checkpoint located directly in the
  downloaded audio. A browser number agreeing with itself proves nothing.
- **Hosts change.** A first URL can serve different content per request; resolve and pin the
  final URL (`fetch(url, {headers: {Range: 'bytes=0-0'}}).then(r => r.url)`) when both sides
  must hear the same version.
- **Real-world data stays in the scratchpad.** It is never committed; delete it when done.

## Not covered

- **Not a phone.** iOS WKWebView and Android WebView differ from desktop Chromium (codecs,
  `Response.url` through native HTTP, background behaviour). Device claims need a device or
  simulator.
- **Not an e2e suite.** Use it for one measured question, not regression coverage; a recurring
  check belongs in the project's Playwright specs.
