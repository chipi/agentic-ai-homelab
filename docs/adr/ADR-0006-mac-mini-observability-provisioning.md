# ADR-0006 — Mac mini as the observability host: fresh-start migration + bootstrap/sops provisioning

**Status:** Accepted (pending the physical Mac mini to execute + validate)
**Date:** 2026-07-20
**Relates to:** ADR-0005 (the platform). The DGX has been the *stopgap*
observability host; the Mac mini is the intended permanent home.

## ctx

The self-hosted platform (VictoriaMetrics/Logs/Traces + Grafana + GlitchTip +
Langfuse) runs on the DGX as a stopgap. The DGX is a GPU workhorse — observability
shouldn't permanently ride on it (contends for a production box; "don't monitor
the box you're monitoring on"). A dedicated always-on Mac mini is the target host.
Need: a repeatable, low-toil "empty Mac mini → running platform" path.

## Decision

1. **The Mac mini becomes the permanent observability host.** The DGX keeps only
   its **collector** (Alloy) — that's Linux/GPU-specific (`network_mode: host`,
   `/rootfs`, DCGM) and does NOT move.
2. **Fresh start — no data migration.** Metrics/logs/traces are short-retention +
   append-only; GlitchTip/Langfuse history is young. Not worth the volume surgery.
3. **Provisioning = a `bootstrap` script + a runbook** (`docs/recipes/mac-mini-
   observability.md`). Light config management — no Ansible/Nix for one host.
4. **Secrets via sops + age** — encrypted secrets committed to git, decrypted at
   bootstrap with an age key the operator holds (password manager / on-host).
   Makes "empty → running" reproducible *and* backs the secrets up (vs today's
   hand-generated `.env` living on one host).
5. **Runtime: OrbStack** (lighter/faster than Docker Desktop; clean start-on-login).
6. **Stable endpoint via MagicDNS.** Senders target a tailnet **name**
   (e.g. `obs.<tailnet>.ts.net`), not the DGX IP `100.69.49.126`, so the move is
   "give the mini the obs role + flip one var" instead of chasing every sender.

## Consequences / trade-offs

- One new tool (**sops**) + an **age key** to custody. Worth it for reproducible,
  backed-up secrets.
- **Cutover work:** every sender repoints DGX → mini — the DGX collector
  (`REMOTE_WRITE_URL`/`LOGS_WRITE_URL`), the GlitchTip DSN, the Langfuse host, the
  VictoriaTraces OTLP endpoint. MagicDNS shrinks this to one variable if adopted
  first. Fresh-start means the mini's Grafana/GlitchTip/Langfuse begin empty.
- **Mac-specific unknowns to validate on first boot** (flagged in the runbook):
  publishing container ports to the `utun` tailnet IP (may need `0.0.0.0` + macOS
  firewall instead); OrbStack auto-start + restart-on-reboot; volume perf.
- New deps recorded here (sops, age, OrbStack) per the deps/big-bets rules.

## Non-goals

- Not migrating existing history (fresh start).
- Not moving the DGX collector or adding Mac host metrics in this ADR (separate).
- Not adopting heavy CM (Ansible/Nix) — revisit only if hosts multiply.

## Rollout

Per `docs/recipes/mac-mini-observability.md`: install prereqs → `tailscale up` →
clone → generate/hold age key → `sops` the secrets → `infra/observability/
bootstrap.sh` (decrypts secrets, writes `.env`s with the tailnet IP, `compose up`
all stacks, verifies) → grant ACL ports → repoint senders (or flip MagicDNS).
