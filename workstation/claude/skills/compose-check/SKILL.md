---
name: compose-check
description: Pre-deploy sanity check for Docker Compose stacks. Validates each compose file with `docker compose config` (read-only), then flags undefined interpolation variables and missing .env before the stack is brought up. Use before `docker compose up`, when editing a compose file, or whenever asked to validate or check a compose stack. Never brings stacks up or down.
---

# compose-check

Catch a broken compose stack *before* `docker compose up`, not after. Validates
syntax, interpolation, and env wiring — strictly **read-only**. This skill never
runs `up`, `down`, `pull`, or anything that mutates a stack or shared state.

## When this applies

Editing a `docker-compose*.yml` / `compose.ya?ml`, or about to deploy one, or
asked to "check / validate the compose stack." Cheap; run it whenever in doubt.

## Check each stack

1. **Find stacks** — `docker-compose.yml`, `docker-compose.*.yml`, `compose.yml`,
   `compose.yaml` (skip dated backups like `*.yml.<date>`). If none, say so.
2. **Validate structure, then classify** — for each file:
   ```bash
   docker compose -f <file> config -q
   ```
   A fresh checkout usually has no `.env` (gitignored, present only on the deploy
   host), so separate "not ready" from "broken":
   - **exit 0** → structure + interpolation valid → **PASS**
   - **fails *only* with `env file ... not found`** → the YAML is fine, the stack
     just needs an `.env` absent from this checkout → **ENV-MISSING** (warn, name
     the exact path). Not a defect.
   - **any other error** (YAML parse, `additional property`, bad interpolation,
     `required variable is missing`) → **FAIL** — surface the message.
3. **Undefined interpolation** — grep for `${VAR}` used *without* a default or
   required marker (`${VAR:-default}` / `${VAR:?msg}`). Any bare `${VAR}` not set
   in the environment or an `.env` becomes an empty string at runtime. List them.
4. **Env readiness** — collect every `.env` path the stacks declare (top-level
   `--env-file`, service `env_file:`) and report which exist vs are missing. When
   a stack is ENV-MISSING and a sibling `.env.example` exists, the fix is
   `cp .env.example .env` (then fill secrets) — say that explicitly.

## Report

- Show full command output; end with one line per stack:
  `COMPOSE CHECK <stack>: PASS | ENV-MISSING | FAIL`.
- On FAIL, name the defect (the YAML error or the undefined `${VAR}`), not just
  the exit code. On ENV-MISSING, name the `.env` to create and the `.env.example` to copy from.

## Conventions this enforces

- **Read-only.** Validation only. Bringing stacks up/down, pruning volumes
  (`down -v`), or pulling images is out of scope and each needs explicit
  human approval anyway.
- **Never commit `.env`.** Secrets live in `.env`, which stays gitignored. If a
  stack needs new vars, document them in an `.env.example`, not the real file.
- **Run stacks in place.** Don't copy composes out to a scratch dir to check
  them — validate them where they live so the right `.env` and relative paths
  resolve.
