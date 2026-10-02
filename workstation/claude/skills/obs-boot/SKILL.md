---
name: obs-boot
description: Check or (re)boot the self-hosted homelab observability stack — VictoriaMetrics/Logs/Traces + Grafana + GlitchTip + Langfuse on the Mac mini, Alloy collectors on the mini, the DGX and prod. The check (endpoints, containers, collector loops, per-host metric freshness, alert-rule drift) is read-only and scripted; booting or recreating anything is gated on explicit approval. Use when asked "is observability healthy / is data flowing", when a dashboard or alert looks dark, after a mini or DGX reboot, or when standing the stack up on a new host.
---

# obs-boot

The homelab observability stack, as it actually runs (checked live 2026-10-02).
There is no Grafana Cloud any more; the old DGX + Grafana Cloud recipe
was removed from the docs on 2026-10-02 (historical copy: https://github.com/chipi/agentic-ai-homelab/blob/613e465/docs/recipes/observability-boot.md). Don't follow it.

| Where | What runs |
|---|---|
| Mac mini (`homelab`) | `victoriametrics` :8428, `victorialogs` :9428, `victoriatraces` :10428, `grafana` :3000, GlitchTip :8090, Langfuse, `caddy` (tailnet TLS), `alloy-homelab` (its own host metrics + logs); launchd loops `com.homelab.dgx-scrape` (TCP health of each DGX service, `dgx_service_up`), `mini-metrics`, `forward-watchdog` |
| DGX (`dgx-llm-1`) | `alloy` (all DGX metrics + container logs + kernel journal → the mini), `dcgm-exporter`, `cadvisor` |
| prod (`prod-podcast`) | Alloy collector (`infra/observability/hosts/prod-podcast/`) pushing to the mini |

The backend ports are loopback- or tailnet-only. Query them on the mini, or through the tailnet names (`https://grafana.tail6d0ed4.ts.net`, …).

## 1. Check (read-only, always first)

```bash
~/.claude/skills/obs-boot/scripts/check.sh            # exit 0 = PASS, 1 = FAIL
~/.claude/skills/obs-boot/scripts/check.sh --stale-seconds 300
```

It checks:
- the 5 health endpoints;
- the backend and collector containers on the mini and the DGX;
- the collector loops;
- how many seconds since each host's last metric sample (FAIL over the threshold, default 600 s, or if a host is missing entirely);
- the alert-rule drift check (`drift: 0 rule(s)` = live Grafana matches the repo).

SSH defaults to the mini and `dgx-llm-1`; override with `HOMELAB_SSH` / `DGX_SSH`.

**Reading a FAIL:**
- **Endpoint or container down** → step 2.
- **One host's metrics stale, the others fresh** → that host's collector or the network path. Probe from **another tailnet node**: a broken colima forward on the mini makes everything look down from the mini itself (runbook `docs/recipes/colima-lima-forwarding-recovery.md`).
- **Drift** → reload alert provisioning (`POST /api/admin/provisioning/alerting/reload`) after confirming the repo is the intended state.

## 2. Boot or recreate — SHARED STATE, explicit approval per action

- **The mini backend:** `infra/observability/bootstrap.sh` decrypts the sops secrets, writes each stack's `.env`, and brings the backend + GlitchTip + Langfuse up. Run `--dry-run` first. Full runbook: `docs/recipes/mac-mini-observability.md`.
- **A collector host:** `docker compose up -d` in `infra/observability/` (or its `hosts/<name>/` variant), with `REMOTE_WRITE_URL` / `LOGS_WRITE_URL` pointing at the mini (`infra/observability/README.md`).
- **Never** `docker compose down -v` on the backend: it deletes the stored metrics, logs and traces. Recreating colima or the databases also wipes tokens other services depend on, e.g. the LiteLLM virtual keys and the triage fleet's GlitchTip and Grafana tokens. See the triage fleet runbook's troubleshooting section.

After any boot: run step 1 again, and it must PASS.

## Not covered

- **Dashboards:** this check doesn't look at their content. Open Grafana.
- **Alert delivery:** whether an alert would actually reach you by email; see infra/delivery.
- **Whether a specific app emits telemetry:** use the `o11y-review` skill for one project's logs, errors and traces.
