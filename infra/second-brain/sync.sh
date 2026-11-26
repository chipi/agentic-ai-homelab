#!/bin/sh
# Brings the content checkout (the content volume) to origin/$BRANCH and prints its commit.
set -eu
# The deploy key arrives on stdin: the engine runs as another user and cannot read the owner-only key folder.
(umask 077; cat > /tmp/deploy_key)
# The checkout must stay readable by sb's uid (10001) in the batch steps.
umask 022
export GIT_SSH_COMMAND="ssh -i /tmp/deploy_key -o IdentitiesOnly=yes -o UserKnownHostsFile=/run/known_hosts -o StrictHostKeyChecking=yes"
git config --global --add safe.directory /content
cd /content
[ -d .git ] || { git init -q && git remote add origin "$REPO_URL"; }
git fetch -q origin "$BRANCH"
git reset -q --hard "origin/$BRANCH"
echo "SHA=$(git rev-parse HEAD)"
