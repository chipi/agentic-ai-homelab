# The evaluation harness only, at the commit a project pins (HARNESS_REF: its pyproject.toml's pin,
# else the instance's own). The research data is never in the image: it lives in the instance's volume.
# openssh-client is for the sync step's deploy key.
FROM python:3.12-slim
ARG HARNESS_REF
RUN test -n "$HARNESS_REF" \
 && apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir "evaluation-harness @ git+https://github.com/chipi/eval-harness@${HARNESS_REF}#subdirectory=harness" \
 && evh --version
WORKDIR /project
