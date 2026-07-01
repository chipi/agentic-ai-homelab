---
name: obs-boot
description: Boot or verify the Grafana Alloy observability stack (DGX → Grafana Cloud). Walks the runbook — Grafana Cloud creds → .env → docker compose up → verify in Grafana Explore → import dashboards → pin image tags. Read and verify steps are safe; the compose up is gated on explicit approval. Use when standing up or checking the observability stack.
---

# obs-boot

Drive and verify the observability stack boot. Source runbook:
`docs/recipes/observability-boot.md`. **Verify steps are read-only; the compose
up is shared-state and gated.**

## Steps

1. **Creds (read-only).** Confirm the three Grafana Cloud values are in
   `infra/observability/.env` (`cp .env.example .env` if missing). Never commit
   the real `.env`.
2. **Config check (read-only).** Run `compose-check` on `infra/observability`
   (`docker compose config -q`).
3. **Boot — SHARED-STATE, approval.** From `infra/observability/` in place:
   `docker compose up -d`.
4. **Verify (read-only).** In Grafana Cloud Explore, confirm node / DCGM / vLLM /
   cAdvisor metrics arrive (filter `instance="homelab-1"`); healthchecks green.
5. **Dashboards + pin tags.** Import the four dashboards; after a verified boot,
   pin the `:latest` image tags to the concrete versions.
