# DGX Spark hard power-off under sustained GPU load — known NVIDIA issue, our exposure, and remediation

**Scope:** this document covers one thing only — the documented DGX Spark / GB10 failure in
which the machine powers completely off under sustained GPU load, leaving no trace, and
requires a physical power-button press. It establishes (1) that the issue exists and is a
platform defect rather than a deployment fault, (2) what we did about it, and (3) the RMA
path if mitigation is not enough.

Hypothesis history, dead ends, and one retracted precursor live separately in
[`DGX-WEDGE-DIFFERENTIAL.md`](DGX-WEDGE-DIFFERENTIAL.md). This file is the standing reference.

**Status:** mitigated, not fixed. Clock cap applied and verified 2026-09-18. Recurrence still
possible — see [Residual risk](#residual-risk).

---

# Part 1 — Assessment: the issue exists

## 1.1 The signature

A machine exhibiting this failure shows **all** of the following. Any one alone is a different
bug.

| Symptom | Distinguishes it from |
|---|---|
| Machine is **off**, not hung — no ping, no SSH, no console | freeze (box stays powered, unreachable) |
| `journalctl -b -1` stops **mid-line on an ordinary entry** | clean shutdown, which writes `shutdown.target` |
| No `shutdown.target`, no service stops, no unmounts | operator- or OS-initiated poweroff |
| `/sys/fs/pstore/` **empty**; no BERT/APEI record | kernel panic, which leaves pstore evidence |
| No `Xid`, no thermal trip, no MCE, no OOM in `dmesg` | GPU fault, thermal trip, memory exhaustion |
| `last -x reboot` shows **no shutdown record** | any orderly stop |
| Hardware watchdog does **not** reset the box | kernel hang — the watchdog would fire |
| Recovery requires the **physical power button** | suspend (resumes), network loss (box still up) |
| On recovery: **full boot**, `uptime 0`, new boot record | resume from suspend or hibernate |

## 1.2 Our evidence

Four events, 2026-09-15 to 2026-09-18, after the box ran clean from 2026-08-13 to 2026-09-16.

Every independent telemetry path stopped within ~60 s of the others — logs, node_exporter,
cadvisor, DCGM, vLLM, and alloy's own self-metrics. A container crash kills one. A GPU hang
kills one. All of them together means the host stopped executing. Confirmed not a network
artifact: ping, `:8003`, and SSH were dead **from the mini**, not merely from a laptop.

Wedge 4 forensics, collected on the following boot:

```
/sys/fs/pstore/                     empty
dmesg  bert|hardware error|mce|xid  only boot-time thermal-zone registration
journalctl -b -1  last line         10:27:02+02:00, ordinary user-session teardown
last -x reboot                      all six boots "still running" — no shutdown record, ever
GPU at idle after boot              10.65 W, 38 C, clocks_event_reasons 0x0
```

Every row of §1.1 matched.

**Conditions before each death**, versus windows that survived the same workload:

```
                            wedge      survivor    delta
kv computed/s (real work)   334.2       229.0     +45.9%
generation tok/s             96.5        70.6     +36.7%
GPU power W                  52.6        44.8     +17.3%
GPU temp C                   73.0        64.0     +14.1%
board zone C                 79.0        71.0     +11.3%
```

**It is not heat.** The box died at 79 C board zone having already survived **84.6 C for 24
minutes** in an earlier run. Peak temperature does not predict death. What does correlate is
**power** and **real prefill work**.

Also measured on our unit: Linux has **no fan interface at all** — no `fan*_input`, no `pwm*`,
and no `Fan` ACPI cooling device. The only cooling levers the OS holds are CPU throttling and
PCIe link-speed reduction. Idle cooling is healthy (54 C post-boot settling to 37-40 C).

## 1.3 Community evidence — this is the platform's most-reported failure

Nine independent NVIDIA forum threads plus three technical blogs, with the same signature.

> *"full hard power-off (not a reboot — the machine powers completely off and must be switched
> back on)… `/sys/fs/pstore` is empty… no vmcore even though kdump is armed… no NVRM Xid, no
> thermal trip logged"*
> — Malousy.Sean, running vLLM, 8 events in 11 days,
> [373251](https://forums.developer.nvidia.com/t/dgx-spark-gb10-reproducibly-hard-powers-off-under-gpu-load-fully-updated-zero-crash-capture/373251)

> *"zero shutdown markers (Reached target Shutdown, systemd-shutdown[1], Powering off). The log
> simply stops mid-operation."*
> — pacardenaz,
> [378315](https://forums.developer.nvidia.com/t/hard-power-off-under-sustained-gpu-load-at-90w-persists-after-full-platform-firmware-update/378315)

> *"Not a hang. Not a kernel panic. Off."* … *"journalctl -b -1 stops mid-line on an ordinary
> entry. The last record is a routine tailscaled session close."*
> — [ai-muninn](https://ai-muninn.com/en/blog/gx10-thermal-hard-poweroff), reproduced deliberately

**The closest analogue to our case** — four power-offs over two days, uptimes of 3 days / 8.7 h
/ 41 min / 73 min under steady local inference, final event peaking at **79 °C**, our exact
number, with DPMS already disabled and clocks already capped at 2000 MHz:

> *"Journald healthy to the final second, no panic, no oops, no Xid, no throttle messages."*
> — pancakedrip24,
> [377044](https://forums.developer.nvidia.com/t/dgx-spark-gb10-thermal-throttling-after-ec-uefi-updates-acpi-zones-96-97c-fans-not-ramping/377044)

Decisively, his **SBSA hardware watchdog (`RuntimeWatchdogSec=2min`) did not reset the box.** It
stayed off until manual power-on. A kernel hang would have been reset. Power went away.

## 1.4 Mechanism: a power transient, not a thermal ceiling

The best-instrumented account used an `fsync`-per-sample external recorder, because journald
loses the final ~40 s:

> *"Swinging violently between 18W and 95W in 30-second intervals"* — synchronised with vLLM's
> prefill. Survived 82–85 W peaks at ~96 °C; **died at a 95 W peak**. Conclusion: *"this is not
> a 'thermal protection shutdown' but rather a sharp power spike triggered overcurrent
> protection (OCP)."*
> — [nob75note](https://note.com/nob75note/n/ned4cc56ead79?hl=en)

**Prefill is the trigger, and specifically non-cached prefill:**

> Freezes hit *"during heavy non-cached prefill"* and explicitly **do not** occur *"during
> normal chat, even at 70% of 256k context fill."*
> — heathen0711,
> [376882](https://forums.developer.nvidia.com/t/total-host-freeze-during-multi-node-tp-2-vllm-prefill/376882)

This matches our telemetry independently. Our prefix-cache hit rate fell from ~50 % to ~35 %
before each death — that is, more non-cached prefill — which is why real compute rose ~46 % and
power ~17 % while measured compute *throughput* stayed flat to within 0.4 %.

A dissenting reading exists and is not refuted: maci0 argues it is *"cooling-capacity-limited"*
rather than OCP, measuring only 49–65 W against a ~140 W budget while the board still trips at
93–96 °C, and found **backwards chassis-fan installation** worth ~18 °C on one unit.

**Critical instrumentation caveat:** `nvidia-smi` under-reads the real hot spot by **8–16 °C**
across three independent measurements (ai-muninn; mbnshahrzad via fieldiag, offset 16.8 °C;
maci0). Board ACPI zones are the honest signal. Our "73 °C" at the wedges was plausibly ~85–89 °C
actual — though we did not measure the offset on this unit.

## 1.5 NVIDIA's position

- **Acknowledged as a known issue with a named workaround.** On the clock cap: *"It looks like
  you are experiencing a know issue. The current workaround is to lower your GPU clock max as
  you described."* — aniculescu,
  [378315](https://forums.developer.nvidia.com/t/hard-power-off-under-sustained-gpu-load-at-90w-persists-after-full-platform-firmware-update/378315)
- **No fan control exists, by design.** *"There is no method to control fan speed on the
  Spark."* — aniculescu,
  [360020](https://forums.developer.nvidia.com/t/fan-control-from-the-os/360020)
- **Not listed on the Known Issues page.** The
  [official page](https://docs.nvidia.com/dgx/dgx-spark/known-issues.html) (updated 2026-09-10)
  carries no fan, thermal, headless, or unexpected-shutdown entry.
- **Deflected on OEM units.** *"We have not been able to reproduce this on an FE DGX Spark. If
  you have an OEM device, please contact your provider support."*

## 1.6 Ruled out

| Hypothesis | Killed by |
|---|---|
| Memory exhaustion / unified-memory pressure | host memory flat at 73.2–73.3 GB available through every final window; 0 OOM kills across 10 h |
| Peak temperature (thermal trip) | survived 84.6 C for 24 min; died at 79 C |
| The ollama load/unload cycle | wedges 2 and 4 had **0 models loaded**; an 8 h run with repeated cycles survived |
| GPU degradation before each wedge | cache-independent throughput flat to **-0.4 %** — see the retraction in `DGX-WEDGE-DIFFERENTIAL.md` |
| Headless fan bug as the *load-time* cause | every community report of it is an **idle** phenomenon (45–70 C at 0 % GPU); one user stress-tested affected and healthy units and both *"reached 75-78°C GPU, passed without crashes"*. Not ruled out as a contributor; ruled out as the documented mechanism. |
| Suspend when headless | not a suspend — the machine stays running and it is a Wi-Fi/NetworkManager teardown ([353777](https://forums.developer.nvidia.com/t/nvidia-dgx-spark-automatically-suspends-when-running-headless-despite-power-config-changes/353777)). A resume would not produce `uptime 0` and a new boot record. |
| Kernel 7.0.0-1019 advisory (2026-09-14) | we run `6.17.0-1021-nvidia` |

---

# Part 2 — Remediation: what we did

## 2.1 Platform firmware update — APPLIED 2026-09-18 10:10Z

```
Embedded Controller   0x03000302 -> 0x03000508   ("EC 3.5.8")
SoC FW (UEFI + GPU)   0x0200980f -> 0x02009b0b   ("SOCFW 2.155.11")
```

Both `Urgency: High`, signed, tested by NVIDIA on Ubuntu 24.04 from our exact prior version.
Staged with `fwupdmgr update -y --no-reboot-check`, applied by reboot, both versions confirmed
moved after boot.

**This did not fix the issue, and may not help at all.** Two users report the hard power-off
persisting or worsening after the same generation of update:

- On **our exact versions** (EC 3.5.8 / SOCFW 2.155.11): *"The unit still hard powers-off under
  load after the update, and sooner than before: before firmware update… died at step 16384
  (91.81 W, GPU 82 C); after firmware update… died at step 8192 (88.82 W, GPU 83 C, CPU 97
  C)."* — pacardenaz,
  [378315](https://forums.developer.nvidia.com/t/hard-power-off-under-sustained-gpu-load-at-90w-persists-after-full-platform-firmware-update/378315)
- One user did report the firmware *stopped* his hard power-off — but it *"did not fix the
  thermal fault"*, merely converted it into a diagnostic error, and he was RMA'd for a sensor
  fault. — digiegg,
  [377365](https://forums.developer.nvidia.com/t/dgx-spark-gb10-partnerdiag-powerstress-reproducibly-hard-powers-off-the-box-acpitz-88-97-8-c-in-5s-all-other-field-tests-pass/377365)

Keep it applied — it is current signed vendor firmware on a box that has died four times — but
do not count it as mitigation.

## 2.2 GPU clock cap — APPLIED AND VERIFIED 2026-09-18

The best-evidenced action available, and the one NVIDIA support names.

```bash
sudo nvidia-smi -pm 1
sudo nvidia-smi -lgc 300,2200
```

Made durable via `infra/dgx/systemd/gpu-clock-cap.service` (installed, enabled, and confirmed by
`systemctl restart` so that `ExecStart` itself is proven to apply the cap, not just the original
shell invocation). `ExecStop` runs `nvidia-smi -rgc`, so the mitigation reverts with
`systemctl stop gpu-clock-cap`.

**Verified under real load** — 25-request prefill burst at 96 % utilisation:

```
2177 MHz, 52.45 W, 51C, 96%
2177 MHz, 43.69 W, 51C, 96%
2184 MHz, 46.05 W, 50C, 96%
2171 MHz, 53.17 W, 49C, 96%
2171 MHz, 52.74 W, 56C, 96%
2184 MHz, 47.24 W, 54C, 96%
2177 MHz, 55.50 W, 54C, 96%
```

Never above 2200 MHz. Peak 55.5 W, 56 C GPU, 65 C board zone.

Expected effect, measured by others:

| Source | Result | Cost |
|---|---|---|
| [tonyd2wild](https://github.com/tonyd2wild/dgx-spark-hard-poweroff-fix) | ~20 log-less power-offs in 3 weeks → **zero** | ~5 % throughput (30.8 → 32.3 tok/s) |
| [ai-muninn](https://ai-muninn.com/en/blog/gx10-thermal-hard-poweroff) | died at 156 s → **survived 251 s**; peak power 93.2 → 74.0 W; time ≥95 C 12 % → 0 % | ~9 % |
| [nob75note](https://note.com/nob75note/n/ned4cc56ead79?hl=en) | power range 85 W → 50 W | not stated |

**NOT verified:** that the unit applies across an actual reboot. It runs correctly on demand;
boot-time ordering against the driver is guarded by a 30 × 2 s `ExecStartPre` retry loop, and a
guard is not a proof. Confirm on the next natural reboot with:

```bash
systemctl is-active gpu-clock-cap && nvidia-smi -q -d CLOCK | grep -A1 '^    Clocks$'
```

## 2.3 Not done, and why

| Action | Status |
|---|---|
| **Smart-plug power scraping** | **The top missing signal.** Total system draw against the 240 W brick is the measurement that would settle OCP-vs-thermal, and GPU die power excludes CPU, 128 GB of unified LPDDR5X under saturated bandwidth, NVMe and networking. Tracked as task #36. Pure observation — changes nothing about how the box behaves. |
| **`dgx-spark-fieldiag` PowerStress** | Not installed. This is the RMA gate — see Part 3. |
| **Lower `--max-num-batched-tokens`** | Weaker evidence; nobody ran a controlled before/after. Note the running engine reports `gpu_memory_utilization=0.25`, not the 0.75 the compose file defaults to, so something in `.env` overrides it — worth understanding before tuning further. |
| **Sustained USB load + `xset -dpms`** | Confirmed by NVIDIA staff, but every measurement behind it is at **idle**. No source shows it helps under sustained GPU load. Cheap; not evidenced for our failure mode. |
| **EC firmware rollback** | **Do not.** One claim, three explicit failures from other users, no NVIDIA sanction, and it re-arms on any blanket `fwupdmgr update`. |
| **FF-A fan-RPM floor override** | Undocumented EC interface, author-declared "at your own risk", volatile across power cycles, needs module signing under Secure Boot, and RPM readback is disputed between the projects implementing it. Last resort only. |
| **Repaste / chassis-fan orientation check** | Four users ended their power-offs this way; one found TIM *"dry as a rock"*; maci0 measured ~18 C from correcting a backwards-installed fan. Physical access required. Does not void warranty per one report, but verify before acting. |

---

# Part 3 — RMA path

`dgx-spark-fieldiag` **PowerStress** is the decision procedure the forum converges on. It
reproduces the hard power-off within minutes, and a failure is an automatic approval:

> *"If you have a failing Field Diagnostic, you are automatically approved for an RMA."*
> — aniculescu

Relevant error codes: `020000600139` and `020000281445` — *"Acceptable temperature limits
exceeded or the thermal sensor is broken or miscalibrated."*

**Precedent:** six users in these threads went to RMA this way. Two of them (heathen0711,
digiegg) had the symptom disappear entirely on replacement units, which is the strongest
available evidence that at least some fraction of these are genuinely defective hardware rather
than a universal platform limit.

**Gotchas:** use version 1.0.9-1 if `ofed-scripts` is unavailable; Secure Boot may need
disabling.

**This is worth running whether or not the clock cap holds.** A pass tells us the hardware is
within spec and the problem is configuration; a fail gets a replacement. Either outcome is more
useful than continuing to observe.

---

## Residual risk

The clock cap **reduces, it does not eliminate**. One user still died at a 2000 MHz cap — lower
than ours at 2200. The box should be treated as mitigated, not repaired.

Recurrence is still plausible, and if it happens the highest-value thing is to have the plug
telemetry in place first, so the next event produces an answer instead of a fifth identical
forensic dead end.

**After any future power-off: pull AC for 60 s to 5 minutes before restarting.** A reboot alone
does not clear the sticky degraded low-power state that ~8 users report
([361294](https://forums.developer.nvidia.com/t/dgx-spark-performance-degradation-gpu-power-draw-issue/361294));
maci0 independently: *"Post-thermal-shutdown reset requires ~5 minutes without power to clear
stuck low-power states."* We did **not** do this after wedge 4 — the box was recovered by button
press alone — though its clocks and idle behaviour read normal afterwards.
