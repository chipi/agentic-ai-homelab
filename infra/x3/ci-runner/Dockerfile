# GitHub's runner image plus the tools GitHub's ubuntu-24.04 VMs have and it lacks, so jobs written
# for those VMs run unchanged. The list is what was measured missing (2026-11-26): common's `make
# check` stopped at "make: command not found". Each runner's engine builds this on its first start
# (ci-runner@.service); change the tag in IMAGE there whenever this file changes.
FROM ghcr.io/actions/actions-runner:2.338.2
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential pkg-config wget zip xz-utils zstd file rsync \
 && rm -rf /var/lib/apt/lists/*
# setup-python's prebuilt Pythons find libpython through a RUNPATH fixed at /opt/hostedtoolcache;
# in the runner's default _work/_tool a Python started without LD_LIBRARY_PATH exits 127 (common's
# test_the_image_script_writes_the_record, run 45806431765 attempt 2).
ENV AGENT_TOOLSDIRECTORY=/opt/hostedtoolcache RUNNER_TOOL_CACHE=/opt/hostedtoolcache
RUN install -d -o runner -g runner /opt/hostedtoolcache
USER runner
