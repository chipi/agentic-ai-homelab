---
name: secrets-scan
description: Scan for secrets (API keys, tokens, private keys, credentials, real .env files) before committing or pushing — enforces "never commit secrets". Prefers gitleaks if installed; otherwise uses high-signal patterns. Reports findings by file:line with the value redacted. Use before any commit/push, when adding config or fixtures, or whenever asked to check for leaked secrets. Read-only.
---

# secrets-scan

Catch secrets before they land in git. Enforces the non-negotiable: `.env`,
credentials, tokens, API keys — never in git, never in fixtures, never in a
commit message. **Read-only** — it never writes; it blocks by reporting.

## Scan (prefer a real scanner, else patterns)

1. **gitleaks** (preferred) — if installed:
   - staged / pre-commit: `gitleaks protect --staged --no-banner -v`
   - whole tree/history: `gitleaks detect --no-banner -v`
   If gitleaks isn't installed, say so and use the fallback.
2. **Pattern fallback** — over `git diff --cached` (staged) or the target diff.
   Redact the matched value in output. High-signal markers:
   - Provider keys: `sk-[A-Za-z0-9]{16,}`, `ghp_[A-Za-z0-9]{20,}`, `github_pat_`,
     `glpat-[A-Za-z0-9_-]{20,}`, `AKIA[0-9A-Z]{16}`, `AIza[0-9A-Za-z_-]{20,}`,
     `xox[baprs]-`, `sk-ant-`
   - Private keys: `-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----`
   - Generic assignments: `(api[_-]?key|secret|token|password|passwd|bearer|auth)`
     followed by `=`/`:` and a 16+ char value
3. **`.env` guard** — flag any real `.env` (not `.env.example`) being added:
   `git diff --cached --name-only | grep -E '(^|/)\.env$'`.

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
