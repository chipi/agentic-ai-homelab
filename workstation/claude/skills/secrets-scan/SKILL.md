---
name: secrets-scan
description: Scan for secrets (API keys, tokens, private keys, credentials, real .env files) before committing or pushing — enforces "never commit secrets". Prefers gitleaks if installed; otherwise uses high-signal patterns. Reports findings by file:line with the value redacted. Use before any commit/push, when adding config or fixtures, or whenever asked to check for leaked secrets. Read-only.
---

# secrets-scan

Catch secrets before they land in git. Enforces the non-negotiable: `.env`,
credentials, tokens, API keys — never in git, never in fixtures, never in a
commit message. **Read-only** — it never writes; it blocks by reporting.

## Run

```bash
~/.claude/skills/secrets-scan/scripts/scan.sh            # staged changes (what `git commit` would add)
~/.claude/skills/secrets-scan/scripts/scan.sh --push     # commits not yet on the upstream (what `git push` sends)
~/.claude/skills/secrets-scan/scripts/scan.sh --range origin/main..HEAD
~/.claude/skills/secrets-scan/scripts/scan.sh --tree [PATH]   # the working tree, no history
```

Run it from inside the repo.
- **With gitleaks:** gitleaks is used when installed, with ~200 provider rules. Findings are
  listed `file:line — rule (commit …)`, with values redacted.
- **Without it:** the script falls back to the same high-signal regexes as the hook below, and
  says so.
- **`.env`:** a real `.env` (not `.env.example`) in the change is a finding by itself.

It ends with `SECRETS SCAN: PASS/FAIL`, exit 1 on FAIL.

**The automatic net:** the `secrets-guard.sh` PreToolUse hook (`workstation/claude/hooks/`,
wired in `~/.claude/settings.json` since 2026-07-30) blocks a `git commit`/`git push` from
Claude whose change matches. Since 2026-10-17 it also runs gitleaks when installed. This script is
the on-demand report with file:line; `ship` runs it as its secrets gate.

Verified 2026-10-17:
- clean staged passes;
- a staged Stripe key, a bad commit range and a staged `.env` each FAIL with file:line or the
  file name;
- without gitleaks, the regex fallback FAILs on an AWS key;
- `--tree workstation/claude/skills` passes.

## Report

- End with `SECRETS SCAN: PASS` or `SECRETS SCAN: FAIL`.
- On FAIL, list each hit as `file:line — <rule>` with the value **redacted**
  (never echo the secret). Tell the operator to remove it AND rotate — a secret
  committed to git is compromised even if later deleted.
- Don't cry wolf on obvious placeholders: `buddy-is-the-king`, `hf_xxx…`,
  `<your-…>`, `${VAR}`, `changeme`, `example`, empty values. Note them as skipped.

## Conventions this enforces

- **Never commit secrets** (rule #29). If one ever lands, treat it as compromised
  and rotate immediately.
- `.env` stays gitignored; only `.env.example` with placeholders is tracked.
- Install gitleaks for real coverage; the pattern fallback catches the common
  shapes but is not exhaustive — say so when you use it.
