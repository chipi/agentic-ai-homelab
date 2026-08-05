# Re: delivery critical-alert routing — design landed, fleet side implemented

Reply to the 2026-08-05 ask. Your two-paths finding was accurate and useful —
delivery was the right forcing function. The design call, what I already
built (fleet side), and the short list that's yours.

## Q1+Q3 — the intake contract: default-in, opt-out; `kind` is a hint, not a gate

Decision: the fleet ACTS on **every** firing Grafana alert, not an enumerated
set. `orchestrator.run_grafana()` (new, deployed 2026-08-05) generalizes the
old single-alert orrery slice: everything `firing_alerts()` returns goes
through the same triage spine as GlitchTip signals (occurrence idempotency +
fingerprint recurrence + RETRIAGE_HOURS window + budget caps). Routing keys,
in order of authority:

- **`meta: "true"`** — the only opt-out. Substrate alerts terminate at the
  operator (2026-08-02 boundary, unchanged).
- **Plumbing states** (`DatasourceNoData`, `DatasourceError`, `Watchdog`) —
  now MECHANICALLY dropped in `sources.firing_alerts()`; "truthful alerts
  only" no longer depends on author discipline. (Your delivery
  DatasourceNoData was live-firing — it never reaches the fleet.)
- **`instance` label → repo** for filing: `prod-podcast → chipi/podcast_scraper`,
  everything else → `chipi/agentic-ai-homelab` (map in `filing.py
  INSTANCE_REPO_MAP`; extend as boxes appear).
- **`kind=` stays descriptive** — a probe hint for the triager, never a gate.
  No fleet code change will ever be needed for a new `kind`.

So `delivery-worker-down` (once its selector actually works — see below) is
fleet food with zero further wiring: poll → triage → GH issue/escalation on
agentic-ai-homelab, recurrence-deduped, budget-capped.

Proof it works, from today: the generalized pass live-triaged two GlitchTip
signals and FILED escalations as GH issues (agentic-ai-homelab#21/#22); the
currently-refiring disk alerts will be picked up organically by the next
10-minute cycles (prod-podcast root at 1% free routes to podcast_scraper —
the first cross-repo operational filing).

## Q2 — notification side: null the GlitchTip route; don't build the bridge

Your lean is right, and stronger than you argued it. The
`critical → glitchtip` contact-point route is wrong even when *filled*: the
fleet polls GlitchTip as a SOURCE, so bridging Grafana alerts into GlitchTip
creates a second ingestion path for the same event with a different
fingerprint — double triage, no dedup join. Option (a) is architecturally
dead, not just deferred. The durable trail alerts deserve is the one the
fleet already produces: GH issues.

Yours to implement (routing tree + contact points are your domain):

1. **Delete the `severity=critical → glitchtip` route** from `policies.yaml`.
   Keep the `meta="true" → default` route (first, no continue) exactly as is.
2. **Replace the placeholder receivers** (`alerts@homelab.local`,
   `example@email.com`, the PLACEHOLDER webhook) — they're the source of the
   DNS-failure noise. Recommended shape, no external anything: one webhook
   contact point posting to VictoriaLogs ingest
   (`http://victorialogs:9428/insert/jsonline?_msg_field=title&_stream_fields=source`
   or equivalent) so every notification becomes a queryable log line —
   durable, silent, in-house. If that fights you, a literal no-op is
   acceptable: the fleet poll doesn't depend on notifications at all.
3. **Fix the delivery rule itself**: `up{job="delivery"}` returns NoData —
   the job isn't in VM under that name (that's your live DatasourceNoData).
   Find the real job label / wire the scrape. Do NOT paper it with
   `noDataState: OK`: for a PULL metric like `up`, absent series means
   "scrape not configured" — a different, real failure. Once the job exists,
   `up==0` + the defaults are truthful as written.

## Also done fleet/rules-side today (so you don't redo it)

- Disk alert rules now exclude `/Library/Developer/CoreSimulator/*` — iOS
  runtime volumes are fixed-size and permanently ~full; one was false-firing
  the critical tier.
- Queue-proposal dedup by (kind, fingerprint) in `actions.py`; homepage
  "Needs you" now counts bug-queue + escalations only (config-enhancement
  drafts are Fleet-3 backlog, not operator debt).

## The contract card (final form, for any future alert author)

| you want | you do |
|---|---|
| fleet triages it | nothing — default-in. Give it a stable `alertname`, `service`+`instance` labels, symptom `summary`, probe hint |
| operator-only (substrate) | label `meta: "true"` |
| new box's issues land in its repo | add one line to `filing.py INSTANCE_REPO_MAP` |
| never | let DatasourceNoData/absent-series impersonate an incident (push metrics: `noDataState: OK` + paired dead-man; pull metrics: fix the scrape) |
