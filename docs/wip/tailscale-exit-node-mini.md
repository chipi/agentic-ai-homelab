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

## READ THIS FIRST — reboots, and the one way this runbook can break them

**Correction (2026-09-30).** The first version of this runbook said the mini's tunnel
only exists while the operator is logged in, so a reboot abroad would lose the exit
node and the remote lifeline. **That stopped being true on 2026-09-10**, and was
already false when this runbook was written. After the 2026-09-08 power cut left the
mini off the tailnet for 30 hours, the LaunchDaemon
`/Library/LaunchDaemons/com.homelab.tailscale-up.plist` was added: at boot it runs
[`infra/tailscale/tailscale-up.sh`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/tailscale/README.md), which drives the
root `macsys` network extension through the in-bundle CLI — no login needed.
Verified on the box 2026-09-30 (plist present; live script identical to the repo).

**The new risk this runbook itself introduces.** At boot, if the backend is not
already `Running`, the script runs `tailscale up --timeout=45s --accept-routes`.
`tailscale up` refuses to run unless *every* non-default setting is restated — the
script's own header documents this for `--accept-routes`. Once Step 1 saves
`--advertise-exit-node` as a preference, that command would be refused on every
retry; after 30 attempts (~25 min) the script gives up and the mini stays **off the
tailnet** — the 2026-09-08 failure, reintroduced by following this runbook.
(Reasoned from the documented `tailscale up` rule, not tested with a reboot.)

So **Step 1 changes the boot script in the same commit** as it advertises the exit
node, and Rollback reverts both. Never "fix" a refused `tailscale up` with
`--reset`: that silently drops `--accept-routes` too.

What still applies abroad: a **power cut** stops everything until power returns,
and nothing outside the house would notice. Enable the exit node and *verify it
works* before you need it, not during.

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

## Step 1 — advertise (on the mini), and keep the boot script in step

**1a. In the repo first**, restate the new flag in
`infra/tailscale/tailscale-up.sh` and update its header note:

```sh
"$TS" up --timeout=45s --accept-routes --advertise-exit-node 2>&1
```

Commit, push, and `git pull` the mini's checkout — the LaunchDaemon runs the
script straight from `~/agentic-ai-homelab`, so the pull is the deploy.

**1b. Then on the mini:**

```sh
/Applications/Tailscale.app/Contents/MacOS/Tailscale set --advertise-exit-node
```

GUI equivalent if the CLI is refused: menu-bar Tailscale → **Run as Exit Node**.
(Use the in-bundle binary above. `/usr/local/bin/tailscale` is a shim that fakes
success and exits 0 on everything else.)

Do 1a before 1b: in the other order there is a window where a reboot would strand
the mini off the tailnet.

**1c. Prove the boot path still works**, without rebooting. Kickstarting the
LaunchDaemon is *not* a test: when the node is already `Running` the script exits
before it reaches `tailscale up`. Run the script's `up` command by hand instead:

```sh
TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
# the OLD boot command must now be refused (a refused `up` changes nothing):
sudo "$TS" up --timeout=45s --accept-routes;  echo "exit=$?"   # want: non-zero, "non-default flags"
# the NEW boot command must succeed (all flags restated = no change):
sudo "$TS" up --timeout=45s --accept-routes --advertise-exit-node;  echo "exit=$?"   # want: 0
```

If the first command *succeeds*, the rule does not apply as expected, and that
command has just cleared `--advertise-exit-node` — re-run 1b, and re-check before
trusting the reboot path. The boot script logs to
`/tmp/tailscale-up.log` (the plist's `StandardOutPath`).

Advertising is harmless on its own — nothing routes through it until a client
selects it *and* the ACL permits it.

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

**Then revert Step 1a** — take `--advertise-exit-node` back out of
`infra/tailscale/tailscale-up.sh`, commit, and pull on the mini. Otherwise the next
boot that reaches `tailscale up` would accept the extra flag and **silently turn the
exit node back on** — `tailscale up` only refuses when a saved setting is *omitted*,
not when one is added. Verify with the 1c check, flags swapped: `up` *with*
`--advertise-exit-node` is now the one that must be refused.

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
