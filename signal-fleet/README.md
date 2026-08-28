# signal-fleet — Signal-to-Action Fleet (Fleet 2)

Autonomous **observability triage**: take live production signals (GlitchTip
errors, Grafana alerts, Umami UX, VictoriaMetrics/Logs/Traces) and decide
**Dismiss / File / Escalate** — sibling to the bug-fix fleet (`bugfix-fleet/`,
RFC-0002). It never touches production and never fixes code; its `File` output
chains to Fleet 1 as a labelled GitHub issue. This is RFC-0002's own Phase-3
("o11y-reactive agents"), promoted to its own project.

## ⚡ Current state — read first (2026-08-19, saves you the archaeology)

- **This IS live** — runs continuously as `fleetd` (LaunchAgent) on the mini, not a
  one-shot. Cycle = `python3 mvp/orchestrator.py --cycle` over Grafana + GlitchTip.
- **Deploy reality (2026-08-20): runs from the GIT CHECKOUT** — `fleetd` runs the
  triage cycle from `~/agentic-ai-homelab/signal-fleet/mvp` (the checkout), so a
  `git pull` on the mini ships code updates with **no scp** (was: an untracked
  `~/signal-fleet/` copy deployed by scp — that drift class is gone). Clean
  separation: **code** = the checkout; **state + secrets** = mini-local under
  `~/signal-fleet/` (gitignored) — `fleet-gateway.env`, the ledger
  (`results/dispositions.tsv`, `results/filed.tsv`), `queue/`. All state paths are
  absolute + env-overridable (`SF_LEDGER`/`SF_QUEUE`/`SF_FILED_LEDGER`…), so the
  code is cwd-independent. fleetd config: `~/fleetd/fleetd.json` — the committed
  `fleetd/deploy/fleetd.json` sets `workdir=~/signal-fleet/mvp`,
  `env_file=~/signal-fleet/fleet-gateway.env`. For "runs from the checkout, no
  scp" to hold, `~/signal-fleet/mvp` must be a symlink into the checkout's `mvp/`
  (NOT re-verified this pass — the mini's `~markodragoljevic` paths aren't readable
  from the ops account; confirm the symlink on the box if this ever surprises you).
- **env files:** `fleet-gateway.env` is the ONE fleetd loads. `fleet.env` is a stale
  duplicate — ignore it (its tokens are old; kept in sync only as a courtesy).
- **LLM = homelab LiteLLM gateway.** Triager posts to
  `SF_OPENROUTER_URL=http://localhost:4001/v1/chat/completions` with the `fleet-triage`
  virtual key (`OPENROUTER_API_KEY` in `fleet-gateway.env`), model `fleet-triage-pro`.
- **Langfuse tracing IS wired now** (project **"agents"**; keys = langfuse init keys).
- **Flood hardening (2026-08):** #2 fail-**closed** on a persistent triager 401 (files
  ONE `fleet-triager-down` issue, not N escalations); #4 storm group-rules
  (cost-cap/budget/402); #5 operational classifier (cost-cap/402 → dismiss-not-ticket,
  no LLM); #7 test/synthetic suppression at ingestion. Full write-up:
  [`docs/wip/signal-fleet-flood-hardening.md`](../docs/wip/signal-fleet-flood-hardening.md).
- **Gotcha — recreation casualties:** a colima/DB recreate wipes the litellm virtual
  key, the Grafana/GlitchTip source tokens, and the Langfuse keys → the fleet 401s and
  fails (historically fails-open → issue flood). If it's misbehaving, check those creds
  first (litellm key: [`infra/litellm/README.md`](../infra/litellm/README.md); tokens
  live in `fleet-gateway.env`).
- **Evals (versioned + reproducible):** `python3 mvp/eval_hardening.py` — a
  deterministic end-to-end eval of the flood hardening (#5/#2/#7) over a versioned
  dataset of the real (scrubbed) flood signals; runs anywhere, no LLM/creds, ALL PASS
  ([`reference-hardening/`](reference-hardening/README.md)). `mvp/score.py` measures
  the LLM triager over the frozen `reference/` fixtures (now committed + scrubbed via
  `mvp/scrub.py`).

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
Triage-only forever (remediation = future Fleet 3). *(Historical Jul-24 caveats now
superseded — see Current state above: it's live as a daemon, files real issues,
covers Grafana + GlitchTip, and Langfuse tracing is wired.)*
