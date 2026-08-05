# Delivery worker image — slim, no ML. Email via Resend HTTP API + self-hosted Web Push.
# Build context is this dir: docker build -f Dockerfile .
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY pyproject.toml README.md tenants.yaml ./
COPY delivery/ ./delivery/

# [obs] wires GlitchTip (sentry_sdk) + OTEL traces; the worker no-ops without their env.
RUN pip install --upgrade pip && pip install ".[obs]"

RUN useradd -u 10001 -m delivery && mkdir -p /var/lib/delivery && chown -R delivery /var/lib/delivery
USER delivery

ENTRYPOINT ["delivery-worker"]
CMD ["--channel", "email"]
