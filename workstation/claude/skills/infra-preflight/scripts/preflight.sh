#!/usr/bin/env bash
# infra-preflight: chipi/infra's gates before a commit or push, one PASS/FAIL/NOT RUN line each.
#   preflight.sh [REPO] [--all-sh] [--base REF]
# REPO defaults to the current directory. Stages:
#   quality                 make quality                (= CI job `quality`)
#   boundary-check          make boundary-check         (= CI job `boundary`; needs ./public)
#   citations-check         make citations-check        (needs ./public)
#   obs-umami-views-check   make obs-umami-views-check  (needs ./public)
#   secrets                 the secrets-scan skill on the commits not yet pushed (gitleaks)
#   actionlint              .github/workflows (the active ones) + local actions, on the dev engine
#   shell lint (shellcheck) .sh changed since merge-base(REF, HEAD) (--all-sh: every tracked .sh)
# The docker stages run only on the dev engine (ADR-0009), never the production socket. If it is not
# running they are NOT RUN, which is not a pass. This script does not start it: `devengine start`.
# Exit 0 all PASS, 1 any FAIL, 3 none failed but something was NOT RUN, 2 usage.
set -uo pipefail
repo="."; all_sh=0; base="origin/main"
while [ $# -gt 0 ]; do
  case "$1" in
    --all-sh) all_sh=1 ;;
    --base) base="${2:?--base needs a ref}"; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) repo="$1" ;;
  esac
  shift
done
cd "$repo" 2>/dev/null || { echo "no such repo: $repo" >&2; exit 2; }
repo="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "not a git repo: $repo" >&2; exit 2; }
cd "$repo" || exit 2
[ -f config/prod-settings.env ] && grep -q '^quality:' Makefile 2>/dev/null \
  || { echo "$repo does not look like chipi/infra (no config/prod-settings.env or quality target)" >&2; exit 2; }

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
logs="$(mktemp -d "${TMPDIR:-/tmp}/infra-preflight.XXXXXX")"
names=(); results=()
record() { names+=("$1"); results+=("$2"); echo "done   $1: $2" ; }
stage() {  # stage NAME CMD...  — runs CMD, log to $logs/NAME.log
  local n="$1"; shift
  echo "run    $n  (tail -f $logs/$n.log)"
  if "$@" >"$logs/$n.log" 2>&1; then record "$n" PASS; else record "$n" "FAIL exit $?"; fi
}

echo "repo   $repo at $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
echo "logs   $logs"
if [ -e public/.git ] || [ -d public/src ]; then
  pub_at="$(git -C public rev-parse --short HEAD 2>/dev/null || echo '?')"
  ref="$(grep -E '^PUBLIC_APP_REF=' config/prod-settings.env 2>/dev/null | cut -d= -f2-)"
  echo "public ./public -> $(readlink public || echo public) at $pub_at; CI checks out PUBLIC_APP_REF=${ref:-unset}"
  has_public=1
else
  echo "public ./public missing: the boundary stages are NOT RUN (docs/guides/MOUNTING_THE_PUBLIC_REPO.md)"
  has_public=0
fi

# Every stage, make quality included, sees only the dev engine: the suite has docker-backed tests
# (test_edge_config_validates.py) that would otherwise reach for /var/run/docker.sock.
unset DOCKER_HOST
export DOCKER_CONTEXT=dev
if docker info >/dev/null 2>&1; then dev_up=1; else dev_up=0
  echo "docker dev engine not running: make quality's docker-backed tests fail or skip (devengine start)"
fi

stage quality make quality
for t in boundary-check citations-check obs-umami-views-check; do
  if [ "$has_public" = 1 ]; then stage "$t" make "$t"; else record "$t" "NOT RUN (no ./public)"; fi
done

scan="$here/../../secrets-scan/scripts/scan.sh"
if [ -x "$scan" ] || [ -f "$scan" ]; then
  stage secrets bash "$scan" --push
elif command -v gitleaks >/dev/null 2>&1; then
  stage secrets gitleaks git --redact --no-banner --log-opts="$base..HEAD" .
else
  record secrets "NOT RUN (no secrets-scan script, no gitleaks)"
fi

if [ "$dev_up" = 1 ]; then
  w="$(mktemp -d "$HOME/.cache/infra-preflight.XXXXXX")"
  chmod 755 "$w"   # mktemp makes it 700; the dev engine VM mounts it as another uid
  mkdir -p "$w/.github/workflows"
  # The ACTIVE workflows. This used to lint .github/workflows-staged, which the cutover emptied
  # (2026-10-28): it then failed "no YAML file found" on every run and linted nothing.
  cp .github/workflows/*.yml "$w/.github/workflows/"
  [ -d .github/actions ] && cp -R .github/actions "$w/.github/actions"
  [ -f .github/actionlint.yaml ] && cp .github/actionlint.yaml "$w/.github/"
  git -C "$w" init -q
  stage actionlint docker run --rm -v "$w:/repo" -w /repo rhysd/actionlint:latest -color=false
  if [ "$all_sh" = 1 ]; then
    shs="$(git ls-files '*.sh')"
  else
    mb="$(git merge-base "$base" HEAD 2>/dev/null || echo HEAD)"
    shs="$( { git diff --name-only --diff-filter=d "$mb"; git ls-files --others --exclude-standard; } | grep -E '\.sh$' | sort -u)"
  fi
  if [ -z "$shs" ]; then
    record shellcheck "PASS (no .sh changed since ${mb:-base}; --all-sh for every file)"
  else
    mkdir -p "$w/sh"
    while IFS= read -r f; do [ -f "$f" ] && mkdir -p "$w/sh/$(dirname "$f")" && cp "$f" "$w/sh/$f"; done <<<"$shs"
    echo "$shs" | sed 's/^/       shellcheck: /'
    # shellcheck disable=SC2046
    stage shellcheck docker run --rm -v "$w/sh:/mnt" -w /mnt koalaman/shellcheck:stable -S warning $(echo "$shs")
  fi
  rm -rf "$w"
else
  record actionlint "NOT RUN (dev docker engine not running: devengine start)"
  record shellcheck "NOT RUN (dev docker engine not running: devengine start)"
fi

fail=0; notrun=0
echo; echo "| stage | result |"; echo "| --- | --- |"
for i in "${!names[@]}"; do
  echo "| ${names[$i]} | ${results[$i]} |"
  case "${results[$i]}" in FAIL*) fail=1 ;; NOT\ RUN*) notrun=1 ;; esac
done
for i in "${!names[@]}"; do
  case "${results[$i]}" in FAIL*)
    echo; echo "## ${names[$i]} — last 25 lines of $logs/${names[$i]}.log"; tail -25 "$logs/${names[$i]}.log" ;;
  esac
done
if [ "$fail" = 1 ]; then echo; echo "INFRA PREFLIGHT: FAIL"; exit 1; fi
if [ "$notrun" = 1 ]; then echo; echo "INFRA PREFLIGHT: INCOMPLETE (nothing failed; NOT RUN is not a pass)"; exit 3; fi
echo; echo "INFRA PREFLIGHT: PASS"
