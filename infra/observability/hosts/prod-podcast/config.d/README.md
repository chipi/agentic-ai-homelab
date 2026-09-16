# prod-podcast `config.d` — where the real files live

**Nothing in this directory is deployed from this repo.** The Alloy drop-ins that
actually run on `prod-podcast` are owned and shipped by `podcast_scraper`:

| file | source |
|---|---|
| `base.alloy` | `podcast_scraper:infra/observability/base.alloy` |
| `selfmon.alloy` | `podcast_scraper:infra/observability/selfmon.alloy` |
| `player.alloy` / `operator.alloy` / `litellm.alloy` | `podcast_scraper:infra/observability/` |

All are deployed by `podcast_scraper:.github/workflows/deploy-config.yml`
(scp → stage → atomic rename → `docker kill -s HUP alloy`). No root required.

## Why `base.alloy` was removed from here

It sat here as a **mirror** that no deploy path shipped, and that is exactly how it
broke. The box copy was hand-edited over SSH as root — twice; the `.bak-<timestamp>`
siblings on the box are the fingerprint — while this copy was edited separately and
never shipped. The two silently diverged by 41 lines, so this repo described a
production that did not exist: a reader would reasonably conclude prod did W3C/Sentry
trace-ID extraction into structured metadata and collected the widened cadvisor
keep-list (PSI pressure, cpu user/system split, scrape errors). It did neither.

A second copy with no deploy path is not documentation — it is a claim nobody checks.
One file, one owner, one deploy path.

## The unshipped work is not lost

The larger variant — `loki.process.homelab_std` trace-ID extraction plus the widened
cadvisor keep-list — is preserved in this repo's history at commit `4407569`:

```bash
git show 4407569:infra/observability/hosts/prod-podcast/config.d/base.alloy
```

It lands deliberately as a follow-up, through the `podcast_scraper` deploy loop, and
only **after** the byte-identical adoption of the running config is proven green. That
ordering is the point: adopt with zero behaviour change first, so any failure identifies
the pipeline rather than the content; then change behaviour through a pipeline already
known to work.

Context: `chipi/agentic-ai-homelab#64`.
