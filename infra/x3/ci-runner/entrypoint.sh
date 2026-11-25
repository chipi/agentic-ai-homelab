#!/bin/bash
# Inside the runner container: restore the registration from the state volume, or register once
# with the token register.sh left there; then run. Everything else (the work folder, tools a job
# installs) lives in the container and is gone when it restarts.
set -euo pipefail
# Ubuntu's container images delete every downloaded .deb after an install; GitHub's runner VMs do
# not, and jobs that cache their apt downloads (podcast_scraper's install-ffmpeg) count on them.
rm -f /etc/apt/apt.conf.d/docker-clean
cd /home/runner
S=/home/runner/state
for f in .runner .credentials .credentials_rsaparams; do
  if [ -f "$S/$f" ]; then cp "$S/$f" .; fi
done
if [ ! -f .runner ]; then
  [ -s "$S/token" ] || { echo "not registered: run infra/x3/ci-runner/register.sh"; exit 3; }
  ./config.sh --unattended --url "$REPO_URL" --token "$(cat "$S/token")" \
    --name "$RUNNER_NAME" --labels "$RUNNER_LABELS" --work _work --replace --disableupdate
  cp .runner .credentials .credentials_rsaparams "$S/"
  rm -f "$S/token"
fi
# One job per container, as on GitHub's VMs: a job left its API server on its port, or its
# web/.e2e-corpus, and the next job's e2e web server "exited early" (studio main, 2026-11-25). The
# job-completed hook marks the job done; once its worker has exited, the runner stops cleanly and
# systemd starts a fresh container (Restart=always). The registration survives in the state volume.
printf '#!/bin/sh\ntouch /tmp/.job-done\n' > /tmp/job-done.sh && chmod 755 /tmp/job-done.sh
export ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/tmp/job-done.sh
./run.sh & pid=$!
while kill -0 "$pid" 2>/dev/null; do
  if [ -f /tmp/.job-done ] && ! pgrep -f Runner.Worker >/dev/null; then
    echo "job finished: stopping for a fresh container"
    kill -INT "$pid"; wait "$pid"; exit 0
  fi
  sleep 2
done
wait "$pid"
