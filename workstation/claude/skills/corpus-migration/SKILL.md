---
name: corpus-migration
description: Apply corpus migrations on prod safely — preflight (free disk for the snapshot, no reprocess/sweep container rewriting the corpus, not near the nightly, pending list exactly as expected), the CLI's own dry run saved for the migrations' owner, a gated apply that runs in the background inside the container and is logged, then verify and an ownership check of files the run wrote (root vs the corpus owner), with the undo recorded. Use when asked to "run the migrations", "apply 0030/0031", "upgrade the corpus", "dry-run the upgrade", or after a deploy that ships a corpus migration.
---

# corpus-migration

podcast_scraper's corpus migrations (`python -m podcast_scraper.cli upgrade status|run|verify`) each
snapshot the whole corpus (13 GB on 2026-10-03) and rewrite it. The steps around them were in a
hand-maintained checklist (POST-DEPLOY-*.md "Migrations … LAST, one run"):

- dry run;
- send the counts and refusals to the owner;
- apply on the operator's go;
- verify;
- check that nothing was left root-owned (`docker exec` runs as root; the corpus belongs to
  `deploy:docker`, uid 1000:1000);
- run the search upsert.

This packages the parts that can be checked by a machine.

## Refuse a handover without its outcome table (podcast_scraper corpus change method)

Before any dry run is planned or any apply, the handover from the migration's owner must carry the
following, per podcast_scraper `docs/guides/CORPUS_CHANGE_METHOD.md` §4–§6. If any item is
missing, reply with what is missing and do not run.

1. **The outcome table:** before → after on a named snapshot clone, for:
   - the gating rows (S1n, S1c, S12, and S1/S2 under the trade rule);
   - the change's own outcome numbers, each with its definition and script.
2. **A fresh independent reviewer's verdict** (GO / GO WITH CONDITIONS), and its conditions.
3. **The predicted apply counts as integers**, so you can check the dry run and the apply against
   them. Any other number: stop.
4. **The run steps for every derived surface** (search upsert, insight-clusters, enrichment
   sidecars, edges, …), and the undo for exactly the migrations being run.
5. **The operator's recorded go** for this apply.

The prod-side half is yours:
- produce the per-episode plan read-only (the dry run plus the owner's plan listing) and send it
  back, so it is diffed against the clone before apply;
- write the job for exactly the migrations being run.

## Job

`~/.local/state/corpus-migration/<job>/job.json`:

```json
{"ssh": "deploy@prod-podcast", "ssh_key": "~/.ssh/podcast_prod_operator",
 "container": "compose-api-1", "cli": "python -m podcast_scraper.cli",
 "corpus_dir_in_container": "/app/output", "corpus_dir_on_host": "/srv/podcast-scraper/corpus",
 "need_gb": 30, "busy_container_regex": "reprocess|sweep|pipeline-llm-run",
 "nightly_utc": "00:00", "guard_min": 90,
 "expect_pending": ["0030_adfree_cut_resynced"],
 "owner_uid": 1000, "owner_gid": 1000,
 "undo": "from podcast_scraper.upgrade.migrations.m0030_adfree_cut_resynced import undo; undo(Path('/app/output'))"}
```

`expect_pending` and `undo` name exactly the migrations this job runs, and nothing else. The example
is the 2026-10-17 0030-alone run. The held naming re-derivation is `0032_naming_voices_rederived`
(it was 0031 until 2026-10-18); `0031_named_voices_shown` is a different migration, run only
with its own outcome table, reviewer verdict and operator go.

Optional `snapshot_dir` passes `--snapshot-dir`. Optional `to_version` passes
`--to <version>` to both dry-run and apply, so a job upgrades to exactly that
version instead of running every pending migration in one go — used when a plan
needs migrations applied one at a time (e.g. the 2026-10-27 0034/0035/0036 run,
one job per migration).

## Run, in order

```bash
M=~/.claude/skills/corpus-migration/scripts/migrate.py
python3 $M <job> status          # the CLI's own status
python3 $M <job> preflight       # PASS/FAIL with reasons; read-only
python3 $M <job> dry-run         # saved under the job dir → send counts/refusals to the owner
python3 $M <job> apply --said "<operator's go, verbatim>" [--dry-run] [--accept-plan-diff <path>]
python3 $M <job> plan-diff       # after an exit 4: the hook's plan-diff file, saved for the owner
python3 $M <job> watch           # follows the log until EXIT=
python3 $M <job> verify
python3 $M <job> ownership       # [--fix --said "..."] chowns what the run left root-owned
```

- `apply` refuses with no recorded dry run, or with any preflight failure. It runs
  `upgrade run --yes` with `docker exec -d` inside the container, so an ssh drop cannot kill it.
  The log is `/tmp/upgrade-<ts>.log` in the container.
- An unexpected pending migration (anything not in `expect_pending`) stops at preflight: ask the
  migrations' owner (for podcast_scraper, the ingestion session) before touching it.
- After it: the search update is incremental, never a rebuild (podcast_scraper: the next pipeline
  run's upsert, or `index-two-tier` without drop/clear), then the project's spot checks.
- Undo is per migration and in reverse order; the job's `undo` text is recorded in the ledger at
  apply time.

### Where the pre-upgrade snapshot lives (podcast_scraper prod, 2026-10-27)

- `upgrade run` copies the whole corpus first, to `/app/.corpus-upgrade-backup-<version>-<utc>`
  inside `compose-api-1` (e.g. `/app/.corpus-upgrade-backup-2.7.29-20261027T101817Z`). Without
  `snapshot_dir` that path is in the container's **writable layer, not a mount**.
- So a deploy that recreates the container **deletes it silently**. "Rollback = this directory"
  holds only until the next deploy; after one, the rollback is the per-migration undo (receipts
  and `.podcast_scraper/upgrade-backups/<tag>/`, on the corpus mount) or the daily
  `snapshot-prod-<date>` in the backup repo. Say which one applies when you report the apply.
- Each run needs about the corpus's size in free disk for that copy: **30 GB** on 2026-10-27.
  The job's `need_gb` is that number; raise it as the corpus grows. Delete a run's snapshot only
  with the operator's go, per path, once its verify passed and a daily snapshot after it exists.

## The outcome hook (podcast_scraper migrations 0031 on)

From 0031, `upgrade run` applies a migration only as it was measured on its snapshot clone (method
§4, `upgrade/outcome_hook.py`). It runs alone: `expect_pending` is exactly that one migration, and
every earlier one has been applied first.

| Exit | Meaning | What you do |
| --- | --- | --- |
| 3 | refused (no shipped outcome, code or verdict not the measured one, not alone, applied set differs): nothing written, no snapshot | send the log's `OUTCOME HOOK` line to the owner; do not retry |
| 4 | stopped: prod's per-episode plan differs from the clone's; only `<corpus>/.podcast_scraper/upgrade-outcomes/<id>.plan-diff.json` written | `plan-diff` saves it; send it to the owner. Apply again only with their accept file (a cause per entry, the operator's go verbatim) via `apply --accept-plan-diff <path in container>` |
| 5 | applied, but the after-scoreboard is not the measured one (or failed): nothing undone, the ledger records it | stop; the receipt (`<id>.json` in the same directory) and the printed undo go to the owner and the operator |

The dry run prints the hook's decision (`outcome hook: plan diff N episode(s)`) and writes nothing.
The receipt and the plan-diff file are written by `docker exec`, so as root; `ownership` checks them
with everything else the run wrote.

## Tested 2026-10-17 (live, read-only)

Preflight on prod during #2332 batch 2: `FAIL busy: ['podcast-reprocess-39026409470']` and
`FAIL pending ['0030_adfree_cut_resynced'] != expected [... '0031_naming_voices_rederived']`
(0031 ships with the next deploy). `apply` without a dry run: `REFUSED`. Parser:
`python3 -m unittest test_migrate`.

## Not covered

- The hook's exits, the accept path and `plan-diff` are tested against the parser and the command
  it builds (`test_migrate`), not against a live container: the first real use is 0031's apply.
- The apply itself has not been run through this script yet. The first real use is the 0030+0031
  run after the next deploy; watch it the first time.
- Spot checks and the search upsert are project-specific; they stay in the project's checklist.
- The nightly guard knows one daily time; other scheduled writers (backups) are not checked.
