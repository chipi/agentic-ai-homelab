# AGENTS.md — <project-name>

This file layers on top of the global `~/.config/opencode/AGENTS.md`.
**Never duplicate, never contradict** rules from the global file. This file
captures only what's specific to *this* project.

If a global rule conflicts with project reality, that's a signal to either:
1. Update the global (if the new reality is generally true), or
2. State the deviation explicitly in this file with the *reason* (per-repo
   precedence is documented in the global "What overrides this file"
   section — but the reasoning must live here).

---

## Project overview

> One-paragraph "what is this and why does it exist". Update before merging
> the first real PR — the placeholder rots fast.

<project-description>

---

## Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | TODO | TODO |
| Build / package | TODO | TODO |
| Test framework | TODO | TODO |
| Linter / formatter | TODO | TODO |
| CI runner | GitHub Actions | matches `<owner>` standard |
| Docs site | MkDocs Material → GH Pages | matches `<owner>` standard |
| Secrets / config | TODO | TODO |
| Deploy target | TODO | TODO |

---

## Project-specific rules

These rules apply ONLY to this repo. Anything universal belongs in the
global AGENTS.md, not here.

1. *(placeholder — replace with real project rules)*

   Examples of what goes here:
   - "All database migrations are gated behind the `feature/migrations`
     branch — never merge to main directly."
   - "The `eval/` directory is fixture data — do not regenerate without
     ADR approval."
   - "Tool-call format is JSON-strict; never return Markdown-wrapped JSON."

---

## Domain knowledge

> What context does an agent need to be effective here that *isn't*
> inferable from reading the code? Save them a 30-minute archaeology
> dig. Examples:
>
> - The data model has a quirk where field X is reused for two purposes;
>   `parser.py:114` is the canonical interpretation.
> - The third-party API's rate limit is 30 req/s sustained but bursts to
>   100; the retry policy in `client.py` is tuned to that, don't loosen
>   it without verifying.
> - The customer's regulatory environment requires that field Y is never
>   logged. The redaction middleware is the load-bearing piece.

*(placeholder)*

---

## Named ADR anchors

These ADRs are referenced often and should be the first thing an agent
reads when working in a related area:

- *(none yet — first ADR goes here)*

---

## Where to look

- **Active session log:** `docs/history/` (latest file = current state).
- **Plan for what's next:** `docs/wip/NEXT_STEPS.md` (or whatever rolling
  plan exists).
- **Big decisions:** `docs/adr/`.
- **Proposals not yet decided:** `docs/rfc/`.

---

## What overrides this file

- Direct instruction in chat: a one-shot ask supersedes a default.
- The global `AGENTS.md` for universal rules — this file only narrows or
  adds context, never overrides global non-negotiables.
- Per-conversation memory: persistent operator preferences captured across
  sessions override cold defaults here.
