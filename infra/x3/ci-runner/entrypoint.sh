#!/bin/bash
# Inside the runner container: restore the registration from the state volume, or register once
# with the token register.sh left there; then run. Tools a job installs live in the container and
# are gone when it restarts; the work folder is a host folder, emptied at each start (below).
set -euo pipefail
# Ubuntu's container images delete every downloaded .deb after an install; GitHub's runner VMs do
# not, and jobs that cache their apt downloads (podcast_scraper's install-ffmpeg) count on them.
rm -f /etc/apt/apt.conf.d/docker-clean
# A job killed mid-run (a restart, the runner lost) leaves its service containers on this runner's
# engine, and the next job's Postgres stopped at "Bind for 0.0.0.0:5432 failed: port is already
# allocated" (player, 2026-11-26). The engine is this runner's alone; everything on it but this
# container is a leftover.
docker ps -a --format '{{.ID}} {{.Names}}' | awk '$2 !~ /^ci-runner-/ {print $1}' | xargs -r docker rm -f -v >/dev/null
docker network ls -q --filter type=custom | xargs -r docker network rm >/dev/null 2>&1 || true
# Jobs run as runner (uid 1001, passwordless sudo, in group docker), as on GitHub's VMs: as root, a
# test that makes a folder read-only to provoke a failure saw the write succeed (infra's
# test_install_app_compose, 2026-11-26). Root does only the set-up here.
chgrp docker /var/run/docker.sock && chmod 660 /var/run/docker.sock
AS_RUNNER() { setpriv --reuid=runner --regid=runner --init-groups env HOME=/home/runner USER=runner "$@"; }
cd /home/runner
S=/home/runner/state
for f in .runner .credentials .credentials_rsaparams; do
  if [ -f "$S/$f" ]; then cp "$S/$f" .; fi
done
chown runner:runner /home/runner
if [ ! -f .runner ]; then
  [ -s "$S/token" ] || { echo "not registered: run infra/x3/ci-runner/register.sh"; exit 3; }
  AS_RUNNER ./config.sh --unattended --url "$REPO_URL" --token "$(cat "$S/token")" \
    --name "$RUNNER_NAME" --labels "$RUNNER_LABELS" --work "${RUNNER_WORK:-_work}" --replace --disableupdate
  cp .runner .credentials .credentials_rsaparams "$S/"
  rm -f "$S/token"
fi
# The work folder is a host folder mounted at its own host path: a job's `docker run -v
# <checkout>/file:...` names a path the engine (on the host, outside this container) must find, and
# under the container's /home/runner it found nothing ("mkdir /home/runner: permission denied",
# player's nginx test, 2026-11-26). It outlives the container, so it is emptied here, before the job.
# TMPDIR lives in it too: a job's `mktemp -d` that it then mounts into `docker run` (infra's
# caddy/validate.sh: "open Caddyfile: no such file or directory") must also be a host path.
if [ -n "${RUNNER_WORK:-}" ]; then
  find "$RUNNER_WORK" -mindepth 1 -delete
  chown runner:runner "$RUNNER_WORK"
  sed -i -E 's#"workFolder": *"[^"]*"#"workFolder": "'"$RUNNER_WORK"'"#' .runner
  if [ -n "${TMPDIR:-}" ]; then install -d -m 1777 "$TMPDIR"; fi
fi
# One job per container, as on GitHub's VMs: a job left its API server on its port, or its
# web/.e2e-corpus, and the next job's e2e web server "exited early" (studio main, 2026-11-25). The
# job-completed hook marks the job done; once its worker has exited, the runner stops cleanly and
# systemd starts a fresh container (Restart=always). The registration survives in the state volume.
printf '#!/bin/sh\ntouch /tmp/.job-done\n' > /tmp/job-done.sh && chmod 755 /tmp/job-done.sh
export ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/tmp/job-done.sh
chown runner:runner .runner .credentials .credentials_rsaparams
AS_RUNNER ./run.sh & pid=$!
while kill -0 "$pid" 2>/dev/null; do
  if [ -f /tmp/.job-done ] && ! pgrep -f Runner.Worker >/dev/null; then
    echo "job finished: stopping for a fresh container"
    # Not SIGINT to run.sh: bash ignores SIGINT in a background job, run.sh and the listener inherit
    # that, and the runner went on to take the next job in the same container (common main,
    # 2026-11-26). The listener ends its session on SIGTERM. Then exit whatever happened: this is
    # PID 1, so the container stops and systemd starts a fresh one.
    pkill -TERM -f Runner.Listener
    for _ in $(seq 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    exit 0
  fi
  sleep 2
done
wait "$pid"
