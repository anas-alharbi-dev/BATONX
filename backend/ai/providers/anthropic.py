"""
Anthropic adapter — the ONLY place that knows the Anthropic Messages API request
and response shapes: forced tool use, tool-schema construction, ``tool_use``
blocks, ``block.input`` extraction, and usage-token extraction.

All of this was previously inline in ``ai.base``; behavior is preserved exactly,
including the self-correction turn (user -> assistant(json) -> user(hint)).
"""
from __future__ import annotations

import json
from typing import Optional

from ai.client import get_client, get_model
from ai.exceptions import AIOperationError
from ai.providers.base import PriorAttempt, StructuredResult

_PROVIDER_NAME = "anthropic"
_MAX_TOKENS = 4096


def _snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _tool(json_schema: dict) -> dict:
    """Anthropic tool spec built from a JSON Schema (from ``model_json_schema()``)."""
    title = json_schema.get("title") or "Output"
    return {
        "name": f"emit_{_snake(title)}",
        "description": f"Return a well-formed {title} object.",
        "input_schema": json_schema,
    }


class AnthropicProvider:
    name = _PROVIDER_NAME

    def ensure_ready(self) -> None:
        # get_client() raises AIOperationError("missing_api_key" / "ai_sdk_missing",
        # retryable=False) before any HTTP call. It is lru_cached, so the call in
        # generate_structured() is free.
        get_client()

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict,
        timeout: float,
        prior_attempt: Optional[PriorAttempt] = None,
    ) -> StructuredResult:
        client = get_client()
        model = get_model()
        tool = _tool(json_schema)

        messages = [{"role": "user", "content": user}]
        if prior_attempt is not None:
            messages.append(
                {"role": "assistant", "content": json.dumps(prior_attempt.output)}
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That response was not valid: {prior_attempt.error}. "
                        "Call the tool again with a corrected response."
                    ),
                }
            )

        response = client.with_options(timeout=timeout).messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=messages,
        )

        usage = getattr(response, "usage", None)
        input_tokens = (getattr(usage, "input_tokens", 0) or 0) if usage else 0
        output_tokens = (getattr(usage, "output_tokens", 0) or 0) if usage else 0

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                return StructuredResult(
                    data=block.input,
                    provider=_PROVIDER_NAME,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

        raise AIOperationError(
            code="ai_no_output",
            message="The AI did not return structured output.",
            retryable=True,
        )
