"""Provider wrappers — 10 real backends + a deterministic fake.

Each provider implements a single `generate(prompt, system)` method that
returns a `Reply` (text + cost estimate + latency + error). Providers
that need a missing env var are filtered out by `discover_providers()`
so the bake-off runs with whatever the operator has.

Country flags are decorative — surfaced in the report so the comparison
celebrates that the global landscape is more than just SF.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional, Protocol


@dataclass
class Reply:
    """One provider's response to one prompt."""

    text: str
    cost_usd: float = 0.0
    latency_s: float = 0.0
    error: Optional[str] = None


class Provider(Protocol):
    """All providers expose the same shape."""

    label: str    # short display name, e.g. "claude-sonnet-4-6"
    flag: str     # country emoji
    org: str      # short org label, e.g. "Anthropic 🇺🇸"

    def generate(self, *, prompt: str, system: str) -> Reply: ...


# ---------------------------------------------------------------------------
# Always-available — for offline demos and tests.


class FakeProvider:
    """Deterministic. No API. Returns a JSON-looking blob keyed on the prompt
    hash so the bake-off can run with zero credentials.

    This is what `make bakeoff-fake` calls. Useful when wiring the runner
    and you just want to see the report flow without burning budget.
    """

    label = "fake-provider"
    flag = "🤖"
    org = "Fake (no API) 🤖"

    def generate(self, *, prompt: str, system: str) -> Reply:
        time.sleep(0.001)
        return Reply(text='{"_fake": "deterministic placeholder"}', cost_usd=0.0, latency_s=0.001)


# ---------------------------------------------------------------------------
# Anthropic — uses its own SDK.


class ClaudeProvider:
    label = "claude-sonnet-4-6"
    flag = "🇺🇸"
    org = "Anthropic 🇺🇸"

    # Rough as-of-writing pricing (USD per 1M tokens). Adjust to your project's
    # billing reality — these are illustrative.
    INPUT_PRICE = 3.0
    OUTPUT_PRICE = 15.0

    def __init__(self, model: Optional[str] = None):
        from anthropic import Anthropic
        self.label = model or self.label
        self._client = Anthropic()

    def generate(self, *, prompt: str, system: str) -> Reply:
        t0 = time.time()
        try:
            resp = self._client.messages.create(
                model=self.label,
                max_tokens=512,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            return Reply(text="", error=f"{type(exc).__name__}: {exc}", latency_s=time.time() - t0)

        text = resp.content[0].text if resp.content else ""
        usage = resp.usage
        cost = (
            (usage.input_tokens or 0) * self.INPUT_PRICE / 1_000_000
            + (usage.output_tokens or 0) * self.OUTPUT_PRICE / 1_000_000
        )
        return Reply(text=text, cost_usd=cost, latency_s=time.time() - t0)


# ---------------------------------------------------------------------------
# Google Gemini — uses its own SDK.


class GeminiProvider:
    label = "gemini-2.5-flash"
    flag = "🇺🇸"
    org = "Google 🇺🇸"

    INPUT_PRICE = 0.30
    OUTPUT_PRICE = 2.50

    def __init__(self, model: Optional[str] = None):
        from google import genai
        self.label = model or self.label
        self._client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    def generate(self, *, prompt: str, system: str) -> Reply:
        from google.genai import types
        t0 = time.time()
        try:
            resp = self._client.models.generate_content(
                model=self.label,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=512,
                ),
            )
        except Exception as exc:
            return Reply(text="", error=f"{type(exc).__name__}: {exc}", latency_s=time.time() - t0)

        text = resp.text or ""
        meta = getattr(resp, "usage_metadata", None)
        in_tok = getattr(meta, "prompt_token_count", 0) or 0 if meta else 0
        out_tok = getattr(meta, "candidates_token_count", 0) or 0 if meta else 0
        cost = in_tok * self.INPUT_PRICE / 1_000_000 + out_tok * self.OUTPUT_PRICE / 1_000_000
        return Reply(text=text, cost_usd=cost, latency_s=time.time() - t0)


# ---------------------------------------------------------------------------
# OpenAI-compatible providers — one shared client class, eight backends.
#
# DeepSeek / Qwen / Kimi / Mistral / xAI / OpenAI / Hugging Face / local vLLM
# all speak OpenAI Chat Completions. Differences live in (base_url, api_key
# env var, default model name, pricing).


class _OpenAICompatProvider:
    """Shared base for OpenAI-compatible chat-completion APIs."""

    base_url: Optional[str] = None
    env_var: str = "OPENAI_API_KEY"
    default_model: str = ""
    label: str = ""
    flag: str = ""
    org: str = ""
    INPUT_PRICE: float = 0.0
    OUTPUT_PRICE: float = 0.0

    def __init__(self, model: Optional[str] = None):
        from openai import OpenAI
        self.label = model or self.default_model
        self._client = OpenAI(
            api_key=os.environ[self.env_var],
            base_url=self.base_url,
        )

    def generate(self, *, prompt: str, system: str) -> Reply:
        t0 = time.time()
        try:
            resp = self._client.chat.completions.create(
                model=self.label,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
            )
        except Exception as exc:
            return Reply(text="", error=f"{type(exc).__name__}: {exc}", latency_s=time.time() - t0)

        text = resp.choices[0].message.content or ""
        usage = resp.usage
        cost = 0.0
        if usage:
            cost = (
                (usage.prompt_tokens or 0) * self.INPUT_PRICE / 1_000_000
                + (usage.completion_tokens or 0) * self.OUTPUT_PRICE / 1_000_000
            )
        return Reply(text=text, cost_usd=cost, latency_s=time.time() - t0)


class OpenAIProvider(_OpenAICompatProvider):
    base_url = None  # SDK default
    env_var = "OPENAI_API_KEY"
    default_model = "gpt-5-mini"
    flag = "🇺🇸"
    org = "OpenAI 🇺🇸"
    INPUT_PRICE = 0.25
    OUTPUT_PRICE = 2.00


class GrokProvider(_OpenAICompatProvider):
    base_url = "https://api.x.ai/v1"
    env_var = "XAI_API_KEY"
    default_model = "grok-2-latest"
    flag = "🇺🇸"
    org = "xAI 🇺🇸"
    INPUT_PRICE = 2.0
    OUTPUT_PRICE = 10.0


class MistralProvider(_OpenAICompatProvider):
    base_url = "https://api.mistral.ai/v1"
    env_var = "MISTRAL_API_KEY"
    default_model = "mistral-small-latest"
    flag = "🇫🇷"
    org = "Mistral 🇫🇷"
    INPUT_PRICE = 0.20
    OUTPUT_PRICE = 0.60


class HuggingFaceProvider(_OpenAICompatProvider):
    """Hugging Face Inference router — routes to open-weight models.

    Pricing varies by underlying provider (Together, Fireworks, Nebius, etc).
    The numbers below are illustrative — check HF's pricing page for the
    model you pick.
    """

    base_url = "https://router.huggingface.co/v1"
    env_var = "HF_TOKEN"
    default_model = "meta-llama/Llama-3.3-70B-Instruct"
    flag = "🇫🇷"
    org = "Hugging Face (→ open models) 🇫🇷"
    INPUT_PRICE = 0.30
    OUTPUT_PRICE = 0.90


class DeepSeekProvider(_OpenAICompatProvider):
    base_url = "https://api.deepseek.com"
    env_var = "DEEPSEEK_API_KEY"
    default_model = "deepseek-chat"
    flag = "🇨🇳"
    org = "DeepSeek 🇨🇳"
    INPUT_PRICE = 0.27
    OUTPUT_PRICE = 1.10


class QwenProvider(_OpenAICompatProvider):
    """Alibaba DashScope OpenAI-compatible endpoint.

    Set DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    if you're outside mainland China (the default points at the China endpoint).
    """

    base_url = os.environ.get(
        "DASHSCOPE_BASE_URL",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    env_var = "DASHSCOPE_API_KEY"
    default_model = "qwen-plus"
    flag = "🇨🇳"
    org = "Alibaba Qwen 🇨🇳"
    INPUT_PRICE = 0.40
    OUTPUT_PRICE = 1.20


class KimiProvider(_OpenAICompatProvider):
    """Moonshot Kimi — the international endpoint (api.moonshot.ai).
    Use api.moonshot.cn if you're on the China side."""

    base_url = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1")
    env_var = "MOONSHOT_API_KEY"
    default_model = "kimi-k2-0905-preview"
    flag = "🇨🇳"
    org = "Moonshot Kimi 🇨🇳"
    INPUT_PRICE = 0.60
    OUTPUT_PRICE = 2.50


class LocalVLLMProvider(_OpenAICompatProvider):
    """Operator's homelab vLLM, reached via tailnet.

    Defaults match `infra/vllm/docker-compose.yml`. Set LOCAL_VLLM_URL and
    LOCAL_VLLM_MODEL for your own setup.
    """

    base_url = os.environ.get("LOCAL_VLLM_URL", "http://localhost:9000/v1")
    env_var = "LOCAL_VLLM_API_KEY"
    default_model = os.environ.get("LOCAL_VLLM_MODEL", "Qwen/Qwen3-Coder-Next-FP8")
    flag = "🏠"
    org = "Local vLLM 🏠"
    INPUT_PRICE = 0.0
    OUTPUT_PRICE = 0.0


# ---------------------------------------------------------------------------
# Registry + auto-discovery.


PROVIDER_CLASSES = [
    ClaudeProvider,
    OpenAIProvider,
    GeminiProvider,
    GrokProvider,
    MistralProvider,
    HuggingFaceProvider,
    DeepSeekProvider,
    QwenProvider,
    KimiProvider,
    LocalVLLMProvider,
]


def discover_providers(*, use_fake: bool = False) -> List[Provider]:
    """Return the providers whose env vars are present (or the fake)."""
    if use_fake:
        return [FakeProvider()]

    ready: List[Provider] = []
    for cls in PROVIDER_CLASSES:
        env_var = getattr(cls, "env_var", None)
        if cls is ClaudeProvider:
            env_var = "ANTHROPIC_API_KEY"
        elif cls is GeminiProvider:
            env_var = "GOOGLE_API_KEY"
        if env_var and not os.environ.get(env_var):
            continue
        try:
            ready.append(cls())
        except Exception as exc:
            print(f"  skip {cls.__name__}: init failed ({type(exc).__name__}: {exc})")
    if not ready:
        print("  no providers found — falling back to FakeProvider")
        ready.append(FakeProvider())
    return ready
