# RFC-0007 — Engineering secrets in sops + age, per project and environment

**Status:** Proposed (2026-10-17, revised the same day after an independent review)
**Counter-proposal to:** [RFC-0006](RFC-0006-self-hosted-infisical-engineering-secrets.md)
(self-hosted Infisical). Same goals, no server.
**Relates to:** ADR-0006 (decided sops + age for the mini, never implemented), ADR-0010
(environment names), the [agent access handbook](../recipes/agent-access.md).
**First projects:** podcast_scraper and orrery.

## Why not RFC-0006 as written

RFC-0006's goals stand:
- one store across the operator's machines (the Omarchy Linux box, now the main dev machine;
  the Mac mini; the Mac laptop);
- on owned hardware;
- agents use secrets without seeing them;
- no secrets in `.env` files.

The homelab review (2026-10-17, against Infisical's current docs) found that its agent controls
are paid on self-hosted Infisical:

- **audit logs:** Pro and up, which needs an Enterprise licence when self-hosted;
- **trusted IPs on identities:** paid;
- **custom roles:** Enterprise. Built-in roles can't be narrowed to one environment or folder.

The independent review added the deciding point. On the mini, the operator account has
passwordless sudo, and agents often run as that account. Any access control enforced by a
**server on that box** (roles, folders, IP limits) is void for such an agent: it can read the
server's encryption key and dump its database. Encrypting each file only to the keys allowed to
read it is the one control that survives a root-equivalent agent. That is what sops + age does,
without a server.

## The idea in one paragraph

Each secret lives in an encrypted file, one per project and environment (`podcast/dev.env`,
`podcast/prod.env`), in a git repo that is just a folder on the mini, reached over SSH. Only the
values are encrypted; the names stay readable. Each file is encrypted only to the keys allowed to
read it. **No key that can open prod exists on any machine where agents run as the operator.**
Dev files hold only capped LiteLLM virtual keys, never provider keys, so everything an agent can
reach is capped money. Programs get secrets through `sops exec-env <file> <command>`: the values
exist only in that child process's environment, never on disk. A small `secrets` command does the
daily work (set, run, push, list, check), and a manifest per project maps each secret to where it
has to go.

## Concepts

- **age**: an encryption tool. A key pair is a private *identity* (`AGE-SECRET-KEY-1…`, kept in a
  file, or in hardware through a plugin) and a public *recipient* (`age1…`, safe to publish).
  Anything encrypted to a set of recipients opens with any one of their identities.
- **sops**: encrypts the values of a dotenv/YAML/JSON file with a fresh data key, and encrypts that
  data key to each recipient. A MAC detects tampering. `.sops.yaml` says which recipients each path
  gets. The commands used here:
  - `sops edit F`: decrypt into an editor, re-encrypt on save;
  - `sops exec-env F 'cmd'`: run `cmd` with F's values in its environment;
  - `sops updatekeys F`: re-encrypt F after recipients change.

## Design

### 1. Keys, and the one rule

**The rule:** no prod-capable key on a machine where agents run as the operator's account. The
operator routinely gives agents an SSH key into that account. An agent there can do anything the
account can, including reading any key file and running the decrypt itself. Harness rules don't
change that (§5).

| Key | Lives | Opens |
|---|---|---|
| `op-omarchy`, `op-mini`, `op-laptop` | a key file on that machine, mode 600 | `*/dev.env`, `*/staging.env`; `op-mini` also `homelab/*` |
| `op-prod` | **one** place, under the operator's control: the laptop's Secure Enclave (`age-plugin-se`, Touch ID per use) | `*/prod.env` |
| `recovery` | **only** in Dashlane, never on a machine | every file |
| `host-mini` | the mini, for stacks and LaunchDaemons that start without a human | `homelab/*` |
| `agents-mini` | the mini's separate `claude` user, mode 600 in its home | `*/dev.env`, `*/agents.env` |

- **A prod change** means setting or rotating a prod value, or pushing prod values to GitHub
  (`secrets set podcast prod …`, `secrets push podcast prod`). It happens on the laptop, with one
  Touch ID prompt each time. Dev work, tests and everything agents do never touch `op-prod`, so
  they never prompt.
- On Linux there is no Secure Enclave. If prod changes should happen on Omarchy instead, `op-prod`
  becomes a passphrase-protected key there, asked for only on prod operations. That needs a test
  first (open question 2).
- Keys are never committed and never copied between machines. Only public recipients go into
  `.sops.yaml`.
- sops on macOS looks for its key file under `~/Library/Application Support/sops/age/keys.txt`,
  not `~/.config/sops/age/keys.txt`. The `secrets` wrapper always sets `SOPS_AGE_KEY_FILE`
  explicitly, so the path never depends on the OS default.

### 2. The repo: a bare git folder on the mini

`~/secrets.git` on the mini, created with `git init --bare`. Each machine clones it over the SSH
it already uses (`git clone homelab:secrets.git`).

- No Docker, no service, nothing to update.
- Every clone is a full copy with full history. The mini's backup job also includes the folder.
- The mini down stops only syncing. Every machine keeps working from its clone.
- Nothing about the secrets, not even the names, goes to GitHub.

```
.sops.yaml                  # path → recipients (§1)
podcast/dev.env  podcast/prod.env  podcast/targets.yaml
orrery/dev.env  orrery/staging.env  orrery/prod.env  orrery/targets.yaml
homelab/<stack>.env         # replaces the mini's plaintext .env files (§7)
bin/secrets                 # the wrapper (§4)
```

Environments follow ADR-0010's names: podcast has `dev` and `prod`; orrery has `dev`, `staging`
and `prod`. A file holds only secrets. Non-secret settings (ports, URLs, flags) stay in the
projects' own config.

### 3. The mapping: one place to say where a secret goes

`<project>/targets.yaml` maps each key, per environment, to its destinations:

```yaml
# podcast/targets.yaml
LITELLM_API_KEY:
  dev:  [local]                                       # the capped proj-podcast-dev virtual key
OPENROUTER_API_KEY:
  prod: [github:repo:PROD_OPENROUTER_API_KEY]         # provider key: prod only
SENTRY_DSN_PLAYER_OBS:
  prod: [github:repo:PROD_SENTRY_DSN_PLAYER_OBS]
PLAYER_APP_SESSION_SECRET:
  prod: [github:env:prod:PLAYER_APP_SESSION_SECRET]   # GitHub environment "prod"
```

- `local`: available to `secrets run`.
- `github:repo:NAME` or `github:env:<env>:NAME`: pushed with `secrets push`.
- `mini:<stack>`: injected when that homelab stack starts.

The VPS runtime is unchanged: deploys still render GitHub secrets onto the box (podcast ADR-115).
This RFC changes where those GitHub secrets come from, not how prod reads them.

### 4. Daily use: the `secrets` command

| Task | Command | What it does |
|---|---|---|
| New or rotated value | `secrets set podcast prod OPENROUTER_API_KEY` | hidden prompt, JSON-encodes the value, `sops set --value-stdin`, commits with a message naming the key, never the value |
| Run with an environment | `secrets run podcast dev -- make serve` | `sops exec-env podcast/dev.env`; values only in that process |
| Push to GitHub | `secrets push podcast prod` | for each `github:` target, decrypts one value into a pipe to `gh secret set NAME` (stdin) |
| See what exists | `secrets ls podcast` | names × environments × targets, never values |
| Check drift | `secrets check podcast` | GitHub secret names and dates vs the manifest: missing, extra, or pushed before the last change |

So "here's a new prod key for podcast" is `secrets set podcast prod <KEY>`, then
`secrets push podcast prod`, both on the laptop.

- Values are never passed as arguments. Arguments land in shell history and `ps`.
- `sops set --value-stdin` (sops 3.13.3) accepts only a JSON value: `printf '"v"' | sops set
  --value-stdin F '["KEY"]'` exits 0, a raw value exits 7 (`not valid JSON`; the cause of sops
  issue #1932). The wrapper JSON-encodes. Verified by the reviewer on the laptop.
- `secrets check` is built in the same step as `set`/`push`, not later. It is what keeps
  `targets.yaml` honest against GitHub's 57 + 10 (podcast) and 1 + 12 (orrery) secrets.

### 5. Agents: what actually protects

The real controls, strongest first:

1. **No prod-capable key on agent machines** (§1). Agents can't decrypt prod, whatever they run.
2. **Dev files hold only capped keys.** Dev `*.env` contains LiteLLM virtual keys with hard
   budgets (today's `proj-podcast-dev`: the DGX model only, $1), never provider keys. Provider keys
   exist only in `*/prod.env` and `homelab/litellm.env`.
3. **A separate OS user for agents**, as `claude` already is on the mini: that user can't read the
   operator's key files (verified). Adopted step by step, starting with the mini, then Omarchy.

Harness rules (Claude Code `settings.json`, the opencode equivalent) are **accident prevention,
not a boundary**:
- allow `secrets run`;
- deny `sops decrypt`, `sops -d`, `sops edit`, `secrets set/push`, and reads of key files.

They match the start of a command string, so `bash -c 'sops -d …'` or `python3 -c "…"` gets
around them, and the operator's settings allow both forms. They stop an agent from printing a
value by mistake; they don't stop a determined process.

No MCP server or tool path ever returns a value into a model's context.

### 6. Making an LLM API key hard to steal

| Leak path | Control |
|---|---|
| Git | values only in the encrypted repo on the mini; nothing on GitHub, not even names |
| The repo copied off a machine | values encrypted to keys that never leave their machines; prod to a hardware key |
| Shell history, `ps` | hidden prompts and pipes; values never as arguments |
| Files on disk, backups | `exec-env` keeps values in process memory; no plaintext `.env` |
| An agent as the operator | no prod key on agent machines; dev holds only capped virtual keys |
| A lost or stolen machine | remove its recipient, `updatekeys`, **rotate** what it could read (old ciphertext still opens with the old key) |
| A key that leaks anyway | the provider caps the damage (below) |

Provider-side limits are the last line:

- **One provider key per environment.** A leaked dev key can't spend prod's money.
- **Spend caps everywhere:** a hard budget on every LiteLLM virtual key, and the provider's own
  per-key limit (OpenRouter) on the upstream keys. Those stay readable on the mini regardless:
  they sit in the LiteLLM container's environment, which a sudo user can inspect.
- **Rotation on any doubt:** `secrets set`, `secrets push`, revoke the old key at the provider.

### 7. Rotation, recovery, and the migration scope

- **Rotate a value:** `secrets set` + `secrets push`, then revoke the old one at the provider.
- **Remove a machine:** delete its recipient from `.sops.yaml`, run `sops updatekeys` on every
  file, commit, then rotate what it could read.
- **Rebuild a machine:** generate a new key on it, add its recipient, run `updatekeys` from a
  machine that can still decrypt (or with the recovery key from Dashlane).
- **Scope on the mini:** about 20 plaintext env files today, not 7:
  - 7 stack `.env` files under `~/agentic-ai-homelab/infra/`;
  - files in `~` (`~/*.env`, e.g. the Langfuse and LiteLLM dev keys);
  - `~/signal-fleet/*.env`, `~/grafana/*.env`, `~/glitchtip/*.env`, `~/umami/*.env`.

  All of them move to `homelab/*` or a project file.

## Rollout

1. **Install sops + age** on Omarchy and the mini (sops 3.13.3 is already on the laptop), and
   `age-plugin-se` on the laptop. New dependencies: operator approval.
2. **Prove the mechanics once**, before migrating anything:
   - `op-prod` in the Secure Enclave works end to end with sops (prompts once per decrypt);
   - `exec-env` keeps values off disk;
   - `set` keeps values out of history and `ps`;
   - `agents-mini` cannot open a `prod` file;
   - `push` updates a GitHub secret.
3. **Create the repo and the wrapper**: `~/secrets.git` on the mini, `.sops.yaml`, `bin/secrets`
   with `set`, `run`, `push`, `ls` and `check` together.
4. **podcast:** move `dev` (capped virtual keys only) and `prod` from Dashlane with `secrets set`.
   Write `targets.yaml` from the GitHub secrets, run `secrets check` until clean, and switch local
   runs to `secrets run`.
5. **orrery:** the same for `dev`, `staging`, `prod`.
6. **homelab:** replace the mini's plaintext env files with `homelab/*` plus `host-mini`. This
   finally implements ADR-0006.
7. **Agent OS users:** move agents on Omarchy to their own user, as on the mini. Iterative.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Self-hosted Infisical (RFC-0006) | Its controls run on a server an operator-account agent can root (passwordless sudo on the mini). Its useful extras (audit log, IP limits, scoped roles) need a licence when self-hosted. Without them it adds Postgres, Redis, backups and a single point of failure for less protection. |
| A private GitHub repo for the encrypted files | Safe if keys stay off GitHub, but names and a growing ciphertext history would sit with GitHub. A bare repo on the mini costs nothing to run. |
| A synced folder without git (e.g. Syncthing) | A sync service to run, no history, no rollback, no clean conflict handling. |
| Encrypted files inside each code repo | All code repos are public: names would reveal accounts, and history keeps old ciphertext. |
| One age key copied to every machine | A lost machine would mean re-keying everything at once. |
| Touch ID for every decrypt | Prompts on every dev run and test. Only `op-prod` uses hardware. |
| Hosted products (1Password, Doppler) | Secrets would leave owned hardware. |
| OpenBao / Vault | A server on the box an agent can root, like Infisical, and heavier. |

## Open questions

1. Where `op-prod` lives: the laptop's Secure Enclave (the default here), or a passphrase-protected
   key on Omarchy (the main dev machine). The laptop keeps prod off every machine where agents
   work; Omarchy is more convenient.
2. If Omarchy holds `op-prod`: how sops gets a passphrase-protected age identity (encrypted
   identity file, `SOPS_AGE_KEY_CMD`, or `age-plugin-yubikey`). Test before choosing.
3. Whether `host-mini` decrypts at every stack start (`secrets run homelab/<stack> -- docker
   compose up`), or stacks keep a rendered `.env` on tmpfs so they restart after a reboot.
4. GitHub environment secrets for orrery's `staging`: a `staging` file, or reuse `dev`?

## Discussion

- 2026-10-17: Written by the homelab agent after reviewing RFC-0006 with the operator. The operator
  asked for: one model for every project, per-environment values mapped to where each one goes, an
  easy way to say "here's a new dev/prod key for podcast", and strong protection for LLM API keys.
- 2026-10-17: Independent review (an advisor agent briefed neutrally on both RFCs) recommended this
  RFC over RFC-0006, with four changes, all applied above:
  - no prod-capable key on the mini;
  - the prod key in the laptop's Secure Enclave;
  - dev files hold only capped virtual keys;
  - wrapper fixes (`SOPS_AGE_KEY_FILE`, JSON-encoded `--value-stdin`), and harness rules described
    as accident prevention only.

  It also corrected the migration scope (~20 env files on the mini, not 7) and verified that the
  mini's `claude` user can't read the operator's key file.
- 2026-10-17: Operator answers to the review's questions:
  - agents will move to separate OS users step by step, not from day one;
  - Omarchy becomes the main dev machine, with the laptop kept for a few things;
  - no Touch ID on routine work (met: only `op-prod` prompts, and only on prod changes);
  - a separate repo service was too much (met: a bare git folder on the mini over SSH, no Docker,
    no service).
