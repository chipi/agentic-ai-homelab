# Triage fleet runbook — install, run, review, improve

How to operate the triage fleet (`signal-fleet`, Fleet 2), written so a different agent can pick it up each week. For what the parts are and why they work the way they do, read the [Triage fleet guide](../signal-fleet-guide.md) first. For the operator's own rituals (inbox, routing, labels), see the [operator playbook](../wip/operator-playbook-fleets.md).

Facts below were checked against the running system on 2026-10-02. Host today: the Mac mini (`homelab`), user `markodragoljevic`, reached from a laptop with `ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab`. Commands marked **[host]** run on the fleet host.

## 1. What has to exist

| Component | Where (today) | Notes |
|---|---|---|
| git checkout of this repo | `~/agentic-ai-homelab` | **the fleet runs its code from here**: deploy = pull |
| fleet state | `~/signal-fleet/` | `results/` (ledgers), `queue/`, `fleet-gateway.env`; never in git |
| fleetd binary + config | `~/fleetd/fleetd`, `~/fleetd/fleetd.json`, log `~/fleetd/fleetd.log` | built from [`fleetd/`](https://github.com/chipi/agentic-ai-homelab/tree/main/fleetd) |
| LaunchDaemon | `/Library/LaunchDaemons/com.homelab.fleetd.plist` | system daemon (survives logout), runs as the fleet user, `RunAtLoad` + `KeepAlive` |
| Python | `/usr/bin/python3` (3.9 on the mini) | **standard library only**; no pip installs needed |
| Ruby | `/usr/bin/ruby` | YAML fallback used by two evals when PyYAML is absent |
| Grafana + VictoriaMetrics/Logs/Traces | homelab observability stack | alerts in, probes and metrics out |
| GlitchTip | `:8090` | error source |
| LiteLLM gateway | `:4001`, virtual key `fleet-triage`, models `fleet-triage-flash` / `fleet-triage-pro` | the triager's LLM ([LiteLLM README](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/litellm/README.md)) |
| Langfuse (optional) | project "agents" | traces of triage calls |
| GitHub | a token that can read and write issues and labels on `chipi/podcast_scraper`, `chipi/orrery`, `chipi/agentic-ai-homelab` | filing |

### `~/signal-fleet/fleet-gateway.env`

This is the **only** env file fleetd loads for the triage fleet; `fleet.env` next to it is a stale leftover. Values are secrets: never print them or commit them.

| Variable | Read by | What it is |
|---|---|---|
| `OPENROUTER_API_KEY` | `triage.py` | the LiteLLM **`fleet-triage` virtual key** (the name is historical) |
| `SF_OPENROUTER_URL` | `config.py` | `http://localhost:4001/v1/chat/completions` (the gateway) |
| `SF_TRIAGE_MODEL` | `config.py` | `fleet-triage-pro` |
| `SF_HOST` | `config.py` | host of Grafana/VM/VL/VT/GlitchTip; `127.0.0.1` when they run on the same box |
| `GITHUB_TOKEN` | `filing.py`, `stale.py` | GitHub token (issues + labels read/write on the three repos) |
| `GLITCHTIP_TOKEN` | `sources.py` | GlitchTip API token, read access to org `homelab` |
| `GRAFANA_TOKEN`, or `GRAFANA_USER` + `GRAFANA_PASSWORD` | `sources.py`, `filing.py` | read firing alerts; write annotations |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | `observ.py` | optional tracing |
| `SF_STALE_NUDGE` | `stale.py` | `1` = the daily "looks resolved?" pass comments and labels; unset = dry run |

Present in the file but **not read by the fleet code** (as of 2026-10-02): `LITELLM_FLEET_TRIAGE_KEY`, `LITELLM_FLEET_BUGFIX_KEY` (the bug-fix fleet's), `GLITCHTIP_FLEET_DSN`, `UMAMI_RO_USER`, `UMAMI_RO_PASSWORD`.

Optional knobs, with their defaults:

| Knob | Default |
|---|---|
| `SF_RETRIAGE_HOURS` | 24 |
| `SF_MAX_PROBES` | 3 |
| `SF_DEFER_LIMIT` | 6 |
| `SF_ALERT_KEY_DEDUP` | on |
| `SF_OPS_REPO` | unset; the fallback repo is `chipi/agentic-ai-homelab` |
| `SF_TRIAGE_MILESTONE` | `triage` |

The paths can be overridden with `SF_LEDGER`, `SF_FILED_LEDGER`, `SF_QUEUE`, `SF_SPEND_FILE`, `SF_DEFER_STATE` and `SF_STALE_LAST_RUN`.

### `~/fleetd/fleetd.json` — the triage block

```json
{
  "name": "triage", "enabled": true, "interval": "10m",
  "cycle_cmd": "python3 orchestrator.py --cycle --limit 10 --no-dry-run",
  "workdir": "/Users/<user>/agentic-ai-homelab/signal-fleet/mvp",
  "env_file": "/Users/<user>/signal-fleet/fleet-gateway.env",
  "stop_flag": "/Users/<user>/signal-fleet/STOP",
  "budget_day_usd": 2.0,
  "spend_file": "/Users/<user>/signal-fleet/results/.last_cycle_spend",
  "stage": "propose", "cycle_timeout": "20m"
}
```

- **`stage`:** `shadow` (no external writes), `propose` (GitHub issues/comments), or `live`.
- **`--no-dry-run` alone does not make the cycle write.** `orchestrator.run_poll` forces a dry run whenever `FLEETD_STAGE=shadow`.
- **The repo copy** [`fleetd/deploy/fleetd.json`](https://github.com/chipi/agentic-ai-homelab/blob/main/fleetd/deploy/fleetd.json) can lag the live file; `make deploy` reports a difference and never overwrites the live config.

## 2. Install on a new host (or move off the mini)

Do it in this order. The ledgers are the part you can't recreate. Without them the fleet re-files every old problem as new.

1. **Freeze the old host** **[old host]**:
    - `touch ~/signal-fleet/STOP` and wait for the current cycle to end (`tail ~/fleetd/fleetd.log`);
    - then `sudo launchctl bootout system/com.homelab.fleetd`.

2. **Copy the state:** `rsync -a ~/signal-fleet/ newhost:~/signal-fleet/`. That covers `results/` (both ledgers and the state files), `queue/` and `fleet-gateway.env`. Check that the row counts match: `wc -l results/*.tsv` on both hosts.
3. **Clone the repo** **[new host]**: `git clone https://github.com/chipi/agentic-ai-homelab ~/agentic-ai-homelab`.
4. **Point the env file at the new environment:** set `SF_HOST` and `SF_OPENROUTER_URL` if the observability stack or LiteLLM live elsewhere. Then check that each credential works before going further:
    - `curl -s -H "Authorization: Bearer $GLITCHTIP_TOKEN" http://$SF_HOST:8090/api/0/projects/` returns a JSON list;
    - `gh api user` with `GITHUB_TOKEN` returns the account;
    - a `chat/completions` call to the gateway with the virtual key returns 200;
    - Grafana `GET /api/alertmanager/grafana/api/v2/alerts` returns 200.

5. **Prove the code on this host:** `cd ~/agentic-ai-homelab && bash signal-fleet/deploy/deploy.sh`. Every gate must say PASS. The gates read frozen corpora and git history only: no LLM, no network beyond the pull.
6. **Build and install fleetd** **[build machine]**:
    - `cd fleetd && make vet test build`;
    - for an Intel mini, `GOOS=darwin GOARCH=amd64` (see `make deploy`);
    - copy the binary to `~/fleetd/fleetd` and write `fleetd.json` (block above) with `"stage": "shadow"` first;
    - install the LaunchDaemon plist (same shape as today's: `/bin/bash -lc 'export PATH=/usr/local/bin:$PATH HOME=<home>; exec <home>/fleetd/fleetd -config <home>/fleetd/fleetd.json'`, `UserName` = the fleet user, `RunAtLoad`, `KeepAlive`, stdout/stderr → `~/fleetd/fleetd.log`);
    - `sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.fleetd.plist`.
   
    On Linux, the equivalent is a systemd service with `Restart=always`.

7. **Remove the STOP flag** (`rm ~/signal-fleet/STOP`). Watch two cycles in `~/fleetd/fleetd.log`: `cycle triage-…: ok`. Check that new ledger rows say `stage` = `shadow`.
8. **Promote to `propose`** once a shadow day looks right (§4 checks): edit `stage` in `fleetd.json`, then `sudo launchctl kickstart -k system/com.homelab.fleetd`.
9. **Surfaces:**
    - Grafana alert rules and dashboards are provisioned from [`infra/observability/backend/grafana/provisioning`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/observability/backend/grafana/provisioning);
    - after any rule change: `POST /api/admin/provisioning/alerting/reload`, then [`rules-drift/drift.py`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/observability/rules-drift/README.md) must report `drift: 0 rule(s)`.

10. **Retire the old host's daemon** for good. Remove its plist so two fleets never file at once: they would race on GitHub and each would have its own ledger.

## 3. Day-to-day operation

| Task | How |
|---|---|
| **Deploy a code change** | merge to `main`, then **[host]** `bash ~/agentic-ai-homelab/signal-fleet/deploy/deploy.sh`. It refuses a dirty checkout, pulls, runs every gate, and **rolls the checkout back** if one fails. New code runs on the next cycle; no restart. |
| **Gate-list caveat** | the first deploy after a change to `deploy.sh` runs the *old* gate list, because bash has already read the script. Run any new eval by hand once after that deploy. |
| **Roll back code** | **[host]** `git -C ~/agentic-ai-homelab reset --hard <prev sha>` (deploy.sh prints it) |
| **Pause the fleet** | **[host]** `touch ~/signal-fleet/STOP`; remove it to resume. `fleetd-silent` alerts after 35 min, on purpose. |
| **Change stage** | edit `stage` in `~/fleetd/fleetd.json`, then `sudo launchctl kickstart -k system/com.homelab.fleetd` |
| **Deploy or roll back fleetd itself** | `cd fleetd && make deploy` / `make rollback` (from the laptop; asks nothing, so get the operator's go first) |
| **Logs** | `~/fleetd/fleetd.log` (one line per cycle); cycle output also goes to VictoriaLogs (`service:fleetd`) |
| **Run one signal through by hand** | the operator asked for this once (2026-10-01). Run `run_glitchtip` from a small script with `sources.glitchtip_unresolved` filtered to one short id, `config.RETRIAGE_HOURS = 0`, the same env file, and `FLEETD_STAGE=propose`. Run it right after a cycle finishes so the two never write the ledger at the same time. |

Never edit a ledger while a cycle runs. Back it up first: `cp filed.tsv filed.tsv.bak-<date>-<reason>`.

### GlitchTip project recreated (same slug)

The new project's short ids restart at 1 and collide with the dead project's ledger rows, so a new error reopens an unrelated old issue. To fix it:

1. Pause the fleet, or work between cycles.
2. Back up `filed.tsv`.
3. Dry run: `python3 filing.py --retire-glitchtip-project <SLUG> <ISO time the new project was created> --dry-run`. Read the list.
4. Run it without `--dry-run`.
5. Re-close any issue the collision reopened, with a comment saying why.

## 4. The weekly review — "how is the fleet doing?"

Automated by the **`triage-fleet-review`** skill (`python3 ~/.claude/skills/triage-fleet-review/scripts/review.py --days 7`), which runs every check below read-only and flags fan-out, reopens and rollup burials for you to judge. For what never reaches the fleet (warnings, logs), add the **`o11y-review`** skill for the same window. Both skills live in [`workstation/claude/skills/`](https://github.com/chipi/agentic-ai-homelab/tree/main/workstation/claude/skills).

Run these read-only checks, then report in four parts: what it did, what went wrong, what it missed, what to improve. Each check states what "healthy" looks like.

1. **Is it alive?**
    - **Check:** the last cycle lines: `tail -20 ~/fleetd/fleetd.log`, plus alerts `fleetd-cycle-failing` / `fleetd-silent` in Grafana.
    - **Healthy:** `ok` every 10 min; daily spend well under $2 (`fleetd_spend_day`).

2. **What did it decide?**
    - **Check:** disposition counts for the week:
        ```sh
        awk -F'\t' -v s="$(date -u -v-7d +%F)" '$1>=s {print $4, $6}' \
          ~/signal-fleet/results/dispositions.tsv | sort | uniq -c
        ```
    - **Healthy:** escalations rare. Many `recurrence` rows for one fingerprint is now a bug: since `b3c4c5f` it writes one per count change, not one per cycle.

3. **What did it do on GitHub?**
    - **Check:** issues touched and fleet comments:
        ```sh
        gh api "repos/chipi/<repo>/issues?since=<7 days ago>&state=all"
        gh api "repos/chipi/<repo>/issues/comments?since=<7 days ago>"
        ```
        Filter comments for `Recurred` / `signal-fleet`.
    - **Look for:**
        - **fan-out:** several issues reopened at once for one condition (2026-10-01: six disk issues);
        - **wrong target:** a recurrence landing on a closed duplicate or on a different bug;
        - **burying:** a real bug as one line in a `[low-signal] aggregate`.

4. **False dismissals** (the one thing no dashboard checks): sample 3–5 recent `dismiss` rows (`awk -F'\t' '$6=="dismiss"' … | tail`). Check each one's cited evidence against GlitchTip or Grafana.
5. **What it cannot see:**
    - recurring WARNING patterns in VictoriaLogs (`_time:7d level:warning`) — warnings never reach the fleet;
    - new GlitchTip projects missing from `filing.REPO_MAP`.

6. **Ledger health:**
    - row counts and growth (`wc -l results/*.tsv`);
    - `.deferred.json` present = something is being deferred;
    - the open `triage-fleet/stale-candidate` issues waiting for the operator.

Turn each finding into one of three things:

- an issue action for the operator (close, mute, route);
- a fleet fix through §5;
- a known gap in the guide.

## 5. Improving the fleet — the loop every change follows

The generic version of this loop, with a replay scaffold, a mutation runner (`mutate.py`) and a baseline git worktree for non-Python projects, is the **`replay-proven-fix`** skill.

Since 2026-09-30 every behaviour change has gone through the same loop, and the next one should too. The operator's requirement is: *for each fix, a replayed test case with the input, today's output, the problem, and the output after the fix.*

1. **Find it in real data**, with counts: "10,764 of 11,700 recurrence rows repeat", not "lots of noise".
2. **Freeze the evidence** as a corpus under `signal-fleet/reference-*/`: ledger snapshots, GitHub issue states, GlitchTip payloads. Scrub secrets and user ids, and commit it. History moves on; a frozen corpus keeps the replay reproducible.
3. **Write the fix.** Prefer a deterministic rule over a prompt change.
4. **Write the replay** `mvp/eval_<thing>_replay.py`:
    - the **baseline** is the code at the commit before the fix, loaded with `git show <BASE_REV>:signal-fleet/mvp/<file>.py`, so the "before" is real, not re-implemented;
    - first assert that **the baseline reproduces history** (the replay is faithful);
    - then compare against the fix, with explicit pass criteria and exit 1 on failure.

5. **Mutation-check the replay:** break the fix in plausible ways and confirm each broken version fails the replay. A replay that passes broken code proves nothing. Two lessons:
    - 2026-10-02: a first disk replay passed a version that still fanned out, until a fan-out check was added;
    - a mutant can "fail" for the wrong reason (a syntax error from a bad `sed`), so read why it failed.

6. **Look at the changed cases themselves**, not only the totals, and judge them against **explicit links**, not titles. On 2026-10-02:
    - **a real catch:** a passing replay sent 13 recurrences into a low-signal bucket, so the rule was narrowed;
    - **a false alarm:** judging by titles, a later change looked like it routed closed bugs to *different* open bugs. GitHub's `duplicateOf` links showed most of those moves were correct, and one apparent mismatch was a GlitchTip short id reused by a different error. Check GitHub's duplicate links and the ledger row's own signal before calling a move wrong.

7. **Gate it:** add the replay to the gate list in [`signal-fleet/deploy/deploy.sh`](https://github.com/chipi/agentic-ai-homelab/blob/main/signal-fleet/deploy/deploy.sh), add unit tests to `mvp/test_units.py`, and run every gate locally.
8. **Commit with the numbers** in the message (input, before, after, mutation result). Push and deploy only with the operator's go.
9. **Verify live:** after deploying, prove the new behaviour on the real system. Either push one real signal through by hand (§3), or run the decision read-only against the live ledger and GitHub. "The replay passed" is not "it works in production".
10. **Update the guide:** a new rule goes under "Why it is built this way", a new limitation under "Known gaps".

### The gates today

| Eval | Guards |
|---|---|
| `eval_hardening.py` | the August 2026 flood: operational classes, fail-closed triager, test-signal suppression |
| `eval_dedup.py` | normalized dedup (norm_key) over a labelled corpus |
| `eval_filing_replay.py --cases-only` | the 2026-09-30 duplicate cases stay comments (alert_key #9) |
| `eval_stale_replay.py` | the "looks resolved?" nudge: who gets nudged, never wrongly |
| `eval_routing_replay.py` | prod-app alerts go to `podcast_scraper`; host/telemetry-dark alerts stay in homelab |
| `eval_triager_failure_replay.py` | triager failures never escalate per signal |
| `eval_glitchtip_litellm_replay.py` | retired GlitchTip rows stop colliding; upstream 429s are dismissed |
| `eval_recurrence_replay.py` | one recurrence row per count change (about 6 min on the mini) |
| `eval_open_preference_replay.py` | a norm_key match prefers the bug's open issue, never a rollup bucket |
| `eval_duplicate_follow_replay.py` | a recurrence on an issue closed as a duplicate goes to its canonical issue |
| `test_units.py` | unit tests (86 on 2026-10-02) |

Alert-rule changes have their own checks under [`infra/observability/rules-drift/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/observability/rules-drift):

- `test_drift.py`;
- `drift.py` (repo vs. live Grafana);
- replays such as `disk_pool_replay.py`, which runs both rule versions against VictoriaMetrics history.

## 6. Troubleshooting

| Symptom | Likely cause | Check / fix |
|---|---|---|
| every cycle fails, or one "triager unavailable" issue appears | LiteLLM virtual key wiped (a colima/DB recreate does this), or budget exhausted | gateway call with the key; recreate the `fleet-triage` key per the LiteLLM README and update `OPENROUTER_API_KEY` |
| GlitchTip or Grafana pass errors in the log | source token wiped by a recreate | re-issue `GLITCHTIP_TOKEN` / `GRAFANA_TOKEN`; test with curl (§2 step 4) |
| a new error reopens an unrelated old issue | GlitchTip project recreated under the same slug | §3 "GlitchTip project recreated" |
| one condition opens or reopens many issues | the alert rule fans out (labels too fine) | fix the **rule**, not the issues; replay the rule against VictoriaMetrics history |
| issues land in the wrong repo | routing: `REPO_MAP` (GlitchTip project prefix) or `INSTANCE_REPO_MAP` / the rule's `instance` label (Grafana) | `eval_routing_replay.py` covers the Grafana side |
| `fleetd-silent` fires | a forgotten `STOP` file, the daemon down, or the host down | `ls ~/signal-fleet/STOP`; `sudo launchctl print system/com.homelab.fleetd` |
| a deploy refuses | dirty checkout (often another session's uncommitted work) | find out whose change it is before touching it; never stash or discard someone else's work |
