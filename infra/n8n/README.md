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
