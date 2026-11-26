# n8n: the installation's plumbing tool

The layer between the company's tools and flotilla (flotilla
[RFC-0014](https://github.com/chipi/flotilla/blob/main/docs/rfc/RFC-0014-visual-plane-and-mashups.md) §4.0, §4.7):
it calls flotilla through flotilla's signed webhook, and flotilla calls it back through signed HTTP. Set up on
2026-11-22 at the operator's go. One workflow, the smoke flow below, and **no connectors**: the operator adds those case by case.

**Licence.** n8n is under the Sustainable Use License: the installation's own internal use is fine; it is never
offered to others as a service.

## Stack

- `n8n` (`docker.n8n.io/n8nio/n8n:2.48.7`, pinned) and `n8n-db` (`postgres:17-alpine`, its own).
- Networks, all internal, nothing published on the host:
  - `plumbing`: n8n, flotillad (flotilla's compose joins it as an external network) and alloy-homelab
    (scrapes `/metrics`).
  - `n8n_db`: n8n and its Postgres only.
  - `mcp` (external, created before this stack): n8n and flotilla's reads proxy, for the case 1 MCP servers (below).
  - `n8n_ui`: n8n and caddy only: the editor at **https://n8n.tail6d0ed4.ts.net** (tailnet only; caddy answers 404 for webhook paths there). Deploy n8n before `infra/reverse-proxy`.
- **Base URL for webhooks, as flotillad's container sees it:** `http://n8n:5678/` (webhooks under
  `/webhook/<path>`, test webhooks under `/webhook-test/<path>`).
- **The route out: only through `n8n-egress`** (Smokescreen, flotilla's build pinned by digest; added 2026-11-22).
  n8n sets `HTTP(S)_PROXY=http://egress:4750` (`NO_PROXY` keeps flotillad and n8n-db direct) and has no
  route of its own: the proxy alone is on the non-internal network `n8n_out`, n8n and the proxy share
  the internal `n8n_egress`.
  - **The allowlist** is [`egress/acl.yaml`](egress/acl.yaml): every other host is refused (407) and logged.
    Since 2026-11-23 it has Google's hosts for case 3 (RFC-0010 amendment A1): `oauth2.googleapis.com`,
    `www.googleapis.com`, `docs.googleapis.com`. A connector's hosts are added there with its RFC-0010
    amendment, then
    `docker compose up -d --force-recreate egress` (n8n keeps running; a plain `up -d` keeps the old proxy, which reads the list only at start, 2026-11-23).
  - **Private addresses are refused** even when listed (no `allow_ranges` in
    [`egress/smokescreen.yaml`](egress/smokescreen.yaml)): the proxy never reaches the LAN, the tailnet or
    the host.
  - n8n itself calls `api.n8n.io` at start even with diagnostics, version checks and templates off; the
    proxy refuses it and logs one line per start.
  - Proven on the X3 on 2026-11-22 with this image and config: a direct `fetch` from n8n failed
    (`EAI_AGAIN`); an HTTP Request node got 407 for an unlisted host, 200 for `example.com` once listed in
    a test ACL, and 407 "Deny: Private Range" for `192.168.1.1` even when listed.

## Run (on the mini, in this checkout)

```sh
cp .env.example .env && chmod 600 .env    # then replace each <generate: ...> with its output
docker compose up -d
docker inspect -f '{{.State.Health.Status}}' n8n   # healthy
bash owner-setup.sh                          # once: the owner login, into ~/n8n/owner.env
```

## Credentials (values never printed)

| What | Where (mini, mode 600) | Variables |
|---|---|---|
| Database password, encryption key | `~/agentic-ai-homelab/infra/n8n/.env` | `N8N_DB_PASSWORD`, `N8N_ENCRYPTION_KEY` |
| Owner login | `~/n8n/owner.env` | `N8N_OWNER_EMAIL`, `N8N_OWNER_PASSWORD` |

`N8N_ENCRYPTION_KEY` encrypts every credential n8n stores; without it a restored database's credentials are
unreadable. The stacks' `.env` files are not in the backups: keep a copy in the password manager.

## Observability and backup

- **Logs:** alloy-homelab ships the containers' stdout like every other container (`service="n8n"`;
  the proxy's decisions as `msg="CANONICAL-PROXY-DECISION"` lines from `n8n-egress`, with `allow`,
  `requested_host` and `decision_reason`).
- **Egress alerts** (Grafana, group `n8n-egress` in `rules.yaml`, 2026-11-23), all on the proxy's log lines:
  - `n8n-egress-refused`: a host outside `egress/acl.yaml` was refused in the last 30 min. `api.n8n.io` is
    left out: n8n calls it a few times a day with its four phone-home settings off (which feature, not
    found) and it is refused as intended.
  - `n8n-egress-errors`: more than 3 allowed connections failed in 30 min (Google unreachable, proxy broken).
  - `n8n-egress-silent`: no connection in 30 min. The case 3 Drive trigger polls every minute, so this means
    the proxy, n8n or the trigger stopped. While that flow is deliberately off, pause this rule.
- **Hub:** the Automation tab's n8n section has an "Egress 7d" card (allowed, refused, failed, top hosts, the
  last refused host, connections per day).
- **Health:** the container healthcheck (`/healthz`), and alloy scrapes `n8n:5678/metrics` (job `n8n`).
  The generic alert `infra-target-down` (warning) fires when `up{job="n8n"}` is 0 for 5 minutes; a
  missing container scrapes as 0 too.
- **Backup:** `n8n-db` is in the nightly `pg_dump` of `infra/backup/dump-observability-dbs.sh`, and so in the
  encrypted off-mini copy.

## Upgrade

n8n migrates its database on start. Bump the tag here, take a dump first
(`docker exec n8n-db pg_dump -U n8n n8n | gzip > ~/db-backups/n8n-db-pre-upgrade.sql.gz`), then
`docker compose up -d` and check health. Undo: the old tag plus that dump restored into `n8n-db`.

## Not covered

- The editor is reachable by every tailnet device; n8n's own login (the owner) is what protects it.
- `plumbing.call` (flotilla's side) is not built; nothing calls n8n yet.
- On 2026-11-22 the owner setup was found undone (login 401, `isInstanceOwnerSetUp=false`, the user row
  never updated) although deploy2's `owner-setup.sh` had printed "owner created" and login 200 that
  morning. Re-running it at 14:08Z stuck (checked in the database). Cause unknown; if the login fails
  again, compare `select "updatedAt" from "user"` with the time of the last deploy.

## The smoke flow (flotilla's `smoke` hook)

Workflow **"flotilla smoke hook (manual)"** (`flotillasmoke001`), manual trigger only (RFC-0010: the one
homelab flow). It proves `plumbing`, the signing secret and flotilla's hook end to end:

1. a Code node builds the timestamp, the delivery (`n8n-smoke-<execution id>-<ms>`) and the body
   `{"probe":"n8n-smoke-<execution id>"}` once, as a string;
2. a Crypto node (v2, HMAC-SHA256, hex) signs `timestamp.delivery.body` with the credential
   **"flotilla smoke hook (HMAC)"** (type `crypto`; the secret from `~/flotilla/config/hooks/smoke.secret`,
   whitespace stripped, put in through stdin and never printed);
3. two HTTP Request nodes POST those exact bytes to `http://flotillad:8488/hooks/smoke` with the
   `X-Flotilla-*` headers: the first must answer 202 (a case opened and closed `resolved_itself`), the
   re-send of the same delivery 200 (a replay);
4. a Code node fails the run on anything else.

Run it from the editor, or on the mini:
`docker exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n n8n execute --id=flotillasmoke001 --rawOutput` (the
other port keeps the one-off process off the running instance's task broker). First run: 2026-11-22,
202 then 200.
- The proxy has no metrics scrape and no alert of its own: a dead `n8n-egress` shows only as failing
  connector calls in n8n's executions.
- The proxy filters by host name, not by path or tool: a listed host is reachable in full.

## Case 3 flows (flotilla RFC-0014 case 3; RFC-0010 amendment A1)

[`flows/`](flows/) holds the three workflows, generated by `flows/gen_flows.js` (the Google ids and credential
ids are in its first lines):

| Workflow | id | State | What it does |
|---|---|---|---|
| case 3: Drive meeting notes -> flotilla meeting hook | `case3meetinghook` | on since 2026-11-23 (flotilla sha-ff08c18) | polls the Drive folder `homelab n8n meeting notes` each minute; a new or changed Doc, .txt or .md is sent signed to `http://flotillad:8488/hooks/meeting` (delivery id = file id + modified time) |
| case 3: flotilla create_tasks -> Google Tasks | `case3createtasks` | published | `POST /webhook/flotilla-create-tasks`: checks flotilla's signature and timestamp, adds the items to the Tasks list `homelab n8n follow-ups`; the delivery id in each task's notes makes a re-send create nothing |
| case 3: flotilla post_decisions -> Google Doc | `case3postdecisio` | published | `POST /webhook/flotilla-post-decisions`: the same checks, appends the text to the Doc `homelab n8n decisions`; the delivery id line makes a re-send append nothing |

Credentials: the three Google OAuth2 ones (the operator's sign-in, 2026-11-23) and three `crypto` (HMAC) ones
from flotilla's secret files (`~/flotilla/config/hooks/meeting.secret`,
`~/flotilla/config/plumbing/{create_tasks,post_decisions}.secret`), imported through stdin by
`flows/install.sh`. Re-run it after changing a flow (it skips existing credentials and overwrites the workflows).

`flows/test_callbacks.sh` signs calls as flotilla does: status before, a bad signature (401), a stale
timestamp (401), send, a re-send (same ref, nothing new), status after. 2026-11-23: 16 of 16 PASS, leaving
one `[test]` task and one `[test]` Doc line.

## Case 1 read servers (MCP) (flotilla RFC-0014 case 1; RFC-0010 amendment A2)

Two read-only MCP servers for flotilla's `knowledge/answer` station (its reads `docs` and `tasks`), built on n8n's
**MCP Server Trigger** and flotilla's own client. Built and proven on a dev engine 2026-11-26; **not yet installed on the mini**.

| Server | Workflow (id) | URL, as flotillad's network sees it | Tools | Bearer credential |
|---|---|---|---|---|
| `docs` | `case 1: docs read server (MCP)` (`case1mcpdocs0001`) | `http://n8n:5678/mcp/case1-docs` | `search {query}`, `read {id}` | `case 1 docs MCP (bearer)` (`c1mcpdocstoken01`) |
| `tasks` | `case 1: tasks read server (MCP)` (`case1mcptasks001`) | `http://n8n:5678/mcp/case1-tasks` | `list {}` | `case 1 tasks MCP (bearer)` (`c1mcptaskstoken1`) |

- **Transport and URL (checked in the 2.48.7 image):** the trigger (node version 2) speaks **streamable HTTP and the
  legacy SSE** at the one path `{WEBHOOK_URL}mcp/<path>` (`GET` = SSE stream, `POST` = messages, `DELETE` = end the
  session). Version 1 of the node used `/sse` and `/messages` under the path; the flows use version 2. A `POST`
  answers `text/event-stream` with one `event: message` (flotilla's `McpClient` reads that), protocol `2025-06-18`,
  session in `Mcp-Session-Id`, kept in n8n's memory: a restart loses it and the client starts a new one on the 404.
  A wrong or missing bearer token is **403**. The server's name is `MCP_Server_Trigger`.
- **Why sub-workflows:** a `Call n8n Workflow Tool` node takes the model's argument names (`query`, `id`) from
  `$fromAI` only when it calls a workflow **by id**; with the workflow inlined, n8n drops those mappings and the tool
  gets one argument called `input` (seen in 2.48.7). So each tool is a small sub-workflow
  (`case1mcpdsearch01`, `case1mcpdread00001`, `case1mcptlist0001`, no trigger of their own) that n8n runs only when it is
  **published**; `install-mcp.sh` publishes them. `tasks.list` shows an optional `input` argument that nothing reads.
- **What they read (constants at the top of `flows/gen_mcp_flows.js`, the case 3 ids; change them there and re-run
  `node flows/gen_mcp_flows.js` and `install-mcp.sh`):** the Drive folder `FOLDER` (meeting notes), the Doc `DOC`
  (decisions) and the Tasks list `LIST` (follow-ups).
  - `search`: Drive `files.list`, `'FOLDER' in parents and fullText contains '<query>' and trashed = false`, at most
    10; the query is cut at 200 characters, control characters out, `\` and `'` escaped. The decisions doc is added
    when every word of the query is in its name or text (Drive cannot filter by id, so the flow reads the doc).
    Each result carries `id`, `name`, `modified` and `webViewLink`.
  - `read`: `files.get` for the metadata first, **refused** unless `FOLDER` is among the parents or the id is `DOC`
    (also refused: trashed, or not a Doc, `.txt` or `.md`); then the text (`export?mimeType=text/plain`, or
    `alt=media`), cut at 60,000 characters with a visible `[cut: ...]` line. The answer starts `title`, `webViewLink`.
    The id must be a Drive id (`[A-Za-z0-9_-]`, it goes into a URL path).
  - `list`: open tasks of `LIST` (first 100), each `title`, `due`, `notes` (cut at 300) and `ref`: the task's
    `webViewLink`, else its id.
  - A refusal is an MCP tool error (`isError`, text `There was an error: "docs.read: refused: ..."`), not a protocol error.
  - Results are JSON text (n8n serialises the sub-workflow's items), links and ids as Google gave them.
- **Credentials.** Two bearer ones, made by `install-mcp.sh` from flotilla's token files; one Google one, **made by
  the operator's sign-in in the editor** (`install-mcp.sh` looks its id up):
  1. Editor, Credentials, Create, **Google OAuth2 API** (the generic type, not Drive or Tasks).
  2. Any name: `install-mcp.sh` takes the one Google OAuth2 API credential (with several, set
     `GOOGLE_RO_CRED_NAME`). Client ID and secret: the OAuth client of case 3
     (Google Cloud project `homelab-n8n`); its redirect URI is the one case 3's credentials already use.
  3. **Scope**, the whole field, space-separated: `https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/tasks.readonly`. Nothing else: this is what makes the servers unable to write.
  4. Optional hardening: Allowed HTTP Request Domains, Specific Domains, `www.googleapis.com`.
  5. **Sign in with Google** and consent as the operator. In Google Cloud, OAuth consent screen (Data access), add the same
     two scopes to the app first. If the app's status is Testing, Google expires its refresh tokens after 7 days:
     set it to In production (internal use) or sign in again each week.
- **Secrets, on the mini (values never printed):**
  `umask 077; mkdir -p ~/flotilla/config/mcp; openssl rand -hex 32 > ~/flotilla/config/mcp/docs.token; openssl rand -hex 32 > ~/flotilla/config/mcp/tasks.token`.
  They are the same files flotilla's reads worker mounts (`config/mcp/<server>.token`).
- **Network.** n8n joins the **external** network `mcp` (`docker-compose.yml`; this stack does not create it). It must
  exist first (`docker network inspect mcp`), or `docker compose up -d` fails; the run recreates `n8n` (about a minute
  down, saved sessions lost). The network carries n8n's whole port, as `plumbing` does: the editor login and the
  callback signatures are what protect those, so only flotilla's reads proxy belongs on `mcp`.
  Flotilla side (its `deploy/compose/README.md`, "The reads worker"): in `config/worker-reads.env`
  `ROUTINE_MCP_DOCS_URL=http://n8n:5678/mcp/case1-docs`, `ROUTINE_MCP_DOCS_TOKEN_FILE=/run/flotilla/mcp-docs.token`, and the
  same two for `TASKS` (`.../mcp/case1-tasks`); `n8n` in `config/egress-reads-acl.yaml`; the `mcp` network's range in
  `allow_ranges`.
- **Egress.** No new host: Drive and Tasks are `www.googleapis.com`, the token refresh `oauth2.googleapis.com`, both
  listed since case 3.
- **Install on the mini** (after the credential, the secrets and the network): from a copy of `flows/`,
  `bash install-mcp.sh`. It stops without the Google credential, imports the two bearer credentials through stdin
  (skips existing ones), puts the Google credential's id into the two files, imports the five workflows (overwriting)
  and publishes them. Re-run it after changing a flow.
- **Test** (reads only; writes nothing anywhere): `flows/test_mcp.py` drives both servers with flotilla's
  `runtime/mcp_client.py`, from a container on `mcp` since n8n publishes nothing:
  ```sh
  docker run --rm --network mcp -v ~/flotilla/config/mcp:/t:ro -v <flotilla checkout>/runtime:/rt:ro \
    -v "$PWD/flows/test_mcp.py":/test_mcp.py:ro -e PYTHONPATH=/rt \
    -e MCP_DOCS_URL=http://n8n:5678/mcp/case1-docs -e MCP_DOCS_TOKEN_FILE=/t/docs.token \
    -e MCP_TASKS_URL=http://n8n:5678/mcp/case1-tasks -e MCP_TASKS_TOKEN_FILE=/t/tasks.token \
    -e TEST_QUERY=<a word the folder has> -e OUTSIDE_ID=<a Drive id outside the folder> python:3.12-slim python /test_mcp.py
  ```
  It checks the tool list, a search with links, a read, the two refusals, a wrong and a missing token, and
  `tasks.list`; ends `N of M PASS`.
- **The proof, on a dev engine, never the mini:** `FLOTILLA_RUNTIME=<flotilla checkout>/runtime bash flows/mcp-proof/run.sh`
  starts a throwaway compose project (n8n at this pin and a Postgres, plus `stub_google.py`, a stand-in for the Drive and
  Tasks endpoints), generates the flows with `node flows/gen_mcp_flows.js <dir> --base http://stub:8080`, installs them
  with the same `install-mcp.sh`, runs `test_mcp.py` with the fixture checks, and removes the project and its volumes.
  2026-11-26: 27 of 27 PASS.

Not covered (case 1 flows):
- **Real Google.** The stub answers the one query shape the flow sends, so Google's own `fullText` semantics (multi-word
  queries, prefixes, ranking), the scopes, the `drive.readonly` export, shared drives and the token refresh are not
  proven; the credential in the proof is a stand-in with a made-up token. The first real search is the check.
- **Where the text is kept.** A server run's saved execution holds each tool's answer, so a document's text sits in
  `n8n-db` (and its backups) until n8n prunes executions (default 336 h). The sub-workflows save no data of a success.
- **Shadows** (flotilla serves them recorded reads, so none reaches here): not exercised.
- The caps: `search` 10 hits, `list` the first 100 tasks (no paging), `read` 60,000 characters (Drive refuses to export
  a Doc over 10 MB: that is a tool error). The station's own `max_result_chars` (20,000) cuts a long read again.
- A session across an n8n restart (the client's 404 handling is flotilla's, tested there) and concurrent callers.
- That `mcp` exists, and flotilla's reads worker reaching these URLs through its proxy: homelab and flotilla plans, not this stack.

## Case 1 Slack flows (flotilla RFC-0014 case 1; RFC-0010 amendment A3)

Questions asked in Slack `#ask` (channel id `C0CM2K87SR1`, a constant at the top of `flows/gen_slack_flows.js`) reach
flotilla's signed `ask` hook, and an approved answer goes back to the question's thread. n8n has no public address, so
Slack's Events API is not used: the question flow **polls**. Built and proven on a dev engine 2026-11-26; **not yet installed on the mini**.

| Workflow | id | State after install | What it does |
|---|---|---|---|
| `case 1: Slack #ask -> flotilla ask hook` | `case1slackask001` | **inactive** (the operator publishes it) | every minute: `conversations.history` since the last message seen; each top-level human message is sent signed to `http://flotillad:8488/hooks/ask` as `{thread, user, text}` |
| `case 1: flotilla reply -> Slack thread` | `case1slackreply1` | published | `POST /webhook/flotilla-reply` (flotilla's `plumbing.reply` callback): checks the signature and timestamp, posts the text with `chat.postMessage` in the question's thread |

**Question flow, in detail**
- **State** is the last message `ts`, in the workflow's static data. The first run (no state) records the newest message's ts
  (or now) and sends nothing: old history is never backfilled. The state survives a re-import of the workflow (checked)
  and a stop: a message posted while the flow is inactive is read when it is next activated, one posted before the very
  first run never is.
- **What counts as a question:** a message with no `subtype`, no `bot_id`, a `user`, non-empty text, and no `thread_ts` or
  `thread_ts == ts`. Bots, thread replies, joins, edits and file shares (a `file_share` subtype) are ignored.
- **The call:** body `{"thread": "<ts>", "user": "<user id>", "text": "<text, cut at 2000 characters>"}`, delivery id
  `slack-C0CM2K87SR1-<ts>` (so a re-post is a replay, 200, on flotilla's side), signed with the credential
  `flotilla ask hook (HMAC)` as case 3's meeting flow does. 202 and 200 are success.
- **Order and failure:** messages go oldest first, one at a time. The stored ts moves past a message only after its call
  succeeded, and the first failure (a 5xx, a 401, a network error) fails the run: the message is sent again next minute.
  Flotilla refusing a message for itself (400, 413, 422: a body over its `max_body`, which non-ASCII text of 2000 characters
  can exceed) is not retried for ever: the flow moves past it and the **next** run fails once, naming it.
- **Paging:** Slack returns the newest messages first, so a gap would open if only the first page were read. The history
  call follows `next_cursor` (50 per page, at most 10 pages) before anything is sent; a longer backlog fails the run and advances nothing.
- **Slack errors:** an `ok: false` answer (a revoked token, a missing scope) fails the run with Slack's `error`, state unchanged.
  Failed runs show in the editor's Executions.

**Reply flow, in detail**
- The request is what `plumbing/call.py` sends: `{mode: send|status, action: "plumbing.reply", case_id, plan_hash, params}`;
  `params` are `channel` (only `general`, mapped to `C0CM2K87SR1`; anything else is 400), `thread` (a Slack ts,
  `^[0-9]{1,20}\.[0-9]{1,10}$`) and `text` (1 to 3000 characters). The post is `chat.postMessage` with `channel`, `thread_ts`,
  `text`, `unfurl_links: false`, `unfurl_media: false`. A bad signature or a timestamp more than 5 minutes off is 401.
- **Idempotence** is per delivery id (flotilla's `plan-<hash>`): after Slack accepts a post, the delivery id and its ref
  (`Slack #ask thread <thread>, reply <ts>`) are kept in the flow's static data (the newest 1000). A re-send answers the same
  ref and posts nothing; `status` answers `{done: true, ref}` for a delivery in that store, else `{done: false}`, which is what
  flotilla's `plumbing_confirmed` check needs. Unlike case 3, the store is the flow's, not the target's: Slack's message does not carry the id,
  so a store lost with the workflow (deleting it, a restore of the database from before the post) would let a re-send post a second time.
- Slack refusing the post (`ok: false`) answers 502 and records nothing, so the retry posts once.

**Credentials.** Two `crypto` (HMAC) ones from flotilla's secret files, imported through stdin by `flows/install-slack.sh`
(never printed): `flotilla ask hook (HMAC)` (`c1slackaskhook01`, `~/flotilla/config/hooks/ask.secret`) and
`flotilla reply callback (HMAC)` (`c1slackreplycb01`, `~/flotilla/config/plumbing/reply.secret`). One **Slack API** credential,
**made by the operator in the editor** (the bot token of the Slack app, scopes `channels:history` and `chat:write`; the app must be
a member of `#ask`): the install script takes the one credential of that type, whatever its name, and stops listing the names when
there are none or several (`SLACK_CRED_NAME` picks one). **Egress:** `slack.com` is in `egress/acl.yaml` (A3).

**The operator's steps on the mini, in order**
1. Secrets (mode 600, the same files flotilla's side mounts): `umask 077; openssl rand -hex 32 > ~/flotilla/config/hooks/ask.secret;
   openssl rand -hex 32 > ~/flotilla/config/plumbing/reply.secret`.
2. From a copy of `flows/`: `bash install-slack.sh`. It imports the credentials and both workflows (overwriting) and publishes
   the reply flow only. Re-run it after changing a flow: it deactivates the question flow again (step 4).
3. Flotilla side, before any question: in `flotillad.yaml` the `ask` hook (`secret_file` the ask secret, `kind: question`,
   `target: thread`, `target_pattern: '[0-9.]{1,32}'`, `asker: {field: user, tool: slack}`,
   `fields: {thread: {type: text, max: 64}, user: {type: text, max: 40}, text: {type: text, max: 2000}}`, the default `max_body` (64 KiB), if not set lower, is enough
   for 2000 characters of any script); in the private host registry `plumbing.reply`'s URL `http://n8n:5678/webhook/flotilla-reply` and its secret file
   (`PLUMBING_REPLY_URL`, `PLUMBING_REPLY_SECRET_FILE`); and in the people file the operator's Slack id under `ids.slack`
   (`U09QUSYGLTF`), which is how the asker is resolved.
4. **Test the reply flow** while the question flow is still inactive: sign a `plumbing.reply` call with `plumbing/call.py` (its
   `execute` and `check`, as `flows/slack-proof/proof.py` does; it posts a real message) and see it land in the thread of a message you made in `#ask`.
5. **Activate the question flow, last and explicitly:** `docker exec n8n n8n publish:workflow --id=case1slackask001` (a running n8n
   applies it shortly) or Publish in the editor. This starts the polling: from the next minute every top-level human message in `#ask`
   opens a question case in flotilla. To stop: `docker exec n8n n8n unpublish:workflow --id=case1slackask001`.
   To run one poll by hand: `docker exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n n8n execute --id=case1slackask001`.

**The proof, on a dev engine, never the mini:** `FLOTILLA_PLUMBING=<flotilla checkout>/plumbing bash flows/slack-proof/run.sh` starts a
throwaway compose project (n8n at this pin and a Postgres, `stub_slack.py` as Slack's Web API and as flotilla's `ask` hook under the
name `flotillad`, which checks the signature with flotilla's own `call.sign`, the window and the delivery pattern), generates the flows with
`node flows/gen_slack_flows.js <dir> --base http://slack:8080`, installs them with the same `install-slack.sh`, runs `proof.py`
(each poll started with `n8n execute`, the reply calls made with flotilla's `plumbing/call.py` `execute` and `check`), and removes the
project and its volumes. Every credential and secret is generated per run. 2026-11-26: 33 of 33 PASS, run twice (EXIT=0 both), the project and its volumes gone after each.

Not covered (case 1 Slack flows):
- **Real Slack.** The stub speaks the response shapes of `conversations.history` and `chat.postMessage` as the flows read them; real
  rate limits (`ratelimited` is a failed run, retried next minute), pagination limits, scopes, the app's membership of `#ask`, message
  edits and deletions, and `Retry-After` are not proven. The first real question is the check.
- **Real flotilla.** The hook stub ports `internal/hook`'s checks (and uses `call.sign`); it is not flotillad. The end-to-end run with
  flotilla's `knowledge/answer` and the approval is flotilla's e2e plus the first real question.
- **Latency and misses:** a question waits up to a minute for the poll. Messages in a thread, edited text, deleted messages and
  file shares are not questions.
- **Where the text is kept:** the question flow's saved executions hold each question's text in `n8n-db` (and its backups) until
  n8n prunes executions (default 336 h); the reply flow's, the reply's.
- **A crash between Slack accepting a reply and n8n saving the delivery id** posts again on the re-send (a window of milliseconds,
  and flotilla's executor never retries a timed-out call).
- **Concurrent callers** of the reply flow with one delivery id at once, and several instances of n8n.
- **The mini:** nothing here has run there; credentials, files and flotilla's config are the operator's steps above.
