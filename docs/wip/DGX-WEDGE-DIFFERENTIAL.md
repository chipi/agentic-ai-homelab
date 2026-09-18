# DGX wedge — competing hypotheses and the evidence for each

**Status:** open. 4 wedges (2026-09-15 ×2, 09-16, 09-18). Box down since 2026-09-18 08:27Z.
**Purpose:** stop reasoning from one theory. Every hypothesis below is stated with the evidence
that supports or kills it, and with the specific check that would settle it.

Data sources: VictoriaMetrics (`http://homelab:8428`), VictoriaLogs (`http://homelab:9428`).
Both survive the DGX being dead — everything here was reconstructed after the fact.

---

## The invariant signature (true of every wedge)

Every independent telemetry path stops within ~60 s of the others:

| source | reads | wedge 4 last sample |
|---|---|---|
| logs (docker) | container stdout | 08:27:14Z |
| node_exporter | `/proc` | 08:27:00Z |
| cadvisor | docker socket, 127 series | 08:27:00Z |
| DCGM | GPU driver | 08:28:00Z |
| vLLM | python process | 08:28:00Z |
| alloy self-metrics | collector's own health | 08:28:00Z |

A container crash kills one. A GPU hang kills one. **All of them together means the host stopped
executing.** Confirmed not a network artifact: ping / `:8003` / ssh were dead *from the mini*, not
just from the operator laptop.

Recovery requires physical intervention. This is the shape of a hardware/firmware event, not an
application fault — which is why most software hypotheses below die on evidence.

---

## RULED OUT (with the data that killed them)

### H1 — Memory exhaustion / unified-memory pressure
**Dead.** Host memory flat at **73.2–73.3 GB available** through every final window, including the
last sample before each wedge. 0 OOM kills in dmesg across 10 h. The `#63` header already said
"depth was never the trigger"; this is the one original claim that survives.

### H2 — Peak temperature (thermal trip)
**Dead as a sufficient cause.** The overnight run that SURVIVED was *hotter*:

| | overnight (survived 8 h) | morning (wedged) |
|---|---|---|
| board zone max | **84.6 °C** | 77.8 °C |
| GPU die max | 70.0 °C | 68.0 °C |
| minutes >78 °C | 24 min | 1 min |

It died at 79 °C having already tolerated 84.6 °C for 24 minutes. Documented GB10 danger zone is
94–96 °C — never reached on our telemetry.
*Residual:* the morning curve never plateaued (58→79 °C monotonic at flat 43 W) while overnight
clearly equilibrated (median 70.9 °C). Slope may matter even if peak does not. Unproven.

### H3 — The ollama load/unload cycle (the `#63` theory)
**Dead.** Wedge 2 had `0 models loaded` at the final sample — nothing to cycle. Wedge 4 likewise
`0 models loaded`. And the 8 h overnight run did repeated load/unload cycles (resident ~6–8 min
per hour, four hours running) under real load and survived.

### H4 — "Dies as load releases"
**Dead, and it was a measurement error.** At wedge 4 the GPU was at **96 % util with 2 requests
running** in the final sample. What looked like a release was a single 10 s vLLM log line between
batches. The original `#63` claim likely came from the same kind of instantaneous line.

### H5 — Load intensity or shape
**Dead.** Requests/5 min in the hour before each event, zero idle buckets in all of them:
```
wedge 1    45 39 52 49 41 52 32 46 50 34 44 29  4
wedge 2    23 50 68 28 26 30 30 35 34 29 34 33
wedge 4    77 46 23 76 21 37 29  8
SURVIVED   36 22 45 24 34 37 41 39 39 35 44 19 37
```
Wedge 1 (steady 29–52) died; the survivor (steady 19–45) did not. No distinguishing shape.
CPU load: overnight max **4.37** vs morning max **2.32** — the survivor worked the CPU *harder*.

### H6 — Accumulation / uptime / leak
**Dead.** Uptime at death: wedge 1 = **796.5 h**, wedge 2 = **2.0 h**, wedge 4 = **45.9 h**. A
33-day uptime and a 2-hour uptime cannot share an accumulation cause.

### H7 — NVMe thermal
**Dead.** 55.9–60.9 °C in both the wedge and survivor windows against a declared crit of 84.8 °C,
and near-identical between them.

### H8 — GPU clock/power wedge (PD MCU latch)
**Dead as a precursor.** The documented wedged state is 611 MHz @ 13–16 W. Ours ran at **2528 MHz
median** (healthy band 2200–2600) with `DCGM_FI_DEV_CLOCK_THROTTLE_REASONS = 0`. The GPU was
healthy right up to the last sample.
*Note:* this does not exclude a PD fault *causing* the power-off — see H10. It only says we were
not already latched.

### H9 — Alloy restart (my 07:57Z intervention)
**Weak, near-dead.** 30 min before wedge 4 I restarted the DGX collector. But wedges 1 and 2
(09-15/16) had **no** restart precursor — that config had not been reloaded since 08-31, which is
exactly why the `#` syntax bug survived undetected. A cause must explain all four.

---

## ⚡ DECIDED 2026-09-18 — smart-plug evidence: THE BOX POWERED ITSELF OFF

The DGX is on a metering smart plug. Operator checked it while the box was down:

* **plug relay ON the whole time, never tripped, no protection event in its history**
* **DGX drawing ~nothing** — household baseline back to its normal ~65 W

That single observation closes two hypotheses that telemetry alone could not separate:

* **H12 kernel lockup — DEAD.** A frozen kernel still executes; CPU+GPU would keep pulling
  the ~44 W they were drawing at 08:27 indefinitely. Zero draw means the rails are down,
  not that software hung.
* **External power cut — DEAD.** The plug never switched or tripped, so nothing removed
  the supply from outside.

What remains is a **self-initiated power-off with NO IDENTIFIED TRIGGER** — the machine cut
its own rails. H10 (PD-firmware) and H11 (EC/thermal) are two mechanisms for the same self-off.

⚠ DO NOT WRITE "under load" HERE. The vendor documents this as an "under-load power-off
issue" and it is tempting to repeat that phrase, but OUR data contradicts load as the
trigger — the run that SURVIVED 8 h was higher on every load measure:

| | overnight (survived 8 h) | morning (died in 12 min) |
|---|---|---|
| GPU power peak | **83.2 W** | 51.3 W |
| board temp max | **84.6 °C** | 77.8 °C |
| CPU load max | **4.37** | 2.32 |
| minutes >78 °C | **24** | 1 |

The ONLY load-related claim the data supports is much weaker: all four wedges happened while
the box was SERVING, none while idle (it has sat idle for long stretches, including a 20 min
idle window that same morning, without incident). So activity may be a NECESSARY precondition.
It is demonstrably not sufficient, and its LEVEL predicts nothing.

That pattern — intermittent, requires activity, but uncorrelated with how much — is what a
marginal hardware/firmware fault looks like (a race, or a component near tolerance), not a
threshold being crossed.

**Consequence for evidence gathering:** `journalctl -b -1 -k` is now LIKELY EMPTY OR
TRUNCATED. An abrupt rail drop gives the kernel no chance to flush; that is exactly why a
power-off leaves no trace where a panic would. Still run it — absence of a panic trace is
itself confirmatory — but do not expect a smoking gun there.

## STILL OPEN

### H10 — USB-C PD / power-delivery firmware fault  ← strongest remaining
The GB10 is powered by a 240 W USB-C PD brick with an MCU that has a **documented firmware bug**
causing hard power-off — the vendor calls it an "under-load power-off issue", independent of
PSU wattage adequacy. (Their phrasing, not a claim about our data: see the warning above —
our heavier run survived.)

**For:** matches the invariant signature exactly (instantaneous whole-host stop, physical
intervention required). Intermittent rather than threshold-driven, which fits a firmware race far
better than any of the thresholds we have now ruled out. Explains why four wedges share no
measurable precondition.
**Against:** we have no direct PD telemetry, so this is argued from shape, not evidence.

**TESTABLE PREDICTION:** if the box returns in a **611 MHz / 13–16 W** state with a misleading
~50 °C "cap", that is the canonical PD-MCU latch and effectively confirms H10. A warm reboot will
NOT clear it (the brick's rails stay powered); it needs a cold drain.

### H11 — EC / firmware thermal management
**For:** NVIDIA forums document ACPI zones reaching 96–97 °C with *fans not ramping* after EC/UEFI
updates. Our morning curve never plateaued, which is what insufficient airflow looks like.
**Against:** we never observed >84.6 °C, and the hotter run survived.
**Blocked by:** we have **no fan telemetry at all** — the box publishes no tachometer to
node_exporter; cooling is EC-controlled and invisible to Linux. `node_cooling_device_*` exists but
is PCIe link-speed + CPU throttle states, all reading 0.

### H12 — Kernel / driver fault
**Untested.** The only evidence that could name it is the previous boot's kernel ring buffer,
which survives reboot and has not been read.

---

## WHEN THE BOX IS BACK — run these BEFORE anything else

```sh
# 1. THE decisive evidence. Previous boot's kernel log. Do this FIRST.
journalctl -b -1 -k --no-pager | tail -200
journalctl -b -1 --no-pager | grep -iE "thermal|throttl|mce|hardware error|critical temp|power|shutdown"

# 2. Did it come back LATCHED? (tests H10 — expect 2200-2600MHz / 80-100W if healthy)
nvidia-smi --query-gpu=clocks.sm,power.draw,temperature.gpu --format=csv
nvidia-smi -q -d PERFORMANCE | grep -A6 "Clocks Event Reasons\|SW Power Cap"

# 3. PD controller firmware state (H10)
sudo fwupdmgr get-devices | grep -iA5 "PD\|power"

# 4. Fans — is there ANY tachometer we are not collecting? (H11)
sensors 2>/dev/null | grep -iE "fan|rpm"
cat /sys/class/hwmon/hwmon*/fan*_input 2>/dev/null
ls /sys/class/thermal/cooling_device*/type | xargs -I{} sh -c 'echo -n "{}: "; cat {}'

# 5. Was it a clean shutdown or an abrupt cut? (distinguishes panic from power-off)
last -x reboot shutdown | head -10
```

**If a normal power cycle does not bring it back:** disconnect mains for **~5 minutes** (the
documented cold-drain). A warm reboot keeps the 240 W brick's rails powered and the PD MCU never
loses state.

---

## Monitoring gap this exposed

We had the thermal data and no alert on it. On metrics **already collected**:

```promql
max(node_thermal_zone_temp{cluster="dgx"}) > 85                    # warn
deriv(max(node_thermal_zone_temp{cluster="dgx"})[10m:]) > 1.5      # climbing >1.5C/min
```

The slope rule would have fired ~08:20Z, about seven minutes before the host died. It would not
have *prevented* the wedge, but it converts a silent death into a warning.

Genuinely missing and not fixable from software: fan RPM.

Sources: [gb10-thermal-toolkit](https://github.com/maci0/gb10-thermal-toolkit) ·
[GX10 PD throttle fix](https://github.com/Sggin1/DGX-SPARK/blob/main/GX10_PD_Throttle_Fix.md) ·
[NVIDIA forum: ACPI zones 96-97C, fans not ramping](https://forums.developer.nvidia.com/t/dgx-spark-gb10-thermal-throttling-after-ec-uefi-updates-acpi-zones-96-97c-fans-not-ramping/377044)
