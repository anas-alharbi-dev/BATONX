"""
Operation runner — the single shared path for every AI operation.

    build prompt -> provider.generate_structured() -> dict
                 -> Pydantic validation
                 -> (one repair retry on validation failure)
                 -> validated model instance

``ai.base`` is provider-agnostic: it only speaks the ``ai.providers.base``
contract (``Provider`` / ``StructuredResult`` / ``PriorAttempt``). Every attempt
that reaches a provider is recorded in ``AIRequestLog``; a pure configuration
failure (missing key) is raised by ``provider.ensure_ready()`` before any
logging, so it produces no row - matching pre-Phase-B behavior. Any failure is
raised as a typed ``AIOperationError`` so the API returns the uniform envelope.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Optional, Type

from pydantic import BaseModel, ValidationError

from ai.client import get_timeout
from ai.exceptions import AIOperationError
from ai.models import AIRequestLog
from ai.providers import get_provider
from ai.providers.base import PriorAttempt, Provider, StructuredResult


@dataclass(frozen=True)
class Operation:
    """A specialized AI operation: an instruction template + an output schema."""

    name: str
    system_prompt: str
    schema: Type[BaseModel]
    build_user_prompt: Callable[[dict], str]
    normalize: Optional[Callable[[dict], dict]] = None
    # Stable, operation-level prompt version recorded on AIRequestLog. Default ""
    # (unversioned); set explicitly per operation when its prompt/schema is
    # deliberately versioned. Not a versioning framework.
    prompt_version: str = ""


class _Meta:
    """Accumulates traceability across the (up to two) provider calls."""

    __slots__ = ("provider", "model", "input_tokens", "output_tokens")

    def __init__(self, provider_name: str) -> None:
        self.provider = provider_name
        self.model = ""
        self.input_tokens = 0
        self.output_tokens = 0

    def add(self, result: StructuredResult) -> None:
        self.provider = result.provider
        self.model = result.model
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens


def run_operation(operation: Operation, context: dict, project=None) -> BaseModel:
    """Execute an AI operation and return a validated Pydantic model instance."""
    provider = get_provider()
    provider.ensure_ready()  # missing_api_key / ai_sdk_missing -> raised here, no log row

    json_schema = operation.schema.model_json_schema()
    user_prompt = operation.build_user_prompt(context)
    timeout = get_timeout()

    started = time.monotonic()
    outcome = "error"
    meta = _Meta(provider.name)
    try:
        result = _run(provider, operation, json_schema, user_prompt, timeout, meta)
        outcome = "ok"
        return result
    except AIOperationError:
        raise
    except Exception as exc:  # network / timeout / provider SDK errors
        raise AIOperationError(
            code="ai_request_failed",
            message="The AI request failed. Please try again.",
            retryable=True,
            details=str(exc),
        )
    finally:
        AIRequestLog.objects.create(
            project=project,
            operation=operation.name,
            provider=meta.provider,
            model=meta.model,
            prompt_version=operation.prompt_version,
            input_tokens=meta.input_tokens,
            output_tokens=meta.output_tokens,
            latency_ms=int((time.monotonic() - started) * 1000),
            outcome=outcome,
        )


def _run(
    provider: Provider,
    operation: Operation,
    json_schema: dict,
    user_prompt: str,
    timeout: float,
    meta: _Meta,
) -> BaseModel:
    first = provider.generate_structured(
        system=operation.system_prompt,
        user=user_prompt,
        json_schema=json_schema,
        timeout=timeout,
    )
    meta.add(first)
    try:
        return _validate(operation, first.data)
    except ValidationError as first_error:
        repaired = provider.generate_structured(
            system=operation.system_prompt,
            user=user_prompt,
            json_schema=json_schema,
            timeout=timeout,
            prior_attempt=PriorAttempt(
                output=first.data, error=_format_errors(first_error)
            ),
        )
        meta.add(repaired)
        try:
            return _validate(operation, repaired.data)
        except ValidationError as second_error:
            raise AIOperationError(
                code="ai_invalid_output",
                message="The AI response did not match the expected format.",
                retryable=True,
                details=_format_errors(second_error),
            )


def _validate(operation: Operation, raw) -> BaseModel:
    data = raw if isinstance(raw, dict) else json.loads(raw)
    if operation.normalize:
        data = operation.normalize(data)
    return operation.schema.model_validate(data)


def _format_errors(err: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}"
        for e in err.errors()
    )
