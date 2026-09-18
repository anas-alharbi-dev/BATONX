"""
Provider selection seam.

Phase B: Anthropic is the only provider. ``get_provider()`` exists so later
phases can add real routing here without touching ``ai.base`` or the operations.
No routing, fallback, or multi-provider logic yet.
"""
from __future__ import annotations

from ai.providers.anthropic import AnthropicProvider
from ai.providers.base import Provider

_ANTHROPIC = AnthropicProvider()


def get_provider() -> Provider:
    return _ANTHROPIC
