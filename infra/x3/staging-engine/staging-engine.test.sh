#!/usr/bin/env bash
# Tests for the X3 staging engine's files (ADR-0013), runnable as a normal user: nothing is installed,
# started or mounted. The daemons validate their own configs; the rest is static.
#   bash infra/x3/staging-engine/staging-engine.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; SETUP="$HERE/../x3-staging-engine-setup.sh"
DEP="$HERE/robotics-staging-deploy"
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }
code() { grep -v '^[[:space:]]*#' "$@"; }

echo "== the daemons accept their configs"
dump=$(containerd --config "$HERE/containerd-staging.toml" config dump 2>&1); crc=$?
chk "containerd parses containerd-staging.toml" "[ $crc = 0 ]"
chk "containerd: root, state, sockets and opt all under the staging paths" \
  "grep -qx \"root = '/var/lib/docker-staging/containerd'\" <<<\"\$dump\" && grep -qx \"state = '/run/containerd-staging'\" <<<\"\$dump\" && grep -q \"address = '/run/containerd-staging/containerd.sock'\" <<<\"\$dump\""
chk "containerd: no path of the system containerd survives the merge" \
  "! grep -qE \"/run/containerd[^-]|/var/lib/containerd|/opt/containerd\" <<<\"\$dump\""
chk "containerd: CRI disabled" "grep -q \"io.containerd.grpc.v1.cri'\" <<<\"\$(grep disabled_plugins <<<\"\$dump\")\""
chk "dockerd --validate accepts daemon.json" "dockerd --validate --config-file '$HERE/daemon.json' >/dev/null 2>&1"
chk "daemon.json: own socket, group robotics, own roots, staging containerd" \
  "jq -e '.hosts == [\"unix:///run/docker-staging.sock\"] and .group == \"robotics\" and .[\"data-root\"] == \"/var/lib/docker-staging/docker\" and .[\"exec-root\"] == \"/run/docker-staging\" and .containerd == \"/run/containerd-staging/containerd.sock\"' '$HERE/daemon.json' >/dev/null"
chk "daemon.json: no bridge, no iptables, no forwarding change, no bip/dns of the system engine" \
  "jq -e '.bridge == \"none\" and .iptables == false and .ip6tables == false and .[\"ip-forward\"] == false and (has(\"bip\") or has(\"dns\") | not)' '$HERE/daemon.json' >/dev/null"
chk "systemd-analyze verify: both units" \
  "systemd-analyze verify '$HERE/containerd-staging.service' '$HERE/docker-staging.service' >/dev/null 2>&1"
chk "units: own config files, mounts required, docker-staging requires containerd-staging" \
  "grep -qx 'ExecStart=/usr/bin/containerd --config /etc/containerd-staging/config.toml' '$HERE/containerd-staging.service' && grep -qx 'RequiresMountsFor=/var/lib/docker-staging' '$HERE/containerd-staging.service' && grep -qx 'ExecStart=/usr/bin/dockerd --config-file /etc/docker-staging/daemon.json' '$HERE/docker-staging.service' && grep -qx 'RequiresMountsFor=/var/lib/docker-staging /srv/robotics-lab' '$HERE/docker-staging.service' && grep -qx 'Requires=containerd-staging.service' '$HERE/docker-staging.service'"
chk "units: no flag on ExecStart that daemon.json also sets (dockerd refuses the pair)" \
  "! grep '^ExecStart=' '$HERE/docker-staging.service' | grep -qE -- '--(host|data-root|exec-root|group|containerd|bridge|iptables)'"

echo "== sudoers: valid, the operator only, the script's five verbs only"
chk "visudo -cf parses it" "visudo -cf '$HERE/robotics-staging.sudoers' >/dev/null 2>&1"
rule=$(code "$HERE/robotics-staging.sudoers" | grep -v -e '^$' -e '^Defaults')
chk "one rule, for marko, as root, NOPASSWD" "[ \$(wc -l <<<\"\$rule\") = 1 ] && grep -q '^marko ALL=(root) NOPASSWD: ' <<<\"\$rule\""
chk "Defaults for the script: env_reset, !setenv; nothing else" \
  "[ \"\$(code '$HERE/robotics-staging.sudoers' | grep '^Defaults')\" = 'Defaults!/usr/local/libexec/robotics-staging-deploy env_reset, !setenv' ]"
chk "commands: only the deploy script with up, up *, rollback, smoke, status, stop" \
  "[ \"\$(sed 's/.*NOPASSWD: //' <<<\"\$rule\" | tr ',' '\n' | sed 's/^ *//' | sort | tr '\n' '|')\" = '/usr/local/libexec/robotics-staging-deploy rollback|/usr/local/libexec/robotics-staging-deploy smoke|/usr/local/libexec/robotics-staging-deploy status|/usr/local/libexec/robotics-staging-deploy stop|/usr/local/libexec/robotics-staging-deploy up|/usr/local/libexec/robotics-staging-deploy up *|' ]"
chk "no SETENV, no ALL command, no wildcard path" "! grep -qE 'SETENV|NOPASSWD: *ALL|libexec/\\*' <<<\"\$rule\""

echo "== robotics-staging-deploy: arguments are checked before anything else"
d() { local -a v; read -ra v <<<"$1"; bash "$DEP" "${v[@]}" >/dev/null 2>&1; echo $?; }
for a in "" "deploy" "up main" "up 4e13c2e" "up $(printf 'A%.0s' {1..40})" "up $(printf 'a%.0s' {1..40}) x" \
         "rollback x" "smoke --browser" "status -v" "stop now" "up ;id" "up \$(id)" "record $(printf 'a%.0s' {1..40})"; do
  chk "refused with usage (exit 2): '$a'" "[ \"\$(d \"\$a\")\" = 2 ]"
done
for a in "up" "up $(printf 'a%.0s' {1..40})" "rollback" "smoke" "status" "stop"; do
  chk "accepted, then refuses as non-root (exit 1): '$a'" "[ \"\$(d \"\$a\")\" = 1 ]"
done
chk "runs deploy.py as the service user from the root checkout, environment cleared" \
  "code '$DEP' | grep -q 'runuser -u \"\$SVC\" -- env -i' && code '$DEP' | grep -q 'python3 \"\$CO/scripts/deploy.py\"'"
chk "the checkout is fetched from GitHub over https, not taken from ~/deploy or /work" \
  "grep -qx 'REPO_URL=https://github.com/chipi/robotics-lab' '$DEP' && ! code '$DEP' | grep -qE '~/deploy|/home/marko|/work/'"
chk "a commit outside GitHub's main is refused" "code '$DEP' | grep -q 'merge-base --is-ancestor \"\$sha\" \"\$main\"'"
chk "starts again with an empty environment, before anything else" \
  "grep -n 'exec env -i _RSD_CLEAN=1' '$DEP' | grep -q . && [ \$(grep -n 'exec env -i _RSD_CLEAN=1' '$DEP' | cut -d: -f1) -lt \$(grep -n '^verb=' '$DEP' | cut -d: -f1) ]"
chk "only up fetches (a rollback works without GitHub); status takes no lock" \
  "[ \$(code '$DEP' | grep -c 'fetch --quiet origin main') = 1 ] && code '$DEP' | grep -q 'elif \[ \"\$verb\" = up \]; then' && code '$DEP' | grep -q 'if \[ \"\$verb\" != status \]; then'"
chk "deploy.py runs in a session of its own (setsid), not on the caller's terminal" "code '$DEP' | grep -q 'exec setsid -w runuser'"
chk "one deploy at a time; each call logged with the sudo user" \
  "code '$DEP' | grep -q 'flock -n 9' && code '$DEP' | grep -q 'logger -t robotics-staging-deploy'"

echo "== setup script: never touches the system engine"
chk "bash -n: setup and deploy scripts" "bash -n '$SETUP' && bash -n '$DEP'"
chk "no start/stop/restart/edit of docker.service, containerd.service, docker.socket or /etc/docker/" \
  "! code '$SETUP' | grep -qE '(docker|containerd)\\.(service|socket)[^-]|/etc/docker/|systemctl [a-z-]+ (docker|containerd)( |$)'"
chk "writes nothing under /var/lib/docker or /var/lib/containerd (the one read is docker info)" "! code '$SETUP' | grep -v 'info --format' | grep -qE '/var/lib/(docker|containerd)([^-]|$)'"
chk "never edits /etc/fstab (prints the lines; the operator adds them)" "! code '$SETUP' | grep -qE '>>?[[:space:]]*/etc/fstab|sed -i.*fstab|tee.*fstab'"
chk "no prune, no rm -rf, no compose down" "! code '$SETUP' '$DEP' | grep -qE 'prune|rm -rf|compose.*down'"
chk "the fstab lines come from wb-storage fstab --staging" "code '$SETUP' | grep -q '\"\$WB\" fstab --staging'"
chk "setup's checks run without pipefail (a 'cmd | grep -q' check must not fail on SIGPIPE)" \
  "grep -q '^ck() { if (set +o pipefail; eval \"\$2\")' '$SETUP' && (set -o pipefail; (echo Server:; sleep 0.2; echo more) | grep -q '^Server:'; [ \$? = 141 ])"
chk "installs exactly what the units and the deploy script name" \
  "! for p in /etc/containerd-staging/config.toml /etc/docker-staging/daemon.json /usr/local/libexec/robotics-staging-deploy /etc/sudoers.d/robotics-staging; do grep -q \"\$p\" '$SETUP' || echo missing; done | grep -q missing"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
