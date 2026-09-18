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

## ⭐ THE PRECURSOR — the only thing that separates every wedge from every survivor

Found 2026-09-18 by mining vLLM's own metrics instead of host symptoms. This is the first
signal that is present in ALL wedge windows and ABSENT in ALL survivor windows.

**At matched prompt sizes, prefill ran ~40% slower before every wedge:**

| | tok/req | prefill tok/s | | tok/req | prefill tok/s |
|---|---|---|---|---|---|
| wedge 1 | 6565 | **11,617** | surv 04:30 | 6259 | 21,284 |
| wedge 2 | 4564 | **10,070** | surv 03:00 | 4712 | 16,391 |
| wedge 4 | 4097 | **9,322** | surv 05:30 | 3914 | 15,034 |

Three pairs matched on prompt size; the wedge window is slower every time (61-83% faster on
the survivor side). The 23:30 survivor reads 8,910 tok/s but its prompts were only 2,158
tokens, where fixed overhead dominates — not comparable.

**And it was hotter at identical everything else:**

```
                  wedge1  wedge4  │  surv03  surv04  surv05
GPU util %          96      96    │    96      96      96
SM clock MHz      2483    2528    │  2528    2528    2528
GPU power W         61      44    │    42      43      48
GPU temp C          75      71    │    63      64      65     <- 7-10C hotter
board zone max C     —      79    │    70      71      73     <- 7-9C hotter
```

Same clock, same power in, ~40% less work out, 7-10C hotter. That is the signature of SMs
STALLING — GPU "utilisation" only means a kernel is resident, not that it is progressing.
Stalled SMs still burn power and still make heat.

**This also corrects the H2 entry above.** That compared wedge PEAKS against the overnight
PEAK and concluded "the survivor ran hotter". At MATCHED windows the wedges run consistently
hotter. The 84.6C overnight figure was a brief excursion; wedge windows sat 7-10C above
comparable survivor windows throughout.

### What the precursor is NOT

* **Not process contention.** `dgx_gpu_process_memory_bytes` is identical in slow and fast
  windows: faster-whisper 0.2 GB, moss 1.9 GB, pyannote 3.0 GB, vllm-prod-vllm 29.5 GB,
  34.6 GB total. Same four processes, same allocations to the decimal.
* **Not memory bandwidth.** DECODE throughput was unaffected (wedges 125/88/77 tok/s vs
  survivors 90/89/84). Decode is memory-bandwidth-bound; prefill is compute-bound. Only the
  compute-bound half degraded.
* **Not KV pressure.** `kv_cache_usage_perc` 0.02-0.08%, zero preemptions, zero swapped.
* **Not queueing.** `num_requests_waiting` = 0, queue time ~0 in every window.

### What it points at

The GPU's arithmetic throughput dropped ~40% while clocks read full and
`DCGM_FI_DEV_CLOCK_THROTTLE_REASONS` stayed 0. That is silent derating happening BELOW what
DCGM reports — i.e. in the EC/firmware layer Linux cannot see. Which is the same layer that
later removed power without telling the OS.

Causality is NOT established: the extra heat may cause the slowdown, or the slowdown may
cause the heat by extending time-at-load. Both readings fit.

### Deliberately NOT alerted on

The operator's call, and correct: an alert saying "the box will die in ~15 minutes" is not
actionable — there is nothing to do with the warning. Recorded as a diagnostic, not a
monitor.

### Gap this exposed

vLLM prefix-cache metrics are NOT collected (a search for prefix/cache in VictoriaMetrics
returns only `alloy_*` and `pg_*`). If the inside-the-LLM angle is ever pursued — e.g. "did
cache hit rate collapse, forcing more real compute per token" — that data does not exist
today.

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

---

## 2026-09-18 10:07Z — recovery #4 forensics, and the firmware finding

Operator pressed the rear button; box came back in ~24 s. Evidence collected on the fresh boot:

| check | result | what it rules out |
|---|---|---|
| `/sys/fs/pstore/` | **empty** | firmware recorded no crash, no BERT/APEI record |
| `dmesg` grep for `bert\|hardware error\|mce\|xid\|throttl` | only boot-time thermal-zone registration | no machine check, no GPU Xid, no thermal trip |
| `journalctl -b -1` last line | `10:27:02+02:00`, ordinary user-session teardown | no `shutdown.target`, no service stops, no unmounts |
| `last -x reboot` | **all six boots show "still running"** | no shutdown record for ANY of the 4 deaths |
| GPU at idle after boot | 10.65 W, 38 °C, `clocks_event_reasons.active = 0x0`, max SM 3003 MHz | came back unlatched and healthy — **kills H10 (PD latch)** |

The journal stops mid-normal-operation with no OS-initiated shutdown of any kind. Combined with the
empty pstore: **nothing in the OS or the driver decided to stop, and firmware logged nothing.**
Power was removed from under a running system, four times.

The final 40 s before death contain only our own 10 s polling loop (`docker ps` / `docker inspect`
as `ops` over Tailscale SSH) and `gpu-process-metrics.service`. Neither can cut power; they are
noise, not cause.

### H12 — stale Embedded Controller / SoC firmware (NEW, ACTIONABLE)

`fwupdmgr get-updates` found **two unapplied NVIDIA updates, both `Urgency: High`**:

```
Embedded Controller   0x03000302 -> 0x03000508   (release 143461, created 2026-06-05)
  "improves the performance and stability of the Embedded Controller in DGX Spark"

SoC FW (UEFI + GPU)   0x0200980f -> 0x02009b0b   (release 143466)
  "improves the performance and stability of the System-on-Chip Firmware
   including UEFI and GPU in DGX Spark"
```

Signed payloads, tested by NVIDIA on Ubuntu 24.04 **from our exact current version**.

**Why it fits:** the EC owns the power rails, the fan curve, and thermal derating, and it is
invisible to Linux. That is exactly the shape of our signature — ~40 % prefill loss plus 7-10 °C
of extra heat at identical clock/power/utilisation with `THROTTLE_REASONS = 0`, then a power cut
with no log anywhere.

**What this does NOT establish:** the changelog is generic vendor boilerplate; there is no evidence
it addresses our specific fault. And the firmware was published 2026-06-05 while the box ran clean
2026-08-13 -> 2026-09-16. Stale firmware alone does not explain "why now" — it only works as an
explanation if the trigger is load-dependent, which is consistent with the context window having
doubled but is not proven by it.

**Counter-signal, stated explicitly:** the NVIDIA forum thread linked directly above is titled
*"thermal throttling AFTER EC/UEFI updates — ACPI zones 96-97 C, fans not ramping."* The update we
are applying is in the same family as one a user blames for a thermal regression. That is a real
argument against the action, not a footnote. Mitigation: watch board-zone temps and fan behaviour
closely on the first loaded run after the flash; `Minimum Version: 0x02003400` indicates a
downgrade path back below the new version exists if temps regress.

**Action taken 2026-09-18 10:10Z** (operator-approved): both capsules staged via
`fwupdmgr update -y --no-reboot-check` -> `Successfully installed firmware`, then
`systemctl reboot` at 10:11:02Z to apply. Containers deliberately NOT stopped by hand — they are
`restart: unless-stopped`, and an explicit `docker stop` would keep them down across the reboot.

### H13 — the fan never ramps because the box is headless (STRONGEST FIT SO FAR)

Measured on our box 2026-09-18 12:22 local, minutes after the post-flash cold boot:

```
/sys/class/hwmon/hwmon*/fan*_input     NO fan tachometer
/sys/class/hwmon/hwmon*/pwm*           NO fan control
nvidia-smi --query-gpu=fan.speed       [N/A]
cooling_device* types                  Processor x20, PCIe_Port_Link_Speed x6
                                       -> NO "Fan" cooling device registered in ACPI
/sys/class/drm/card*/status            glob does not expand — no DRM card enumerated
systemctl is-active display-manager    active
thermal zones at IDLE (GPU 11 W)       z0 54.9 C, z4 54.9 C, rest 42.8-44.7 C
```

This retroactively **confirms** the earlier line "genuinely missing and not fixable from software:
fan RPM" — which was asserted before it was checked. It is now checked. Linux has no fan interface
of any kind: nothing to read, nothing to write, and ACPI does not register a fan as a cooling
device. The EC owns the fan alone and never tells the OS.

Multiple independent reports say DGX Spark fans do not spin when the machine is headless:

- [Fans do not spin in headless boot mode, temperature rises to ~70 C](https://forums.developer.nvidia.com/t/dgx-spark-gb10-fans-do-not-spin-in-headless-boot-mode-temperature-rises-to-70-c/361960)
  — no HDMI, fans never start, temperature climbs **with no workload at all**. NVIDIA staff reply:
  *"This is not expected behavior and I cannot reproduce this."* No official fix in-thread. One
  user reports enabling a local X11 login with HDMI attached took idle from 55-58 C down to 36-40 C.
- [Fans stop when the screen goes dark or running from SSH](https://forums.developer.nvidia.com/t/dgx-spark-fans-stop-when-the-screen-goes-dark-or-running-from-ssh-box-gets-too-hot-to-touch-fire-hazard/378945)
  — with a display attached, fans cut ~1 min after blanking; mouse movement restores them.
- [Low fan speed / high temps, no Linux or BIOS fan control](https://dredyson.com/fix-dgx-spark-low-fan-speed-and-high-temps-a-beginners-step-by-step-guide-to-understanding-thermal-performance-fan-control-limitations-and-proven-workarounds-for-overheating-issues/)

Reference idle temperatures from those threads: healthy headless unit **34-35 C**; affected units
**60-70 C with no workload**. Ours reads **54.9 C at idle** and was still rising when measured.

**H13 STATUS: the supporting evidence was RETRACTED within the hour — see the retraction below.**
Idle thermal drift was measured and came back healthy (54 C post-boot transient falling to 37-40 C
and holding, against a 34-35 C healthy reference and a 60-70 C affected reference). The fan cools
this box fine at idle. H13 is not dead — a fan that idles fine but fails to ramp under sustained
load is untested — but it no longer has the prefill evidence behind it.

**Candidate interventions, untested here:** attach an HDMI display or EDID dummy plug; keep a
graphical session non-blanked; external forced-air cooling.

---

## RETRACTION 2026-09-18 — the precursor was a measurement artifact

**The "~40 % prefill degradation before every wedge" does not exist.** It was the prefix-cache hit
rate falling, measured with a metric that cannot tell the two apart.

The original precursor used `request_prompt_tokens_sum / request_prefill_time_seconds_sum`. Prompt
tokens include tokens served from the prefix cache, which cost approximately no compute. That ratio
therefore conflates "the GPU got slower" with "fewer tokens came from cache".

`vllm:request_prefill_kv_computed_tokens` is "new KV tokens computed during prefill (**excluding
cached tokens**)". Dividing it by prefill time gives real compute throughput, immune to cache-rate
changes. It was in VictoriaMetrics the whole time.

| window | OLD tok/s | TRUE tok/s | cache hit % |
|---|---|---|---|
| wedge 1 DIED | 11,617 | 6,201 | 47.0 |
| wedge 2 DIED | 10,070 | 6,671 | 32.6 |
| wedge 4 DIED | 9,322 | 6,818 | 26.6 |
| surv 03:00 | 16,391 | 6,922 | 58.0 |
| surv 04:30 | 21,284 | 5,742 | 73.4 |
| surv 05:30 | 15,034 | 5,584 | 62.1 |

```
OLD  prompt-tokens/s   wedge 10,336   survivor 15,405    -32.9%
TRUE kv-computed/s     wedge  6,563   survivor  6,593     -0.4%
cache hit %            wedge   35.4   survivor   50.5    -29.9%
```

**Compute throughput before every death was flat to within 0.4 %.** No degradation, ever.

### What was actually happening

Measured on real-work metrics over the same windows:

```
                            wedge      survivor    delta
kv computed/s (real work)   334.2       229.0     +45.9%
generation tok/s             96.5        70.6     +36.7%
GPU power W                  52.6        44.8     +17.3%
GPU temp C                   73.0        64.0     +14.1%
board zone C                 79.0        71.0     +11.3%
```

The box was not degrading. It was doing **~46 % more real work, drawing ~17 % more power, running
11-14 % hotter**. The temperature rise attributed to failing cooling is fully accounted for by
more work going in.

### Errors of record

1. **"+7-10 C at *identical* clock, power and utilisation."** False. The precursor table in this
   very document showed wedge 1 at **61 W** against survivors at **42-48 W**. The word "identical"
   was written over a table that contradicted it.
2. **"vLLM prefix-cache metrics are NOT collected."** False. All eight relevant series
   (`request_prefill_kv_computed_tokens_sum/_count`, `prefix_cache_hits_total`,
   `prefix_cache_queries_total`, `prompt_tokens_cached_total`, `num_preemptions_total`, …) exist
   continuously across 09-15..09-18. A search returned nothing and was reported as fact instead of
   re-run — the exact failure mode that rule exists to prevent. A task was then filed on the false
   premise, deferring the one measurement that mattered.
3. **H12 and H13 were both propped up by the artifact.** Each was presented as "fitting every
   observation" while resting on a degradation that never occurred.

### What survives, unchanged

- Four unclean power losses; nothing in pstore, dmesg, or the journal; physical button required.
- Linux has no fan interface at all — no tachometer, no PWM, no ACPI fan cooling device.
- Idle cooling is healthy: 54 C post-boot falling to 37-40 C and holding.
- **It died at 79 C board / 73 C GPU having already survived 84.6 C.** Peak temperature is not
  the trigger, and now neither is degraded cooling.

### Where that points

Not heat — **total power draw**. The deaths correlate with a +17 % GPU power rise on a chassis fed
by a 240 W brick, and GPU die power excludes CPU, 128 GB of unified LPDDR5X under saturated
bandwidth, NVMe and networking. An EC cutting the rails on an over-current or over-budget condition
produces exactly what we see: instantaneous loss, no OS involvement, no firmware log, button to
recover.

Stated as a direction, not a conclusion. The previous confident hypothesis was wrong and this one
has had no adversarial pass yet.

**The measurement that would settle it is the smart plug** (total system draw at the wall, against
the 240 W budget) — deferred in task #36, partly on error 2 above. It is pure observation and
changes nothing about how the box behaves.

### Next measurement — the discriminator

`/tmp/prefill_live.py` reports prefill tokens/sec against the measured bands:

```
healthy survivors   15,000 - 21,300 tok/s
pre-wedge windows    9,300 - 11,600 tok/s
```

On the first loaded run after the flash:
- reads **healthy** -> the box boots healthy and degrades under load; whether firmware fixed
  anything is then only answerable by time-to-next-wedge.
- reads **degraded immediately** -> the degradation survives a power cycle AND a firmware flash,
  which would point at the silicon rather than the controller.
