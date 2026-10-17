# RFC-0006 — Self-hosted Infisical on the Mac mini for engineering secrets

**Status:** Proposed (2026-10-17)
**Runs on:** the `homelab` Mac mini, as a production stack (not the dev engine, ADR-0009).
**Serves:** the operator's Mac laptop, the Mac mini, the Linux dev workstation, and the agents
running on them.
**Relates to:** ADR-0005 (self-hosted services, Tailscale-only exposure), ADR-0006 (sops + age for
the mini's own provisioning secrets), ADR-0009 (dev vs production Docker engine),
[observability endpoints](../recipes/observability-endpoints.md) (per-service Tailscale nodes),
[agent access handbook](../recipes/agent-access.md).

Written from a conversation in a podcast_scraper session on 2026-10-17, so the homelab agent can
take the discussion over. Product facts about Infisical are as the author knew them in mid-2026
and are **not verified against current docs**; every one of them is listed again under Open
questions.

## Motivation

Engineering secrets live in Dashlane today: API keys, GitHub tokens, provider keys, DSNs, and every
value that ends up as a GitHub Actions secret. Dashlane stays the operator's **password manager**.
It is not a good **engineering-secrets store**:

- No CLI path that injects a secret into a process. Getting a value into a deploy, a `.env` or a
  GitHub secret means copy-paste.
- No machine identity. An agent cannot be given read access to *some* secrets without being given
  the operator's whole vault.
- No per-read audit trail for automation.

What the operator wants:

1. One store for engineering secrets, synced across macOS (laptop, mini) and Linux (workstation).
2. Very secure, and on hardware the operator owns.
3. Agents can **use** secrets to automate work without the values appearing in plain text: not in
   files, transcripts, shell history or git.
4. Local development stops keeping secrets in `.env` files.

Out of scope: personal passwords (they stay in Dashlane) and the prod runtime secrets model in
podcast_scraper (ADR-115 there: GitHub secrets staged into `/dev/shm` on the VPS). That model is
not changed by this RFC.

## Proposal

Self-host **Infisical** (open source, MIT core) on the Mac mini, reachable only over the tailnet.
Engineering secrets move from Dashlane into it. Humans and agents read secrets by **injecting them
into a child process** (`infisical run -- <cmd>`), never by printing them.

### 1. The stack on the mini

| Container | Role |
|---|---|
| `infisical` | API server + web UI |
| `postgres` | the encrypted secret store |
| `redis` | queues and cache |

- Lives under `infra/infisical/` like the other stacks, images pinned, `.env` gitignored, and its
  bootstrap secrets in sops + age per ADR-0006.
- Runs on the mini's **production** engine. It is a long-running service, not dev work, so the
  dev-engine contract (ADR-0009) does not apply to it, and dev containers never touch it.
- Exposed like Grafana and Langfuse: a dedicated Tailscale certificate node, for example
  `https://secrets.tail6d0ed4.ts.net`, through `infra/reverse-proxy/`. There is no public port and
  no `tailscale serve`.
- A Tailscale ACL grant limits who reaches it: the operator's three machines, and nothing else
  until a need is shown (see §6 on CI runners).

### 2. Data model

`project → environment (dev / prod) → folder → secret`.

- A value can reference another (`${prod.github.PAT}`), so a secret is stored once and used in
  several places.
- Every change is versioned, and every read is in the audit log under the identity that made it.
- Suggested starting layout: one project per product (`podcast`, `orrery`, `homelab`), with `dev`
  and `prod` environments, and an `/agents` folder holding only what agents need.

### 3. Root keys, backups and failure

- The server's `ENCRYPTION_KEY` and `AUTH_SECRET` decrypt everything. They are kept in **Dashlane**
  and in the stack's sops file, never only on the mini.
- Postgres is backed up encrypted and **off the mini**. Database backup + the two keys = rebuild in
  minutes. Without the keys, a backup is unreadable.
- **Single point of failure.** With the mini down or a machine off the tailnet, nothing can fetch
  secrets. The few secrets needed to recover the mini itself (Tailscale auth, the age key, the root
  keys, GitHub access) stay in Dashlane.
- Whether the CLI caches secrets locally for use while the server is unreachable is an open
  question. Recalled, not verified.

### 4. Operator workflow and `.env` files

Each machine logs in once as the operator:

```bash
infisical login        # browser login; token kept in macOS Keychain / Linux keyring
cd ~/projects/<repo>
infisical init         # writes .infisical.json: project id + default env, no secrets
```

Secrets are injected rather than read from files:

```bash
infisical run --env=dev -- make serve
infisical run --env=dev -- docker compose up   # compose interpolation sees the values
```

What happens to `.env`:

- `.env` keeps **only non-secret settings** (ports, flags, URLs). Secrets come from `infisical run`
  and never sit on disk.
- A Makefile wraps it once: `RUN := infisical run --env=dev --`, then `$(RUN) uvicorn …`.
- A tool that insists on a file can get one from `infisical export --format=dotenv`. That file is
  **plaintext**: write it only to tmpfs (`/dev/shm` on Linux), the way podcast_scraper's prod
  deploy already handles secrets, and delete it after.
- Servers that need rendered files (for example the podcast VPS, later) can use the **Infisical
  Agent** daemon, which renders templates and re-renders on change. Not part of the first step.

### 5. Agent integration

**a. A machine identity per agent context, never the operator's login.** For example
`agents-mini` and `agents-workstation`:

- Universal Auth (client id + client secret).
- Read-only, one project, `dev` only, folder `/agents`. GitHub admin tokens and prod credentials
  are not in that folder.
- Short access-token TTL (for example 1 h), and trusted IPs restricted to tailnet addresses.
- Every read appears in the audit log under that identity, and each identity can be revoked alone.

**b. One wrapper as the only entry point** (`with-secrets`):

```bash
#!/usr/bin/env bash
# The client secret lives in the agent user's Keychain (or a 0600 file), never in a repo.
export INFISICAL_TOKEN=$(infisical login --method=universal-auth \
  --client-id="$AGENT_CLIENT_ID" \
  --client-secret="$(security find-generic-password -s infisical-agent -w)" \
  --silent --plain)
exec infisical run --projectId=<id> --env=dev --path=/agents -- "$@"
```

The agent runs `with-secrets make test`. Values exist only in that child process's environment.
The Linux variant reads the client secret from the keyring or a 0600 file instead of `security`.

**c. Harness permission rules.** Claude Code `settings.json` (and the opencode equivalent):

- allow: the `with-secrets` wrapper;
- deny: `infisical secrets*`, `infisical export*`, reads of the client-secret file or Keychain
  entry, and `infisical login` with any method other than the wrapper's.

**d. No MCP server for reading values.** Infisical publishes an MCP server, but an MCP tool's result
enters the model's context, so reading a secret through it puts the value in the transcript: the
exact thing this RFC is meant to prevent. At most, use it to list secret *names*.

**The limit, stated plainly.** A process running under `with-secrets` holds real values and could
print them. Injection keeps secrets out of files, transcripts, history and git. It does not make a
process that holds a secret harmless. The controls are the narrow scope, short tokens, the audit
log and per-identity revocation.

### 6. GitHub Actions

Two options, neither required for the first step:

- **Sync out.** Infisical pushes chosen values into GitHub repository or environment secrets. Needs
  only outbound access from the mini to `api.github.com`. The operator currently prefers to copy
  GitHub secrets by hand; that keeps working, and this stays optional.
- **Pull at job time.** A workflow authenticates to Infisical with GitHub OIDC (no stored token)
  and fetches values. The runner must reach the mini over the tailnet; podcast_scraper's deploy
  workflows already join it. This would mean fewer GitHub secrets, but every deploy would then
  depend on the mini being up. **Not recommended now.**

### 7. Migration from Dashlane

- Done by the operator, by hand, in the web UI, one secret at a time. No import scripts.
- Not `infisical secrets set KEY=value` on a command line: the value lands in shell history.
- Dashlane keeps personal passwords and the Infisical root keys.

### 8. Suggested rollout

1. Stand up the stack on the mini, tailnet node, ACL grant, backups, root keys into Dashlane.
2. Operator login on all three machines; move one repo's dev secrets (podcast_scraper is the
   obvious candidate) and switch its `.env` to non-secrets plus `infisical run`.
3. Create `agents-mini`, the `/agents` folder, the wrapper and the harness deny rules; prove an
   agent can run a test that needs a key without the key appearing anywhere in its transcript.
4. Repeat for the workstation, then other repos.
5. Decide §6 separately, later.

## Open questions

Unverified product facts (check against current Infisical docs before building):

1. Which features need a paid licence when self-hosted: custom roles, secret rotation, dynamic
   secrets, audit-log retention, IP allowlisting on identities.
2. Whether the CLI keeps a local cache usable while the server is unreachable, and how it is stored.
3. Current CLI flags: `--path`, `--projectId`, `login --method=universal-auth --plain`,
   `export --format=dotenv`.
4. The current self-host requirements (Postgres and Redis versions, memory) and whether the image
   runs well on the mini's production engine.
5. The exact shape and scope of Infisical's MCP server.

Design questions for the operator and the homelab agent:

6. Project layout: one project per product, or one project with folders?
7. Where the off-box Postgres backup goes, and how restore is tested.
8. How the agents' client secrets are provisioned on each host, and who rotates them.
9. Whether prod secrets live here at all in the first step, or only `dev`.
10. Whether this also replaces the sops + age secrets of the homelab stacks (ADR-0006), or sits
    beside them. The age key is the root of that chain and must stay outside Infisical either way.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| **1Password** (`op run`, service accounts, SSH agent) | The most polished CLI and agent story, but it would replace or duplicate Dashlane, and the operator does not use 1Password. Hosted only. |
| **Bitwarden Secrets Manager** (`bws run`, machine accounts) | Good fit and open source, but hosted unless running Bitwarden's full self-host; Vaultwarden does not provide Secrets Manager (recalled, not verified). |
| **Doppler** | Hosted only; secrets would leave the operator's hardware. |
| **HashiCorp Vault / OpenBao** | The enterprise standard, with dynamic credentials and policies, but too much to run and unseal for one operator. |
| **sops + age only** (as ADR-0006) | Good for encrypted files in git, already used, kept. No cross-device CLI injection, no machine identities, no read audit. |
| **Stay on Dashlane** | No injection, no machine identities, no audit; agents cannot be given a scoped subset. |

## Discussion

- 2026-10-17 — Drafted from a podcast_scraper session at the operator's request. The operator chose
  self-hosted Infisical over 1Password to keep Dashlane for passwords and keep secrets on owned
  hardware. Handed to the homelab agent for review and to continue the discussion with the
  operator.
- 2026-10-17 — Homelab review against Infisical's current docs: audit logs, trusted IPs on
  identities and custom (environment/folder-scoped) roles need a licence when self-hosted, and the
  CLI caches fetched secrets for offline use (storage undocumented). The operator chose the
  server-less counter-proposal, [RFC-0007](RFC-0007-sops-age-engineering-secrets.md) (sops + age).
