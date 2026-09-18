"""
Phase E verification — Review Prompt stage (Build Prompt = execution instructions;
Review Prompt = verification instructions).

Deterministic paths only. The live review_prompt_generation round trip is PENDING
an ANTHROPIC_API_KEY; every AI-touching test here uses a fake provider.
"""
import json
import unittest.mock as mock

from pydantic import ValidationError
from tests.base import AuthenticatedAPITestCase

from ai.models import AIRequestLog
from ai.operations.review_prompt_generation import (
    REVIEW_PROMPT_GENERATION,
    PROMPT_VERSION,
    ReviewPrompt,
)
from ai.providers.base import StructuredResult
from projects.models import GeneratedPrompt, Project
from tests.test_phase4 import APPROVED_DT, NOW, make_roadmap_project
from tests.test_phase_d_business_logic import bl_content


def deep_text(obj) -> str:
    return json.dumps(obj, default=str).lower()


class FakeProvider:
    """Captures the rendered user prompt; returns a fixed structured payload."""

    name = "fake"

    def __init__(self, payload):
        self.payload = payload
        self.last_user = None
        self.calls = 0

    def ensure_ready(self):
        pass

    def generate_structured(self, *, system, user, json_schema, timeout, prior_attempt=None):
        self.calls += 1
        self.last_user = user
        return StructuredResult(
            data=self.payload, provider=self.name, model="fake-1",
            input_tokens=1, output_tokens=1,
        )


VALID_REVIEW = {"prompt_markdown": "# Review objective\n" + "verify the task. " * 40}


def roadmap_project_with_bl(*, with_bl: bool = True) -> Project:
    """Approved roadmap; T1/T2 completed so T3 (refs FR1, dep T2) is unblocked."""
    project = make_roadmap_project(approved=True)
    for phase in project.roadmap["content"]["phases"]:
        for t in phase["tasks"]:
            if t["id"] in ("T1", "T2"):
                t["status"] = "completed"
    fields = ["roadmap"]
    if with_bl:
        project.business_logic = {
            "content": bl_content(), "generated_at": NOW,
            "updated_at": NOW, "approved_at": NOW,
        }
        project.business_logic_approved_at = APPROVED_DT
        fields += ["business_logic", "business_logic_approved_at"]
    project.save(update_fields=fields)
    return project


def _url(project, task_id="T3"):
    return f"/api/projects/{project.slug}/roadmap/tasks/{task_id}/review-prompt/"


# --- schema ----------------------------------------------------------------


class ReviewPromptSchemaTests(AuthenticatedAPITestCase):
    def test_short_prompt_rejected(self):
        with self.assertRaises(ValidationError):
            ReviewPrompt.model_validate({"prompt_markdown": "too short"})

    def test_full_prompt_accepted(self):
        model = ReviewPrompt.model_validate(VALID_REVIEW)
        self.assertTrue(model.prompt_markdown)

    def test_operation_wiring(self):
        self.assertEqual(REVIEW_PROMPT_GENERATION.name, "review_prompt_generation")
        self.assertEqual(REVIEW_PROMPT_GENERATION.schema, ReviewPrompt)
        self.assertEqual(REVIEW_PROMPT_GENERATION.prompt_version, "review_prompt/v1")
        self.assertEqual(PROMPT_VERSION, "review_prompt/v1")


# --- guards / envelope ---------------------------------------------------


class ReviewPromptGuardTests(AuthenticatedAPITestCase):
    def test_unknown_project_returns_404_envelope(self):
        res = self.client.post(
            "/api/projects/nope/roadmap/tasks/T1/review-prompt/"
        )
        self.assertEqual(res.status_code, 404)
        body = res.json()
        self.assertEqual(set(body.keys()), {"error"})
        self.assertEqual(
            set(body["error"].keys()), {"code", "message", "retryable", "details"}
        )
        self.assertEqual(body["error"]["code"], "project_not_found")

    def test_roadmap_not_approved_returns_409(self):
        project = make_roadmap_project()  # draft roadmap
        res = self.client.post(_url(project, "T1"))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "roadmap_not_approved")

    def test_unknown_task_returns_404(self):
        project = make_roadmap_project(approved=True)
        res = self.client.post(_url(project, "T404"))
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "task_not_found")

    def test_blocked_task_returns_409_and_persists_nothing(self):
        project = make_roadmap_project(approved=True)  # T2/T3 blocked
        res = self.client.post(_url(project, "T3"))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "task_blocked")
        self.assertEqual(res.json()["error"]["details"]["unfinished"], ["T2"])
        self.assertEqual(GeneratedPrompt.objects.count(), 0)

    def test_missing_api_key_returns_502_and_persists_nothing(self):
        project = roadmap_project_with_bl()
        res = self.client.post(_url(project))
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
        self.assertEqual(GeneratedPrompt.objects.count(), 0)

    def test_ai_invalid_output_persists_nothing(self):
        project = roadmap_project_with_bl()
        fake = FakeProvider({"prompt_markdown": "too short"})  # fails schema twice
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(_url(project))
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "ai_invalid_output")
        self.assertEqual(GeneratedPrompt.objects.count(), 0)

    def test_generation_attempt_does_not_change_task_status(self):
        project = roadmap_project_with_bl()
        res = self.client.post(_url(project))  # 502, no key
        self.assertEqual(res.status_code, 502)
        project.refresh_from_db()
        statuses = {
            t["id"]: t["status"]
            for p in project.roadmap["content"]["phases"]
            for t in p["tasks"]
        }
        self.assertEqual(statuses["T3"], "not_started")


# --- stale-context policy ---------------------------------------------


class ReviewPromptStaleContextTests(AuthenticatedAPITestCase):
    def test_stale_architecture_blocks_generation(self):
        project = roadmap_project_with_bl()
        project.downstream_stale = {"architecture": True}
        project.save(update_fields=["downstream_stale"])
        fake = FakeProvider(VALID_REVIEW)
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(_url(project))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "stale_context")
        self.assertEqual(res.json()["error"]["details"]["stale"], ["architecture"])
        self.assertEqual(fake.calls, 0)
        self.assertEqual(GeneratedPrompt.objects.count(), 0)

    def test_stale_roadmap_and_business_logic_reported(self):
        project = roadmap_project_with_bl()
        project.downstream_stale = {"roadmap": True, "business_logic": True}
        project.save(update_fields=["downstream_stale"])
        res = self.client.post(_url(project))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(
            res.json()["error"]["details"]["stale"], ["business_logic", "roadmap"]
        )

    def test_no_stale_flag_allows_generation(self):
        project = roadmap_project_with_bl()
        self.assertEqual(project.downstream_stale, {})
        fake = FakeProvider(VALID_REVIEW)
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(_url(project))
        self.assertEqual(res.status_code, 200)

    def test_build_prompt_has_no_stale_guard(self):
        """Regression: the Build Prompt path is unchanged — stale flags do not
        block it (it reaches the AI call and fails only on the missing key)."""
        project = roadmap_project_with_bl()
        project.downstream_stale = {"architecture": True}
        project.save(update_fields=["downstream_stale"])
        res = self.client.post(
            f"/api/projects/{project.slug}/roadmap/tasks/T3/build-prompt/"
        )
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")


# --- successful generation / persistence / history ------------------


class ReviewPromptPersistenceTests(AuthenticatedAPITestCase):
    def _generate(self, project, task_id="T3"):
        fake = FakeProvider(VALID_REVIEW)
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(_url(project, task_id))
        return res, fake

    def test_success_persists_generated_prompt_kind_review(self):
        project = roadmap_project_with_bl()
        res, _ = self._generate(project)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(GeneratedPrompt.objects.count(), 1)
        row = GeneratedPrompt.objects.get()
        self.assertEqual(row.kind, GeneratedPrompt.Kind.REVIEW)
        self.assertEqual(row.task_id, "T3")
        self.assertEqual(row.task_title, "Supplier catalog API")
        self.assertTrue(row.content.startswith("# Review objective"))
        self.assertTrue(row.model)

    def test_workspace_payload_returns_review_prompt(self):
        project = roadmap_project_with_bl()
        res, _ = self._generate(project)
        body = res.json()
        kinds = [p["kind"] for p in body["prompts"]]
        self.assertIn("review", kinds)
        self.assertEqual(
            set(body["prompts"][0].keys()),
            {"id", "kind", "content", "model", "created_at"},
        )

    def test_regenerate_appends_history_never_overwrites(self):
        project = roadmap_project_with_bl()
        self._generate(project)
        self._generate(project)
        rows = GeneratedPrompt.objects.filter(kind="review")
        self.assertEqual(rows.count(), 2)

    def test_previous_build_prompt_not_overwritten(self):
        project = roadmap_project_with_bl()
        build = GeneratedPrompt.objects.create(
            project=project, task_id="T3", task_title="Supplier catalog API",
            kind=GeneratedPrompt.Kind.BUILD, content="B" * 300,
            context_snapshot={"task": {"id": "T3"}}, model="m",
        )
        self._generate(project)
        build.refresh_from_db()
        self.assertEqual(build.content, "B" * 300)
        self.assertEqual(build.kind, "build")
        self.assertEqual(GeneratedPrompt.objects.filter(kind="build").count(), 1)
        self.assertEqual(GeneratedPrompt.objects.filter(kind="review").count(), 1)

    def test_context_snapshot_is_stored(self):
        project = roadmap_project_with_bl()
        self._generate(project)
        snap = GeneratedPrompt.objects.get(kind="review").context_snapshot
        self.assertEqual(snap["task"]["id"], "T3")
        self.assertTrue(snap["architecture"]["style"])
        self.assertNotIn("context_digest", deep_text(snap))
        self.assertNotIn("anthropic", deep_text(snap))

    def test_deleting_project_cascades_review_prompts(self):
        project = roadmap_project_with_bl()
        self._generate(project)
        project.delete()
        self.assertEqual(GeneratedPrompt.objects.count(), 0)


# --- context propagation / traceability -----------------------------


class ReviewPromptContextTests(AuthenticatedAPITestCase):
    def _generate(self, project, task_id="T3"):
        fake = FakeProvider(VALID_REVIEW)
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(_url(project, task_id))
        return res, fake

    def test_business_logic_reaches_generation(self):
        project = roadmap_project_with_bl()
        _, fake = self._generate(project)
        self.assertIn("APPROVED BUSINESS LOGIC", fake.last_user)
        self.assertIn(
            "Only a manager may approve an order over $1000", fake.last_user
        )

    def test_acceptance_criteria_reaches_generation(self):
        project = roadmap_project_with_bl()
        _, fake = self._generate(project)
        self.assertIn("Acceptance criteria:", fake.last_user)
        self.assertIn("Supplier catalog API works end to end.", fake.last_user)

    def test_architecture_context_reaches_generation(self):
        project = roadmap_project_with_bl()
        _, fake = self._generate(project)
        self.assertIn("ARCHITECTURE", fake.last_user)
        self.assertIn("Catalog service", fake.last_user)
        self.assertIn("Monolith - One team.", fake.last_user)

    def test_requirement_to_business_rule_traceability_preserved(self):
        project = roadmap_project_with_bl()
        res, fake = self._generate(project)
        # rendered prompt keeps the BR -> FR link
        self.assertIn("[reqs: FR1]", fake.last_user)
        # snapshot keeps the structured trace
        snap = GeneratedPrompt.objects.get(kind="review").context_snapshot
        br = snap["business_logic"]["business_rules"][0]
        self.assertEqual(br["id"], "BR-01")
        self.assertIn("FR1", br["related_requirements"])

    def test_latest_build_prompt_included_when_available(self):
        project = roadmap_project_with_bl()
        GeneratedPrompt.objects.create(
            project=project, task_id="T3", task_title="Supplier catalog API",
            kind=GeneratedPrompt.Kind.BUILD,
            content="BUILD-PROMPT-MARKER build the catalog api " * 8,
            context_snapshot={"task": {"id": "T3"}}, model="m",
        )
        res, fake = self._generate(project)
        self.assertIn("PRIOR BUILD PROMPT", fake.last_user)
        self.assertIn("BUILD-PROMPT-MARKER", fake.last_user)
        snap = GeneratedPrompt.objects.get(kind="review").context_snapshot
        self.assertIn("build_prompt", snap)
        self.assertEqual(snap["build_prompt"]["model"], "m")

    def test_generation_works_without_a_build_prompt(self):
        project = roadmap_project_with_bl()
        res, fake = self._generate(project)
        self.assertEqual(res.status_code, 200)
        self.assertIn("none stored", fake.last_user)
        snap = GeneratedPrompt.objects.get(kind="review").context_snapshot
        self.assertNotIn("build_prompt", snap)

    def test_grandfathered_project_without_business_logic_still_generates(self):
        project = roadmap_project_with_bl(with_bl=False)
        res, fake = self._generate(project)
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("APPROVED BUSINESS LOGIC", fake.last_user)


# --- prompt version / provider isolation --------------------------


class ReviewPromptVersionAndIsolationTests(AuthenticatedAPITestCase):
    def test_ai_request_log_records_prompt_version(self):
        project = roadmap_project_with_bl()
        fake = FakeProvider(VALID_REVIEW)
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(_url(project))
        log = AIRequestLog.objects.filter(
            operation="review_prompt_generation"
        ).latest("id")
        self.assertEqual(log.prompt_version, "review_prompt/v1")
        self.assertEqual(log.outcome, "ok")
        self.assertEqual(log.provider, "fake")

    def test_missing_key_writes_no_log_row(self):
        project = roadmap_project_with_bl()
        self.client.post(_url(project))  # 502, missing key -> ensure_ready raises
        self.assertFalse(
            AIRequestLog.objects.filter(
                operation="review_prompt_generation"
            ).exists()
        )

    def test_operation_has_no_provider_specific_code(self):
        from pathlib import Path
        from ai.operations import review_prompt_generation as op

        src = Path(op.__file__).read_text()
        for token in ("anthropic", "messages.create", "tool_use", "with_options"):
            self.assertNotIn(token, src)


# --- build-prompt regression ----------------------------------------


class BuildPromptUnchangedTests(AuthenticatedAPITestCase):
    def test_build_prompt_still_generates_and_persists_kind_build(self):
        project = roadmap_project_with_bl()
        fake = FakeProvider({"prompt_markdown": "# Role\n" + "detail " * 60})
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                f"/api/projects/{project.slug}/roadmap/tasks/T3/build-prompt/"
            )
        self.assertEqual(res.status_code, 200)
        row = GeneratedPrompt.objects.get()
        self.assertEqual(row.kind, GeneratedPrompt.Kind.BUILD)

    def test_build_prompt_missing_key_unchanged(self):
        project = make_roadmap_project(approved=True)
        res = self.client.post(
            f"/api/projects/{project.slug}/roadmap/tasks/T1/build-prompt/"
        )
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
