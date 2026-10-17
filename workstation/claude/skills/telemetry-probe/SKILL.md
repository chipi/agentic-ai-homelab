---
name: telemetry-probe
description: Prove a telemetry path end to end with one labelled test signal, then delete it — a GlitchTip error, an Umami event or a Langfuse trace is sent, read back from the target, checked ABSENT from sibling targets (prod vs dev, staging vs prod), deleted, and the deletion confirmed. Ends with PROBE PASS/FAIL. Use when asked to "prove it works", "send a test event", "check dev doesn't land in prod", after wiring a new DSN, site id or Langfuse key, or before telling another agent that a pipeline is verified.
---

# telemetry-probe

Every "probe it, then clean up" in this repo used to be a hand-written script, and it went
wrong in the same places each time (2026-10-16/17):
- deleting with GlitchTip's read-only token (403);
- the legacy `/store/` endpoint, which drops `debug_meta`;
- forgetting the Umami session row;
- calling a delete done before the re-read showed it gone.

This skill does it the tested way.

## Run (on the mini, through host-run)

```bash
P=~/.claude/skills/telemetry-probe/scripts/probe.py
R=~/.claude/skills/host-run/scripts/run.sh

$R homelab $P glitchtip --project player-dev --assert-absent player,player-api
$R homelab $P umami     --site "Player (dev)" --assert-absent Player
$R homelab $P langfuse  --keys '~/podcast-langfuse-dev.env'
```

| Option | Meaning |
|---|---|
| `--project` / `--site` | the GlitchTip project slug, or the Umami site name or id, that **should** receive the probe |
| `--assert-absent a,b` | targets that must **not** receive it; this is the isolation check (dev vs prod) |
| `--keys FILE` | Langfuse: the env file with that project's key pair (see the handbook, section 8) |
| `--keep` | leave the probe in place, e.g. as a baseline another agent asked for |

**Labels:** every probe is labelled `zz-probe-<utc>`, with GlitchTip `environment=probe` and
Umami hostname `telemetry-probe.localhost`. Nothing real is mistaken for one.

**Exit 0 / `PROBE: PASS`** only when all three hold:
1. the probe landed in the target;
2. it is absent from every `--assert-absent` target;
3. unless `--keep`, the delete was accepted **and** a re-read shows it gone.

### How each service is done

- **GlitchTip:**
  - sends a Sentry envelope to `/api/<id>/envelope/` (not `/store/`), using the project's own
    DSN key;
  - reads with the fleet's read-only token;
  - deletes through the superuser session login (the handbook's curl recipe), then waits for a
    404.
- **Umami:**
  - POSTs `/api/send` with a browser User-Agent. Umami's bot filter answers 200
    `{"beep":"boop"}` and stores nothing for non-browser UAs; the script detects that.
  - checks `website_event`, then deletes the event, its `event_data`, and the session if
    nothing else uses it, in one transaction.
- **Langfuse:**
  - `trace-create` through `/api/public/ingestion`, read back by id;
  - `DELETE` is asynchronous, so the script waits for a 404.

## Verified

2026-10-17, all on dev targets:
- **GlitchTip:** a `player-dev` probe, absent from `player` and `player-api`, deleted, 404
  confirmed.
- **Umami:** a `Player (dev)` probe, absent from `Player`, deleted with its session.
- **Langfuse:** a `podcast-dev` probe, deleted, 404 confirmed.
- **Negative control:** `--assert-absent "Player (dev)"` on its own target reported `FAIL`
  (exit 1) and still deleted the probe, leaving 0 `zz-probe` events.

## Rules

- **Prefer dev targets.** A probe into a **prod** project or site needs the operator's go, and
  the owning agent should know: they watch those dashboards.
- Never `--keep` a probe in prod unless the owner asked for it.
- The script prints no secrets. It reads credentials on the mini from the files listed in the
  handbook's credentials table.

## Not covered

- **Source-map resolution:** it needs a real live JS file and its debug id; the handbook,
  section 7, and the `deploy-verify` skill cover it.
- **VictoriaLogs:** deletion is disabled there, so a probe line can't be removed. Write probe
  log lines only when the operator agrees, and label them.
- **LiteLLM key checks:** see `mint-credential` (call, refused alias, trace).
- **Fleet noise:** the signal-fleet sees GlitchTip probes while they exist. A short-lived,
  labelled one is ignored as a probe, but don't leave them around.
