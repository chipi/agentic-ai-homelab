# Runbook — mini box pruning: remove the desktop-era software

**Status: EXECUTED 2026-08-30** — all 12 vendors removed vendor-by-vendor
with health checks green after each (29 containers, page + grafana 200
throughout); ~8.7G freed (Adobe support 4.8G, Backblaze bzpkg 1.9G,
/opt/X11, apps, misc). `/Library/LaunchDaemons` now holds ONLY the four
`com.homelab.*` entries + `org.cindori.AuthHelper`; `/Library/LaunchAgents`
has zero third-party entries.

Deliberately KEPT (personal data / pending decision):
- `~/Library/Application Support/Adobe` (1.1G) — Photoshop/Lightroom prefs
  + a Digital Editions DRM folder; personal-data class, not daemon debris.
  Operator call whenever.
- `org.cindori.AuthHelper` (+ its `/Library/PrivilegedHelperTools` binary)
  — identified as the TRIM Enabler / Sensei privileged helper (app long
  gone, helper not running). Not on the approved list; awaiting a yes.

Original plan below, kept for the record. Operator approved removing ALL
of it ("not using it as a personal computer anymore") — including
Backblaze and CCC, cleared by the evidence below. Executed independent of
the colima window (needed no VM downtime).

**Method: one vendor at a time, verify between each.** For every vendor:
(1) unload+delete its launchd plists, (2) run its own uninstaller if one
exists (they clean kexts/helpers pkgutil knows about), (3) delete app +
`/Library/Application Support` + caches, (4) verify no process from that
vendor survives and the homelab stack is untouched (`docker ps` count,
page 200). Keep a log of what was removed.

## Evidence gathered 2026-08-30 (why each is safe to remove)

- **Backblaze** — last file transmitted **2024-08-04** (bzreports log);
  `bzserv` not running. It has backed up NOTHING in >2 years — removing
  it destroys no live backup path. (The homelab's real backups are the
  nightly DB dumps + the repo.)
- **Bombich CCC** — daemon plist exists but **no process and no
  `/Library/Application Support/com.bombich.ccc`** — the app is already
  gone; this is orphaned debris.
- Most others likewise: `/Applications` retains only **Adobe Digital
  Editions** ×2 from the whole list — everything else is daemon/agent
  debris of already-removed apps.

## Inventory (daemons D = /Library/LaunchDaemons, agents A = /Library/LaunchAgents)

| Vendor | Debris found | Uninstall path |
|---|---|---|
| Adobe | D: agsservice, SwitchBoard · A: AAM.Updater-1.0, AdobeCreativeCloud, GC.Invoker-1.0 · Apps: Digital Editions ×2 | unload plists; delete apps; `/Library/Application Support/Adobe`; `pkgutil --pkgs \| grep -i adobe` for receipts |
| Backblaze | D: com.backblaze.bzserv · `/Library/Backblaze.bzpkg` (1.9G) | bzpkg ships an uninstaller app (`/Library/Backblaze.bzpkg/BzUninstall...`); run it, then remove leftovers |
| Bombich CCC | D: com.bombich.ccc (orphan) | unload + delete plist; sweep `~/Library/Application Support/com.bombich*` if any |
| Fitbit | D: com.fitbit.galileod | unload + delete plist + `/Library/Application Support/Fitbit*` if any |
| Google | D: GoogleUpdater.wake.system, keystone.daemon · A: keystone.agent, keystone.xpcservice | `~/Library/Google/GoogleSoftwareUpdate/GoogleSoftwareUpdate.bundle/Contents/Resources/ksinstall --uninstall` if present, else unload + delete plists + `/Library/Google` |
| LaCie | D: desktopmanager.service · A: eventsactions.launcher.agent | unload + delete plists + `/Library/Application Support/LaCie*` |
| Logitech | A: vc.LogiVCCoreService *(found in recon; not on the original list — same treatment)* | unload + delete plist + support dirs |
| Microsoft | D: autoupdate.helper, office.licensingV2.helper · A: update.agent | unload + delete plists; keep ONLY if any MS Office use is expected (operator said no) |
| Sonos | D: com.sonos.smbbump | unload + delete plist |
| Wacom | D: displayhelper, UpdateHelper · A: DataStoreMgr, IOManager, wacomtablet | Wacom ships "Wacom Tablet Utility → Remove"; else unload plists + `/Library/Application Support/Tablet` + prefpane |
| XQuartz | D: privileged_startx · A: startx · `/opt/X11` | unload plists; `sudo rm -rf /opt/X11 /Library/Launch*/org.macosforge.xquartz.*` (canonical XQuartz removal) |
| **org.cindori.AuthHelper** | D only | **NOT on the approved list — identify first** (likely Sensei/CleanMyDrive helper), then ask before removing |

## Order & guardrails

1. Start with the pure-debris entries (CCC, Fitbit, Sonos, LaCie —
   nothing but a plist): tiny blast radius, builds the verification rhythm.
2. Then Google/Microsoft/Wacom/Logitech/XQuartz, then Adobe (most pieces),
   then Backblaze last (biggest footprint, has its own uninstaller).
3. After EACH vendor: `docker ps -q | wc -l` → 29, home page answers,
   `launchctl print system/<label>` errors (gone), no vendor process in `ps`.
4. Anything that resists or looks shared (a kext in use, a pkg receipt
   spanning vendors) → STOP and note it, don't force.
5. `org.cindori.AuthHelper` stays until identified + separately approved.

## Expected gain

Modest but real: ~10 fewer daemons/agents (RAM + periodic CPU wakeups +
update-checker network chatter + attack surface), ~2G+ disk (Backblaze
bzpkg 1.9G, Adobe apps, /opt/X11), and a box whose process list finally
matches its job.
