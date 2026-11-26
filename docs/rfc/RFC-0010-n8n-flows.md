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

### A2. RFC-0014 case 1, flotilla answers a question from documents and tasks (2026-11-26)

- **The connector:** Google again, on **one new credential** of the generic type Google OAuth2 API (any name:
  `install-mcp.sh` finds it by type), made by the operator's sign-in in the editor. Its scopes are exactly
  `drive.readonly` and `tasks.readonly`, so it cannot write: the read path's rule (above) that reads have their
  own credentials, separate from the callback flows' write ones. It uses the same OAuth client and Google Cloud
  project as A1; the consent screen needs those two scopes added.
- **The hosts:** none new. Drive and Tasks are `www.googleapis.com`, the token refresh is `oauth2.googleapis.com`;
  both are in `infra/n8n/egress/acl.yaml` since A1.
- **The flows, the read path of the rule (n8n's MCP Server Trigger fronting read-only tools):**
  - `case 1: docs read server (MCP)` (`case1mcpdocs0001`, served at `/mcp/case1-docs`): tools `search {query}` and
    `read {id}`. `search` is Drive's `files.list` on the meeting-notes folder, plus the decisions doc when every word
    of the query is in its name or text. `read` fetches the file's metadata first and refuses unless the folder is
    among its parents or it is the decisions doc, then returns the text (a Doc exported as plain text, a `.txt`
    or `.md` as is), cut at 60,000 characters and saying so;
  - `case 1: tasks read server (MCP)` (`case1mcptasks001`, `/mcp/case1-tasks`): tool `list {}`, the open tasks of
    the follow-ups list;
  - each tool's steps are a sub-workflow (`case1mcpdsearch01`, `case1mcpdread00001`, `case1mcptlist0001`) that the
    tool node calls by id; they have no trigger of their own and are published only because n8n runs no other kind.
  The model gives the one argument; the folder, the doc, the list and every limit are fixed in the flow
  (`flows/gen_mcp_flows.js`, constants at its top). Refusals come back as an MCP tool error.
- **Their single outputs:** none. Both servers only read; the credential could not write if they tried.
- **Who may call them:** a bearer token per server (n8n credentials `case 1 docs MCP (bearer)` and
  `case 1 tasks MCP (bearer)`, the secrets in flotilla's `config/mcp/*.token`). They are on the external
  `mcp` network, beside flotilla's reads proxy. n8n serves its whole port on every network it joins, as on `plumbing`:
  what keeps a caller on `mcp` out of the editor and the signed callback webhooks is n8n's login and those webhooks'
  signatures, so only flotilla's reads proxy and the MCP servers it fronts belong on `mcp`.
- **Shadows never call them** (the rule above): a read creates a saved execution. These flows save no data of a
  successful sub-run, but n8n still keeps the server run, which holds each tool's answer (a document's text) in
  `n8n-db` until n8n prunes executions (README, "Case 1 read servers (MCP)").

### A3. RFC-0014 case 1, questions asked in Slack and answered in their thread (2026-11-26)

- **The connector:** Slack, on one credential (type Slack API): the bot token of the operator's Slack app,
  created and installed by the operator on 2026-11-26, its allowed domains limited to `slack.com`. Its bot
  scopes are `channels:history` (read `#ask`) and `chat:write` (post the reply); no token rotation, which n8n's
  fixed-token credential cannot follow.
- **The host:** `slack.com` (the Web API, `https://slack.com/api/...`), added to `infra/n8n/egress/acl.yaml`.
- **No inbound:** Slack's Events API needs a public HTTPS address and n8n is tailnet only, so the question flow
  polls `#ask` once a minute (`conversations.history` since the last message it saw) instead of being called.
- **The flows (built and proven on a dev engine 2026-11-26, not yet on the mini):** `case 1: Slack #ask -> flotilla ask hook`
  (`case1slackask001`) polls `conversations.history` each minute with the last message's `ts` kept in the workflow's static
  data, and sends each top-level human message (`{thread, user, text}`, delivery id `slack-<channel>-<ts>`) to flotilla's signed
  hook `ask`, oldest first, advancing only past a message whose call succeeded; its first run sends nothing (no backfill). It is
  imported inactive: publishing it is the operator's explicit step, because it starts the polling. `case 1: flotilla reply ->
  Slack thread` (`case1slackreply1`) is flotilla's signed `plumbing.reply` callback, verified like A1's (signature, 5-minute
  window), idempotent per delivery id, and posts with `chat.postMessage` in the question's thread (`channel` `general` is `#ask`,
  unfurling off). Their single outputs: the hook call, and one message per approved reply. Credentials: the Slack one above, and
  two HMAC ones from flotilla's `ask` and `reply` secret files. Details, install and the proof: `infra/n8n/README.md`, "Case 1 Slack flows".

### A4. A second brain agent in Slack, n8n only: mention the bot, get a sourced answer in the thread (2026-11-26)

- **What:** one n8n workflow, no flotilla. Someone mentions the bot (display name `Second Brain`) in any channel it
  is invited to, including inside a thread; an AI Agent answers from three read-only MCP servers (second-brain's
  library, and A2's docs and tasks), cites every claim, and the answer is posted in the thread. It **replaces
  flotilla case 1's ask flow** (`case1slackask001`, A3), which stays imported and unpublished; A3's reply flow is
  not used by it. A3's poll is not reused: a mention is pushed to the flow, nothing is read on a schedule.
- **The connector:** the same Slack app as A3, with **Socket Mode** (the app opens the connection out to Slack, so no
  public address is needed), an app-level token (`connections:write`), the bot event `app_mention` and the bot scope
  `app_mentions:read`; `channels:history` (A3) is what reading a thread needs (`groups:history` for private channels).
  n8n has no Socket Mode trigger (its Slack Trigger is the Events API, which needs an inbound address), so a **bridge**
  does it: `infra/n8n/sb-bridge/bridge.js`, Node built-ins only, run from n8n's own pinned image (no package, no
  build), one container. It acks every envelope at once, reconnects on `disconnect` or a closed socket, keeps the
  Slack retries of one `event_id` to one call, and POSTs `{channel, ts, thread_ts, user, text, event_id, bot}` to the
  workflow's webhook, signed `HMAC-SHA256(secret, timestamp + "." + body)` in `X-SB-Timestamp` and `X-SB-Signature`
  (the style of flotilla's hooks), 5-minute window. Its log lines carry ids and a status, never text or a token.
- **The hosts and networks:** `*.slack.com` is added to `infra/n8n/egress/acl.yaml` (the socket is
  `wss-primary.slack.com`; `slack.com` has been there since A3). The bridge reaches Slack through the same Smokescreen
  proxy as n8n (Node's `NODE_USE_ENV_PROXY`), and n8n by a new internal network `sbbridge` that only n8n and the bridge
  join. The model and the MCP servers are **not** reached through the proxy (it refuses private addresses): n8n reaches
  them on their own networks, and their host names go into n8n's `NO_PROXY` (`n8n` is there already).
- **The flow** (`second brain: Slack mention -> answer in thread`, `sbaskagent00001`, imported inactive): webhook
  `/webhook/second-brain-mention` (signature and window, 401 otherwise; 200 at once) -> once per mention (channel and
  `ts`, and `event_id`, kept in static data) -> the bot's own `<@BOT>` taken out of the text -> in a thread,
  `conversations.replies` (the newest 20 messages, 6,000 characters) as context -> the Tools Agent (an OpenAI-compatible
  chat model on one n8n credential, three MCP Client Tools with bearer credentials, a system prompt that allows only
  what the tools returned and asks for `[n]` citations and a `Sources:` list) -> a **citation check** in code (every
  listed source must be an id, link or title that a tool returned in that same execution; otherwise the answer is
  replaced by "I could not find a sourced answer." and the execution records why) -> `chat.postMessage` in the thread
  (`[second brain]` label, unfurling off, `<!` sent as `&lt;!`). A model or tool error for one mention is logged and
  answered "I hit an error answering this; try again later." once. Credentials: the Slack one (A3), the model one (an
  OpenAI-compatible base URL and key; LiteLLM on the mini), the bridge's HMAC secret and three bearer tokens (library,
  docs, tasks).
- **Built and proven on a dev engine 2026-11-26, not on the mini:** `infra/n8n/flows/sb-agent-proof/` (second-brain's
  real server over its own fixtures, stubs for docs, tasks and Slack with a Socket Mode server, the real bridge, the
  X3's Ollama as the model). Details, install and the operator's steps: `infra/n8n/README.md`, "Second brain agent
  (n8n only)".

## Not covered

- Which company tools connect first, and the hook's design: flotilla RFC-0014.
- **Which hosts n8n may reach, and the rest of each example's e2e.** The route out exists since
  2026-11-22: an egress proxy like flotilla's (`n8n-egress`, `infra/n8n/egress/`), and n8n has no other.
  Its allowlist is empty on purpose. It grows with the examples (operator, 2026-11-22): as each RFC-0014
  case is built, the hosts its tools need are added, along with the credentials, connectors and flows
  it needs on n8n. Each is a short amendment here naming the case, the connector, its hosts and its
  credential, so the allowlist always matches the cases that run, and nothing is added ahead of one.
- Who may log in to the editor: the owner account only, today.
