# tailscale — keep the mini's own node on the tailnet without a login

The mini runs the **macsys** Tailscale (notarised app bundle). Its tunnel is
started by the GUI app, which lives in a user login session. The mini boots to
the login window, so on an unattended reboot the host never rejoins the tailnet.

That is not theoretical. On **2026-09-08 14:21 UTC** the mini lost power. The
LaunchDaemons brought all 29 containers back **81 seconds** after it was powered
on again — but `homelab` itself stayed off the tailnet for **30 hours**, so SSH
and everything addressing the host directly (Umami ingest on `:3001`) were dead,
while the per-service Caddy tailnet nodes (`grafana.`, `vm.`, …) looked perfectly
healthy and hid the problem.

`tailscale-up.sh` drives the **root network system extension** through the
in-bundle CLI, which needs no session. Retries while the network settles.

## Install

```sh
sudo cp com.homelab.tailscale-up.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.homelab.tailscale-up.plist
sudo chmod 644 /Library/LaunchDaemons/com.homelab.tailscale-up.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.tailscale-up.plist
```

## Two traps

- **Use the in-bundle binary**, `/Applications/Tailscale.app/Contents/MacOS/Tailscale`.
  `/usr/local/bin/tailscale` is a **shim** that only fakes `tailscale ip` and
  `exit 0`s everything else — failures there are silent.
- **`--accept-routes` must be restated.** `tailscale up` refuses to run unless every
  non-default flag is repeated, and it will tell you to use `--reset`. Do not:
  `--reset` drops the saved preference. Restate the flag instead.

Verify from another tailnet host — `rx` must be non-zero, not just `tx`:

```sh
tailscale status | grep homelab
tailscale ping homelab
```
