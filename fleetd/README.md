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
make vet test build                    # every target ends in PASS / FAIL
./fleetd -config fleetd.json -once     # one cycle per enabled fleet (smoke)
make deploy                            # vet + test, amd64 build, swap binary, restart
make rollback | status | stop | start | logs
```

On the mini fleetd runs as the **system LaunchDaemon**
`system/com.homelab.fleetd` (`/Library/LaunchDaemons/com.homelab.fleetd.plist`,
installed by `infra/mini-setup.sh`), so it runs with nobody logged in. Never
install it as a LaunchAgent as well: that would start a second supervisor. The
mini is an **Intel** Mac (x86_64); `make deploy` cross-compiles
`GOOS=darwin GOARCH=amd64`. It keeps the previous binary as `fleetd.prev` for
`make rollback`, and never overwrites the live `fleetd.json`; a difference from
`deploy/fleetd.json` is printed instead.

## Controls

- **Kill switch:** `touch <stop_flag>` (per fleet) — next cycle is skipped;
  remove to resume. Hard stop: `make stop` (STOP flags + `launchctl bootout`).
  On SIGTERM, fleetd sends SIGTERM to each in-flight cycle's process group,
  then SIGKILL after 10 s — under launchd's 20 s exit timeout.
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
- Runs in its own process group. On timeout, the **whole group** (every child
  the cycle started) gets SIGTERM, then SIGKILL 10 s later. A cycle that must
  not be killed mid-write should keep its own deadline under `cycle_timeout`.
- Do not leave background children behind. fleetd stops waiting for a child
  still holding the output 10 s after the cycle exits, and logs it.
- Respect `FLEETD_STAGE`; in `shadow` take NO actions.
- Optionally write cycle spend (USD, plain number) to `spend_file`.
