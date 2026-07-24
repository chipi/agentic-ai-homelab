# signal-fleet — Signal-to-Action Fleet (Fleet 2)

Autonomous **observability triage**: take live production signals (GlitchTip
errors, Grafana alerts, Umami UX, VictoriaMetrics/Logs/Traces) and decide
**Dismiss / File / Escalate** — sibling to the bug-fix fleet (`bugfix-fleet/`,
RFC-0002). It never touches production and never fixes code; its `File` output
chains to Fleet 1 as a labelled GitHub issue. This is RFC-0002's own Phase-3
("o11y-reactive agents"), promoted to its own project.

## Status (2026-07-24)
- **Design:** SIGNALS.md living doc; **RFC-0003** (Proposed). Fleet-1's reviewer
  ran **2 rounds** — all findings folded (intent gate, L1-candidate seam, ledger,
  propose-first Dismiss, GlitchTip reconcile, host, Phase-A seam).
- **Phase 0 (infra consumption): ✅ PROVEN** — every surface consumable with live
  data via its prescribed API (`PHASE-0-infra.md`). Stack confirmed on `homelab`.
- **MVP first vertical slice: ✅ BUILT + verified live** — `mvp/` runs
  poll → correlate → triage (structured + intent gate) → act → ledger. On the
  orrery launch-data-stale signal it dismissed from real refresh-log evidence and
  recommended the alert fix.

## Read in this order
| # | Artifact | What it is |
|---|---|---|
| 1 | [`SIGNALS.md`](SIGNALS.md) | **north-star living design** — architecture, the intent gate (§4.1), dispositions/taxonomy (§7), correlation (§6), sources (§8), state (§9), autonomy (§10), open questions (§12), **the MVP plan (§13)**, discussion log (§14) |
| 2 | [`../docs/rfc/RFC-0003-signal-to-action-fleet.md`](../docs/rfc/RFC-0003-signal-to-action-fleet.md) | crystallized RFC (mirrors RFC-0002) |
| 3 | [`PHASE-0-infra.md`](PHASE-0-infra.md) | per-surface consume recipe + live test evidence |
| 4 | [`mvp/`](mvp/README.md) | the working first-slice code |
| 5 | [`REVIEW-2026-07-24-fleet1-architectural.md`](REVIEW-2026-07-24-fleet1-architectural.md) | Fleet-1 reviewer's rounds 1–2 (already folded) |
| 6 | [`test-receiver/`](test-receiver/receiver.py) | webhook test-ingress stub (Phase-0) |

## What to review / decide
- **Design soundness** — the intent-source gate, L1-candidate seam, dispositions
  compose + filed-work taxonomy, correlation-as-query-join.
- **Phase-0 approach** — prescribed-consumer methods per surface (no DB hacks).
- **The MVP code** (`mvp/`) — the poll→correlate→triage→act spine + the
  deterministic intent gate; reuse of Fleet-1 patterns (SIGNALS §13.4).
- **Open decisions** — SIGNALS §12 (taxonomy names, trigger wiring, harness/model,
  feedback training, intent-source registry) and §13.1 (**target repo** to turn
  `File` from dry-run to live).

## Boundaries (deliberate, not gaps to fix now)
Triage-only forever (remediation = future Fleet 3); MVP `File` is dry-run pending
the target repo; single-shot poll (no daemon); orrery-only (GlitchTip errors =
Phase B); patterns reused but not yet the TS worker seam; Langfuse tracing not
wired.
