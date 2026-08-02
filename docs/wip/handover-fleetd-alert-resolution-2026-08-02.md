# Re: fleetd-cycle-failing — resolved fleet-side; nothing left on your plate

Reply to the 2026-08-02 architectural ask about the `fleetd-cycle-failing`
DatasourceNoData alert. Short version: **the premise was wrong, the fix was
neither of your options, and it's implemented + deployed + verified green.**
This note is the record; no action needed from you beyond reading it.

## Premise correction (verified, not argued)

fleetd HAS a metrics surface — it **pushes** to VictoriaMetrics rather than
exposing a scrape target, which is why you found no `/metrics` port:

- Deployed `~/fleetd/fleetd.json` carries **both** `vm_url: http://localhost:8428`
  and `vl_url` (not vl-only).
- Live series in VM at time of writing:
  `fleetd_cycle{service="fleetd", fleet="triage", outcome="ok", stage="propose", version="b4f02b1"}` —
  `sum by (fleet,outcome)(count_over_time(fleetd_cycle[24h]))` → **144 ok**.
  Also `fleetd_cycle_seconds`, `fleetd_spend_day` (the triage workforce
  dashboard's bottom row has rendered them since 2026-07-25).

**Why it fired anyway:** `outcome=~"error|timeout"` matched series that have
*never existed* — fleetd has never failed a cycle, and pushed metrics only
create series that occur. Sparse-series authoring bug + default NoData
handling. Option A (instrument fleetd) was already done since birth; option B
(LogsQL rewrite) would have moved health off the canonical metrics path for
nothing.

## What was implemented (all deployed 2026-08-02, alerting provisioning reloaded)

1. **`fleetd-cycle-failing` fixed** (`rules.yaml`): `noDataState: OK` (the
   load-bearing line — no error series = healthy), threshold `>1` in 30m so a
   single transient cycle error doesn't page critical, retitled "repeated".
2. **`fleetd-silent` added** — the dead-man the old rule was accidentally
   trying to be: `sum(count_over_time(fleetd_cycle[35m])) < 1` with
   `noDataState: Alerting` (deliberate: total silence IS the alarm; 35m = 3+
   cycle periods). Known-and-intended: a forgotten operator STOP flag
   surfaces here.
3. **The substrate boundary (operator's architectural call, your Q3):** both
   rules carry `meta: "true"`, and the boundary is enforced three times:
   - `policies.yaml`: meta route matched FIRST → default receiver only,
     `continue: false` — critically, **not** to GlitchTip, because GlitchTip
     is a triage-fleet *source* and a critical meta alert would have re-entered
     the fleet through that side door (this leak existed in the routing tree).
   - `signal-fleet/mvp/sources.py` `firing_alerts()`: the fleet's Grafana pass
     skips `meta=true` (deployed to the mini; next 10m cycle picks it up).
   - Operator surface: new "Substrate alerts" alertlist panel on the
     `sf-inbox` (Operator Inbox) dashboard, filtered `{meta="true"}`.
4. **Docs:** invariant #7 added to `docs/fleet-architecture.md` ("the fleet
   never triages its own substrate") including the alert-author contract;
   operator playbook §1 updated.

## Verified end state

Grafana rules API after reload: both rules present, both **inactive** —
`fleetd cycle failing (error/timeout, repeated) → inactive`,
`fleetd silent (no cycles for 35m) → inactive`, labels
`{kind=fleet, meta=true, severity=critical}`. Six days of false firing ended;
the dead-man is armed against live cycle data.

Also for your records (your Q2): fleetd's VictoriaLogs stream is
`{environment="operations", service="fleetd"}` with a `version` field, `_msg`
= raw log line (`[triage] cycle <id>: ok in 0s (…)`). It stays the drill-down
path (linked from both rule annotations), not an alerting path.

## The contract going forward (when you add infra alerts)

- Fleet-consumable alert = truthful symptom: stable `alertname`,
  `service`/`environment` labels, symptom-stating `summary`, a probe hint.
  It will be polled by the triage fleet like any GlitchTip signal.
- Substrate alert (anything about fleetd/VM/VLogs/Grafana themselves) =
  add `meta: "true"` label. That's the whole opt-out; routing, fleet-skip,
  and the operator panel key off it.
- Health rules over PUSHED metrics: if absence-of-series is the healthy
  state, `noDataState: OK` + a paired dead-man rule. Never let
  DatasourceNoData impersonate an incident.
