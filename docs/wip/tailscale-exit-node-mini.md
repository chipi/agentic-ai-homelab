# Runbook — Mac mini as a Tailscale exit node (NL egress)

**Status:** prepared 2026-09-02, **not executed**. Prepared from a remote network
where TCP to the tailnet would not establish, so every "current state" line below
is marked verified or unverified — check the unverified ones on the box first.

## Why

Operator travels and occasionally needs to reach **Dutch government sites that
accept NL-only traffic**. Routing the phone through the mini puts that traffic on
the home *residential* connection — which is the right shape for this, since those
sites typically reject datacenter/commercial-VPN ranges. Exceptional, on-demand
use: the exit node is a switch to flip when needed, not a default route.

Chosen host: **the mini** (`homelab`, `tag:homelab-host`, 100.87.33.61). Not the
DGX — that box carries production ASR/GPU work and should not route browsing.
Both sit behind the same home line anyway, so the egress IP is identical; the
choice is about which machine is safe to burden.

## READ THIS FIRST — the travel risk

**The mini's tailnet tunnel only exists while the operator is logged in.** It runs
the `macsys` (standalone) Tailscale app with **no boot daemon**; a login-less
reboot loses the tailnet path entirely. See
[`mac-mini-headless-server.md`](mac-mini-headless-server.md) — the headless
`tailscaled` swap is a known PAUSED item.

Consequence for this feature: if the mini reboots while you are abroad, you lose
the exit node **and** the ability to fix it remotely, because the same tunnel is
the remote lifeline. Do not rely on this as your only route to a
time-critical government deadline. Flip it on and *verify it works* before you
need it, not during.

Fixing that properly = finishing the paused headless swap. Out of scope here.

## Prerequisites (verify on the box)

| Check | Expected | Status |
|---|---|---|
| Tailscale variant | **`macsys` = standalone** | **verified via repo notes** — this matters: the Mac App Store variant (`macos`) is sandboxed and does **not** support advertising an exit node. Standalone does. |
| `tailscale version` | ≥ 1.60ish | unverified — could not SSH |
| IP forwarding | `net.inet.ip.forwarding = 1` | unverified — macOS needs OS-level forwarding for exit-node function |
| Node tag | `tag:homelab-host` | verified from ACL + status |

```sh
# on the mini
/Applications/Tailscale.app/Contents/MacOS/Tailscale version
sysctl net.inet.ip.forwarding          # want: 1
```

If forwarding is 0:

```sh
sudo sysctl -w net.inet.ip.forwarding=1
# persist across reboot:
echo 'net.inet.ip.forwarding=1' | sudo tee -a /etc/sysctl.conf
```

## Step 1 — advertise (on the mini)

```sh
/Applications/Tailscale.app/Contents/MacOS/Tailscale set --advertise-exit-node
```

GUI equivalent if the CLI is refused: menu-bar Tailscale → **Run as Exit Node**.

Turn it back off any time with `--advertise-exit-node=false`. Advertising is
harmless on its own — nothing routes through it until a client selects it *and*
the ACL permits it.

## Step 2 — approve it (admin console, one click)

`autoApprovers` is deliberately empty in the ACL:

```json
"autoApprovers": { "routes": {}, "exitNode": [] },
```

with the comment *"manual approval for any new tagged device, slowing down the
bad-key compromise path."* **Keep it that way.** Approve the mini once by hand at
Admin console → Machines → `homelab` → **Edit route settings → Use as exit node**.

(You *could* add `"exitNode": ["tag:homelab-host"]` to auto-approve, at the cost
that anyone who compromised a key and minted a `tag:homelab-host` device could
self-approve as an exit node. One manual click is cheaper than that risk.)

## Step 3 — ACL grant (podcast_scraper repo, GitOps)

The tailnet policy lives at **`tailscale/policy.hujson` in `chipi/podcast_scraper`**
(not this repo) and ships via that repo's GitOps action. The ACL is implicit-deny
with narrowly scoped port grants, and there is currently **no `autogroup:internet`
rule at all**, so exit-node traffic is denied by default today.

Add one rule inside `"acls"` — suggested placement right after the existing
`autogroup:admin → tag:homelab-host:...` grant (~line 216):

```json
,
{
  // Exit-node egress. Lets the operator's own devices (phone/laptop) route
  // internet traffic through an approved exit node — the mini, for NL-only
  // government sites while travelling. `autogroup:internet` is the special
  // exit-node destination; it does NOT grant tailnet-internal access beyond
  // the per-port rules above. Scoped to autogroup:admin deliberately: no
  // tagged/CI identity should ever egress through home.
  "action": "accept",
  "src":    ["autogroup:admin"],
  "dst":    ["autogroup:internet:*"]
}
```

Scoping note: `autogroup:admin` covers the operator's own devices (the phone
`iphone-15-pro` is owned by the operator account, not tagged). No tag is granted
egress, so CI runners and service nodes cannot route through the house.

## Step 4 — use it (iPhone)

Tailscale app → **Exit Node** → select `homelab`. Toggle off to stop.
There is no "on demand" rule needed; leave it off and select it only when a
NL-only site requires it.

## Verify

```sh
# 1. the mini is offering it
/Applications/Tailscale.app/Contents/MacOS/Tailscale status --json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["ExitNodeOption"])'   # want: True

# 2. from the phone, with the exit node selected, load an IP-echo page.
#    Want: the HOME public IP, geolocating to NL — not the mobile carrier's.
```

Confirm the home line's egress IP really does geolocate to the Netherlands
**before** relying on it — that is the entire premise and it has not been checked.

## Rollback

```sh
/Applications/Tailscale.app/Contents/MacOS/Tailscale set --advertise-exit-node=false
```

Plus revert the ACL rule if you want egress denied at the policy layer too. The
approval in the admin console can be left in place; it does nothing while the node
is not advertising.

## Expected performance

Every request becomes phone → NL mini → site → back. Measured from the operator's
current location, European Tailscale relays sit at **~240ms**, and no direct path
was available (all traffic relayed). Assume noticeable sluggishness and that home
*upload* bandwidth is the ceiling. Fine for form-filling on a government portal;
not a general browsing mode.

## NOT verified

- Tailscale version and `net.inet.ip.forwarding` on the mini — TCP to the tailnet
  would not establish from the preparing network (`tailscale ping` succeeded via
  the Amsterdam relay, but SSH/HTTPS to every tailnet host timed out).
- Whether the home egress IP geolocates to NL (the premise of the whole exercise).
- Whether any specific government site accepts it.

Sources: [Tailscale exit nodes](https://tailscale.com/docs/features/exit-nodes) ·
[macOS variants](https://tailscale.com/docs/concepts/macos-variants)
