"""
Anthropic client wrapper.

The API key is read from server-side settings and never leaves this process. If
the SDK or key is missing, a typed ``AIOperationError`` is raised so callers get
the uniform error envelope instead of a 500.
"""
from functools import lru_cache

from django.conf import settings

from ai.exceptions import AIOperationError


@lru_cache(maxsize=1)
def get_client():
    if not settings.ANTHROPIC_API_KEY:
        raise AIOperationError(
            code="missing_api_key",
            message="ANTHROPIC_API_KEY is not configured on the server.",
            retryable=False,
        )
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover - defensive
        raise AIOperationError(
            code="ai_sdk_missing",
            message="The Anthropic SDK is not installed on the server.",
            retryable=False,
            details=str(exc),
        )
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def get_model() -> str:
    return settings.VYRA_MODEL


def get_timeout() -> float:
    return settings.VYRA_AI_TIMEOUT_SECONDS
