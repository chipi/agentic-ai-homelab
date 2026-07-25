# fleetd — fleet supervisor daemon

The RFC-0004 supervisor: one static Go binary running both fleets' cycles
on the mini. Deliberately dumb — scheduling, kill-switch, budget guard,
metrics, digest transport; all intelligence stays in the fleets' Python
cores. Tech rationale + framework audit: ADR-0008.

**Config is JSON** (`fleetd.json`, see the example) — deviation from
RFC-0004's TOML sketch: TOML needs a third-party dep and this module is
deliberately stdlib-only.

## Build / test / deploy

```sh
cd fleetd
go vet ./... && go build -o fleetd .
./fleetd -config fleetd.json -once     # one cycle per enabled fleet (smoke)
# deploy to the mini (arm64 mac -> same arch, plain build works; explicit:)
GOOS=darwin GOARCH=arm64 go build -o fleetd . && scp fleetd homelab:~/fleetd/
```

Run under launchd on the mini (plist lands with the Track A shadow
deployment; until then: `nohup ~/fleetd/fleetd -config ~/fleetd/fleetd.json &`).

## Controls

- **Kill switch:** `touch <stop_flag>` (per fleet) — next cycle is skipped;
  remove to resume. Hard stop: `launchctl unload` / SIGTERM (drains the
  in-flight cycle).
- **Budget:** per-fleet `budget_day_usd`; the cycle reports its spend into
  `spend_file` (one number, USD), fleetd accumulates per local day and
  pauses the fleet at the cap. Layer 2 of 3 (per-item caps in the cores,
  OpenRouter key limit as backstop).
- **Stage:** `shadow | propose | live`, passed to cycles as `FLEETD_STAGE`.
  Promotion = config edit + restart. Per-class autonomy lives in the cores.

## Cycle contract (what a fleet's `cycle_cmd` must honor)

- Idempotent per tick (the cores' ledgers own dedup).
- Exit 0 on success; nonzero/timeout is logged with output tail and counted
  in `fleetd_cycle{outcome}`.
- Respect `FLEETD_STAGE`; in `shadow` take NO actions.
- Optionally write cycle spend (USD, plain number) to `spend_file`.
