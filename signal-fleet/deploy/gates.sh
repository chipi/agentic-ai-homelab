#!/usr/bin/env bash
# signal-fleet/deploy/gates.sh — the triage fleet's deploy gates, run over freshly pulled code.
#
# Called by deploy/hooks/gate.d/10-signal-fleet.sh from deploy/mini-deploy.sh, with CHECKOUT, PREV
# and NOW in the environment. Exits non-zero when any gate is red, and mini-deploy.sh then rolls the
# checkout back. The gates are deterministic: no LLM, no network, no cost. (Moved out of the old
# signal-fleet/deploy/deploy.sh unchanged, 2026-11-08.)
set -uo pipefail

CHECKOUT="${CHECKOUT:-${SF_CHECKOUT:-$HOME/agentic-ai-homelab}}"
SF="$CHECKOUT/signal-fleet"
PREV="${PREV:-}"; NOW="${NOW:-}"
say() { printf '%s\n' "$*"; }

[ -f "$SF/mvp/orchestrator.py" ] || { say "FAIL $SF/mvp not found — wrong checkout?"; exit 1; }

cd "$SF/mvp" || { say "FAIL cannot cd to $SF/mvp"; exit 1; }
GATE_HOME="$(mktemp -d)"
ok=1
for g in eval_hardening.py eval_dedup.py eval_filing_replay.py eval_stale_replay.py eval_routing_replay.py eval_triager_failure_replay.py eval_glitchtip_litellm_replay.py eval_recurrence_replay.py eval_open_preference_replay.py eval_duplicate_follow_replay.py eval_identity_replay.py eval_promotion_replay.py eval_oom_edge_replay.py eval_assistant_failover_replay.py eval_inbox_open_replay.py test_units.py test_capture.py test_scrub.py; do
  # eval_filing_replay: the 2026-09-30 duplicate cases must stay comments (#9)
  args=""; [ "$g" = eval_filing_replay.py ] && args="--cases-only"
  # HOME = an empty dir: every live state path is under ~/signal-fleet, so no gate can
  # read the host's ledgers (2026-10-17: a replay passed on a laptop, failed on the mini)
  if HOME="$GATE_HOME" SF_OBSERV_DISABLED=1 python3 "$g" $args >"/tmp/sf-deploy-$g.log" 2>&1; then
    say "PASS $g"
  else
    say "FAIL $g:"; tail -3 "/tmp/sf-deploy-$g.log" | sed 's/^/    /'; ok=0
  fi
done
rm -rf "$GATE_HOME"

# the filing gate (private repo chipi/fleet-eval-data): when filing/stale or what they import changed, replay the
# newest frozen week with $PREV and $NOW; any change in what filing does fails unless SF_FILING_GATE_ACCEPT="<why>".
# Real HOME: it reads ~/signal-fleet/frozen, the deploy log and fleetd.log (read-only).
FILING_GATE="${SF_FILING_GATE:-$HOME/fleet-eval-data/projects/signal-fleet-filing/scripts/filing_gate.py}"
if [ "$ok" -eq 1 ] && [ -f "$FILING_GATE" ]; then
  if SF_CHECKOUT="$CHECKOUT" python3 "$FILING_GATE" "$PREV" "$NOW" >/tmp/sf-deploy-filing_gate.log 2>&1; then
    say "$(tail -1 /tmp/sf-deploy-filing_gate.log)"
  else
    say "FAIL filing_gate (full list: /tmp/sf-deploy-filing_gate.log):"; tail -8 /tmp/sf-deploy-filing_gate.log | sed 's/^/    /'; ok=0
  fi
elif [ "$ok" -eq 1 ]; then
  say "filing gate: NOT RUN (no $FILING_GATE)"
fi

[ "$ok" -eq 1 ]
