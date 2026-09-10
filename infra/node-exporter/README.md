# node-exporter — host metrics for the mini

Prometheus `node_exporter` on `:9100`, scraped by [`mini-metrics`](../mini-metrics/README.md)
and pushed to VictoriaMetrics as `node_*`. Installed via Homebrew
(`/usr/local/opt/node_exporter`); this directory owns only the **launchd** unit.

Brew installs its service as a **LaunchAgent**, which dies with the login window.
When the mini rebooted unattended on 2026-09-09 this never came back, taking ~405
`node_*` series with it — the host was blind while every container looked healthy.
It runs as a LaunchDaemon here for that reason.

## Install

```sh
sudo cp homebrew.mxcl.node_exporter.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/homebrew.mxcl.node_exporter.plist
sudo chmod 644 /Library/LaunchDaemons/homebrew.mxcl.node_exporter.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/homebrew.mxcl.node_exporter.plist
```

If `brew services` was used previously, unload the agent first or you get two
copies bound to `:9100` and the second fails to listen.

## Verify

```sh
curl -s localhost:9100/metrics | head -3
```
