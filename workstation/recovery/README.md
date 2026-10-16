# recovery — the tiny encrypted recovery bundle

The workstation is rebuilt from this repository, the project repositories, and fresh
logins. What none of those can reproduce is a small amount of machine-local state:
untracked project `.env` files, local overrides, a few configs. `wb-recovery` puts
exactly that, and nothing else, into one client-side encrypted file that is kept
**off the machine**. It is not a home-directory backup and never includes caches,
Docker state, dependencies, build products, tokens or session state.

## Public / private boundary

| Public (this repo) | Private (never committed) |
|---|---|
| `wb-recovery` (mechanism), `manifest.example.tsv` (schema, placeholders), tests, this README | `~/.config/wb-recovery/manifest.tsv` (the real paths, mode 0600), the bundles, the passphrase |

`.gitignore` refuses `*.tar.gpg`, sidecars, partials and a `manifest.tsv` next to the
tool, as a second line of defence.

## Manifest

Tab-separated `CLASS<TAB>PATH<TAB>NOTE` (see `manifest.example.tsv`):

| Class | In the bundle | Meaning |
|---|---|---|
| `REQUIRED_PRIVATE` | yes | unique, needed to resume work; missing, a symlink or not a regular file stops the backup |
| `OPTIONAL_PRIVATE` | yes | unique and useful; missing is skipped with a warning |
| `CODIFIED` | no | reproducible from a repository |
| `REAUTH` | no | recreated by logging in (SSH keys, `gh`, Claude/Codex/OpenCode auth, Tailscale identity) |
| `REPRODUCIBLE` | no | rebuilt by tools |
| `EXCLUDED` | no | deliberately not kept (generated files) |

The non-included classes are never read; they make the decision auditable. A
directory entry adds every regular file below it and is refused if anything inside is a
symlink or special file. Symlinks are never followed.

## Encryption and the passphrase

GnuPG symmetric OpenPGP: AES-256, iterated and salted SHA-512 key derivation, with
OpenPGP's integrity protection. The passphrase is typed at gpg's own terminal prompt
(`--pinentry-mode loopback`), so it never appears in argv, shell history or this tool's
output, and it never opens a GUI prompt on a screen the remote operator cannot see.
Agent caching is off (`--no-symkey-cache`): every decryption proves the passphrase is
known.

**The passphrase must survive the machine.** Choose it once and keep it in two places
off the workstation (a password manager on another device, and paper in a safe place).
Without it the bundle is unreadable; with it, the bundle plus this repository restores
the unique state on any Linux machine with GnuPG.

## Commands

```bash
wb-recovery inventory                       # metadata + sha256 of every included file, never contents
wb-recovery backup -o <dir>                 # <dir>/wb-recovery-<host>-<UTC>.tar.gpg (+ .sha256), both 0600
wb-recovery verify <bundle> [--sha256 <h>]  # decrypt in memory; every entry's sha256/mode/size vs. the embedded manifest
wb-recovery restore-plan <bundle>           # extract into a fresh 0700 dir under $XDG_RUNTIME_DIR (tmpfs) and print a plan
wb-recovery discard <dir>                   # remove a restore dir it created
```

- `backup` streams `tar` straight into `gpg`; no plaintext archive touches disk. The
  only staged file is the metadata manifest, in a private dir that is removed on success,
  failure or interrupt. A file that changes while it is read voids the backup.
- `verify` fails on a wrong passphrase, any corruption or tampering (encrypted
  sha256, OpenPGP integrity), and any difference between the embedded manifest and the
  contents (hash, mode, size, missing or extra entries).
- `restore-plan` never writes outside its own new directory; it refuses a non-empty
  target and `/`, verifies what it extracted, and prints `install -D -m <mode> …` lines
  for files that are missing or differ on the live machine. You run the lines you want.

## Off-machine copy (the X3 and its Mac)

The X3 does not trust the Mac's SSH host key, and nothing here changes SSH trust. The
Mac already reaches the X3, so the Mac pulls:

```bash
# on the Mac
mkdir -p ~/X3-recovery && chmod 700 ~/X3-recovery
scp 'omarchy:<bundle path>' 'omarchy:<bundle path>.sha256' ~/X3-recovery/
cd ~/X3-recovery && shasum -a 256 -c "$(basename '<bundle path>').sha256"
```

To prove the off-machine copy, not the original, restores: push the Mac's copy back to
a fresh path on the X3 and run `verify` and `restore-plan` on that file.

## Fire test

X3 destroyed: install Linux, clone this repo, run `install.sh`, log in again (GitHub,
Tailscale, agents), clone the projects, copy the bundle from the Mac, then
`wb-recovery restore-plan <bundle>` and install the files it lists. What the bundle
does not cover is listed per class in the private manifest; anything only in a running
process or uncommitted in a repository is out of scope by design.

## LUKS header and recovery keyslot (not part of this bundle)

A LUKS header backup only repairs the same physical disk; if the disk is destroyed it is
useless, and it lets anyone with an old passphrase open that disk. Keep it apart from
this bundle: one encrypted file per disk, stored off-machine, replaced whenever a
keyslot changes. A second recovery keyslot (a long random passphrase kept like the
bundle passphrase) protects against a forgotten passphrase on the working disk. Both are
separate, deliberate changes, not done by this tool.

## Tests

`bash workstation/recovery/wb-recovery.test.sh`: synthetic secrets only, scratch HOME,
GNUPGHOME and runtime dir. Covers inclusion/exclusion, fail-closed on missing or
symlinked required files and on symlinks inside directories, exact embedded metadata,
OpenPGP format, no secret in the encrypted bytes or in any output, wrong passphrase,
flipped byte and truncation, forged manifests (lying hash, extra entry), restore into a
private tmpfs dir with preserved modes, never touching live files, refusing non-empty
targets and `/`, no plaintext staging left after success or failure, and that nothing
enters the repository.
