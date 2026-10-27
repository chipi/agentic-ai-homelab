---
name: deploy-verify
description: Before/after gate for a deploy's telemetry — snapshot before, then check that every service still logs with environment=prod, traces carry the deployed release, scrape jobs are up and counters have series, no GlitchTip issue appeared since the deploy (each new one listed with status), Langfuse app traces carry the release, Umami still receives events, and (orrery) every live JS file's debugId matches an uploaded source-map bundle. Ends with DEPLOY-VERIFY PASS/FAIL. Use when asked to "verify the deploy", "check telemetry after the release", "did anything break since the deploy", or "do source maps resolve".
---

# deploy-verify

After every deploy on 2026-10-16/17, someone wrote a fresh verify script per service by hand.
This is that script, once, for both projects. It is a **gate**: expected against live,
PASS/FAIL. `o11y-review` is a **review**: patterns and counts over a window. Use both:
- the gate first;
- then `o11y-review` for anything the gate flags.

## Run (on the mini, through host-run)

```bash
V=~/.claude/skills/deploy-verify/scripts/verify.py
R=~/.claude/skills/host-run/scripts/run.sh

$R homelab $V snapshot --project closelistening --out /tmp/cl-base.json     # before the deploy
# ...deploy, then let it serve traffic for a while (10+ minutes)...
$R homelab $V compare --project closelistening --baseline /tmp/cl-base.json --release sha-ded80e0
$R homelab $V compare --project orrery --since 2026-10-17T08:21:00Z --sourcemaps
```

- **Projects:** `closelistening` and `orrery`. The `PROFILES` table in the script lists each
  one's services, scrape jobs, counters, GlitchTip projects, Langfuse key file, Umami sites and
  live URL. Add a project there.
- **`--since`:** use it when there is no baseline, i.e. the time the new version went live.
- **`--release`:** the image tag the deploy shipped (`sha-<7>`, ADR-0010).
  - For podcast, run from the deploy's **image tag**, not the workflow commit. On 2026-10-16
    deploy-all ran from b0edbb9 and deployed `sha-ded80e0`.
  - orrery's web release is `gha-<short sha>` and isn't checked by this flag.

| Check | PASS means |
|---|---|
| logs | each service has prod lines since the deploy. Non-prod lines (dev runs) are INFO; lines with no environment label FAIL. |
| traces | each traced service has traces since the deploy, and `service.version` includes `--release` |
| metrics | every scrape job `up=1`; every listed counter has series over 2 days (`count_over_time`, not an instant query) |
| errors | **no** GlitchTip issue first seen since the deploy. Each new one FAILs the gate on purpose: someone has to look. Its status is shown. |
| langfuse | app traces since the deploy all carry `--release`. LiteLLM's own `litellm-*` traces are ignored. |
| umami | each site got events since the deploy, with the latest event's time. Zero events is INCONCLUSIVE while the time since the deploy is shorter than the quiet gap before it, from the site's last event to the deploy (sparse traffic: re-run `compare` later), and WARN once it is older. A failed Umami query is a FAIL, not "0 events" |
| sourcemaps | every live `_app/immutable` JS with a debugId has a stored GlitchTip bundle. Unmatched stubs under 1 KB are INFO. |

## Verified

**2026-10-17, podcast deploy `sha-ded80e0`** (since 2026-10-16 19:31):
- logs, traces, metrics and Langfuse passed;
- it FAILed on four new GlitchTip issues, three already known (the smoke alert, two reprocess
  issues);
- one **was not known**: `PLAYER-1I`, an Android `ForegroundServiceStartNotAllowedException`.
  The manual checks had missed it, and it was handed to the mobile session.

**orrery** (since 08:21):
- PASS, with 59 of 61 live JS files matched to bundles, the two map-less stubs as INFO, and
  dev lines from omarchy as INFO.

**Fixes made while testing:**
- Cloudflare 403s Python's default User-Agent, so the script uses a browser UA;
- `litellm-acompletion` traces are LiteLLM's own, so they're ignored;
- dev lines are INFO, not FAIL.

## Not covered

- **App behaviour** (user-facing smoke tests): the deploy workflows' own smoke steps do that.
- **The DGX services** (vLLM, pyannote): use `dgx-status` and `infra-drift`.
- **Release names:** GlitchTip release tags aren't checked, because orrery and podcast name
  them differently.
- **An unknown regression with no error:** the gate sees signals, not intent. Read the
  `o11y-review` output for warnings.
