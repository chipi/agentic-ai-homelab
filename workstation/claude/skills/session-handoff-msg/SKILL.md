---
name: session-handoff-msg
description: Check a message to another Claude session (ingestion, mobile, homelab, orrery, a subagent) before sending it — refuses leftover placeholders (<ids>, {x}, $VAR, TODO, a bare ALL_CAPS_TOKEN) and any state claim (held, deployed, applied, pushed, approved, verified, green, done …) that has no proof command passing right now. Use before every SendMessage that asks another session to confirm, decide or act, or that tells it what state prod or a job is in.
---

# session-handoff-msg

Two messages to the ingestion session on 2026-10-17 went out wrong in the same exchange:

1. The episode list was the literal text `BATCH2_IDS`; the ids were never filled in.
2. It said "I am holding it until you answer" while the chain script would still have approved the
   gate. The hold became real only afterwards.

A peer acts on what the message says. A wrong state claim to a peer is the same failure as one to
the operator (truthfulness rules 0.0 and 0.2), and placeholders are how drafts leak out.

## Run

Write the message to a file, then:

```bash
L=~/.claude/skills/session-handoff-msg/scripts/lint_msg.py
python3 $L /tmp/msg.txt \
  --proof "holding=python3 ~/.claude/skills/prod-batch-chain/scripts/batch_chain.py podcast-2332 status | grep -q 'HOLD: yes'" \
  --proof "approved=gh api repos/OWNER/REPO/actions/runs/RUN/approvals -q '.[].state' | grep -qx approved" \
  --allow PROD_SSH_HOST_KEY --not-a-claim done
```

- `SENDABLE` (exit 0): send the printed text with SendMessage, unchanged.
- `REFUSED` (exit 1): fix each line it lists. Do not send a "correction" afterwards instead.
- `--proof WORD='cmd'`: one per state word in the message. The command must exit 0 now. Prove it from
  the system itself (`gh`, `ssh`, a ledger), not from your own earlier message.
- `--allow TOKEN`: a real ALL_CAPS name. Prefer putting it in backticks, which needs no flag.
- `--not-a-claim WORD`: the word is used descriptively ("when it is done, …").

## Tests

`cd scripts && python3 -m unittest test_lint_msg` replays both 2026-10-17 messages; both are refused.

## Not covered

- It cannot tell whether the content is right (the right ids, the right run). It only catches the two
  shapes that went wrong: unfilled placeholders and unproven state.
- A state stated without one of the listed words ("nothing will start") passes. Add the word to
  `STATE_WORDS` when one slips through.
