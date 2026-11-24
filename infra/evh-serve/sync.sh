#!/bin/sh
# Brings the instance's checkout (the repo volume) to origin/$BRANCH, then prints what update.sh
# decides on: the commit, the harness pin in pyproject.toml (empty when it has none) and the commit
# the served catalog was built from.
set -eu
cp /run/deploy_key /tmp/deploy_key && chmod 600 /tmp/deploy_key
export GIT_SSH_COMMAND="ssh -i /tmp/deploy_key -o IdentitiesOnly=yes -o UserKnownHostsFile=/run/known_hosts -o StrictHostKeyChecking=yes"
git config --global --add safe.directory /project
cd /project
# .build is a mount point, so the folder is never empty: init + fetch, not clone.
[ -d .git ] || { git init -q && git remote add origin "$REPO_URL"; }
git fetch -q origin "$BRANCH"
git reset -q --hard "origin/$BRANCH"
echo "SHA=$(git rev-parse HEAD)"
echo "PIN=$(sed -nE 's/.*eval-harness@([0-9a-f]{40}).*/\1/p' pyproject.toml 2>/dev/null | head -1)"
echo "DEPLOYED=$(cat .build/catalog/.deployed 2>/dev/null || true)"
