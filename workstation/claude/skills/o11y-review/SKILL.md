---
name: o11y-review
description: Review one project's observability over a time window, read-only. Covers log volume, warning and error patterns (normalized and counted), GlitchTip errors (new vs. old), traces (slow operations and outbound calls), and what the triage fleet did on the project's repo, with an optional handover file. Use for "what happened overnight / during the ingest / since the deploy" questions on Close Listening (podcast + player), Orrery, or homelab services. Runs against the homelab observability stack (VictoriaLogs, GlitchTip, VictoriaTraces).
---

# o11y-review

One project, one window, the observability lens. It's read-only: queries only, no writes anywhere.

## Run

```bash
python3 ~/.claude/skills/o11y-review/scripts/review.py --project closelistening --since 16h
python3 ~/.claude/skills/o11y-review/scripts/review.py --project orrery \
    --start 2026-10-01T18:00:00Z --end 2026-10-02T08:00:00Z --handover /tmp/handover.md
```

**Projects:** `closelistening` (alias `podcast`), `orrery`, `homelab`. To add one, add an entry to `PROJECTS` in the script:
- `logs`: a VictoriaLogs filter;
- `glitchtip`: GlitchTip short-id prefixes;
- `traces`: trace service names;
- `repo`: the GitHub repo the fleet files into.

**Access:** the stack's ports are loopback-only on the homelab host, so the queries run there over SSH.
- **SSH:** the default is the Mac mini (`ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab`); override with `--ssh` / `HOMELAB_SSH`.
- **GlitchTip:** the token is read on the host from `~/signal-fleet/fleet-gateway.env` and is never printed.
- **Fleet actions:** come from local `gh`.

It took about 16 s for a 14-hour Close Listening window (2026-10-02).

## Then: read it like an engineer, not a counter

1. **Systematic beats loud.** A warning in 26 of 28 runs matters more than one error. Look at the "streams" column.
2. **New beats old.** A `NEW` GlitchTip issue first seen in the window is the first thing to explain.
3. **Traces show where time went:** the slowest outbound calls name the bottleneck service. If the report says "API cap 1000 hit", the trace numbers are partial.
4. **Check before claiming.** Open the actual log lines in VictoriaLogs (`_time:[start, end] <filter> "<pattern words>"`) before calling a pattern a bug. Normalization merges lines; read real examples.
5. **Hand over facts, not guesses.** With `--handover`, the report is written as-is. Before sending it, add the things you checked yourself and a "not verified" list, e.g. whether an affected item was lost or retried.

## Known limits (verified 2026-10-02)

- **Logs with no level field are not classified.** They count as `-`, so warning and error patterns don't come out of them. Today that means all Orrery logs and most homelab container logs.
- **Python tracebacks** normalize to their first line ("recent call last"). Read them in VictoriaLogs.
- **Messages that differ by a name or free text** (e.g. speaker names) don't collapse into one pattern. The long tail of 1-count lines is often one pattern.
- **Traces:** the API caps at 1000 traces per service and window, and error spans depend on instrumentation; on 2026-10-02 the pipeline logged ERRORs but marked 0 error spans.
- **Metrics and alerts are not included.** Use Grafana, or the `triage-fleet-review` skill for what the fleet did.
