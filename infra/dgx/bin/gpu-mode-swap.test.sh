#!/usr/bin/env bash
# Tests gpu-mode-swap.sh against stub docker/curl/systemctl/nvidia-smi: no GPU, no containers.
# A "container" is a file; it serves its model once it has been up for its load delay.
#   bash infra/dgx/bin/gpu-mode-swap.test.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SWAP="$HERE/gpu-mode-swap.sh"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
FAILS=0
pass() { echo "PASS $*"; }
bad()  { echo "FAIL $*"; FAILS=$((FAILS + 1)); }

export FAKE="$T/fake"
mkdir -p "$FAKE"/{containers,delay,model,ports} "$T/bin" "$T/home"

# stack dir -> container name, port, model
mkstack() {  # <dir name> <container> <port> <model> <load delay s>
    mkdir -p "$T/stacks/$1"
    echo "$2" >"$T/stacks/$1/.svc"
    echo "VLLM_API_KEY=k-$1" >"$T/stacks/$1/.env"
    echo "$2" >"$FAKE/ports/$3"
    echo "$4" >"$FAKE/model/$2"
    echo "$5" >"$FAKE/delay/$2"
}

cat >"$T/bin/docker" <<'EOF'
#!/usr/bin/env bash
C="$FAKE/containers"
case "$1" in
  compose)
    svc="$(cat .svc)"
    echo "compose $2 $svc" >>"$FAKE/calls"
    case "$2" in
      up)   [[ -f "$FAKE/fail-up-$svc" ]] && exit 1
            [[ "$(cut -d' ' -f1 "$C/$svc" 2>/dev/null)" == running ]] || echo "running $(date +%s)" >"$C/$svc" ;;
      down) rm -f "$C/$svc" ;;
    esac ;;
  ps)      for f in "$C"/*; do [[ -f "$f" ]] && [[ "$(cut -d' ' -f1 "$f")" == running ]] && basename "$f"; done; true ;;
  inspect) n="${!#}"; [[ -f "$C/$n" ]] || exit 1; [[ "$2" == -f ]] && cut -d' ' -f1 "$C/$n"; true ;;
  rm)      rm -f "$C/${!#}" ;;
  start|stop) exit 0 ;;
esac
EOF
cat >"$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
url="${!#}"
port="$(sed -E 's#^https?://[^:/]+:([0-9]+).*#\1#' <<<"$url")"
[[ "$url" == *-K* ]] && true
cat >/dev/null 2>&1 </dev/stdin &
name="$(cat "$FAKE/ports/$port" 2>/dev/null)" || exit 7
st="$(cat "$FAKE/containers/$name" 2>/dev/null)" || exit 7
[[ "${st%% *}" == running ]] || exit 7
(( $(date +%s) - ${st##* } >= $(cat "$FAKE/delay/$name") )) || exit 22
case "$url" in
  */health)    exit 0 ;;
  */v1/models) printf '{"data":[{"id":"%s"},{"id":"alias"}]}' "$(cat "$FAKE/model/$name")" ;;
esac
EOF
cat >"$T/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >>"$FAKE/calls"
case "$1" in
  is-active) [[ -f "$FAKE/ollama-active" ]] ;;
  stop)      rm -f "$FAKE/ollama-active" ;;
  start|restart) touch "$FAKE/ollama-active" ;;
esac
EOF
printf '#!/usr/bin/env bash\ncase "$*" in *utilization.gpu*) echo 0;; esac\n' >"$T/bin/nvidia-smi"
chmod +x "$T/bin"/*

mkstack prod-vllm vllm-prod-vllm 8003 Model/Prod 6
mkstack translate vllm-translate 8005 google/translategemma-12b-it 9

export PATH="$T/bin:$PATH" HOME="$T/home"
export GPU_MODE_DOCKER=docker GPU_MODE_SUDO="" GPU_MODE_STATE_DIR="$T/state"
export GPU_MODE_PRODVLLM_DIR="$T/stacks/prod-vllm" GPU_MODE_TRANSLATE_DIR="$T/stacks/translate"
export GPU_MODE_PRODVLLM_MODEL=Model/Prod GPU_MODE_START_TIMEOUT=40
export GPU_MODE_INFRA_ROOT="$T/none" GPU_MODE_CODER_DIR="$T/none/c"

reset() { rm -f "$FAKE"/containers/* "$FAKE/calls" "$FAKE"/fail-up-*; touch "$FAKE/ollama-active"; }
lastline() { tail -1 "$T/state/last.log"; }

# 1. ollama -> prod: both stacks serve, exit 0, OK line; ollama stopped and not restarted
reset
out="$("$SWAP" prod 2>&1)"; rc=$?
[[ $rc == 0 && "$(lastline)" == "MODE=prod OK" ]] && pass "prod from cold: exit 0, MODE=prod OK" || bad "prod from cold: rc=$rc last='$(lastline)'"
[[ ! -f "$FAKE/ollama-active" ]] && ! grep -q 'systemctl restart' "$FAKE/calls" \
    && pass "prod: ollama stopped and not restarted" || bad "prod: ollama left running ($(grep systemctl "$FAKE/calls" | tr '\n' ';'))"
grep -q "log: $T/state/swap-" <<<"$out" && pass "caller is told the log path" || bad "no log path in caller output"

# 2. re-run with prod up and translate down: starts only translate
rm -f "$FAKE/containers/vllm-translate" "$FAKE/calls"
"$SWAP" prod >/dev/null 2>&1; rc=$?
ups="$(grep -c 'compose up' "$FAKE/calls")"
[[ $rc == 0 ]] && grep -q 'compose up vllm-translate' "$FAKE/calls" && ! grep -q 'compose up vllm-prod-vllm\|compose down' "$FAKE/calls" \
    && pass "re-run starts only the missing translate (ups=$ups, no downs)" || bad "re-run: rc=$rc calls: $(tr '\n' ';' <"$FAKE/calls")"

# 3. translate never serves the expected model: non-zero with a FAILED line
reset
GPU_MODE_TRANSLATE_MODEL=not/this-model GPU_MODE_START_TIMEOUT=15 "$SWAP" prod >/dev/null 2>&1; rc=$?
[[ $rc == 1 && "$(lastline)" == "MODE=prod FAILED: translate not serving"* ]] \
    && pass "wrong translate model: exit 1, '$(lastline | cut -c1-60)…'" || bad "wrong model: rc=$rc last='$(lastline)'"

# 4. translate compose fails: non-zero, FAILED, not the old warn-and-exit-0
reset; touch "$FAKE/fail-up-vllm-translate"
"$SWAP" prod >/dev/null 2>&1; rc=$?
[[ $rc == 1 && "$(lastline)" == "MODE=prod FAILED:"* ]] && pass "translate cannot start: exit 1, FAILED" || bad "compose fail: rc=$rc last='$(lastline)'"

# 5. the caller dies mid-swap: the swap still completes and records OK
reset
"$SWAP" prod >/dev/null 2>&1 &
caller=$!
sleep 3; kill -9 "$caller" 2>/dev/null; wait "$caller" 2>/dev/null
for _ in $(seq 1 30); do grep -q '^MODE=' "$T/state/last.log" && break; sleep 1; done
[[ "$(lastline)" == "MODE=prod OK" ]] && [[ -f "$FAKE/containers/vllm-translate" ]] \
    && pass "caller killed at 3 s: swap finished, MODE=prod OK" || bad "caller killed: last='$(lastline)'"

# 6. a second swap while one runs is refused with exit 4
reset
"$SWAP" prod >/dev/null 2>&1 &
first=$!
sleep 2
"$SWAP" prod >/dev/null 2>&1; rc=$?
wait "$first"
[[ $rc == 4 ]] && pass "concurrent swap refused (exit 4)" || bad "concurrent swap: rc=$rc"

# 7. free leaves no vLLM running; --json prints one result object on stdout
json="$("$SWAP" free --json 2>/dev/null)"; rc=$?
[[ $rc == 0 && -z "$(ls "$FAKE/containers")" && "$json" == '{"mode":"free","success":true'* ]] \
    && pass "free: nothing left, json ok" || bad "free: rc=$rc left=$(ls "$FAKE/containers") json=$json"

# 8. status never detaches
"$SWAP" status 2>&1 | grep -q 'running detached' && bad "status detached" || pass "status runs inline"

echo "$(( 8 - FAILS > 0 ? 1 : 0 ))" >/dev/null
(( FAILS == 0 )) && echo "ALL PASS" || { echo "$FAILS FAILED"; exit 1; }
