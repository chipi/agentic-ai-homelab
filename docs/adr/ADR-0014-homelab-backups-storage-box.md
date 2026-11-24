# ADR-0014 — Homelab backups go to the Hetzner Storage Box, with restic, one sub-account per host

**Status:** Accepted (2026-11-24, operator); not built yet. The plan and its order are below.
**Date:** 2026-11-24

## Context

On 2026-11-24 the homelab had one off-site backup: the mini's nightly job
(`infra/backup/dump-observability-dbs.sh`, launchd `com.homelab.db-backup`, 04:30). It covers:

- `pg_dump` of glitchtip, langfuse, litellm, umami and n8n;
- tars of Home Assistant, Mosquitto and flotillad;
- `offsite.sh`, which age-encrypts every file into a GitHub Release of the private repo
  `chipi/homelab-backup` (7 nightly plus 4 Sunday copies, about 420 MB a night);
- the Grafana alert `homelab-backup-offsite-stale`, which fires after 30 h without a success.

It missed 2026-11-21 (`OFFSITE FAIL: no files for stamp 20261121-043004`).

Nothing else is backed up off-site:

- the stack `.env` files on the mini, n8n's encryption key among them (ADR-0006's sops plan was
  never built);
- the X3's `.env` files (orrery, oceancanvas);
- robotics-lab's staging state and data on the X3 (ADR-0013);
- the mini's `n8n-data`, `grafana-data`, GlitchTip uploads, Caddy's tailnet identities;
- Langfuse's ClickHouse and MinIO;
- the DGX's Open WebUI.

No homelab dump has ever been restored.

The operator already pays for a Hetzner Storage Box (BX11, 1 TB, fsn1), tofu-managed in chipi/infra
(`storage_box.tf`). podcast_scraper's audio archive and Postgres backups use it, one sub-account
each, jailed to a directory. Access is SFTP on port 23. Weekly box snapshots are kept at the
account level, out of reach of any sub-account.

## Decision

The operator decided on 2026-11-24:

1. **All homelab backups go to the Storage Box.** The mini's GitHub-Releases job is replaced, not
   extended.
2. **restic, one repository per host, one sub-account per host**: `homelab_mini`
   (`homelab/mini/`), `homelab_x3` (`homelab/x3/`), `homelab_dgx` (`homelab/dgx/`).
   - They are tofu-managed in chipi/infra, written by infra; `infra-apply` needs the operator's go.
   - A leaked host key reaches only that host's directory, and the box's snapshots cover even that.
   - restic encrypts with a per-host repository password: a mode-600 file on the host, with a copy
     in the operator's password manager.
   - Login is with an SSH key installed in the jail's `.ssh/authorized_keys`, never a password.
   - Known hosts come from infra's pinned `infra/postgres/storagebox_known_hosts`.
3. **What is backed up:**

   | Host | What | How |
   | --- | --- | --- |
   | mini | the five Postgres DBs, HA, Mosquitto, flotillad | the existing dumps, then `restic backup` of that night's files |
   | mini | stack `.env` files and `~/n8n/owner.env` | `restic backup` of the files (the repository is encrypted) |
   | mini | `n8n_n8n-data`, `backend_grafana-data`, `glitchtip_uploads`, `reverse-proxy_caddy_data`, `reverse-proxy_flotilla_hosts_state` | a tar of each volume through a throwaway container, then restic |
   | mini | Langfuse ClickHouse + MinIO | ClickHouse's own `BACKUP`, a MinIO mirror; never a tar of a live store |
   | X3 | robotics-lab staging | `sqlite3 .backup` of `mission-control.sqlite`; `state/mission-control`, `state/deploy/*.json` and `state/deploy/robotics-lab/`, `data`, `data-archive` (robotics-lab's keep table, 2026-11-24) |
   | X3 | the `.env` files of the storage-separation runbook | restic |
   | DGX | Open WebUI (`webui.db`) | SQLite `.backup` in the container, then restic |

   Left out, as rebuildable or accepted losses: Victoria* (ADR-0006), models, repos in git, the
   Observatory index, `deploy/trees`, Redis.
4. **Retention:** `restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune`, run
   weekly.
5. **Watching:** each host pushes `homelab_backup_last_success_timestamp{host}` after a good run.
   One alert covers all three at 30 h, replacing `homelab-backup-offsite-stale` once the mini moves.
6. **A monthly restore test** on the mini:
   - restore the latest dumps into a temporary folder;
   - load each Postgres dump into a throwaway `postgres` container and count its tables;
   - check that each SQLite copy opens;
   - push a metric; its alert means "the backups exist but would not restore".
7. **Order:**
   1. the chipi/infra PR and apply, and the SSH keys;
   2. the mini, with `.env` files first;
   3. the X3 (robotics-lab after its cut-over);
   4. the mini's volumes and Langfuse;
   5. the DGX;
   6. the restore test.

   The GitHub-Releases job keeps running until restic has 14 green nights on the mini. Retiring it
   and deleting its releases is the operator's go.

## Consequences

- One place, room for growth: robotics-lab's data alone is estimated at 5-10 GB a month in batch
  weeks, which GitHub Releases is not meant for.
- New on each host:
  - `restic`, installed with the host's package manager: brew on the mini, pacman on the X3, apt
    on the DGX (the operator's step where it needs root);
  - an SSH key, a repository password and a scheduled job;
  - on the X3, a system timer that runs as `robotics`: a second exception to its user-units rule.
- Secrets leave the hosts for the first time. They are encrypted by restic, and a restore needs
  the repository password from the password manager.
- The box is shared with podcast_scraper. Its usage against 1 TB is not yet known (asked of infra).

## Alternatives considered

- **Keep GitHub Releases and extend it** (age per file). It works today, but has no dedup or
  incremental copies, a 2 GB-per-file limit, and growing data is not what Releases are for.
- **Both targets** (Releases for the mini, the box for the rest). Rejected by the operator: two
  mechanisms to watch.
- **rclone with a password** (infra's pattern). It needs a password in a file or env for an
  unattended job. restic's sftp backend with a key is simpler for a host-run job.
- **Infisical or sops for secrets** (RFC-0006/0007). That is about managing secrets, not backing
  them up, and is left open.

## References

[ADR-0006](ADR-0006-mac-mini-observability-provisioning.md),
[ADR-0013](ADR-0013-x3-staging-docker-engine.md); `infra/backup/`; chipi/infra
`infra/terraform/storage_box.tf`, `docs/recipes/prod-audio-archive.md`.
