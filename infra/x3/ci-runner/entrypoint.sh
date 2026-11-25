#!/bin/bash
# Inside the runner container: restore the registration from the state volume, or register once
# with the token register.sh left there; then run. Everything else (the work folder, tools a job
# installs) lives in the container and is gone when it restarts.
set -euo pipefail
# Jobs written for GitHub's runners call sudo, and this image grants it to `runner` only. The
# runner runs as root here (rootless: root is gh-runner on the X3), so root gets the same rule.
echo 'root ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-root && chmod 440 /etc/sudoers.d/90-root
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
exec ./run.sh
