# NoData replay — acceptance record for fix #4 (2026-09-30)

**Input.** 30 days of Grafana alert state history: 71 NoData transitions across 16 rules
(`/api/annotations?type=alert`). For each one, VictoriaMetrics was queried at that moment
(`nodata_replay.py`): did the host's `node_load1` still have samples in the last 10 min, and
was the mini's colima forward up?

| class | count | meaning |
|---|---|---|
| METRIC ONLY | 24 | host fine; only that rule's series briefly absent — pure noise |
| FORWARD DOWN | 29 | the mini's colima host↔VM forward broke (08-14, 08-17, 09-03) |
| HOST DARK | 18 | the whole host stopped reporting (mini 09-09 power cut; prod 09-16; DGX wedges) |

**Dead-man coverage of the 47 real-outage episodes** (was the dead-man firing at that moment,
per its own state history):

- **Covered:** 09-03 forward break (`mini-forward-down`); prod dark 09-15/16 (`prod-silent`);
  every DGX wedge on 09-15, 09-16 and 09-18 (`dgx-silent`).
- **Before the rule existed:** 08-14 and 08-17 forward breaks. `mini-forward-down` was added
  2026-08-18, so it covers them from then on.
- **Cannot be covered from the mini:** the mini's own power cut (09-09). Nothing hosted on
  the mini can alert while it is down (RFC-0005 open question 7: an external dead-man).

**Conclusion.** No NoData notification was ever the only signal of an outage that a
dead-man existed for. 24 were noise; the rest duplicated a dead-man alert.

**Change.** `noDataState: OK` on the 9 rules that still used the default, each with a
comment naming its covering dead-man. The 15 `Alerting` rules are the dead-mans themselves
and stay. `test_drift.py::TestNoDataPolicy` now requires every rule to declare
`noDataState`, and `Alerting` only for dead-man-shaped queries.

**After (replayed):** the 9 rules produce no NoData notifications. Of the 71 historical
transitions, what remains is the 5 from `dgx-gpu-metrics-stale` (a dead-man, intended) and
1 `Normal (NoData)` on a rule already set to OK, which is not a notification. The 13 from
`podcast-pipeline-jobs-failing` / `podcast-enricher-failing` were fixed earlier the same
day (d986d93).
