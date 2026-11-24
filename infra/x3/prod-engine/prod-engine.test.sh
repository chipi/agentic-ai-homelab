#!/usr/bin/env bash
# Tests for the X3 prod engine's files (ADR-0013), runnable as a normal user: nothing is installed,
# started or mounted. The daemons validate their own configs; the rest is static.
#   bash infra/x3/prod-engine/prod-engine.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; SETUP="$HERE/../x3-prod-engine-setup.sh"
DEP="$HERE/robotics-prod-deploy"
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }
code() { grep -v '^[[:space:]]*#' "$@"; }

echo "== the daemons accept their configs"
dump=$(containerd --config "$HERE/containerd-prod.toml" config dump 2>&1); crc=$?
chk "containerd parses containerd-prod.toml" "[ $crc = 0 ]"
chk "containerd: root, state, sockets and opt all under the prod paths" \
  "grep -qx \"root = '/var/lib/docker-prod/containerd'\" <<<\"\$dump\" && grep -qx \"state = '/run/containerd-prod'\" <<<\"\$dump\" && grep -q \"address = '/run/containerd-prod/containerd.sock'\" <<<\"\$dump\""
chk "containerd: no path of the system containerd survives the merge" \
  "! grep -qE \"/run/containerd[^-]|/var/lib/containerd|/opt/containerd\" <<<\"\$dump\""
chk "containerd: CRI disabled" "grep -q \"io.containerd.grpc.v1.cri'\" <<<\"\$(grep disabled_plugins <<<\"\$dump\")\""
chk "dockerd --validate accepts daemon.json" "dockerd --validate --config-file '$HERE/daemon.json' >/dev/null 2>&1"
chk "daemon.json: own socket, group robotics, own roots, prod containerd" \
  "jq -e '.hosts == [\"unix:///run/docker-prod.sock\"] and .group == \"robotics\" and .[\"data-root\"] == \"/var/lib/docker-prod/docker\" and .[\"exec-root\"] == \"/run/docker-prod\" and .containerd == \"/run/containerd-prod/containerd.sock\"' '$HERE/daemon.json' >/dev/null"
chk "daemon.json: no bridge, no iptables, no forwarding change, no bip/dns of the system engine" \
  "jq -e '.bridge == \"none\" and .iptables == false and .ip6tables == false and .[\"ip-forward\"] == false and (has(\"bip\") or has(\"dns\") | not)' '$HERE/daemon.json' >/dev/null"
chk "systemd-analyze verify: both units" \
  "systemd-analyze verify '$HERE/containerd-prod.service' '$HERE/docker-prod.service' >/dev/null 2>&1"
chk "units: own config files, mounts required, docker-prod requires containerd-prod" \
  "grep -qx 'ExecStart=/usr/bin/containerd --config /etc/containerd-prod/config.toml' '$HERE/containerd-prod.service' && grep -qx 'RequiresMountsFor=/var/lib/docker-prod' '$HERE/containerd-prod.service' && grep -qx 'ExecStart=/usr/bin/dockerd --config-file /etc/docker-prod/daemon.json' '$HERE/docker-prod.service' && grep -qx 'RequiresMountsFor=/var/lib/docker-prod /srv/robotics-lab' '$HERE/docker-prod.service' && grep -qx 'Requires=containerd-prod.service' '$HERE/docker-prod.service'"
chk "units: no flag on ExecStart that daemon.json also sets (dockerd refuses the pair)" \
  "! grep '^ExecStart=' '$HERE/docker-prod.service' | grep -qE -- '--(host|data-root|exec-root|group|containerd|bridge|iptables)'"

echo "== sudoers: valid, the operator only, the script's four verbs only"
chk "visudo -cf parses it" "visudo -cf '$HERE/robotics-prod.sudoers' >/dev/null 2>&1"
rule=$(code "$HERE/robotics-prod.sudoers" | grep -v '^$')
chk "one rule, for marko, as root, NOPASSWD" "[ \$(wc -l <<<\"\$rule\") = 1 ] && grep -q '^marko ALL=(root) NOPASSWD: ' <<<\"\$rule\""
chk "commands: only the deploy script with up, up *, rollback, smoke, status" \
  "[ \"\$(sed 's/.*NOPASSWD: //' <<<\"\$rule\" | tr ',' '\n' | sed 's/^ *//' | sort | tr '\n' '|')\" = '/usr/local/libexec/robotics-prod-deploy rollback|/usr/local/libexec/robotics-prod-deploy smoke|/usr/local/libexec/robotics-prod-deploy status|/usr/local/libexec/robotics-prod-deploy up|/usr/local/libexec/robotics-prod-deploy up *|' ]"
chk "no SETENV, no ALL command, no wildcard path" "! grep -qE 'SETENV|NOPASSWD: *ALL|libexec/\\*' <<<\"\$rule\""

echo "== robotics-prod-deploy: arguments are checked before anything else"
d() { local -a v; read -ra v <<<"$1"; bash "$DEP" "${v[@]}" >/dev/null 2>&1; echo $?; }
for a in "" "deploy" "up main" "up 4e13c2e" "up $(printf 'A%.0s' {1..40})" "up $(printf 'a%.0s' {1..40}) x" \
         "rollback x" "smoke --browser" "status -v" "up ;id" "up \$(id)" "record $(printf 'a%.0s' {1..40})"; do
  chk "refused with usage (exit 2): '$a'" "[ \"\$(d \"\$a\")\" = 2 ]"
done
for a in "up" "up $(printf 'a%.0s' {1..40})" "rollback" "smoke" "status"; do
  chk "accepted, then refuses as non-root (exit 1): '$a'" "[ \"\$(d \"\$a\")\" = 1 ]"
done
chk "runs deploy.py as the service user from the root checkout, environment cleared" \
  "code '$DEP' | grep -q 'exec runuser -u \"\$SVC\" -- env -i' && code '$DEP' | grep -q 'python3 \"\$CO/scripts/deploy.py\"'"
chk "the checkout is fetched from GitHub over https, not taken from ~/deploy or /work" \
  "grep -qx 'REPO_URL=https://github.com/chipi/robotics-lab' '$DEP' && ! code '$DEP' | grep -qE '~/deploy|/home/marko|/work/'"
chk "a commit outside GitHub's main is refused" "code '$DEP' | grep -q 'merge-base --is-ancestor \"\$sha\" \"\$main\"'"
chk "one deploy at a time; each call logged with the sudo user" \
  "code '$DEP' | grep -q 'flock -n 9' && code '$DEP' | grep -q 'logger -t robotics-prod-deploy'"

echo "== setup script: never touches the system engine"
chk "bash -n: setup and deploy scripts" "bash -n '$SETUP' && bash -n '$DEP'"
chk "no start/stop/restart/edit of docker.service, containerd.service, docker.socket or /etc/docker/" \
  "! code '$SETUP' | grep -qE '(docker|containerd)\\.(service|socket)[^-]|/etc/docker/|systemctl [a-z-]+ (docker|containerd)( |$)'"
chk "writes nothing under /var/lib/docker or /var/lib/containerd (the one read is docker info)" "! code '$SETUP' | grep -v 'info --format' | grep -qE '/var/lib/(docker|containerd)([^-]|$)'"
chk "never edits /etc/fstab (prints the lines; the operator adds them)" "! code '$SETUP' | grep -qE '>>?[[:space:]]*/etc/fstab|sed -i.*fstab|tee.*fstab'"
chk "no prune, no rm -rf, no compose down" "! code '$SETUP' '$DEP' | grep -qE 'prune|rm -rf|compose.*down'"
chk "the fstab lines come from wb-storage fstab --prod" "code '$SETUP' | grep -q '\"\$WB\" fstab --prod'"
chk "installs exactly what the units and the deploy script name" \
  "! for p in /etc/containerd-prod/config.toml /etc/docker-prod/daemon.json /usr/local/libexec/robotics-prod-deploy /etc/sudoers.d/robotics-prod; do grep -q \"\$p\" '$SETUP' || echo missing; done | grep -q missing"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
