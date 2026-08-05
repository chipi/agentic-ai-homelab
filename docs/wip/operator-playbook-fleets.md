# Operator playbook — running the fleets (as of 2026-07-29)

Your side of the machine, in ritual form. The fleets do the volume; you do
four small rituals: **glance, route, answer, merge**. Everything here uses
things that exist today — real URLs, real labels, real issues.

State when written: Fleet 2 (triage) **live at propose** — files GitHub
issues autonomously. Fleet 1 (bug-fix) verified, listening on
`triage-fleet/routed:bugfix`, orrery-only, dispatched manually.

---

## 1. The daily glance (30 seconds, phone-friendly)

**Go to: `http://homelab:3000` → Homelab → "Fleet Workforce — Triage".**

Top row is yours:

| panel | meaning | act when |
|---|---|---|
| **Needs your attention** | queued work + escalations | it's yellow/red and you have a minute |
| **Escalations (7d)** | fleet couldn't decide, wants your brain | any number > 0 |
| **Oldest queued item** | how long work has waited on you | red (>3 days) = you're the bottleneck |
| **Queue by kind** | what's piling where | `bug` grows = routing candidates waiting |

**Click any of these numbers** → "Triage — Operator Inbox" dashboard: the
actual items with titles and escalation reasons inline. Read there, act in
GitHub (next section).

Storm check: "Dispositions over time" spikes + annotation markers
("filed podcast_scraper#1347…") = an incident got grouped and filed; the
recurrence counter absorbing hundreds of rows is the fleet working, not
failing.

**Substrate alerts are YOURS alone (2026-08-02):** the bottom panel of the
Operator Inbox shows `meta=true` alerts — fleetd down/failing, VM/Grafana
health. The fleet deliberately cannot see these (a broken fleet can't
triage its own substrate), so anything firing there has exactly one
responder: you. `fleetd-silent` also fires ~35m after a STOP flag you
forgot to remove — that's a feature.

## 2. The routing ritual (when you have 10 minutes)

**Go to your routing inbox — issues the fleet assessed as machine-fixable:**

- All repos at once: <https://github.com/search?q=owner%3Achipi+is%3Aissue+is%3Aopen+label%3A%22triage-fleet%2Factionable%22>
- Everything the fleet filed: <https://github.com/search?q=owner%3Achipi+is%3Aissue+is%3Aopen+label%3A%22triage-fleet%2Ffiled%22>
- Escalations awaiting you: <https://github.com/search?q=owner%3Achipi+is%3Aissue+is%3Aopen+label%3A%22triage-fleet%2Fescalated%22>

On any fleet-filed issue, your four "buttons" (all native GitHub actions —
the fleet reads them back):

| you do | it means | what happens |
|---|---|---|
| add label `triage-fleet/routed:bugfix` | dispatch Fleet 1 | chain picks it up (see §3) |
| close the issue | dismissed / not worth it | filing ledger respects it; recurrence <7d reopens, later recurrence files fresh with a back-link |
| comment | answer a question / add context | fleet re-triages with your comment as reporter input |
| add label `triage-fleet/muted` | never bother me with this fingerprint again | permanent silence for that signal |

**Worked example (real, sitting there now):** the Gemini storm is ONE issue
— `chipi/podcast_scraper#1347` — with 7 storm variants threaded as comments.
When B3 (podcast repo support) lands, dispatching that whole incident to
Fleet 1 = one label click on #1347. Until then it's read-only evidence.

**Worked example (mute):** when the browser transient
`TypeError: Importing a module script failed` escalates again, it will
arrive as a GH issue. If you agree it's noise: label `triage-fleet/muted`,
done forever. (It escalated 3× in shadow — this is the designed fix.)

`config-enhancement` issues: do **not** route them — Fleet 1 can't test
config (no failing test to write). They accumulate as the pre-triaged
backlog for Fleet 3. Just read or ignore for now.

## 3. Dispatching Fleet 1 (today: orrery only, manual trigger)

1. On an **orrery** issue: add `triage-fleet/routed:bugfix`.
2. On your Mac:
   ```
   cd ~/Projects/agentic-ai-homelab/fleetd && make chain
   ```
3. Watch or walk away — the chain is bounded (3 kick-backs, $3, 20min/episode).
   Outcomes land back on the issue:
   - **draft PR** on orrery + Claude review comment → your merge/reject is
     the verdict (§4)
   - **`triage-fleet/needs-info` + a question comment** → answer like a
     reporter: what you observed, what "fixed" means. Then re-run `make chain`.
   - **stuck** (budget exhausted) → the chain ledger names the wall; ping
     the agent session with it.

**Writing your own bug tickets** (the "first real bug" path): write it like
a busy maintainer — symptom, where you saw it, what correct looks like.
Do NOT enrich with file paths or acceptance criteria; the loop earns those
mechanically (advisor pins topology 15/15; needs-info extracts acceptance).
Label it `triage-fleet/routed:bugfix` directly — no need to wait for the
triage fleet.

## 4. Judging a draft PR (you are the ground truth now)

Read like a maintainer, not a grader:
- Does the **regression test** actually encode the bug? (repro-first is
  mechanically enforced — a test WILL be in the diff; judge if it's the
  *right* test)
- Is the fix at the cause or papering the symptom?
- Read Claude's review comment — it's comment-only, you decide.
- **Merge** = shipped. **Comment+close PR** = rejected; say why in one line —
  every rejection becomes a fixture for the next config round.

## 5. The weekly ritual (~15 min — the false-dismiss audit)

The one thing no dashboard can verify: were the dismissals RIGHT?

1. `ssh -i ~/.ssh/homelab_mini homelab`
2. `awk -F'\t' '$6=="dismiss"' ~/signal-fleet/results/dispositions.tsv | tail -20 | cut -f1,5,15`
3. For 3–5 of them: open GlitchTip (`https://homelab.tail6d0ed4.ts.net:8445`) and sanity-check
   the fleet's cited evidence. A wrong dismissal = say it in session — it
   becomes a frozen fixture and a prompt/gate fix.
4. Glance "fleetd day spend vs $2 cap" on the dashboard while you're there.
5. **Spend reconciliation (added 2026-08-05, keys per vertical now live):**
   compare three ledgers that must roughly agree — homepage "LLM spend by
   vertical" cards (OpenRouter billing truth, per key), Grafana "LLM
   Gateway" per-key table (LiteLLM metering), and the fleet dashboards'
   self-reported spend. Drift >10% between any pair = an accounting bug
   (this check caught a 4x self-report undercount and is currently chasing
   a gateway-key discrepancy). One glance, three numbers.

## 6. Kill switches & rollback (when something feels wrong)

| lever | command / place | effect |
|---|---|---|
| STOP flag | `ssh homelab touch ~/signal-fleet/STOP` | triage loop pauses next cycle (remove file to resume) |
| stage rollback | `fleetd/deploy/fleetd.json` → `"stage": "shadow"`, then `make deploy` | back to zero external writes |
| binary rollback | `cd fleetd && make rollback` | previous fleetd build |
| budget caps | already armed: $2/day triage, $3/chain bugfix | hard stops, no action needed |
| GH token rotation | GitHub → Settings → Fine-grained tokens; paste new into `~/signal-fleet/fleet.env` + `fleet-gateway.env` on the mini | old token dead everywhere |

## 7. What you deliberately do NOT do

- Don't route `config-enhancement` (Fleet 3 scope, needs its RFC first).
- Don't enrich bug tickets to oracle grade — that blinds the measurement.
- Don't merge a fleet PR you wouldn't merge from a human.
- Don't watch the dashboards more than the rituals need — absorbed
  attention is the metric everything here minimizes.
