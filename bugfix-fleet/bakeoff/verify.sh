#!/bin/bash
export NODE_OPTIONS="--max-old-space-size=4096"
ROOT=~/.bugfix-fleet/bakeoff; SRC=$ROOT/orrery-src; WT=$ROOT/orrery
AUTH=/Users/markodragoljevic/Projects/agentic-ai-homelab/bugfix-fleet/bakeoff/oracles/orrery/image-bytes.test.ts
run_oracle(){ ( cd "$WT" && npx vitest run "$1" --reporter=json --outputFile=/tmp/vres.json >/dev/null 2>&1 ); }
cnt(){ jq -r "[.testResults[].assertionResults[]|select(.status==\"$1\")]|length" /tmp/vres.json 2>/dev/null || echo ERR; }
verify(){
  local sha=$1 oracle=$2 code=$3 name=$4 authored=$5
  echo "═══ $name ($sha) base=${sha}^ ═══"
  git -C "$WT" reset --hard "${sha}^" -q 2>/dev/null; git -C "$WT" clean -fd -q 2>/dev/null
  ( cd "$WT" && npm run i18n:compile >/dev/null 2>&1 )
  if [ -n "$authored" ]; then mkdir -p "$WT/$(dirname "$oracle")"; cp "$authored" "$WT/$oracle"
  else git -C "$SRC" diff "${sha}^" "$sha" -- "$oracle" | git -C "$WT" apply 2>/dev/null; fi
  run_oracle "$oracle"; local f=$(cnt failed)
  if [ "$f" = "ERR" ]; then
    echo "  deps mismatch → npm install…"; ( cd "$WT" && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install >/dev/null 2>&1; npm run i18n:compile >/dev/null 2>&1 )
    run_oracle "$oracle"; f=$(cnt failed)
  fi
  echo "  RED at base: $f failing  (want >0 = bug reproduces)"
  for cf in $code; do git -C "$WT" checkout "$sha" -- "$cf" 2>/dev/null; done
  run_oracle "$oracle"; local f2=$(cnt failed) p2=$(cnt passed)
  echo "  after golden fix: $f2 failing / $p2 passing  (want 0 failing)"
  if [ "$f" != "ERR" ] && [ "$f" -gt 0 ] 2>/dev/null && [ "$f2" = "0" ]; then echo "  ✅ VERIFIED"; else echo "  ⚠️  CHECK ($name)"; fi
}
verify 0d6644f9 src/lib/orbital/fly-physics.test.ts     "src/lib/orbital/fly-physics.ts"                fly-physics
verify aaaab7f6 src/lib/credits-grouping.test.ts        "src/lib/credits-grouping.ts"                   credits
verify 9ca0f2b3 src/lib/audio-tour.test.ts              "src/lib/components/AudioOverlay.svelte"        audio-tour
verify 19fb2f17 src/lib/mission-arc.test.ts             "src/lib/mission-arc.ts"                        mission-arc
verify a5cf0981 src/lib/astronomy/horizontal.test.ts    "src/lib/satellite/look-angles.ts"             look-angles
verify feb64eaef src/lib/data.test.ts                   "src/lib/data.ts"                               images-data
verify 78a79e8 scripts/lib/image-bytes.test.ts          "scripts/lib/image-bytes.ts scripts/audit-image-mime.ts scripts/fetch-assets.ts scripts/validate-data.ts" image-bytes "$AUTH"
echo "═══ DONE ═══"
