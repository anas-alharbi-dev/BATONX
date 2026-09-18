# AI Architecture

## Current

BATONX's AI usage is narrow and structural by design: every AI call exists to produce one *structured, schema-validated draft* for a human to review — never to make a decision, apply a change, or execute anything.

**The operation runner (`backend/ai/base.py`)** is the single shared path for every AI-backed operation in the product:

```
build prompt → provider.generate_structured() → dict
             → Pydantic schema validation
             → one repair retry on validation failure
             → validated model instance
```

It is provider-agnostic: it only depends on the `Provider` protocol defined in `backend/ai/providers/base.py` (a `generate_structured` method plus an `ensure_ready` readiness check), never on a specific SDK's request/response shape.

**The provider abstraction (`backend/ai/providers/`)** is the seam that keeps generation swappable. One adapter is implemented today: `anthropic.py`, wrapping the Anthropic SDK behind that same protocol. `ai/client.py` holds the actual SDK client, constructed once and cached; the API key is read from server-side settings and never reaches the browser.

**Logging (`AIRequestLog`)** records every attempt — operation, outcome, model, token counts, latency — for cost and debugging visibility, independent of whether the caller's business logic succeeds.

**Failure handling** is explicit and typed (`AIOperationError`), carrying a `code`, a human-readable `message`, and whether the frontend should offer a retry. A missing API key produces the same honest, typed `missing_api_key` response every AI-backed page already knows how to render — never a bare 500.

## What this means in practice today

- Exactly one AI provider is wired: Anthropic.
- There is no multi-provider router, no cost-based or capability-based provider selection, and no runtime provider switching.
- Every AI-generated artifact (Blueprint, Architecture, Metric definitions, Insights, Build/Review Prompts, …) is written through the same runner and lands as a draft — the human approval step downstream is identical regardless of which provider produced it.
- Local development without a configured `ANTHROPIC_API_KEY` is a fully supported, honestly-labeled state: deterministic features work normally; AI-backed generation surfaces "AI isn't configured" instead of failing silently or faking a result.

## Future / Planned

Not implemented — listed here explicitly so the current scope is never overstated:

- Additional provider adapters behind the existing `Provider` protocol
- Provider routing/selection logic (cost, capability, or fallback-based)
- Any form of autonomous execution — BATONX's AI usage stays scoped to producing a reviewable draft; it does not gain the ability to act without a human decision in between
