"""
Provider abstraction for structured generation.

``ai.base.run_operation`` depends only on this contract - it never sees a
provider SDK's request or response shape. One implementation ships in Phase B
(Anthropic); the ``ai.providers.get_provider`` seam resolves it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class PriorAttempt:
    """A previous structured attempt that failed schema validation, passed back
    to the provider so it can present a self-correction turn however it likes."""

    output: dict
    error: str


@dataclass(frozen=True)
class StructuredResult:
    """Normalized output of one structured-generation call. Everything
    ``ai.base`` needs; nothing provider-specific."""

    data: dict
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class Provider(Protocol):
    """Structured generation against one model. Stateless per call."""

    name: str

    def ensure_ready(self) -> None:
        """Raise ``AIOperationError`` (retryable=False) if the provider cannot
        run at all (missing key, missing SDK). Called by ``run_operation``
        BEFORE any request-logging, so a pure configuration failure never
        produces an ``AIRequestLog`` row - matching pre-Phase-B behavior."""

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict,
        timeout: float,
        prior_attempt: Optional[PriorAttempt] = None,
    ) -> StructuredResult:
        """One forced-structured call. Must return ``StructuredResult`` or raise
        ``AIOperationError`` for provider-known failures (e.g. no structured
        output). Other exceptions propagate and ``run_operation`` wraps them as
        ``ai_request_failed``."""
