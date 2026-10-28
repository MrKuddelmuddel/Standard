"""Model provider abstraction. The app never depends on one vendor; tests use a scripted fake provider.

Providers return the raw assistant content (passed back unchanged on the next turn, which keeps thinking blocks
valid) plus a normalized view of the blocks for the agent loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import Settings

# USD per million tokens (input, output), first-party API list prices. Used for cost estimates only.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-1": (10.0, 50.0),
}


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class Turn:
    raw_content: Any
    blocks: list[Block]
    stop_reason: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    stop_detail: str | None = None


class Provider(Protocol):
    name: str
    model: str

    def create(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], max_tokens: int
    ) -> Turn: ...


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    p = PRICES.get(model)
    if p is None:
        return None
    return round(input_tokens / 1e6 * p[0] + output_tokens / 1e6 * p[1], 6)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=settings.ai_max_seconds, max_retries=2
        )
        self.model = settings.ai_model
        self.effort = settings.ai_effort
        self.fallback = settings.ai_refusal_fallback

    def create(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], max_tokens: int) -> Turn:
        a = self._anthropic
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "tools": tools,
            "output_config": {"effort": self.effort},
        }
        try:
            if self.fallback:
                # Server-side refusal fallback: a policy decline is retried on a suitable model inside the same call.
                resp = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                )
            else:
                resp = self.client.messages.create(**kwargs)
        except a.AuthenticationError as exc:
            raise ProviderError("auth_failed", "The AI provider rejected the API key.") from exc
        except a.RateLimitError as exc:
            raise ProviderError("rate_limited", "The AI provider is rate limiting requests. Try again later.") from exc
        except a.APITimeoutError as exc:
            raise ProviderError("timeout", "The AI provider did not answer in time.") from exc
        except a.BadRequestError as exc:
            raise ProviderError("bad_request", f"The AI provider rejected the request: {exc.message[:200]}") from exc
        except a.APIStatusError as exc:
            raise ProviderError("provider_error", f"The AI provider returned HTTP {exc.status_code}.") from exc
        except a.APIConnectionError as exc:
            raise ProviderError("network_error", "Could not reach the AI provider.") from exc
        blocks: list[Block] = []
        for b in resp.content:
            if b.type == "text":
                blocks.append(Block("text", text=b.text))
            elif b.type == "tool_use":
                blocks.append(Block("tool_use", id=b.id, name=b.name, input=dict(b.input or {})))
        detail = None
        if resp.stop_reason == "refusal" and getattr(resp, "stop_details", None):
            detail = getattr(resp.stop_details, "category", None)
        return Turn(
            raw_content=resp.content,
            blocks=blocks,
            stop_reason=resp.stop_reason or "",
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=resp.model,
            stop_detail=detail,
        )


def get_provider(settings: Settings) -> Provider | None:
    if settings.ai_configured:
        return AnthropicProvider(settings)
    return None
