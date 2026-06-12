# Philosophy

How I work with agentic AI. One page. No metaphors.

## The premise

LLMs are real engineering collaborators now. Not assistants, not autocomplete —
collaborators with judgment, ability to act, and the capacity to ship work.
That changes what *I* have to do well to get good outcomes.

The job is no longer "write the code". The job is:
- Decide what we're building, and why.
- Frame the work so an agent can do it without supervision.
- Verify the result, because confident-sounding wrong output is the default
  failure mode.

Everything in this repo serves one of those three.

## What I optimize for

**Velocity through clarity, not through skipping verification.**

An agent given a clear, well-framed task can produce a working PR in minutes.
The same agent given a fuzzy task will burn an hour producing plausible
nonsense. The bottleneck is not the model — it's the framing.

So I invest in:
- **Rules of the road** (`AGENTS.md`) — the things I shouldn't have to repeat.
- **Project anchors** (ADRs, RFCs, PRDs) — so "why" is searchable, not
  reconstructed from memory.
- **Layered validation gates** (Makefile tiers) — so the cost of checking
  matches the size of the change.
- **Reproducibility** (pinned model revisions, pinned image tags) — so when
  something breaks, the variable space is small.

## Cloud or local?

Both. They serve different needs:

| Cloud (Claude, OpenAI, Gemini) | Local (vLLM, Ollama) |
|---|---|
| Best frontier capabilities | Predictable cost, no rate limits |
| No infra to maintain | Total privacy, no data egress |
| Pay per token | Pay once for hardware |
| Tool/MCP use is mature | Tool use varies by model |
| Latency variable | Latency knowable + tunable |

I use cloud for complex agentic work (long context, deep tool use, novel
problems). I use local for: high-volume eval sweeps, anything I'd rather
not send to a third party, interactive coding sessions where I'm iterating
fast and don't want network latency.

The good setup makes the choice ergonomic: same client, multiple endpoints,
swap in seconds.

## Things I will not do

- **Skip verification because "the model usually gets this right".** Past
  reliability is not a guarantee. Verify the output of the thing you actually
  ran.
- **Add safeguards an agent didn't ask for.** If I tell an agent "fix this
  bug", the response is the fix — not "I added validation around X just in
  case". Scope creep from agents is exhausting; I avoid it in myself.
- **Treat prompts as code.** Prompts decay. The model behind them changes.
  What's stable is the *structure* of the work (the inputs, expected
  outputs, the verification harness), not the prompt strings.
- **Hide complexity behind abstractions.** If a Docker Compose has 20 args
  to `vllm serve`, those args belong in the compose with comments. Not
  buried in a wrapper script I'll forget about.

## Things I will do

- **Write down decisions as they're made.** Future-me reads ADRs more than
  any other documentation. Two paragraphs at the time of decision saves a
  half-day of archaeology three months later.
- **Re-run the cheapest check that proves the point.** Not the heaviest. CI
  minutes have a cost, even on personal projects, but the bigger cost is the
  feedback loop length.
- **Commit to a pinned version before celebrating it works.** Floating tags
  (`latest`, `main`) drift. The setup that "works fast" today won't next
  week unless I pin it today.
- **Maintain a single global ruleset** (`AGENTS.md`) and let projects
  layer on top. Repeating "always do X" in every repo is its own kind of
  drift; if it's in the global, projects can just say "yes, plus these
  five specifics".

## What this repo is for

It's the place where these patterns are codified once instead of being
re-derived in every conversation. Future agents reading it should be able to
pick up my preferences without me having to re-state them. Future me should
be able to spin up a new project (or rebuild a homelab) without thinking.

If something here doesn't earn its place anymore, it gets deleted. The
absence of guidance is not the same as the lack of an opinion — but it's
better than guidance that's gone stale.
