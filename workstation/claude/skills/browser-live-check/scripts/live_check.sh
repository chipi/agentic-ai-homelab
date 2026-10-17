#!/usr/bin/env bash
# Run a function from a project's own TS/JS code in a real headless Chromium; print its JSON.
#
#   live_check.sh <project_dir> <entry.ts|js> <window_fn> [args.json] [--timeout-s N]
#
# <entry> exposes the function on window, e.g.
#     import { AudioSync } from './src/player/audioSync'
#     ;(window as any).runCheck = async (ref: any, url: string) => { ... return {...} }
# Its imports resolve from <project_dir>: the entry is copied there for the bundle (as
# .live-check-entry-<pid>.<ext>) and removed on exit, whatever happens.
#
# Uses only what the project already has: its bundler (node_modules/.bin/rolldown, else esbuild)
# and its Playwright (node_modules/playwright or @playwright/test). Installs nothing.
# Serves the bundle on an ephemeral 127.0.0.1 port; kills only the server it started.
#
# Exit: 0 ok (JSON on stdout), 1 the function threw / page error, 2 setup failed.
set -euo pipefail

usage() { sed -n '2,15p' "$0" >&2; exit 2; }
[ $# -ge 3 ] || usage
PROJECT="$(cd "$1" && pwd)"; ENTRY="$2"; FN="$3"; shift 3
ARGS='[]'; TIMEOUT_S=300
while [ $# -gt 0 ]; do
  case "$1" in
    --timeout-s) TIMEOUT_S="$2"; shift 2 ;;
    *) ARGS="$(cat "$1")"; shift ;;
  esac
done
[ -f "$ENTRY" ] || { echo "live-check: no entry file $ENTRY" >&2; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/live-check.XXXXXX")"
EXT="${ENTRY##*.}"
COPY="$PROJECT/.live-check-entry-$$.$EXT"
SERVER_PID=""
cleanup() {
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
  rm -f "$COPY"
  rm -rf "$WORK"
}
trap cleanup EXIT INT TERM

cp "$ENTRY" "$COPY"
BIN="$PROJECT/node_modules/.bin"
if [ -x "$BIN/rolldown" ]; then
  (cd "$PROJECT" && env -u NODE_OPTIONS "$BIN/rolldown" "./$(basename "$COPY")" --format iife \
     --file "$WORK/bundle.js" >"$WORK/bundle.log" 2>&1) \
    || { echo "live-check: rolldown failed:" >&2; cat "$WORK/bundle.log" >&2; exit 2; }
elif [ -x "$BIN/esbuild" ]; then
  (cd "$PROJECT" && env -u NODE_OPTIONS "$BIN/esbuild" "./$(basename "$COPY")" --bundle \
     --format=iife --outfile="$WORK/bundle.js" >"$WORK/bundle.log" 2>&1) \
    || { echo "live-check: esbuild failed:" >&2; cat "$WORK/bundle.log" >&2; exit 2; }
else
  echo "live-check: no rolldown or esbuild in $BIN — use the project's bundler; do not npx-install one" >&2
  exit 2
fi
rm -f "$COPY"

PW=""
for p in playwright @playwright/test; do
  [ -d "$PROJECT/node_modules/$p" ] && { PW="$PROJECT/node_modules/$p"; break; }
done
[ -n "$PW" ] || { echo "live-check: no playwright in $PROJECT/node_modules" >&2; exit 2; }

printf '<!doctype html><meta charset=utf-8><script src="bundle.js"></script>' >"$WORK/index.html"
# Port 0 = the OS picks a free one; read it back from the server's own banner.
(cd "$WORK" && exec python3 -u -m http.server 0 --bind 127.0.0.1 >"$WORK/server.log" 2>&1) &
SERVER_PID=$!
PORT=""
for _ in $(seq 1 50); do
  PORT="$(sed -n 's/.*port \([0-9][0-9]*\).*/\1/p' "$WORK/server.log" | head -1)"
  [ -n "$PORT" ] && break
  sleep 0.1
done
[ -n "$PORT" ] || { echo "live-check: static server did not start" >&2; cat "$WORK/server.log" >&2; exit 2; }

printf '%s' "$ARGS" >"$WORK/args.json"
cat >"$WORK/run.cjs" <<'EOF'
const [pw, url, fn, argsFile, timeoutS] = process.argv.slice(2);
const { chromium } = require(pw);
const args = JSON.parse(require('fs').readFileSync(argsFile, 'utf8'));
(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    page.on('console', (m) => { if (m.type() === 'error') console.error('console error:', m.text().slice(0, 300)); });
    page.on('pageerror', (e) => console.error('page error:', String(e).slice(0, 300)));
    page.setDefaultTimeout(Number(timeoutS) * 1000);
    await page.goto(url);
    const out = await page.evaluate(
      ([f, a]) => { if (typeof window[f] !== 'function') throw new Error(`window.${f} is not a function`); return window[f](...a); },
      [fn, args],
    );
    process.stdout.write(JSON.stringify(out) + '\n');
  } finally {
    await browser.close();
  }
})().catch((e) => { console.error('live-check: FAILED', e.message); process.exit(1); });
EOF
env -u NODE_OPTIONS node "$WORK/run.cjs" "$PW" "http://127.0.0.1:$PORT/index.html" "$FN" "$WORK/args.json" "$TIMEOUT_S"
