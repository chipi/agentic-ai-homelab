# caffeinate — keep the mini awake

`caffeinate -dimsu` held open for the life of the machine: no display, idle, disk
or system sleep. The mini is a 24/7 host; a sleeping host stops scraping, stops
serving the tailnet, and looks identical to a dead one.

Belt-and-braces with `pmset` (`sleep 0`, `disksleep 0`). Keep both — `pmset` is the
policy, this is the assertion that survives something re-enabling it.

Was a LaunchAgent, so it only applied once someone logged in. Now a LaunchDaemon.

## Install

```sh
sudo cp com.homelab.caffeinate.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.homelab.caffeinate.plist
sudo chmod 644 /Library/LaunchDaemons/com.homelab.caffeinate.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.caffeinate.plist
```

## Verify

```sh
pmset -g assertions | grep -i caffeinate
```
