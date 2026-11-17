# Fleets: moved to flotilla

The agent fleets (triage, bug fixing, remediation, seo, ops) and their docs live in
[flotilla](https://github.com/chipi/flotilla). The code left this repo between 2026-11-08 and 2026-11-16, and its
docs followed on 2026-11-17 (the operator's decision). This repo keeps homelab's own operations: the hosts, the
gateway, the keys, observability.

**Every fleet note, per fleet, across flotilla, this repo and the private fleet-eval-data:**
[flotilla's Fleets index](https://github.com/chipi/flotilla/blob/main/docs/fleets/README.md).

| Was here | Now in flotilla |
|---|---|
| `docs/signal-fleet-guide.md` | [docs/operations/triage.md](https://github.com/chipi/flotilla/blob/main/docs/operations/triage.md) |
| `docs/recipes/signal-fleet-runbook.md` | [docs/operations/triage-runbook.md](https://github.com/chipi/flotilla/blob/main/docs/operations/triage-runbook.md) |
| `docs/fleet-architecture.md` | [docs/history/homelab/fleet-architecture.md](https://github.com/chipi/flotilla/blob/main/docs/history/homelab/fleet-architecture.md) |
| `docs/recipes/fleetd-deploy.md` | [docs/history/homelab/fleetd-deploy.md](https://github.com/chipi/flotilla/blob/main/docs/history/homelab/fleetd-deploy.md) |
| RFC-0002, RFC-0003, RFC-0004, RFC-0005 | [docs/history/homelab/](https://github.com/chipi/flotilla/tree/main/docs/history/homelab) (same names) |
| ADR-0008 | [docs/history/homelab/](https://github.com/chipi/flotilla/tree/main/docs/history/homelab) (same name) |
| `docs/history/0005-bakeoff-matrix-arc.md` | [docs/history/homelab/](https://github.com/chipi/flotilla/tree/main/docs/history/homelab) (same name) |

Their text up to the move is in this repo's git history. The open items stay here for now:
[fleet items](wip/fleet-items.md) (the fleet session's) and [flotilla items](wip/flotilla-items.md) (the flotilla
session's).
