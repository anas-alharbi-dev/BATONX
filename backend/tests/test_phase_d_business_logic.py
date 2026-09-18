"""
Phase D verification — Business Logic stage (Blueprint -> Business Logic -> Architecture).

Deterministic paths only. The live business_logic_generation round trip is
PENDING an ANTHROPIC_API_KEY.
"""
import copy
import unittest.mock as mock
from datetime import datetime, timezone as dt_timezone

from pydantic import ValidationError
from tests.base import AuthenticatedAPITestCase, default_owner

from ai.operations.business_logic_generation import (
    BUSINESS_LOGIC_GENERATION,
    BusinessLogicDraft,
    BusinessRuleDraft,
)
from ai.providers.base import StructuredResult
from projects import dependencies as dep
from projects.business_logic import (
    BusinessLogicContent,
    canonical_requirement,
    normalize_business_logic_content,
)
from projects.context import build_context_digest
from projects.context_selection import assemble_task_context
from projects.models import GeneratedPrompt, Project, ProjectStage
from projects.services import (
    approve_architecture,
    approve_business_logic,
    approve_blueprint,
    generate_architecture,
    generate_roadmap,
    update_business_logic,
)
from tests.test_phase3 import (
    BLUEPRINT_CONTENT,
    NOW,
    APPROVED_DT,
    architecture_content,
    make_approved_blueprint_project,
)
from tests.test_phase4 import make_roadmap_project

# --- fixtures --------------------------------------------------------------


def bl_content(**overrides) -> dict:
    content = {
        "summary": "Buyers order from suppliers; managers approve large orders.",
        "actors": [
            {"name": "Buyer", "description": "Places orders."},
            {"name": "Manager", "description": "Approves large orders."},
        ],
        "permissions": [
            {"actor": "Manager", "can": ["Approve order", "Reject order"],
             "conditions": ["Order status is Pending"]},
        ],
        "business_rules": [
            {
                "id": "BR-01",
                "statement": "Only a manager may approve an order over $1000.",
                "actor": "Manager",
                "conditions": ["Order total > 1000", "Order status is Pending"],
                "outcome": "Order status changes to Approved or Rejected.",
                "exceptions": ["The buyer cannot approve their own order."],
                "validations": [],
                "related_requirements": ["FR1"],
                "derived": False,
            },
            {
                "id": "BR-02",
                "statement": "An order cannot be edited once approved.",
                "actor": "",
                "conditions": ["Order status is Approved"],
                "outcome": "Edit attempts are rejected.",
                "exceptions": [],
                "validations": [],
                "related_requirements": ["FR2"],
                "derived": True,
            },
        ],
        "validations": [
            {"id": "VAL-01", "rule": "An order line quantity must be positive.",
             "applies_to": "Order line", "related_requirements": ["FR2"]},
        ],
        "approval_flows": [
            {"name": "Large order approval", "approver": "Manager",
             "steps": ["Buyer submits order", "Manager reviews", "Manager approves or rejects"],
             "conditions": ["Order total > 1000"], "related_requirements": ["FR1"]},
        ],
        "state_transitions": [
            {"entity": "Order", "from_state": "Pending", "to_state": "Approved",
             "trigger": "Manager approves", "actor": "Manager",
             "guards": ["Order total > 1000 requires manager"],
             "effects": ["Supplier is notified"], "related_requirements": ["FR1"]},
        ],
        "edge_cases": [
            {"id": "EC-01", "scenario": "Buyer approves their own order",
             "expected_behavior": "The action is rejected with an authorization error.",
             "related_requirements": ["FR1"]},
        ],
        "open_questions": ["Is there a maximum order value?"],
    }
    content.update(overrides)
    return content


def project_with_approved_bl(**overrides) -> Project:
    project = make_approved_blueprint_project(**overrides)
    project.business_logic = {
        "content": bl_content(),
        "generated_at": NOW,
        "updated_at": NOW,
        "approved_at": NOW,
    }
    project.business_logic_approved_at = APPROVED_DT
    project.stage = ProjectStage.BUSINESS_LOGIC
    project.save(update_fields=["business_logic", "business_logic_approved_at", "stage"])
    return project


class FakeProvider:
    """Captures the rendered user prompt; returns a fixed structured payload."""

    name = "fake"

    def __init__(self, payload):
        self.payload = payload
        self.last_user = None

    def ensure_ready(self):
        pass

    def generate_structured(self, *, system, user, json_schema, timeout, prior_attempt=None):
        self.last_user = user
        return StructuredResult(
            data=self.payload, provider=self.name, model="fake-1",
            input_tokens=1, output_tokens=1,
        )


# --- schema / normalization --------------------------------------------


class BusinessLogicSchemaTests(AuthenticatedAPITestCase):
    def test_valid_content(self):
        model = BusinessLogicContent.model_validate(bl_content())
        self.assertEqual(len(model.business_rules), 2)

    def test_requires_at_least_one_actor_and_rule(self):
        with self.assertRaises(ValidationError):
            BusinessLogicContent.model_validate(bl_content(actors=[]))
        with self.assertRaises(ValidationError):
            BusinessLogicContent.model_validate(bl_content(business_rules=[]))

    def test_missing_summary_rejected(self):
        c = bl_content()
        del c["summary"]
        with self.assertRaises(ValidationError):
            BusinessLogicContent.model_validate(c)

    def test_deterministic_id_assignment(self):
        raw = bl_content(
            business_rules=[
                {"statement": "Rule with no id.", "related_requirements": []},
                {"id": "BR-09", "statement": "Keeps id.", "related_requirements": []},
                {"id": "", "statement": "Blank id.", "related_requirements": []},
            ],
            validations=[{"rule": "V1"}, {"rule": "V2"}],
            edge_cases=[{"scenario": "S", "expected_behavior": "B"}],
        )
        norm = normalize_business_logic_content(raw)
        br_ids = [r["id"] for r in norm["business_rules"]]
        self.assertEqual(br_ids[1], "BR-09")
        self.assertTrue(all(i.startswith("BR-") for i in br_ids))
        self.assertEqual(len(set(br_ids)), 3)
        self.assertEqual([v["id"] for v in norm["validations"]], ["VAL-01", "VAL-02"])
        self.assertEqual(norm["edge_cases"][0]["id"], "EC-01")

    def test_requirement_reference_canonicalisation(self):
        self.assertEqual(canonical_requirement("FR-08"), "FR8")
        self.assertEqual(canonical_requirement("fr 8"), "FR8")
        self.assertEqual(canonical_requirement("FR8"), "FR8")
        self.assertEqual(canonical_requirement("REQ-3"), "REQ-3")
        norm = normalize_business_logic_content(
            bl_content(
                business_rules=[
                    {"statement": "x", "related_requirements": ["FR-01", "fr 1", "FR2"]}
                ]
            )
        )
        self.assertEqual(
            norm["business_rules"][0]["related_requirements"], ["FR1", "FR2"]
        )

    def test_normalize_is_idempotent(self):
        once = normalize_business_logic_content(bl_content())
        twice = normalize_business_logic_content(once)
        self.assertEqual(once, twice)

    def test_draft_schema_has_no_ids(self):
        self.assertNotIn("id", BusinessRuleDraft.model_fields)
        self.assertIn("id", BusinessLogicContent.model_fields["business_rules"]
                      .annotation.__args__[0].model_fields)


# --- workflow gates + lifecycle --------------------------------------


class BusinessLogicGenerateGuardTests(AuthenticatedAPITestCase):
    def _url(self, p):
        return f"/api/projects/{p.slug}/business-logic/generate/"

    def test_unknown_project_404(self):
        res = self.client.post("/api/projects/nope/business-logic/generate/")
        self.assertEqual(res.status_code, 404)

    def test_cannot_generate_before_blueprint_approval(self):
        project = Project.objects.create(
            original_idea="x",
            stage=ProjectStage.BLUEPRINT,
            owner=default_owner(),
            blueprint={"content": BLUEPRINT_CONTENT, "approved_at": None},
            discovery={"questions": [], "answers": {}, "generated_at": NOW, "answered_at": NOW},
        )
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "blueprint_not_approved")

    def test_locked_stage_returns_409(self):
        project = make_roadmap_project(approved=True)  # stage=roadmap
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "invalid_workflow_state")

    def test_missing_api_key_502_no_side_effects(self):
        project = make_approved_blueprint_project()  # stage=blueprint, bp approved
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
        project.refresh_from_db()
        self.assertEqual(project.stage, ProjectStage.BLUEPRINT)
        self.assertEqual(project.business_logic, {})

    def test_generation_persists_only_after_valid_ai_result(self):
        project = make_approved_blueprint_project()
        # invalid structured output -> ai_invalid_output, nothing persisted
        fake = FakeProvider({"summary": "x"})  # missing actors/business_rules
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 502)
        project.refresh_from_db()
        self.assertEqual(project.business_logic, {})
        self.assertEqual(project.stage, ProjectStage.BLUEPRINT)

    def test_successful_generation_persists_draft_and_advances_stage(self):
        project = make_approved_blueprint_project()
        fake = FakeProvider(BusinessLogicDraft.model_validate(bl_content()).model_dump(mode="json"))
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.stage, ProjectStage.BUSINESS_LOGIC)
        self.assertIsNone(project.business_logic_approved_at)
        self.assertEqual(len(project.business_logic["content"]["business_rules"]), 2)
        # prompt_version recorded
        from ai.models import AIRequestLog
        log = AIRequestLog.objects.get(operation="business_logic_generation")
        self.assertEqual(log.prompt_version, "business_logic/v1")
        self.assertEqual(log.provider, "fake")


class BusinessLogicUpdateTests(AuthenticatedAPITestCase):
    def _url(self, p):
        return f"/api/projects/{p.slug}/business-logic/"

    def test_edit_section(self):
        project = project_with_approved_bl()
        new_summary = "Rewritten behavioral summary."
        res = self.client.patch(
            self._url(project), {"content": {"summary": new_summary}}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.business_logic["content"]["summary"], new_summary)
        self.assertIsNone(project.business_logic_approved_at)  # reverted to draft

    def test_invalid_edit_rejected(self):
        project = project_with_approved_bl()
        res = self.client.patch(
            self._url(project), {"content": {"actors": []}}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_business_logic")
        project.refresh_from_db()
        self.assertEqual(len(project.business_logic["content"]["actors"]), 2)

    def test_unknown_section_rejected(self):
        project = project_with_approved_bl()
        res = self.client.patch(
            self._url(project), {"content": {"policies": []}}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("policies", res.json()["error"]["details"]["unknown"])

    def test_edit_before_generation_409(self):
        project = make_approved_blueprint_project()
        res = self.client.patch(
            self._url(project), {"content": {"summary": "x"}}, format="json"
        )
        self.assertEqual(res.status_code, 409)

    def test_edit_renumbers_new_rule_ids(self):
        project = project_with_approved_bl()
        rules = copy.deepcopy(project.business_logic["content"]["business_rules"])
        rules.append({"statement": "A brand new rule.", "related_requirements": ["FR-03"]})
        res = self.client.patch(
            self._url(project), {"content": {"business_rules": rules}}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        ids = [r["id"] for r in project.business_logic["content"]["business_rules"]]
        self.assertEqual(len(ids), 3)
        self.assertTrue(all(i.startswith("BR-") for i in ids))
        # traceability canonicalised on the new rule
        self.assertEqual(
            project.business_logic["content"]["business_rules"][2]["related_requirements"],
            ["FR3"],
        )


class BusinessLogicApproveTests(AuthenticatedAPITestCase):
    def _url(self, p):
        return f"/api/projects/{p.slug}/business-logic/approve/"

    def test_approve_sets_timestamp_and_digest(self):
        project = make_approved_blueprint_project()
        project.business_logic = {"content": bl_content(), "generated_at": NOW, "updated_at": NOW, "approved_at": None}
        project.stage = ProjectStage.BUSINESS_LOGIC
        project.save(update_fields=["business_logic", "stage"])

        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertIsNotNone(project.business_logic_approved_at)
        d = project.context_digest["business_logic"]
        self.assertEqual(d["summary"], bl_content()["summary"])
        self.assertEqual([r["id"] for r in d["business_rules"]], ["BR-01", "BR-02"])
        self.assertEqual(d["business_rules"][0]["related_requirements"], ["FR1"])
        # concise: no verbose per-rule fields in the digest
        self.assertNotIn("conditions", d["business_rules"][0])
        self.assertNotIn("outcome", d["business_rules"][0])
        # business_logic appears in the digest, after blueprint
        keys = list(project.context_digest.keys())
        self.assertIn("business_logic", keys)
        self.assertGreater(keys.index("business_logic"), keys.index("blueprint"))

    def test_approve_wrong_stage_409(self):
        project = make_roadmap_project(approved=True)
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)

    def test_approve_without_content_409(self):
        project = make_approved_blueprint_project()
        project.stage = ProjectStage.BUSINESS_LOGIC
        project.save(update_fields=["stage"])
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)


# --- gate on Architecture + grandfathering --------------------------


class ArchitectureGateTests(AuthenticatedAPITestCase):
    def test_new_project_architecture_gated_on_business_logic(self):
        project = make_approved_blueprint_project()  # no BL, no architecture
        res = self.client.post(f"/api/projects/{project.slug}/architecture/generate/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "business_logic_not_approved")

    def test_after_business_logic_approved_architecture_reaches_ai(self):
        project = project_with_approved_bl()
        res = self.client.post(f"/api/projects/{project.slug}/architecture/generate/")
        # gate passed -> reaches run_operation -> missing key
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")

    def test_grandfathered_project_with_architecture_is_exempt(self):
        # a pre-Phase-D project: architecture content already, no Business Logic
        project = make_roadmap_project()  # stage=roadmap, arch+roadmap content, NO bl
        project.stage = ProjectStage.ARCHITECTURE
        project.save(update_fields=["stage"])
        res = self.client.post(f"/api/projects/{project.slug}/architecture/generate/")
        # not blocked by the BL gate -> reaches AI -> missing key
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
        # and it stays readable
        get = self.client.get(f"/api/projects/{project.slug}/")
        self.assertEqual(get.status_code, 200)
        self.assertEqual(get.json()["business_logic"], {})


# --- stale integration ----------------------------------------------


class BusinessLogicStaleTests(AuthenticatedAPITestCase):
    def test_blueprint_change_marks_business_logic_architecture_roadmap(self):
        project = make_roadmap_project(approved=True)  # bp+arch+roadmap approved
        project.business_logic_approved_at = APPROVED_DT  # also BL approved
        project.save(update_fields=["business_logic_approved_at"])
        changed = dep.mark_downstream_stale(project, "blueprint")
        self.assertTrue(changed)
        self.assertEqual(
            project.downstream_stale,
            {"business_logic": True, "architecture": True, "roadmap": True},
        )

    def test_business_logic_change_marks_architecture_and_roadmap_only(self):
        project = make_roadmap_project(approved=True)
        project.business_logic_approved_at = APPROVED_DT
        project.save(update_fields=["business_logic_approved_at"])
        dep.mark_downstream_stale(project, "business_logic")
        self.assertEqual(
            project.downstream_stale, {"architecture": True, "roadmap": True}
        )
        self.assertNotIn("business_logic", project.downstream_stale)

    def test_approving_business_logic_clears_only_its_own_flag(self):
        project = project_with_approved_bl()
        project.business_logic_approved_at = None
        project.downstream_stale = {
            "business_logic": True, "architecture": True, "roadmap": True,
        }
        project.save(update_fields=["business_logic_approved_at", "downstream_stale"])

        project = approve_business_logic(project)

        self.assertEqual(
            project.downstream_stale, {"architecture": True, "roadmap": True}
        )
        self.assertIsNotNone(project.business_logic_approved_at)

    def test_stale_marking_never_deletes_or_unapproves_downstream(self):
        project = make_roadmap_project(approved=True)
        project.business_logic_approved_at = APPROVED_DT
        arch_content = project.architecture["content"]
        rm_approved = project.roadmap_approved_at
        arch_approved = project.architecture_approved_at
        project.save(update_fields=["business_logic_approved_at"])

        dep.mark_downstream_stale(project, "blueprint")

        self.assertEqual(project.architecture["content"], arch_content)
        self.assertEqual(project.architecture_approved_at, arch_approved)
        self.assertEqual(project.roadmap_approved_at, rm_approved)


# --- downstream AI consumption + context selection -----------------


class DownstreamConsumptionTests(AuthenticatedAPITestCase):
    def test_architecture_generation_receives_approved_business_logic(self):
        project = project_with_approved_bl()
        fake = FakeProvider(architecture_content())
        with mock.patch("ai.base.get_provider", return_value=fake):
            generate_architecture(project)
        self.assertIn("Only a manager may approve an order over $1000", fake.last_user)
        self.assertIn("APPROVED BUSINESS LOGIC", fake.last_user)

    def test_roadmap_generation_receives_business_logic(self):
        project = project_with_approved_bl()
        # progress it to an approved architecture first
        fake_arch = FakeProvider(architecture_content())
        with mock.patch("ai.base.get_provider", return_value=fake_arch):
            generate_architecture(project)
        project = approve_architecture(project)

        from tests.test_phase4 import roadmap_content
        # roadmap_content() ids are pre-normalized T1.. ; strip ids so draft schema fits
        draft = {
            "phases": [
                {
                    "title": p["title"],
                    "objective": p["objective"],
                    "tasks": [
                        {
                            "title": t["title"], "objective": t["objective"],
                            "why": t["why"], "dependencies": [],
                            "expected_output": t["expected_output"],
                            "acceptance_criteria": t["acceptance_criteria"],
                        }
                        for t in p["tasks"]
                    ],
                }
                for p in roadmap_content()["phases"]
            ]
        }
        fake_rm = FakeProvider(draft)
        with mock.patch("ai.base.get_provider", return_value=fake_rm):
            generate_roadmap(project)
        self.assertIn("Only a manager may approve an order over $1000", fake_rm.last_user)

    def test_task_context_selection_picks_rules_traced_to_task_requirements(self):
        project = make_roadmap_project(approved=True)
        # attach approved Business Logic whose BR-01 traces to FR1
        project.business_logic = {"content": bl_content(), "generated_at": NOW, "updated_at": NOW, "approved_at": NOW}
        project.business_logic_approved_at = APPROVED_DT
        project.save(update_fields=["business_logic", "business_logic_approved_at"])

        # T3 in the phase4 roadmap fixture references FR1
        ctx = assemble_task_context(project, "T3")
        bl = ctx["business_logic"]
        self.assertTrue(bl)
        rule_ids = {r["id"] for r in bl["business_rules"]}
        self.assertIn("BR-01", rule_ids)  # traced via FR1
        # traceability preserved through selection
        self.assertIn("FR1", bl["business_rules"][0]["related_requirements"])

    def test_build_prompt_receives_task_relevant_business_rules(self):
        project = make_roadmap_project(approved=True)
        project.business_logic = {"content": bl_content(), "generated_at": NOW, "updated_at": NOW, "approved_at": NOW}
        project.business_logic_approved_at = APPROVED_DT
        # unblock T3: complete its prerequisites
        for phase in project.roadmap["content"]["phases"]:
            for t in phase["tasks"]:
                if t["id"] in ("T1", "T2"):
                    t["status"] = "completed"
        project.save(update_fields=["business_logic", "business_logic_approved_at", "roadmap"])

        fake = FakeProvider({"prompt_markdown": "# Role\n" + "detail " * 60})
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                f"/api/projects/{project.slug}/roadmap/tasks/T3/build-prompt/"
            )
        self.assertEqual(res.status_code, 200)
        self.assertIn("Only a manager may approve an order over $1000", fake.last_user)
        self.assertIn("APPROVED BUSINESS LOGIC", fake.last_user)

    def test_grandfathered_project_task_context_has_empty_business_logic(self):
        project = make_roadmap_project(approved=True)  # no BL
        ctx = assemble_task_context(project, "T1")
        self.assertEqual(ctx["business_logic"], {})


# --- security / envelope / provider isolation ----------------------


class SecurityAndEnvelopeTests(AuthenticatedAPITestCase):
    def test_error_envelope_shape_unchanged(self):
        project = make_approved_blueprint_project()
        res = self.client.post(f"/api/projects/{project.slug}/business-logic/generate/")
        body = res.json()
        self.assertEqual(set(body.keys()), {"error"})
        self.assertEqual(
            set(body["error"].keys()), {"code", "message", "retryable", "details"}
        )

    def test_serializer_exposes_business_logic_not_context_digest(self):
        project = project_with_approved_bl()
        res = self.client.get(f"/api/projects/{project.slug}/")
        payload = res.json()
        self.assertIn("business_logic", payload)
        self.assertIn("business_logic_approved_at", payload)
        self.assertNotIn("context_digest", payload)

    def test_business_logic_operation_has_no_provider_specific_code(self):
        from pathlib import Path
        from ai.operations import business_logic_generation as op

        src = Path(op.__file__).read_text()
        for token in ("anthropic", "messages.create", "tool_use", "with_options"):
            self.assertNotIn(token, src)

    def test_business_logic_operation_uses_run_operation_pattern(self):
        self.assertEqual(BUSINESS_LOGIC_GENERATION.name, "business_logic_generation")
        self.assertEqual(BUSINESS_LOGIC_GENERATION.schema, BusinessLogicDraft)
        self.assertEqual(BUSINESS_LOGIC_GENERATION.prompt_version, "business_logic/v1")
