# The evaluation harness only, at the commit chipi/fleet-eval-data pins (HARNESS_REF, read from its
# pyproject.toml by update.sh). The research data is never in the image: the checkout is mounted.
FROM python:3.12-slim
ARG HARNESS_REF
RUN test -n "$HARNESS_REF" \
 && apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir "evaluation-harness @ git+https://github.com/chipi/eval-harness@${HARNESS_REF}#subdirectory=harness" \
 && evh --version
WORKDIR /project
