"""Claude API with prompt caching — minimal demo.

Three sequential calls against the Anthropic API. The system prompt is
marked cacheable; per-call user messages are unique. Calls 2 and 3 should
read from the cache established by call 1.

Run: python run.py
"""

import os
import sys

from anthropic import Anthropic

# Model comes from env, with a known-good default.
# Migrate by changing ANTHROPIC_MODEL — never edit this line directly.
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# A stable preamble large enough to be cacheable. Minimum is 1024 tokens
# for Sonnet (2048 for Haiku). This one runs ~1300 tokens — comfortably
# over the floor. Repeat-padded for didactic clarity; real preambles are
# instructions / context / tool definitions, not lorem.
STABLE_PREAMBLE = (
    "You are a careful technical assistant. Respond concisely. "
    "Prefer plain answers over hedged qualifications. "
    "When uncertain, say so explicitly rather than guessing.\n\n"
    "Operating context for this session:\n"
    + "\n".join(
        f"- Rule {i}: This is placeholder context to demonstrate "
        f"that the preamble must be substantial enough to exceed the "
        f"cache minimum size. In a real application, replace these "
        f"lines with actual system instructions, domain rules, or "
        f"tool definitions that don't change between calls."
        for i in range(1, 16)
    )
)


def log_cache_usage(call_n: int, response) -> None:
    """Print the cache telemetry from a response.

    Adapt to your project's observability layer. Stdout is fine for
    demos; in production this should be a metric (Grafana / Sentry /
    structured log).
    """
    u = response.usage
    created = getattr(u, "cache_creation_input_tokens", 0) or 0
    read = getattr(u, "cache_read_input_tokens", 0) or 0
    print(
        f"[Call {call_n}]  model={MODEL}  "
        f"cache: created={created:<6} read={read}"
    )


def call_with_caching(client: Anthropic, call_n: int, user_message: str):
    """Single API call with the stable preamble marked as cacheable."""
    return client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=[
            {
                "type": "text",
                "text": STABLE_PREAMBLE,
                # The cache marker — anything before this in `system`
                # is cached for ~5 minutes. The `messages` list is
                # always per-request, never cached.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    client = Anthropic()

    prompts = [
        "Say hello in three different programming languages.",
        "What's 2 + 2? Explain in one sentence.",
        "Name a color that starts with the letter 'M'.",
    ]

    for i, prompt in enumerate(prompts, start=1):
        response = call_with_caching(client, i, prompt)
        log_cache_usage(i, response)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
