"""
Phase 1 verification tests (Idea -> Discovery).

These cover everything that does NOT require a live Anthropic call:
- error envelopes and status codes
- transactional project creation (no partial rows on AI failure)
- discovery-answer validation (complete / incomplete / invalid / wrong stage)
- the discovery_generation output schema

The live idea_analysis + discovery_generation round trip is verified separately
once an ANTHROPIC_API_KEY is available (see README: PENDING).
"""
from django.test import override_settings
from pydantic import ValidationError
from tests.base import AuthenticatedAPITestCase, default_owner

from ai.operations.discovery_generation import DiscoveryQuestions
from projects.models import Project, ProjectStage


def make_project(**overrides) -> Project:
    questions = [
        {
            "id": "q1",
            "question": "Who places orders in the platform?",
            "type": "single_select",
            "options": ["Restaurant staff", "Suppliers", "Both"],
            "why_it_matters": "Sets the primary role and permissions model.",
        },
        {
            "id": "q2",
            "question": "Which capabilities are in the first release?",
            "type": "multi_select",
            "options": ["Catalog", "Quotes", "Ordering", "Invoicing"],
            "why_it_matters": "Defines MVP scope.",
        },
        {
            "id": "q3",
            "question": "Describe how pricing is determined.",
            "type": "text",
            "options": [],
            "why_it_matters": "Drives the pricing data model.",
        },
    ]
    data = {
        "original_idea": "A marketplace where restaurants compare suppliers and order.",
        "stage": ProjectStage.DISCOVERY,
        "owner": default_owner(),
        "discovery": {
            "questions": questions,
            "answers": {},
            "generated_at": "2026-08-28T00:00:00+00:00",
            "answered_at": None,
        },
    }
    data.update(overrides)
    return Project.objects.create(**data)


class HealthTests(AuthenticatedAPITestCase):
    def test_health_ok(self):
        res = self.client.get("/api/health/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["database"], "ok")


class CreateProjectTests(AuthenticatedAPITestCase):
    def test_empty_idea_returns_400_envelope(self):
        res = self.client.post("/api/projects/", {"idea": "   "}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "empty_idea")
        self.assertEqual(Project.objects.count(), 0)

    @override_settings(ANTHROPIC_API_KEY="")
    def test_missing_key_returns_502_and_creates_no_project(self):
        res = self.client.post(
            "/api/projects/", {"idea": "A tool to schedule dentist visits"}, format="json"
        )
        self.assertEqual(res.status_code, 502)
        body = res.json()["error"]
        self.assertEqual(body["code"], "missing_api_key")
        self.assertFalse(body["retryable"])
        self.assertEqual(Project.objects.count(), 0)


class ProjectDetailTests(AuthenticatedAPITestCase):
    def test_missing_project_returns_404_envelope(self):
        res = self.client.get("/api/projects/does-not-exist/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "project_not_found")

    def test_existing_project_includes_discovery(self):
        project = make_project()
        res = self.client.get(f"/api/projects/{project.slug}/")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["stage"], "discovery")
        self.assertEqual(len(payload["discovery"]["questions"]), 3)
        self.assertNotIn("context_digest", payload)


class DiscoveryAnswersTests(AuthenticatedAPITestCase):
    def _url(self, project):
        return f"/api/projects/{project.slug}/discovery/answers/"

    def test_happy_path_persists_answers(self):
        project = make_project()
        answers = {
            "q1": "Both",
            "q2": ["Catalog", "Ordering"],
            "q3": "Supplier-specific negotiated pricing.",
        }
        res = self.client.post(self._url(project), {"answers": answers}, format="json")
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.discovery["answers"], answers)
        self.assertIsNotNone(project.discovery["answered_at"])

    def test_incomplete_answers_returns_400_with_missing_list(self):
        project = make_project()
        res = self.client.post(
            self._url(project), {"answers": {"q1": "Both"}}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        body = res.json()["error"]
        self.assertEqual(body["code"], "incomplete_answers")
        self.assertCountEqual(body["details"]["missing"], ["q2", "q3"])
        project.refresh_from_db()
        self.assertEqual(project.discovery["answers"], {})

    def test_invalid_option_returns_400(self):
        project = make_project()
        answers = {"q1": "Nobody", "q2": ["Catalog"], "q3": "x"}
        res = self.client.post(self._url(project), {"answers": answers}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_answer")

    def test_multi_select_rejects_unknown_values(self):
        project = make_project()
        answers = {"q1": "Both", "q2": ["Catalog", "Telepathy"], "q3": "x"}
        res = self.client.post(self._url(project), {"answers": answers}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_answer")

    def test_wrong_stage_returns_409(self):
        project = make_project(stage=ProjectStage.BLUEPRINT)
        answers = {"q1": "Both", "q2": ["Catalog"], "q3": "x"}
        res = self.client.post(self._url(project), {"answers": answers}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "invalid_workflow_state")

    def test_unknown_project_returns_404(self):
        res = self.client.post(
            "/api/projects/nope/discovery/answers/", {"answers": {}}, format="json"
        )
        self.assertEqual(res.status_code, 404)

    def test_answers_can_be_edited(self):
        project = make_project()
        first = {"q1": "Both", "q2": ["Catalog"], "q3": "flat pricing"}
        self.client.post(self._url(project), {"answers": first}, format="json")
        second = {"q1": "Suppliers", "q2": ["Quotes", "Ordering"], "q3": "negotiated"}
        res = self.client.post(self._url(project), {"answers": second}, format="json")
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.discovery["answers"], second)


class DiscoverySchemaTests(AuthenticatedAPITestCase):
    def _q(self, **over):
        base = {
            "question": "Does the platform take payment?",
            "type": "single_select",
            "options": ["Yes", "No"],
            "why_it_matters": "Determines whether a payment provider is needed.",
        }
        base.update(over)
        return base

    def test_valid_payload(self):
        model = DiscoveryQuestions.model_validate(
            {"questions": [self._q(), self._q(type="text", options=[]), self._q()]}
        )
        self.assertEqual(len(model.questions), 3)

    def test_too_few_questions_rejected(self):
        with self.assertRaises(ValidationError):
            DiscoveryQuestions.model_validate({"questions": [self._q(), self._q()]})

    def test_select_without_enough_options_rejected(self):
        with self.assertRaises(ValidationError):
            DiscoveryQuestions.model_validate(
                {"questions": [self._q(options=["Only one"]), self._q(), self._q()]}
            )

    def test_text_question_options_are_cleared(self):
        model = DiscoveryQuestions.model_validate(
            {
                "questions": [
                    self._q(type="text", options=["stray", "options"]),
                    self._q(),
                    self._q(),
                ]
            }
        )
        self.assertEqual(model.questions[0].options, [])
