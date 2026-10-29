---
name: prod-deploy
description: Bracket a prod deploy with checks — preflight a sha (every required CI workflow on that commit succeeded, every image published as sha-<7> on ghcr), dispatch the deploy workflow and approve its environment gates only with the operator's recorded go (run matched by time + actor), then verify by reading the box that every app container actually runs sha-<7> and the must-run set is up. Use when asked to "deploy X", "is this sha deployable", "what's on prod", "did the deploy land", "verify the deploy", before dispatching deploy-all-prod or any deploy workflow.
---

# prod-deploy

Deploys were preflighted and verified by hand from long POST-DEPLOY checklists. Three past
failures this catches mechanically:

- A 9-character sha passed and failed every surface at its manifest check (run 38752921829).
- An empty sha let surfaces resolve different shas (2026-09-14).
- The deploy report said "deployed" without reading what the box runs.

Preflight on 2026-10-17 also showed that `sha-ded80e0` went out with Snyk cancelled on its commit.

## Config

`~/.local/state/prod-deploy/<project>.json` (podcast example):

```json
{"repo": "chipi/podcast_scraper", "dispatch_repo": "chipi/infra", "workflow": "deploy-all-prod.yml",
 "dispatch_inputs": {"confirm": "DEPLOY_ALL"}, "sha_input": "image_sha",
 "required_ci": ["Python application", "Docker Build & Test", "CodeQL Advanced", "Snyk Security Scan"],
 "images": ["ghcr.io/chipi/podcast-scraper-stack-api", "ghcr.io/chipi/podcast-scraper-stack-viewer",
            "ghcr.io/chipi/podcast-scraper-stack-pipeline-llm", "ghcr.io/chipi/podcast-scraper-learning-app",
            "ghcr.io/chipi/podcast-obs"],
 "approvable_environments": ["prod"],
 "ssh": "deploy@prod-podcast", "ssh_key": "~/.ssh/podcast_prod_operator",
 "sha_containers_regex": "^(compose|operator|player)-",
 "must_run": ["compose-api-1", "player-api-1", "..."], "health": [{"url": "https://…", "expect": 200}]}
```

`repo` is where CI and the images are checked. `dispatch_repo` (optional, default `repo`) holds the
deploy workflow: `dispatch` and `approve` act there. Podcast deploys run from `chipi/infra` since the
2026-10-28 cutover.

## Run

```bash
D=~/.claude/skills/prod-deploy/scripts/deploy.py
python3 $D podcast preflight <sha>                        # read-only; prints the exact dispatch command
# before the dispatch: a box inventory to diff against afterwards (podcast; root, read-only)
ssh root@prod-podcast 'python3 /srv/podcast-infra/current/scripts/ops/box_inventory.py snap pre-<sha7>'
python3 $D podcast dispatch <sha> --said "<operator's go>"   # refuses if preflight fails (--force-preflight only on the operator's explicit waiver)
python3 $D podcast approve <run_id> --said "<operator's go>" # only environments in approvable_environments
python3 $D podcast verify <sha>                           # after the run: the box runs it
ssh root@prod-podcast 'B=/srv/podcast-infra/current/scripts/ops/box_inventory.py; python3 $B snap post-<sha7> && python3 $B diff pre-<sha7> post-<sha7>'
```

The diff must show only release keys and the changes the deploy was meant to make. Without the
`pre-` snapshot, the only baseline is the previous deploy's `post-`, and every other tenant's change
since then lands in the same diff (2026-10-29: 17 hours, 32 changes, attributed by hand).

- Each deploy needs its own go. A go for the previous deploy, or a peer session's go, does not count.
- `verify` checks images and the must-run set only. Then also run:
  - the project's smokes (podcast: `scripts/ops/post_deploy_smoke.sh`, `scripts/smoke/post_deploy.py`);
  - the deploy's telemetry: the `deploy-verify` skill (snapshot before the dispatch, check after:
    logs with environment=prod, traces carry the release, no new GlitchTip issues, Langfuse,
    Umami);
  - errors since the deploy: `o11y-review` over the window, or the Close Listening Obs MCP
    (`prod_recent_errors`, `obs_surface`);
  - for a telemetry path you changed, `telemetry-probe`;
  - the project's post-deploy list.
- CI on the sha you are about to deploy, live: the `ci-watch` skill.

## Tested 2026-10-17 (live, read-only)

- `preflight ded80e0`: 3 CI PASS, `FAIL CI Snyk Security Scan: completed cancelled`, 5 images HTTP 200.
- `verify ded80e0`: 10/10 containers on `sha-ded80e0`, `VERIFY PASS`.
- `verify 76bec92`: `VERIFY FAIL`, naming every container still on ded80e0.
- `dispatch` and `approve` have not been run yet (no deploy since). Use them on the next deploy and
  watch the first one closely.

## Not covered

- Config files (Caddy vhosts, Alloy) deploy separately (`deploy-config.yml`). This does not check
  them.
- `required_ci` is by workflow name. A renamed workflow shows as NOT RUN, which is a FAIL. Update
  the config when that happens.
