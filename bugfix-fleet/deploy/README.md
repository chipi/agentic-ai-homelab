# bugfix-metrics — launchd unit

Runs [`../run-metrics.sh`](../run-metrics.sh) every 120s (`StartInterval`) and
exits. Pushes bugfix-fleet counters to VictoriaMetrics.

Was a LaunchAgent, so it only ran once someone logged in. It is a LaunchDaemon
now — see [`../../infra/tailscale/README.md`](../../infra/tailscale/README.md)
for the 30h outage that motivated moving every host service off LaunchAgents.

## Expect one or two failed runs immediately after boot

`RunAtLoad` fires before DNS is necessarily up, and the script talks to
`api.github.com`:

```
cause: [TypeError: fetch failed]
  Error: getaddrinfo ENOTFOUND api.github.com  errno: -3008
```

Measured on the 2026-09-10 reboot test: runs 1 and 2 exited 1, run 3 exited 0
about four minutes after boot. `StartInterval` retries, so this self-corrects
and needs no intervention. As a LaunchAgent it never showed up, because login
always happened long after the network settled.

Only worth investigating if `last exit code` is still 1 well beyond a few
minutes past boot:

```sh
sudo launchctl print system/com.homelab.bugfix-metrics | grep -E 'runs|last exit code'
tail /tmp/bugfix-metrics.log
```

## Install

```sh
sudo cp com.homelab.bugfix-metrics.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.homelab.bugfix-metrics.plist
sudo chmod 644 /Library/LaunchDaemons/com.homelab.bugfix-metrics.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.bugfix-metrics.plist
```
