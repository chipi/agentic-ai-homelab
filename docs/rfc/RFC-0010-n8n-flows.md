# RFC-0010 — What n8n is for on the homelab, and which flows to build

**Status:** Accepted (operator, 2026-11-22). Reviewed by the flotilla session the same day: no competition with
flotilla; its changes are in (the rule's wording, the two allowed ways to write, the read path, shadows,
the smoke hook, the route out).
**Relates to:** [`infra/n8n/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/n8n) (the
service, set up 2026-11-22), flotilla
[RFC-0014](https://github.com/chipi/flotilla/blob/main/docs/rfc/RFC-0014-visual-plane-and-mashups.md)
(§4.0 the three layers, §4.7 the hook and `plumbing.call`), the Hub
([`infra/homelab-home/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/homelab-home):
`status-job.js`, `briefing-job.js`), [RFC-0008](RFC-0008-x3-local-assistant.md) (the morning briefing),
the Grafana alert rules.

## Motivation

n8n now runs on the mini as the plumbing layer of flotilla RFC-0014: the company's tools (records) on
one side, flotilla (decisions) on the other, n8n moving data between them. It has no workflows. On
2026-11-22 the homelab session suggested four flows for things the homelab already runs. This RFC
checks each against what already does the job, so that n8n does not become a second hub, a second
alerting path or a second triage fleet.

## The rule this RFC proposes

1. **n8n moves data; it decides nothing.** In RFC-0014 §4.0's words: a deterministic step (route,
   copy, format, notify) is the plumbing's; a step that needs judgement or has consequences (decide,
   answer, draft, file, change something) is a flotilla routine, which has the ledger, the caps and the
   review. So an n8n flow may route, filter by a fixed rule, reshape a payload and send a fixed
   notification ("a file landed"), nothing more.
2. **An n8n flow writes to a company tool in one of two ways only:**
   - (a) as the body of a flotilla callback (`plumbing.call`): triggered only by a signed call from
     flotillad, which the flow verifies (HMAC over timestamp and body, a five-minute window), and it
     writes exactly the declared payload, no more;
   - (b) as a deterministic copy or notification, named in this RFC as an amendment with its single
     output.

   Nothing a model produced reaches a company tool except through (a), so it is in flotilla's ledger
   and approved first. Any other flow built in the editor that writes is not allowed.
3. **n8n is for tools that have no other path in.** Where the homelab already reads a system with code
   it owns (the Hub's jobs, alloy, Grafana's rules), that code stays the one path; n8n does not read
   the same source a second time.
4. **One owner per output.** Every place the operator looks (the Hub, the morning push, Slack, GitHub
   issues) has exactly one producer. A flow that would write to one of them is a change to that
   producer, decided there.

## The four suggested flows, checked

| Flow (as suggested) | What already does it | Verdict |
|---|---|---|
| A. Grafana alerts into a daily digest of what fired and resolved, to the Hub or email | The morning briefing (`briefing-job.js`, 07:00): Grafana's alert history, GlitchTip and the Hub's status, written to `www/briefing/` and pushed to the phone | **Drop.** A second digest of the same alerts. A change to the digest is a change to the briefing |
| B. New GlitchTip prod issues enriched with the deploy and the log lines, then a notification | flotilla's triage fleet (signal-fleet) reads GlitchTip, correlates and files; the briefing lists new issues | **Drop.** This is a triage decision, and flotilla's. Enrichment, if wanted, is a triage routine's step |
| C. Morning check that the nightly backup and the off-mini upload succeeded, as a Hub tile | Alert `homelab-backup-offsite-stale` (30 h); the backup job's `ops_event/v1` backup events, which the Hub's timeline already reads | **Drop as an n8n flow.** If a tile is wanted, it is a few lines in `hub-status.js` over the events it already reads |
| D. Hub tiles (DGX mode, LiteLLM spend against caps, Umami visitors) read on a schedule | `status-job.js` every 5 minutes: spend, capacity, Umami numbers; the DGX's mode is read by the Hub's DGX column | **Drop.** The Hub's status job is the one reader; a missing tile is added there |

All four duplicate code that exists. The suggestions were made without checking the Hub's jobs first.

## What n8n is for here, then

- **RFC-0014's plumbing, first.** Which tools, and when, is flotilla's and the operator's decision,
  case by case (RFC-0014 §4.7). The homelab's part is the service: network, credentials, backup,
  health. Three kinds of flow:
  - **hook flows:** a company tool's events into flotilla's signed hook;
  - **callback flows:** flotilla's `plumbing.call` out to a tool (rule 2a);
  - **the read path** (RFC-0014 §4.8): n8n's MCP server trigger fronting read-only tools (the wiki,
    the documents, the tracker) for flotilla routines. Its credentials to those tools are read-only
    and separate from the callback flows' write credentials.
- **Shadows never call n8n.** A read through n8n creates a saved execution, which is a write, so
  flotilla serves shadow runs the recorded reads instead (§4.8). Nothing routes a shadow to n8n.
- **One homelab flow, as the smoke test of that path:** when flotilla's hook exists, a single
  workflow that sends a fixed, labelled test event on demand (a manual trigger, no schedule) to
  flotilla's dedicated **`smoke`** hook, whose case kind closes itself on arrival, and checks the
  answer. Never a real hook (`meeting`, `ask`): every accepted call there opens a real case. It proves
  the network (`plumbing`), the signing secret and the hook end to end, the way `telemetry-probe`
  proves a telemetry path. It writes nothing anywhere else.
- **Later, only through this RFC's rule:** a tool with no other path in (a SaaS without an API the Hub
  could poll, an inbound webhook from a service on the tailnet). Each one is a short amendment here,
  naming its single output and why no existing producer covers it.

## Boundary with flotilla: the review (2026-11-22)

The flotilla session found nothing here that competes with flotilla:

1. The judgement line: agreed, with the wording now in rule 1 (routing and fixed notifications are
   the plumbing's).
2. Writes from the editor: changed to rule 2. The callbacks are themselves n8n flows that write, so the
   rule names the two allowed ways rather than barring writes.
3. Reads of the Hub's sources: none planned. Triage reads GlitchTip and the alerts directly, as today;
   RFC-0014's live reads are the company's tools, not the Hub's. The Hub stays the producer of what the
   operator sees.

Added from the review: the read path, shadows, the `smoke` hook, and the route out below.

## Amendments

### A1. RFC-0014 case 3, a meeting into decisions and follow-ups (operator's go, 2026-11-23)

- **The connector:** Google, as the operator's own Google account, through three n8n credentials:
  `google drive (homelab)`, `google docs (homelab)` and `google tasks (homelab)`. All three use one
  OAuth client in the Google Cloud project `homelab-n8n`; the operator did the consent in the editor.
- **The hosts** (`infra/n8n/egress/acl.yaml`):
  - `oauth2.googleapis.com` for the token exchange;
  - `www.googleapis.com` for Drive and Tasks;
  - `docs.googleapis.com` for Docs.

  The first runs' proxy log shows whether n8n's Google nodes call any other host.
- **The flows, each a flow allowed by rule 2:**
  - a Drive trigger on the folder `homelab n8n meeting notes` sends a new or changed file's text to
    flotilla's `meeting` hook (a hook flow);
  - `plumbing.create_tasks` adds tasks to the Tasks list `homelab n8n follow-ups` (a callback flow, 2a);
  - `plumbing.post_decisions` appends to the Doc `homelab n8n decisions` (a callback flow, 2a).
- **Their single outputs:** the Tasks list and the Doc. The Drive folder is read only.
- **The secrets:** the `meeting` hook's secret and the two callback secrets are n8n credentials
  (option a, as the smoke flow's).

## Not covered

- Which company tools connect first, and the hook's design: flotilla RFC-0014.
- **Which hosts n8n may reach, and the rest of each example's e2e.** The route out exists since
  2026-11-22: an egress proxy like flotilla's (`n8n-egress`, `infra/n8n/egress/`), and n8n has no other.
  Its allowlist is empty on purpose. It grows with the examples (operator, 2026-11-22): as each RFC-0014
  case is built, the hosts its tools need are added, along with the credentials, connectors and flows
  it needs on n8n. Each is a short amendment here naming the case, the connector, its hosts and its
  credential, so the allowlist always matches the cases that run, and nothing is added ahead of one.
- Who may log in to the editor: the owner account only, today.
