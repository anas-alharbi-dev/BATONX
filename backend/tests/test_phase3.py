"""
Phase 3 verification tests (Blueprint -> Architecture).

Every deterministic path: the Architecture schema + normalization, the
generate/edit/approve workflow guards (incl. the cross-phase "blueprint must be
approved" gate), transactional persistence, and the Project Context digest
rebuild. The live architecture_generation round trip is PENDING an
ANTHROPIC_API_KEY (README).
"""
import copy
from datetime import datetime, timezone as dt_timezone

from pydantic import ValidationError
from tests.base import AuthenticatedAPITestCase, default_owner

from projects.architecture import (
    ArchitectureContent,
    normalize_architecture_content,
)
from projects.models import Project, ProjectStage
from projects.services import approve_blueprint

NOW = "2026-08-29T00:00:00+00:00"
APPROVED_DT = datetime(2026, 8, 29, tzinfo=dt_timezone.utc)

# Minimal valid Business Logic so post-Phase-D architecture generation clears the
# "business_logic_not_approved" gate.
BL_CONTENT = {
    "summary": "Buyers order from suppliers; managers approve large orders.",
    "actors": [{"name": "Buyer", "description": "Places orders."}],
    "permissions": [],
    "business_rules": [
        {
            "id": "BR-01",
            "statement": "Only a manager may approve an order over $1000.",
            "actor": "Manager",
            "conditions": [],
            "outcome": "",
            "exceptions": [],
            "validations": [],
            "related_requirements": ["FR1"],
            "derived": False,
        }
    ],
    "validations": [],
    "approval_flows": [],
    "state_transitions": [],
    "edge_cases": [],
    "open_questions": [],
}


def approve_business_logic_on(project):
    """Seed an approved Business Logic on a stage=blueprint project."""
    project.business_logic = {
        "content": BL_CONTENT,
        "generated_at": NOW,
        "updated_at": NOW,
        "approved_at": NOW,
    }
    project.business_logic_approved_at = APPROVED_DT
    project.stage = ProjectStage.BUSINESS_LOGIC
    project.save(
        update_fields=["business_logic", "business_logic_approved_at", "stage"]
    )
    return project

BLUEPRINT_CONTENT = {
    "product_summary": "A marketplace connecting restaurants with produce suppliers.",
    "problem": "Restaurants can't compare supplier prices without phone calls.",
    "solution": "A web marketplace with catalogs, quotes, and ordering.",
    "target_users": ["Independent restaurants", "Regional suppliers"],
    "user_roles": [
        {"name": "Restaurant buyer", "description": "Compares suppliers, orders."},
        {"name": "Supplier", "description": "Publishes a catalog, fulfills orders."},
    ],
    "core_features": ["Catalogs", "Quotes", "Ordering"],
    "mvp_features": ["Catalogs", "Ordering"],
    "future_features": ["Invoicing"],
    "functional_requirements": [
        {"id": "FR1", "text": "A supplier can publish a price list.", "priority": "must"},
        {"id": "FR2", "text": "A buyer can place an order.", "priority": "must"},
    ],
    "business_rules": ["Supplier pricing is private."],
    "user_flows": [{"name": "Order", "steps": ["Browse", "Add", "Confirm"]}],
    "out_of_scope": ["In-platform payments"],
}


def architecture_content(**overrides) -> dict:
    content = {
        "overview": {
            "style": "Modular monolith",
            "summary": "A single Django service with a Next.js frontend and Postgres.",
        },
        "frontend": {"choice": "Next.js + TypeScript", "why": "One framework the team knows."},
        "backend": {"choice": "Django + DRF", "why": "Batteries-included, fast to build."},
        "database": {"choice": "PostgreSQL", "why": "Relational data with JSON where useful."},
        "auth": {"approach": "Session auth for buyers, API keys for suppliers", "why": "Two audiences, two needs."},
        "components": [
            {"name": "Catalog service", "responsibility": "Supplier price lists and search."},
            {"name": "Ordering service", "responsibility": "Quotes and orders."},
        ],
        "api_areas": [
            {"name": "Catalog API", "purpose": "Publish and browse price lists."},
            {"name": "Ordering API", "purpose": "Create quotes and orders."},
        ],
        "data_model": [
            {"entity": "Supplier", "fields": ["name", "region"], "relationships": ["has many PriceList"]},
            {"entity": "Order", "fields": ["status", "total"], "relationships": ["belongs to Restaurant"]},
        ],
        "integrations": [
            {"name": "Email (transactional)", "purpose": "Order notifications", "why": "Users expect email receipts."}
        ],
        "security": [
            "Scope supplier API keys to their own catalog.",
            "Never expose one supplier's pricing to another.",
        ],
        "deployment": {"approach": "Single container + managed Postgres", "why": "Small team, low ops."},
        "key_decisions": [
            {"decision": "Monolith over microservices", "rationale": "Two bounded contexts, one team."}
        ],
        "constraints": ["No in-platform payments in the MVP."],
    }
    content.update(overrides)
    return content


def make_arch_project(*, approved: bool = False, stage=ProjectStage.ARCHITECTURE, **overrides) -> Project:
    data = {
        "original_idea": "A marketplace where restaurants compare suppliers and order.",
        "stage": stage,
        "owner": default_owner(),
        "blueprint": {"content": BLUEPRINT_CONTENT, "generated_at": NOW, "updated_at": NOW, "approved_at": NOW},
        "blueprint_approved_at": APPROVED_DT,
        "context_digest": {"idea_analysis": {"domain": "B2B marketplace"}, "blueprint": {"mvp_features": ["Catalogs", "Ordering"]}},
        "discovery": {"questions": [], "answers": {}, "generated_at": NOW, "answered_at": NOW},
        "architecture": {
            "content": architecture_content(),
            "generated_at": NOW,
            "updated_at": NOW,
            "approved_at": None,
        },
    }
    data.update(overrides)
    project = Project.objects.create(**data)
    if approved:
        from projects.services import approve_architecture

        project = approve_architecture(project)
    return project


def make_approved_blueprint_project(**overrides) -> Project:
    """stage=blueprint, blueprint approved, no architecture yet."""
    data = {
        "original_idea": "A marketplace where restaurants compare suppliers and order.",
        "stage": ProjectStage.BLUEPRINT,
        "owner": default_owner(),
        "blueprint": {"content": BLUEPRINT_CONTENT, "generated_at": NOW, "updated_at": NOW, "approved_at": None},
        "discovery": {"questions": [], "answers": {}, "generated_at": NOW, "answered_at": NOW},
        "context_digest": {"idea_analysis": {"domain": "B2B marketplace"}},
    }
    data.update(overrides)
    project = Project.objects.create(**data)
    return approve_blueprint(project)


class ArchitectureSchemaTests(AuthenticatedAPITestCase):
    def test_valid_content(self):
        model = ArchitectureContent.model_validate(architecture_content())
        self.assertEqual(model.overview.style, "Modular monolith")
        self.assertEqual(len(model.data_model), 2)

    def test_missing_required_section_rejected(self):
        content = architecture_content()
        del content["overview"]
        with self.assertRaises(ValidationError):
            ArchitectureContent.model_validate(content)

    def test_empty_security_rejected(self):
        with self.assertRaises(ValidationError):
            ArchitectureContent.model_validate(architecture_content(security=[]))

    def test_empty_components_rejected(self):
        with self.assertRaises(ValidationError):
            ArchitectureContent.model_validate(architecture_content(components=[]))

    def test_tech_choice_requires_why(self):
        content = architecture_content()
        content["frontend"] = {"choice": "Next.js"}
        with self.assertRaises(ValidationError):
            ArchitectureContent.model_validate(content)

    def test_normalize_strips_blanks(self):
        raw = architecture_content(
            security=["Real practice", "  ", ""],
            constraints=["", "  "],
            data_model=[
                {"entity": "X", "fields": ["a", "", "  "], "relationships": [""]},
            ],
        )
        normalized = normalize_architecture_content(raw)
        self.assertEqual(normalized["security"], ["Real practice"])
        self.assertEqual(normalized["constraints"], [])
        self.assertEqual(normalized["data_model"][0]["fields"], ["a"])
        self.assertEqual(normalized["data_model"][0]["relationships"], [])


class ArchitectureGenerateGuardTests(AuthenticatedAPITestCase):
    def _url(self, project):
        return f"/api/projects/{project.slug}/architecture/generate/"

    def test_unknown_project_returns_404(self):
        res = self.client.post("/api/projects/nope/architecture/generate/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "project_not_found")

    def test_blueprint_not_approved_returns_409(self):
        project = Project.objects.create(
            original_idea="x",
            stage=ProjectStage.BLUEPRINT,
            owner=default_owner(),
            blueprint={"content": BLUEPRINT_CONTENT, "generated_at": NOW, "updated_at": NOW},
            discovery={"questions": [], "answers": {}, "generated_at": NOW, "answered_at": NOW},
        )
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "blueprint_not_approved")

    def test_locked_stage_returns_409(self):
        project = make_arch_project(stage=ProjectStage.ROADMAP)
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "invalid_workflow_state")

    def test_missing_api_key_returns_502_and_no_side_effects(self):
        project = approve_business_logic_on(make_approved_blueprint_project())
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
        project.refresh_from_db()
        self.assertEqual(project.stage, ProjectStage.BUSINESS_LOGIC)
        self.assertEqual(project.architecture, {})

    def test_regenerate_missing_key_keeps_existing_approval(self):
        project = make_arch_project(approved=True)
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 502)
        project.refresh_from_db()
        self.assertIsNotNone(project.architecture_approved_at)
        self.assertEqual(project.stage, ProjectStage.ARCHITECTURE)


class ArchitectureUpdateTests(AuthenticatedAPITestCase):
    def _url(self, project):
        return f"/api/projects/{project.slug}/architecture/"

    def test_edit_fields_section(self):
        project = make_arch_project()
        res = self.client.patch(
            self._url(project),
            {"content": {"frontend": {"choice": "SvelteKit", "why": "Smaller bundle."}}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.architecture["content"]["frontend"]["choice"], "SvelteKit")

    def test_edit_invalid_value_returns_400(self):
        project = make_arch_project()
        res = self.client.patch(
            self._url(project), {"content": {"security": []}}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_architecture")
        project.refresh_from_db()
        self.assertEqual(len(project.architecture["content"]["security"]), 2)

    def test_unknown_section_returns_400(self):
        project = make_arch_project()
        res = self.client.patch(
            self._url(project), {"content": {"caching_layer": "redis"}}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("caching_layer", res.json()["error"]["details"]["unknown"])

    def test_edit_before_generation_returns_409(self):
        project = make_approved_blueprint_project()
        res = self.client.patch(
            self._url(project), {"content": {"security": ["x"]}}, format="json"
        )
        self.assertEqual(res.status_code, 409)

    def test_edit_data_model_entities(self):
        project = make_arch_project()
        entities = copy.deepcopy(project.architecture["content"]["data_model"])
        entities.append({"entity": "PriceList", "fields": ["effective_date"], "relationships": ["belongs to Supplier"]})
        res = self.client.patch(
            self._url(project), {"content": {"data_model": entities}}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(len(project.architecture["content"]["data_model"]), 3)

    def test_edit_reverts_approval_and_updates_context(self):
        project = make_arch_project(approved=True)
        self.assertIn("architecture", project.context_digest)
        res = self.client.patch(
            self._url(project),
            {"content": {"overview": {"style": "Layered monolith", "summary": "Revised."}}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertIsNone(project.architecture_approved_at)
        self.assertNotIn("architecture", project.context_digest)
        self.assertIn("blueprint", project.context_digest)  # blueprint stays


class ArchitectureApproveTests(AuthenticatedAPITestCase):
    def _url(self, project):
        return f"/api/projects/{project.slug}/architecture/approve/"

    def test_approve_sets_timestamp_and_rebuilds_context(self):
        project = make_arch_project()
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertIsNotNone(project.architecture_approved_at)
        digest = project.context_digest["architecture"]
        self.assertEqual(digest["style"], "Modular monolith")
        self.assertEqual(digest["frontend"], "Next.js + TypeScript")
        self.assertEqual(digest["components"], ["Catalog service", "Ordering service"])
        self.assertIn("idea_analysis", project.context_digest)
        self.assertIn("blueprint", project.context_digest)

    def test_approve_without_architecture_returns_409(self):
        project = make_approved_blueprint_project()
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)

    def test_approve_wrong_stage_returns_409(self):
        project = make_arch_project(stage=ProjectStage.ROADMAP)
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)


class ArchitectureSerializerTests(AuthenticatedAPITestCase):
    def test_detail_exposes_architecture_not_context_digest(self):
        project = make_arch_project(approved=True)
        res = self.client.get(f"/api/projects/{project.slug}/")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertIn("architecture", payload)
        self.assertIsNotNone(payload["architecture_approved_at"])
        self.assertEqual(len(payload["architecture"]["content"]["data_model"]), 2)
        self.assertNotIn("context_digest", payload)


class CrossPhaseContextTests(AuthenticatedAPITestCase):
    def test_full_digest_after_all_approvals(self):
        project = make_arch_project(approved=True)
        project.refresh_from_db()
        self.assertEqual(
            set(project.context_digest.keys()),
            {"idea_analysis", "blueprint", "architecture"},
        )

    def test_blueprint_locked_once_architecture_exists(self):
        project = make_arch_project()  # stage = architecture
        res = self.client.patch(
            f"/api/projects/{project.slug}/blueprint/",
            {"content": {"problem": "changed"}},
            format="json",
        )
        self.assertEqual(res.status_code, 409)
