#!/usr/bin/env bash
# host-run: run a script FILE on a homelab host — copy it, run it, stream the output, clean up.
#   run.sh <host> <script.sh|script.py> [args...]
# Hosts: homelab (the mini, operator account), homelab-claude, dgx (dgx-llm-1), prod (deploy@prod-podcast).
# Exit status is the remote script's. Never pass secrets as args: the script loads them on the host.
set -euo pipefail
[ $# -ge 2 ] || { echo "usage: run.sh <homelab|homelab-claude|dgx|prod> <script.sh|script.py> [args...]" >&2; exit 2; }
host=$1; file=$2; shift 2
[ -f "$file" ] || { echo "host-run: no such file: $file" >&2; exit 2; }
case "$host" in
  homelab|mini) SSH=(ssh -i "$HOME/.ssh/homelab_mini" -o IdentitiesOnly=yes markodragoljevic@homelab) ;;
  homelab-claude) SSH=(ssh homelab-claude) ;;
  dgx|dgx-llm-1) SSH=(ssh markodragoljevic@dgx-llm-1) ;;
  prod|prod-podcast) SSH=(ssh deploy@prod-podcast) ;;
  *) echo "host-run: unknown host '$host'" >&2; exit 2 ;;
esac
SSH+=(-o ConnectTimeout=15 -o BatchMode=yes)
case "$file" in
  *.py) interp=python3 ;;
  *) interp=bash ;;
esac
remote=$("${SSH[@]}" 'mktemp /tmp/host-run.XXXXXX') || { echo "host-run: cannot reach $host" >&2; exit 3; }
trap '"${SSH[@]}" "rm -f $remote" >/dev/null 2>&1 || true' EXIT
"${SSH[@]}" "cat > $remote && chmod 700 $remote" < "$file"
# PATH: non-interactive shells on the mini lack /usr/local/bin (docker lives there).
args=""; for a in "$@"; do args+=" $(printf '%q' "$a")"; done
set +e
"${SSH[@]}" "PATH=/usr/local/bin:/opt/homebrew/bin:\$PATH $interp $remote$args"
rc=$?
set -e
exit $rc
