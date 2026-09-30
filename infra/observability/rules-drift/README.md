# rules-drift — is Grafana running the rules the repo says?

Grafana loads `backend/grafana/provisioning/alerting/rules.yaml` only on an
alerting-provisioning **reload**. A committed rule change is not live until then.
On 2026-09-30 two committed changes had silently never loaded for 12 days. A
fixed rule kept firing a false critical alert (#58), and four delivery rules
never ran.

`drift.py` compares `rules.yaml` with Grafana's provisioned rules, per uid:

| kind | meaning |
|---|---|
| `missing` | in the repo, not live — a committed rule that never took effect |
| `extra` | live, not in the repo — a rule nobody can review |
| `changed` | both, but the behaviour differs: queries, conditions, `for`, `noDataState`, title or labels |

Annotations are ignored on purpose, and durations compare as seconds (`0s` = `0m`).

## Where it runs

The mini-metrics loop (`infra/mini-metrics/push.sh`) runs it every ~15 min and
pushes `grafana_alert_rules_drift{kind}`, `grafana_alert_rules_drift_check_ok`,
and `grafana_alert_rules_drift_last_check_timestamp` (only when the check ran).
Two `meta` alerts in `rules.yaml` read them:

- `grafana-alert-rules-drift` — drift present for 30 min.
- `grafana-alert-rules-drift-check-stale` — the check has not run for 1 h (dead-man).

## By hand

```sh
# against live Grafana (on the mini)
python3 infra/observability/rules-drift/drift.py \
  --repo infra/observability/backend/grafana/provisioning/alerting/rules.yaml \
  --grafana http://localhost:3000 --env infra/observability/backend/.env
# fix drift: reload provisioning
curl -u admin:$GRAFANA_ADMIN_PASSWORD -X POST http://localhost:3000/api/admin/provisioning/alerting/reload
```

Exit code: 0 = no drift, 1 = drift, 2 = could not check. No PyYAML is needed.
On the mini's `/usr/bin/python3` it falls back to macOS's system Ruby YAML parser.

## Tests

`python3 test_drift.py` replays the real 2026-09-30 state (`fixtures/`). Before
the reload, the repo against live Grafana reports exactly the five real drifts
(4 missing delivery rules, the changed #58 rule). After it, it reports zero.
