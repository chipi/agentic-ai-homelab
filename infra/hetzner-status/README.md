# hetzner-status — Hetzner bulletins, correlated with our infra

Hetzner has no alerts API. It publishes incidents and maintenance on
<https://status.hetzner.com/>, with an Atom feed at `https://status.hetzner.com/en.atom`. `poll.py`
reads that feed every 10 minutes on the mini, correlates each bulletin with where prod runs
(`ours.json`), and writes it to VictoriaLogs; bulletins that are relevant now also become a metric
the hub page shows as a banner.

## Correlation (`ours.json`)

| relevance | when | alerts | hub banner |
|---|---|---|---|
| `direct` | our exact datacenter (`NBG1-DC3`, prod-podcast), a whole-location bulletin for the server's location (`NBG1`), or text that names one of our datacenters | yes | red, ongoing or starting within 7 days |
| `nearby` | same city, other or unknown datacenter: other `NBG1-*`, and `FSN1` (the audio Storage Box; its datacenter is not known) | no | amber, ongoing or starting within 7 days |
| `service` | a Hetzner service we use (`Cloud Server`, `Network`, `Storage Box`, …), not tied to a place | no | grey, only while ongoing |
| `other` | everything else | no | no |

"Ongoing" = started and not ended; a bulletin without an end counts as ongoing for 72 h after its
start (Hetzner rarely posts one and leaves notices in the feed for months). If prod moves
(chipi/infra `infra/terraform` `location`), or the Storage Box's datacenter becomes known, edit
`ours.json`. The server's datacenter comes from its metadata:
`curl -s http://169.254.169.254/hetzner/v1/metadata/availability-zone` on the box.

## What lands where

- **VictoriaLogs**, stream `app=hetzner-status, service=hetzner-status, environment=operations,
  instance=homelab`. One line per bulletin update; `_time` = when the poller saw it (the bulletin's
  own time is the `updated` field; using it as `_time` would drop old-but-current notices, which
  fall outside VictoriaLogs' retention). Fields: `title`, `summary`, `link`, `category` (a
  datacenter like `FSN1-DC22` or a service), `location` (the matching category), `relevance`,
  `kind` (`maintenance` if the title says so, else `incident`), `start`, `end`, `backfill`
  (`true` = already in the feed when watching started; never alerts). Lines written before
  2026-10-29 16:00Z carry the older `affects` field instead of `relevance`.
- **VictoriaMetrics**: `hetzner_status_poll_ok`, `hetzner_status_last_success_timestamp`,
  `hetzner_status_feed_entries{relevance}`, and `hetzner_status_active{relevance, phase
  (ongoing|upcoming), kind, category, title, start, end, link} 1` for the banner-worthy bulletins,
  re-pushed every poll (read it with `last_over_time(…[15m])`).
- **Alerts** (`rules.yaml`, group `hetzner-status`, `meta="true"`: email to the operator, not the
  triage fleet): `hetzner-status-ours` (a new or updated `direct` bulletin),
  `hetzner-status-poller-stale`.
- **Hub page**: a Hetzner bar at the top while `hetzner_status_active` has a series.
- **Dashboard**: Production Infra → "Hetzner status bulletins" (uid `hetzner-status`).

## Your own alerts

Any LogsQL over the fields above works as a Grafana rule on the `victorialogs` datasource, e.g.
nearby maintenance too:
`app:hetzner-status relevance:in(direct, nearby) kind:maintenance backfill:false | stats by (title, start, link) count() as value`.

## Install / update (run-in-place, like ci-ops-poller)

```sh
sudo cp com.homelab.hetzner-status.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.homelab.hetzner-status.plist
sudo chmod 644 /Library/LaunchDaemons/com.homelab.hetzner-status.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.hetzner-status.plist
```

It is one long-lived loop: after a `git pull`, restart it with
`sudo launchctl kickstart -k system/com.homelab.hetzner-status`. Log: `/tmp/hetzner-status.log`.
`state.json` (gitignored) holds the bulletin ids already sent; deleting it makes the next run a
backfill again (`HETZNER_BACKFILL=1` forces one). Optional environment: `POLL_INTERVAL` (600 s),
`HETZNER_UPCOMING_DAYS` (7), `HETZNER_OPEN_ENDED_HOURS` (72).

Tests: `python3 -m pytest test_poll.py` (stdlib only at runtime; pytest only for the tests).
