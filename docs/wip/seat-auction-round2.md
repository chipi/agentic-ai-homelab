# Seat auction — round 2 plan (worker floor + advisor challengers)

2026-07-26. The workforce principle: every seat goes to the **cheapest
model that passes that seat's bar**, measured on the frozen instruments —
never assumed from benchmarks. Round 1 results (BAKEOFF §6.3 3k/3l):
worker seat — flash ties v4-pro on every decisive cell; advisor seat —
glm-5.2 holds (only model 3/3 on the decoy fixture), kimi disqualified on
latency (27-min consultations).

## Worker seat — find the floor

Bar, in order (a sieve — later stages only for survivors):

1. **Gate row** — 5 fix-ready bugs, single episode each (~$0.30/model).
   Kills models that can't hold an agentic tool loop. <5/5 = out.
2. **Decisive row** — 5 cells × k=3 (the instrument flash tied v4-pro on).
3. **Closed-loop chain** — fly-physics-L0 k=3 (advisor pin-following +
   reporter integration; flash's own confirmation running 2026-07-26).

Scoring: **$/chain, not $/token** — a cheap model that grinds 40 turns
costs more than flash bailing in 8. runs.tsv/flow.tsv capture this.

| candidate | in/out $/M | note |
|---|---|---|
| `z-ai/glm-4.7-flash` | 0.06/0.40 | cheapest in catalog; z-ai already enabled — pilot, runnable NOW |
| `qwen/qwen3-coder-30b-a3b-instruct` | 0.07/0.27 | coder-tuned; most likely "cheapest that works" |
| `qwen/qwen3.5-flash-02-23` | 0.07/0.26 | Qwen flash tier, 1M ctx |
| `bytedance-seed/seed-2.0-mini` | 0.10/0.40 | vendor-diversity probe |
| `qwen/qwen3-coder-next` | 0.11/0.80 | fallback if coder-30b fails the gate row |

DeepSeek has no rung below v4-flash (v3.2 is older AND pricier) — the
floor hunt is Qwen/z-ai/ByteDance territory.

## Advisor seat — challenge glm-5.2

Round-1 finding: the seat is TWO skills. glm profile = decoy **3/3** /
confirm **1/3** (it invents on must-not-invent). flash is the mirror
(2/3 / 3/3). Challenger bar: **≥3/3 decoy AND ≥2/3 confirm**, wall
<10 min/consult. Instrument: `advisor_eval.sh 3 <models>` on the 3
frozen fixtures (~$0.5–1/model). If nobody clears both bars → don't
upgrade the model, SPLIT the consultation (confirm-mode vs redirect-mode
prompts); the acceptance transition already removes the worst confirm
failures from the loop side.

| candidate | in/out $/M | note |
|---|---|---|
| `qwen/qwen3.7-plus` | 0.32/1.28 | strongest untested cheap-reasoner family; half glm's price |
| `minimax/minimax-m3` | 0.30/1.20 | current MiniMax reasoning line, 1M ctx |
| `stepfun/step-3.7-flash` | 0.20/1.15 | wildcard — a $0.20 advisor would be a finding |
| `qwen/qwen3-max-thinking` | 0.78/3.90 | premium probe — "does the seat want MORE reasoning than glm?" |

Skipped deliberately: kimi-k2-thinking (latency), glm-5.1/5-turbo
(older/pricier siblings), kimi-k3/qwen3.7-max (wrong price direction for
a $0.15/consult seat).

## Operator enablement — consolidated (OpenRouter dashboard)

Providers to allow (privacy/ZDR allowlist; deepseek, z-ai, moonshot
already work):

- [ ] **Alibaba / Qwen** (worker + advisor candidates)
- [ ] **MiniMax** (advisor)
- [ ] **StepFun** (advisor)
- [ ] **ByteDance Seed** (worker)

Monthly org cap: raised 2026-07-26 after the $50 cap killed the round-1
sweep mid-grid (403 = instant empty completions — dead-call guards now
everywhere). Round-2 budget ≈ $8–15 total.

## Same iteration: per-vertical key split

Operator decision 2026-07-26: spend attribution per vertical, one
OpenRouter key each — **rewire AFTER the in-flight confirmations
finish** so measurements stay on one key.

- [ ] **pi key** → `~/.pi/agent/auth.json` (replaces the shared key; all
      lab bake-off spend)
- [ ] **opencode key** → opencode auth config (`opencode auth login` /
      its auth.json) — opencode column spend
- [ ] **fleet key** → mini, fleetd env (`fleet.env`) — production chain
      spend (the key operator created at deploy time, never wired)

Operator holds/creates the keys; wiring is a per-file paste + one
smoke-call each. LiteLLM virtual keys stay as-is (gateway layer,
orthogonal).

## Order of execution

1. (running) flash-as-worker closed-loop k=3 — the promotion gate for
   "pin worker seat to flash, retire v4-pro from the loop"
2. glm-4.7-flash gate row (no enablement needed) — floor-hunt pilot
3. Operator enables providers → advisor round (4 models × 3 fixtures × k=3)
   + worker sieve (gate rows, then decisive for survivors)
4. Key split rewire + smoke tests (closes the measurement window)
5. Results → BAKEOFF §6.3 3m; seat table updated; losers documented
