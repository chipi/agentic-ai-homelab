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
is the 2026-10-17 0030-alone run; 0031 is held.

Optional `snapshot_dir` passes `--snapshot-dir`.

## Run, in order

```bash
M=~/.claude/skills/corpus-migration/scripts/migrate.py
python3 $M <job> status          # the CLI's own status
python3 $M <job> preflight       # PASS/FAIL with reasons; read-only
python3 $M <job> dry-run         # saved under the job dir → send counts/refusals to the owner
python3 $M <job> apply --said "<operator's go, verbatim>" [--dry-run]
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

## Tested 2026-10-17 (live, read-only)

Preflight on prod during #2332 batch 2: `FAIL busy: ['podcast-reprocess-39026409470']` and
`FAIL pending ['0030_adfree_cut_resynced'] != expected [... '0031_naming_voices_rederived']`
(0031 ships with the next deploy). `apply` without a dry run: `REFUSED`. Parser:
`python3 -m unittest test_migrate`.

## Not covered

- The apply itself has not been run through this script yet. The first real use is the 0030+0031
  run after the next deploy; watch it the first time.
- Spot checks and the search upsert are project-specific; they stay in the project's checklist.
- The nightly guard knows one daily time; other scheduled writers (backups) are not checked.
