"""
Phase B verification — AI provider boundary.

Confirms ``ai.base.run_operation`` is provider-agnostic: it works against a fake
provider, no Anthropic request/response shape remains in ``ai/base.py``,
``AIRequestLog.provider`` is populated from the normalized result, the
repair-retry and error semantics are unchanged, and a pure configuration failure
(``missing_api_key``) still produces no log row.
"""
import unittest.mock as mock
from pathlib import Path

from pydantic import BaseModel
from tests.base import AuthenticatedAPITestCase

from ai.base import Operation, run_operation
from ai.exceptions import AIOperationError
from ai.models import AIRequestLog
from ai.providers.base import PriorAttempt, StructuredResult


class EchoOut(BaseModel):
    value: str


ECHO_OP = Operation(
    name="test_echo",
    system_prompt="sys",
    schema=EchoOut,
    build_user_prompt=lambda ctx: f"user:{ctx['x']}",
)


class FakeProvider:
    name = "fake"

    def __init__(self, script):
        # each item: dict -> returned as StructuredResult.data; Exception -> raised
        self._script = list(script)
        self.calls: list[dict] = []
        self.ready_calls = 0
        self.ready_error: Exception | None = None

    def ensure_ready(self) -> None:
        self.ready_calls += 1
        if self.ready_error:
            raise self.ready_error

    def generate_structured(
        self, *, system, user, json_schema, timeout, prior_attempt=None
    ) -> StructuredResult:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "json_schema": json_schema,
                "timeout": timeout,
                "prior_attempt": prior_attempt,
            }
        )
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return StructuredResult(
            data=item,
            provider=self.name,
            model="fake-model-x",
            input_tokens=11,
            output_tokens=7,
        )


def _use(provider):
    return mock.patch("ai.base.get_provider", return_value=provider)


class ProviderContractTests(AuthenticatedAPITestCase):
    def test_happy_path_with_fake_provider(self):
        fp = FakeProvider([{"value": "hello"}])
        with _use(fp):
            result = run_operation(ECHO_OP, {"x": "hi"})
        self.assertEqual(result.value, "hello")
        self.assertEqual(len(fp.calls), 1)
        self.assertEqual(fp.calls[0]["user"], "user:hi")
        self.assertEqual(fp.calls[0]["json_schema"]["title"], "EchoOut")
        self.assertIsNone(fp.calls[0]["prior_attempt"])

        log = AIRequestLog.objects.get(operation="test_echo")
        self.assertEqual(log.provider, "fake")
        self.assertEqual(log.model, "fake-model-x")
        self.assertEqual(log.prompt_version, "")
        self.assertEqual((log.input_tokens, log.output_tokens), (11, 7))
        self.assertEqual(log.outcome, "ok")

    def test_repair_retry_invalid_then_valid(self):
        fp = FakeProvider([{"wrong": 1}, {"value": "fixed"}])
        with _use(fp):
            result = run_operation(ECHO_OP, {"x": "z"})
        self.assertEqual(result.value, "fixed")
        self.assertEqual(len(fp.calls), 2)

        prior = fp.calls[1]["prior_attempt"]
        self.assertIsInstance(prior, PriorAttempt)
        self.assertEqual(prior.output, {"wrong": 1})
        self.assertTrue(prior.error)

        log = AIRequestLog.objects.get(operation="test_echo")
        self.assertEqual(log.outcome, "ok")
        self.assertEqual((log.input_tokens, log.output_tokens), (22, 14))  # accumulated

    def test_repair_retry_exhausted_raises_ai_invalid_output(self):
        fp = FakeProvider([{"wrong": 1}, {"still": "bad"}])
        with _use(fp):
            with self.assertRaises(AIOperationError) as ctx:
                run_operation(ECHO_OP, {"x": "z"})
        self.assertEqual(ctx.exception.code, "ai_invalid_output")
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(len(fp.calls), 2)

        log = AIRequestLog.objects.get(operation="test_echo")
        self.assertEqual(log.outcome, "error")

    def test_missing_api_key_via_ensure_ready_makes_no_log_row(self):
        fp = FakeProvider([])
        fp.ready_error = AIOperationError(
            "missing_api_key", "not configured", retryable=False
        )
        with _use(fp):
            with self.assertRaises(AIOperationError) as ctx:
                run_operation(ECHO_OP, {"x": "z"})
        self.assertEqual(ctx.exception.code, "missing_api_key")
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual(fp.ready_calls, 1)
        self.assertEqual(len(fp.calls), 0)
        self.assertEqual(AIRequestLog.objects.count(), 0)

    def test_generic_provider_error_becomes_ai_request_failed(self):
        fp = FakeProvider([RuntimeError("boom")])
        with _use(fp):
            with self.assertRaises(AIOperationError) as ctx:
                run_operation(ECHO_OP, {"x": "z"})
        self.assertEqual(ctx.exception.code, "ai_request_failed")
        self.assertTrue(ctx.exception.retryable)

        log = AIRequestLog.objects.get(operation="test_echo")
        self.assertEqual(log.outcome, "error")

    def test_real_operation_flows_through_the_seam(self):
        from ai.operations.idea_analysis import IDEA_ANALYSIS

        payload = {
            "domain": "B2B marketplace",
            "product_type_guess": "web app",
            "known": ["x"],
            "unknowns": ["y"],
            "assumptions": [],
        }
        with _use(FakeProvider([payload])):
            result = run_operation(IDEA_ANALYSIS, {"idea": "a marketplace"})
        self.assertEqual(result.domain, "B2B marketplace")


class ProviderIsolationTests(AuthenticatedAPITestCase):
    def test_ai_base_has_no_anthropic_shape(self):
        from ai import base as ai_base

        src = Path(ai_base.__file__).read_text()
        for token in (
            "tool_use",
            "messages.create",
            "block.input",
            "with_options",
            "input_schema",
            "response.content",
            "tool_choice",
            "import anthropic",
            "from anthropic",
        ):
            self.assertNotIn(token, src, f"ai/base.py still references {token!r}")

    def test_anthropic_adapter_owns_the_shape(self):
        from ai.providers import anthropic as adapter

        src = Path(adapter.__file__).read_text()
        for token in (
            "messages.create",
            "tool_use",
            "tool_choice",
            "input_schema",
            "with_options",
        ):
            self.assertIn(token, src, f"anthropic adapter missing {token!r}")
