# RFC-0007 — Engineering secrets in sops + age, per project and environment

**Status:** Proposed (2026-10-17)
**Counter-proposal to:** [RFC-0006](RFC-0006-self-hosted-infisical-engineering-secrets.md)
(self-hosted Infisical). Same goals, no server.
**Relates to:** ADR-0006 (decided sops + age for the mini, never implemented), ADR-0010
(environment names), the [agent access handbook](../recipes/agent-access.md).
**First projects:** podcast_scraper and orrery.

## Why not RFC-0006 as written

RFC-0006's goals stand: one store across the laptop, the mini and the Linux workstation; on owned
hardware; agents use secrets without seeing them; no secrets in `.env` files. The homelab review
(2026-10-17, against Infisical's current docs) found that its agent controls are paid on
self-hosted Infisical:

- **audit logs:** Pro and up, which needs an Enterprise licence when self-hosted;
- **trusted IPs on identities:** paid;
- **custom roles:** Enterprise. Built-in roles can't be narrowed to one environment or folder.

The CLI also caches fetched secrets on disk for offline use, and the docs don't say how they are
stored. Without a licence, Infisical adds a server (Postgres, Redis, backups, root keys, a single
point of failure) but no protection beyond what injection and harness rules already give. Those
two give the same protection with sops + age, without the server.

## The idea in one paragraph

Each secret lives in an encrypted file in a **private** git repo, one file per project and
environment (`podcast/dev.env`, `podcast/prod.env`). Only the values are encrypted; the names stay
readable. Each machine and each agent host has its own age key, and each file is encrypted only to
the keys allowed to read it, so access is enforced by encryption. Programs get secrets by
`sops exec-env <file> <command>`: the values exist only in that child process's environment, never
on disk. A small `secrets` command handles the daily tasks: set a value, run with an environment,
push to GitHub, show what's where. A manifest per project maps each secret to the places it has to
reach (a local run, a GitHub repo or environment secret).

## Concepts

- **age**: an encryption tool. A key pair is a private *identity* (`AGE-SECRET-KEY-1…`, kept in a
  file) and a public *recipient* (`age1…`, safe to publish). Anything encrypted to a set of
  recipients can be opened by any one of their identities.
- **sops**: encrypts the values of a dotenv/YAML/JSON file with a fresh data key, and encrypts that
  data key to each recipient. A MAC detects tampering. `.sops.yaml` says which recipients each path
  gets. The commands used here:
  - `sops edit F`: decrypt into an editor, re-encrypt on save;
  - `sops exec-env F 'cmd'`: run `cmd` with F's values in its environment;
  - `sops updatekeys F`: re-encrypt F after recipients change.

## Design

### 1. Keys

| Key | Lives | Reads |
|---|---|---|
| `op-laptop`, `op-mini`, `op-workstation` | `~/.config/sops/age/keys.txt` on that machine, mode 600 | every file |
| `recovery` | **only** in Dashlane (never on a machine) | every file; used to rebuild a lost machine's access |
| `agents-mini`, `agents-workstation` | a separate key file per agent host, mode 600, loaded only by the `secrets` wrapper | `*/dev.env` and `*/agents.env` only, never `prod` |
| `host-mini` | the mini, for stacks and LaunchDaemons that start without a human | `homelab/*.env` only |

One key per machine means a lost laptop is removed alone. Private keys are never committed and
never copied between machines; only the public recipients go into `.sops.yaml`.

### 2. The repo

A new **private** repo, `chipi/secrets`. All the code repos (agentic-ai-homelab, podcast_scraper,
orrery, eval-harness) are public; encrypted values would be safe there, but the names would reveal
which providers and accounts exist, and old ciphertext stays in public history forever. A private
repo removes both risks. It also gives a second lock: reading a value needs repo access *and* a key.

```
.sops.yaml                  # path → recipients
podcast/dev.env             # op-* + recovery + agents-*
podcast/prod.env            # op-* + recovery only
podcast/targets.yaml        # where each key goes (§3)
orrery/dev.env  orrery/staging.env  orrery/prod.env  orrery/targets.yaml
homelab/<stack>.env         # op-* + recovery + host-mini: replaces the mini's plain .env files
bin/secrets                 # the wrapper (§4)
```

Environments follow ADR-0010's names: podcast has `dev` and `prod`; orrery has `dev`, `staging`
and `prod`. A file holds only secrets. Non-secret settings (ports, URLs, flags) stay in the
projects' own `.env` or config.

### 3. The mapping: one place to say where a secret goes

`<project>/targets.yaml` maps each key, per environment, to its destinations. For example:

```yaml
# podcast/targets.yaml
OPENROUTER_API_KEY:
  dev:  [local]                                  # sops exec-env for local runs
  prod: [github:repo:PROD_OPENROUTER_API_KEY]    # repo-level GitHub secret
SENTRY_DSN_PLAYER_OBS:
  prod: [github:repo:PROD_SENTRY_DSN_PLAYER_OBS]
PLAYER_APP_SESSION_SECRET:
  prod: [github:env:prod:PLAYER_APP_SESSION_SECRET]  # GitHub environment "prod"
```

- `local`: available to `secrets run`.
- `github:repo:NAME` or `github:env:<env>:NAME`: pushed with `secrets push`.
- `mini:<stack>`: injected when that homelab stack starts.

The VPS runtime is unchanged: deploys still render GitHub secrets onto the box (podcast ADR-115).
This RFC changes where those GitHub secrets come from, not how prod reads them.

### 4. Daily use: the `secrets` command

| Task | Command | What it does |
|---|---|---|
| New or rotated value | `secrets set podcast prod OPENROUTER_API_KEY` | prompts with hidden input, writes the encrypted value, commits it with a message naming the key, never the value |
| Run with an environment | `secrets run podcast dev -- make serve` | `sops exec-env podcast/dev.env`; values only in that process |
| Push to GitHub | `secrets push podcast prod` | for each `github:` target, decrypts one value into a pipe to `gh secret set NAME` (stdin) |
| See what exists | `secrets ls podcast` | names × environments × targets, never values |
| Check drift | `secrets check podcast` | GitHub secret names and dates vs the manifest: missing, extra, or pushed before the last change |

So "here's a new prod key for podcast" is `secrets set podcast prod <KEY>`, then
`secrets push podcast prod`.

- Values are never passed as arguments. Arguments land in shell history and `ps`.
- `set` uses `sops set --value-stdin`, which exists but is reported broken in some versions
  (sops issue #1932). Verify it first; if it fails, `set` falls back to `sops edit` with the editor
  pointed at a small script that writes the value read from the hidden prompt.

### 5. Agents

- An agent runs `secrets run podcast dev -- <cmd>` with its own key (`agents-mini`). That key opens
  only `dev` and `agents` files. It is **cryptographically** unable to read `prod`, whatever
  command it runs.
- Harness rules (Claude Code `settings.json`, the opencode equivalent):
  - allow `secrets run`;
  - deny `sops decrypt`, `sops -d`, `sops edit`, `secrets set/push`, and reads of any
    `keys.txt` or agent key file.
- **The limit:** agents run as the operator's account on the mini and laptop, so an agent process
  *could* read the operator's key file if the harness let it. The harness rules are the real guard
  for that boundary. Prod values are the exception: the agent hosts' keys can't open them at all.
- No MCP or tool path ever returns a value into a model's context.

### 6. Making an LLM API key hard to steal

The paths a key leaks by, and what closes each:

| Leak path | Control |
|---|---|
| Git (public repos) | values only in the private repo, encrypted; code repos hold names at most |
| The secrets repo leaks | values are encrypted to keys that never leave the machines; names only |
| Shell history, `ps` | values only through hidden prompts and pipes, never as arguments |
| Files on disk, backups | `exec-env` keeps values in process memory; no plaintext `.env` |
| Agent transcripts | agents use `secrets run`; harness denies decrypt/print; prod keys unreadable by agent keys |
| A lost or stolen machine | remove its recipient, `updatekeys`, **rotate** what it could read (old ciphertext in git history still opens with the old key) |
| A key that leaks anyway | the provider caps its damage (below) |

Provider-side limits are the last line, and the cheapest:

- **One provider key per environment.** A leaked dev key can't spend prod's money.
- **A spend cap on every key** at the provider (OpenRouter per-key limits). LLM calls go through
  LiteLLM virtual keys, which also cap spend and scope models: the mini's `proj-podcast-dev`,
  prod's `proj-podcast-prod`.
- **Rotation on any doubt:** `secrets set`, `secrets push`, revoke the old key at the provider.

### 7. Rotation and recovery

- **Rotate a value:** `secrets set` + `secrets push`, then revoke the old one at the provider.
- **Remove a machine:** delete its recipient from `.sops.yaml`, run `sops updatekeys` on every file,
  commit, then rotate what it could read.
- **Rebuild a machine:** generate a new key on it, add its recipient, run `updatekeys` from a machine
  that can still decrypt (or with the recovery key from Dashlane).
- **Back up:** the private repo on GitHub plus each machine's clone. The recovery key in Dashlane is
  what makes those copies useful.

## Rollout

1. **Install sops + age** on the three machines (Homebrew; the Linux package). They are new
   dependencies and need the operator's approval.
2. **Generate keys** and put `recovery` in Dashlane. Create `chipi/secrets` (private) with
   `.sops.yaml` and the `secrets` wrapper.
3. **Prove the mechanics once** before migrating anything:
   - `exec-env` keeps values off disk;
   - `set` keeps values out of history and `ps`;
   - an agent key cannot open a `prod` file;
   - `push` updates a GitHub secret.
4. **podcast:** move `dev` and `prod` from Dashlane with `secrets set`, write `targets.yaml` from the
   57 repo + 10 `prod` environment secrets on GitHub today, run `secrets check` until clean, and
   switch local runs to `secrets run`.
5. **orrery:** the same for `dev`, `staging`, `prod` (12 `prod` environment secrets today).
6. **homelab:** replace the mini's plain `.env` files with `homelab/<stack>.env` plus `host-mini`.
   This finally implements ADR-0006.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Self-hosted Infisical (RFC-0006) | Its agent controls (audit logs, trusted IPs, scoped roles) need a licence when self-hosted; without them it adds a server, backups and a single point of failure for no extra protection. Revisit if a web UI, read audit or automatic syncs are wanted, with a licence budgeted. |
| Encrypted files inside each code repo | All the code repos are public: names would reveal accounts, and history keeps old ciphertext forever. |
| One age key copied to every machine | A lost machine would mean re-keying everything at once. |
| Bitwarden Secrets Manager | Self-hosting it means running Bitwarden's full server (recalled, not verified). |
| OpenBao / Vault | Too much to run and unseal for one operator. |
| Stay on Dashlane + plain `.env` | No injection, no scoping for agents, plaintext files on disk. |

## Open questions

1. `sops set --value-stdin` on the installed version (sops issue #1932), or the `edit` fallback.
2. GitHub environment secrets for staging-only orrery values: one `staging` file, or reuse `dev`?
3. Does `secrets check` need anything beyond names and timestamps? GitHub never returns values, so
   it can't detect a wrong value, only a missing or stale one.
4. Whether `host-mini` decrypts at stack start (`secrets run homelab/<stack> -- docker compose up`)
   or the stacks keep a rendered `.env` on tmpfs for restarts after a reboot.

## Discussion

- 2026-10-17: Written by the homelab agent after reviewing RFC-0006 with the operator. The operator
  chose this direction and asked for: one model for every project, per-environment values mapped
  to where each one goes, an easy way to say "here's a new dev/prod key for podcast", and strong
  protection for LLM API keys. First projects: podcast_scraper and orrery.
