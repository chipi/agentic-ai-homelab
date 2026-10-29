# hetzner-status — Hetzner bulletins into Grafana

Hetzner has no alerts API. It publishes incidents and maintenance on
<https://status.hetzner.com/>, with an Atom feed at `https://status.hetzner.com/en.atom`. `poll.py`
reads that feed every 10 minutes on the mini and writes one event per new or updated bulletin to
VictoriaLogs, so bulletins can be searched, shown and alerted on like any other log.

## What lands where

- **VictoriaLogs**, stream `app=hetzner-status, service=hetzner-status, environment=operations,
  instance=homelab`. One line per bulletin update, `_time` = the bulletin's `updated`. Fields:

  | field | meaning |
  |---|---|
  | `title`, `summary`, `link` | the bulletin |
  | `category` | Hetzner's category: a datacenter (`FSN1-DC22`) or a service (`Cloud Server`, `Network`, `General`) |
  | `location` | the matching one of our locations, if any |
  | `affects` | `ours` (category names nbg1 = prod-podcast, or fsn1 = audio Storage Box), `service` (a service we use), `other` |
  | `kind` | `maintenance` (title says so) or `incident` |
  | `start`, `end` | from the bulletin text, when given |
  | `backfill` | `true` for what was already in the feed on the first run; those never alert |

- **VictoriaMetrics**: `hetzner_status_poll_ok`, `hetzner_status_last_success_timestamp`,
  `hetzner_status_feed_entries{affects}`.

- **Alerts** (`rules.yaml`, group `hetzner-status`, `meta="true"`: email to the operator, not the
  triage fleet): `hetzner-status-ours`, `hetzner-status-service`, `hetzner-status-poller-stale`.
- **Dashboard**: Production Infra → "Hetzner status bulletins" (uid `hetzner-status`).

## Your own alerts

Any LogsQL over the fields above works as a Grafana rule on the `victorialogs` datasource, e.g. only
maintenance in nbg1:
`app:hetzner-status location:~"^NBG1" kind:maintenance backfill:false | stats by (title, start, link) count() as value`.

## Configuration

Environment, all optional: `HETZNER_LOCATIONS` (default `NBG1,FSN1`; a category equal to one, or
`<LOC>-<dc>`, is `ours`), `HETZNER_SERVICES` (comma list of category names counted as `service`),
`POLL_INTERVAL` (600 s). If prod moves location (infra/terraform `location`), update
`HETZNER_LOCATIONS`.

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
backfill again.

Tests: `python3 -m pytest test_poll.py` (stdlib only at runtime; pytest only for the tests).
