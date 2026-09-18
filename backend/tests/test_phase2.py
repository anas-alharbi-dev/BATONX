"""
Phase 2 verification tests (Discovery -> Product Blueprint).

Covers every deterministic path: the stored Blueprint schema + normalization,
the generate/edit/approve workflow guards, transactional persistence, and the
Project Context digest rebuild. The live blueprint_generation round trip is
verified separately once an ANTHROPIC_API_KEY is available (README: PENDING).
"""
import copy

from pydantic import ValidationError
from tests.base import AuthenticatedAPITestCase, default_owner

from projects.blueprint import BlueprintContent, normalize_blueprint_content
from projects.models import Project, ProjectStage


def blueprint_content(**overrides) -> dict:
    content = {
        "product_summary": "A marketplace connecting restaurants with produce suppliers.",
        "problem": "Restaurants can't compare supplier prices without phone calls.",
        "solution": "A web marketplace with supplier catalogs, quotes, and ordering.",
        "target_users": ["Independent restaurants", "Regional produce suppliers"],
        "user_roles": [
            {"name": "Restaurant buyer", "description": "Compares suppliers and places orders."},
            {"name": "Supplier", "description": "Publishes a catalog and fulfills orders."},
        ],
        "core_features": ["Supplier catalogs", "Quote requests", "Ordering", "Invoicing"],
        "mvp_features": ["Supplier catalogs", "Ordering"],
        "future_features": ["Invoicing", "Delivery tracking"],
        "functional_requirements": [
            {"id": "FR1", "text": "A supplier can publish a price list.", "priority": "must"},
            {"id": "FR2", "text": "A buyer can place an order with a supplier.", "priority": "must"},
        ],
        "business_rules": ["Prices are supplier-specific and never shown to competitors."],
        "user_flows": [
            {"name": "Place an order", "steps": ["Browse catalogs", "Add items", "Confirm order"]}
        ],
        "out_of_scope": ["Payments inside the platform"],
    }
    content.update(overrides)
    return content


def make_blueprint_project(*, approved: bool = False, **overrides) -> Project:
    now = "2026-08-29T00:00:00+00:00"
    data = {
        "original_idea": "A marketplace where restaurants compare suppliers and order.",
        "stage": ProjectStage.BLUEPRINT,
        "owner": default_owner(),
        "context_digest": {"idea_analysis": {"domain": "B2B marketplace"}},
        "discovery": {
            "questions": [],
            "answers": {},
            "generated_at": now,
            "answered_at": now,
        },
        "blueprint": {
            "content": blueprint_content(),
            "generated_at": now,
            "updated_at": now,
            "approved_at": None,
        },
    }
    data.update(overrides)
    project = Project.objects.create(**data)
    if approved:
        from projects.services import approve_blueprint

        project = approve_blueprint(project)
    return project


def make_answered_discovery_project(**overrides) -> Project:
    now = "2026-08-29T00:00:00+00:00"
    data = {
        "original_idea": "A booking app for climbing gyms.",
        "stage": ProjectStage.DISCOVERY,
        "owner": default_owner(),
        "context_digest": {"idea_analysis": {"domain": "fitness SaaS"}},
        "discovery": {
            "questions": [
                {"id": "q1", "question": "Web or mobile?", "type": "single_select",
                 "options": ["Web", "Mobile"], "why_it_matters": "Platform."}
            ],
            "answers": {"q1": "Web"},
            "generated_at": now,
            "answered_at": now,
        },
    }
    data.update(overrides)
    return Project.objects.create(**data)


class BlueprintSchemaTests(AuthenticatedAPITestCase):
    def test_valid_content(self):
        model = BlueprintContent.model_validate(blueprint_content())
        self.assertEqual(len(model.functional_requirements), 2)

    def test_missing_required_section_rejected(self):
        content = blueprint_content()
        del content["problem"]
        with self.assertRaises(ValidationError):
            BlueprintContent.model_validate(content)

    def test_empty_mvp_features_rejected(self):
        with self.assertRaises(ValidationError):
            BlueprintContent.model_validate(blueprint_content(mvp_features=[]))

    def test_bad_priority_rejected(self):
        content = blueprint_content()
        content["functional_requirements"][0]["priority"] = "urgent"
        with self.assertRaises(ValidationError):
            BlueprintContent.model_validate(content)

    def test_normalize_assigns_and_preserves_requirement_ids(self):
        raw = blueprint_content(
            functional_requirements=[
                {"text": "Requirement without id.", "priority": "should"},
                {"id": "FR9", "text": "Keeps its id.", "priority": "must"},
                {"id": "", "text": "Blank id gets one.", "priority": "could"},
            ]
        )
        normalized = normalize_blueprint_content(raw)
        ids = [r["id"] for r in normalized["functional_requirements"]]
        self.assertEqual(ids[1], "FR9")
        self.assertTrue(all(ids))
        self.assertEqual(len(set(ids)), 3)

    def test_normalize_strips_blank_list_entries(self):
        normalized = normalize_blueprint_content(
            blueprint_content(mvp_features=["Real feature", "  ", ""])
        )
        self.assertEqual(normalized["mvp_features"], ["Real feature"])


class BlueprintGenerateGuardTests(AuthenticatedAPITestCase):
    def _url(self, project):
        return f"/api/projects/{project.slug}/blueprint/generate/"

    def test_unknown_project_returns_404(self):
        res = self.client.post("/api/projects/nope/blueprint/generate/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "project_not_found")

    def test_discovery_not_answered_returns_409_before_ai(self):
        project = make_answered_discovery_project(
            discovery={"questions": [], "answers": {}, "generated_at": None, "answered_at": None}
        )
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "discovery_incomplete")

    def test_locked_stage_returns_409(self):
        project = make_answered_discovery_project(stage=ProjectStage.ARCHITECTURE)
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "invalid_workflow_state")

    def test_missing_api_key_returns_502_and_no_side_effects(self):
        project = make_answered_discovery_project()
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
        project.refresh_from_db()
        self.assertEqual(project.stage, ProjectStage.DISCOVERY)
        self.assertEqual(project.blueprint, {})

    def test_regenerate_with_missing_key_keeps_existing_approval(self):
        project = make_blueprint_project(approved=True)
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 502)
        project.refresh_from_db()
        self.assertIsNotNone(project.blueprint_approved_at)  # untouched
        self.assertEqual(project.stage, ProjectStage.BLUEPRINT)


class BlueprintUpdateTests(AuthenticatedAPITestCase):
    def _url(self, project):
        return f"/api/projects/{project.slug}/blueprint/"

    def test_edit_prose_section(self):
        project = make_blueprint_project()
        res = self.client.patch(
            self._url(project),
            {"content": {"problem": "Rewritten problem statement."}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.blueprint["content"]["problem"], "Rewritten problem statement.")

    def test_edit_invalid_section_value_returns_400(self):
        project = make_blueprint_project()
        res = self.client.patch(
            self._url(project), {"content": {"mvp_features": []}}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_blueprint")
        project.refresh_from_db()
        self.assertEqual(project.blueprint["content"]["mvp_features"], ["Supplier catalogs", "Ordering"])

    def test_unknown_section_returns_400(self):
        project = make_blueprint_project()
        res = self.client.patch(
            self._url(project), {"content": {"pricing_model": "freemium"}}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("pricing_model", res.json()["error"]["details"]["unknown"])

    def test_edit_before_generation_returns_409(self):
        project = make_answered_discovery_project()
        res = self.client.patch(
            self._url(project), {"content": {"problem": "x"}}, format="json"
        )
        self.assertEqual(res.status_code, 409)

    def test_edit_mints_ids_for_new_requirements(self):
        project = make_blueprint_project()
        reqs = copy.deepcopy(project.blueprint["content"]["functional_requirements"])
        reqs.append({"text": "A buyer can save a supplier as a favourite.", "priority": "could"})
        res = self.client.patch(
            self._url(project), {"content": {"functional_requirements": reqs}}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        new_ids = [r["id"] for r in project.blueprint["content"]["functional_requirements"]]
        self.assertEqual(len(new_ids), 3)
        self.assertTrue(all(new_ids))

    def test_edit_reverts_approval_and_updates_context(self):
        project = make_blueprint_project(approved=True)
        self.assertIn("blueprint", project.context_digest)
        res = self.client.patch(
            self._url(project),
            {"content": {"solution": "A revised solution paragraph."}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertIsNone(project.blueprint_approved_at)
        self.assertNotIn("blueprint", project.context_digest)


class BlueprintApproveTests(AuthenticatedAPITestCase):
    def _url(self, project):
        return f"/api/projects/{project.slug}/blueprint/approve/"

    def test_approve_sets_timestamp_and_rebuilds_context(self):
        project = make_blueprint_project()
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertIsNotNone(project.blueprint_approved_at)
        digest = project.context_digest["blueprint"]
        self.assertEqual(digest["mvp_features"], ["Supplier catalogs", "Ordering"])
        self.assertEqual(digest["user_roles"], ["Restaurant buyer", "Supplier"])
        self.assertEqual(len(digest["functional_requirements"]), 2)
        self.assertIn("idea_analysis", project.context_digest)

    def test_approve_without_blueprint_returns_409(self):
        project = make_answered_discovery_project()
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)

    def test_approve_wrong_stage_returns_409(self):
        project = make_blueprint_project(stage=ProjectStage.ARCHITECTURE)
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)


class BlueprintSerializerTests(AuthenticatedAPITestCase):
    def test_detail_exposes_blueprint_not_context_digest(self):
        project = make_blueprint_project(approved=True)
        res = self.client.get(f"/api/projects/{project.slug}/")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertIn("blueprint", payload)
        self.assertIsNotNone(payload["blueprint_approved_at"])
        self.assertEqual(len(payload["blueprint"]["content"]["user_roles"]), 2)
        self.assertNotIn("context_digest", payload)
