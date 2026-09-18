"""
Phase 4 verification tests (Architecture -> Development Roadmap).

Every deterministic path: the Roadmap schema + normalization (id/order
assignment, dependency resolution, DAG enforcement), the
generate/edit/regenerate/approve guards, task-status transitions with dependency
gating, the derived progress + next-recommended-task logic, transactional
persistence, and the Project Context digest rebuild. The live
roadmap_generation round trip is PENDING an ANTHROPIC_API_KEY.
"""
import copy
from datetime import datetime, timezone as dt_timezone

from pydantic import ValidationError
from tests.base import AuthenticatedAPITestCase, default_owner

from projects.models import Project, ProjectStage
from projects.roadmap import (
    RoadmapContent,
    compute_progress,
    next_recommended_task,
    normalize_roadmap_content,
)
from projects.services import approve_architecture, approve_blueprint

NOW = "2026-08-29T00:00:00+00:00"
APPROVED_DT = datetime(2026, 8, 29, tzinfo=dt_timezone.utc)

BP_CONTENT = {
    "product_summary": "A marketplace connecting restaurants with produce suppliers.",
    "problem": "No easy price comparison.",
    "solution": "A web marketplace.",
    "target_users": ["Restaurants", "Suppliers"],
    "user_roles": [{"name": "Buyer", "description": "Orders."}, {"name": "Supplier", "description": "Sells."}],
    "core_features": ["Catalogs", "Ordering"],
    "mvp_features": ["Catalogs", "Ordering"],
    "future_features": ["Invoicing"],
    "functional_requirements": [
        {"id": "FR1", "text": "A supplier can publish a price list.", "priority": "must"},
        {"id": "FR2", "text": "A buyer can place an order.", "priority": "must"},
    ],
    "business_rules": ["Pricing is private."],
    "user_flows": [{"name": "Order", "steps": ["Browse", "Confirm"]}],
    "out_of_scope": ["Payments"],
}
ARCH_CONTENT = {
    "overview": {"style": "Modular monolith", "summary": "One Django service, Next.js, Postgres."},
    "frontend": {"choice": "Next.js", "why": "Familiar."},
    "backend": {"choice": "Django + DRF", "why": "Fast for CRUD."},
    "database": {"choice": "PostgreSQL", "why": "Relational."},
    "auth": {"approach": "Sessions + API keys", "why": "Two audiences."},
    "components": [{"name": "Catalog service", "responsibility": "Price lists."}],
    "api_areas": [{"name": "Catalog API", "purpose": "Publish price lists."}],
    "data_model": [{"entity": "Supplier", "fields": ["name"], "relationships": ["has many PriceList"]}],
    "integrations": [],
    "security": ["Scope API keys to a supplier's own catalog."],
    "deployment": {"approach": "Single container + managed Postgres", "why": "Low ops."},
    "key_decisions": [{"decision": "Monolith", "rationale": "One team."}],
    "constraints": ["No payments in MVP."],
}


def roadmap_content(**overrides) -> dict:
    """A pre-normalized 2-phase / 4-task roadmap (T1 <- T2 <- T3 <- T4)."""

    def task(i, title, deps, status="not_started"):
        return {
            "id": f"T{i}",
            "order": i,
            "phase_id": "P1" if i <= 2 else "P2",
            "title": title,
            "objective": f"Deliver {title.lower()}.",
            "why": "Needed for the MVP.",
            "requirements": ["FR1"] if i == 3 else [],
            "dependencies": deps,
            "expected_output": f"{title} committed and passing checks.",
            "acceptance_criteria": [f"{title} works end to end."],
            "status": status,
        }

    content = {
        "phases": [
            {
                "id": "P1",
                "order": 1,
                "title": "Foundation",
                "objective": "Stand up the project skeleton.",
                "tasks": [
                    task(1, "Project setup", []),
                    task(2, "Database schema", ["T1"]),
                ],
            },
            {
                "id": "P2",
                "order": 2,
                "title": "Core domain",
                "objective": "Build catalog and ordering.",
                "tasks": [
                    task(3, "Supplier catalog API", ["T2"]),
                    task(4, "Ordering API", ["T3"]),
                ],
            },
        ]
    }
    content.update(overrides)
    return content


def make_roadmap_project(*, approved: bool = False, stage=ProjectStage.ROADMAP, **overrides) -> Project:
    data = {
        "original_idea": "A marketplace where restaurants compare suppliers and order.",
        "stage": stage,
        "owner": default_owner(),
        "discovery": {"questions": [], "answers": {}, "generated_at": NOW, "answered_at": NOW},
        "blueprint": {"content": BP_CONTENT, "generated_at": NOW, "updated_at": NOW, "approved_at": NOW},
        "blueprint_approved_at": APPROVED_DT,
        "architecture": {"content": ARCH_CONTENT, "generated_at": NOW, "updated_at": NOW, "approved_at": NOW},
        "architecture_approved_at": APPROVED_DT,
        "context_digest": {"idea_analysis": {"domain": "B2B marketplace"}},
        "roadmap": {"content": roadmap_content(), "generated_at": NOW, "updated_at": NOW, "approved_at": None},
    }
    data.update(overrides)
    project = Project.objects.create(**data)
    if approved:
        from projects.services import approve_roadmap

        project = approve_roadmap(project)
    return project


def make_approved_architecture_project(**overrides) -> Project:
    """stage=architecture, blueprint + architecture approved, no roadmap."""
    data = {
        "original_idea": "A marketplace where restaurants compare suppliers and order.",
        "stage": ProjectStage.BLUEPRINT,
        "owner": default_owner(),
        "discovery": {"questions": [], "answers": {}, "generated_at": NOW, "answered_at": NOW},
        "blueprint": {"content": BP_CONTENT, "generated_at": NOW, "updated_at": NOW, "approved_at": None},
        "context_digest": {"idea_analysis": {"domain": "B2B marketplace"}},
    }
    data.update(overrides)
    project = Project.objects.create(**data)
    project = approve_blueprint(project)
    project.architecture = {"content": ARCH_CONTENT, "generated_at": NOW, "updated_at": NOW, "approved_at": None}
    project.stage = ProjectStage.ARCHITECTURE
    project.save()
    return approve_architecture(project)


# --- schema + normalization ------------------------------------------


class RoadmapSchemaTests(AuthenticatedAPITestCase):
    def test_valid_content(self):
        model = RoadmapContent.model_validate(roadmap_content())
        self.assertEqual(len(model.phases), 2)

    def test_phase_without_tasks_rejected(self):
        bad = roadmap_content()
        bad["phases"][1]["tasks"] = []
        with self.assertRaises(ValidationError):
            RoadmapContent.model_validate(bad)

    def test_task_without_acceptance_criteria_rejected(self):
        bad = roadmap_content()
        bad["phases"][0]["tasks"][0]["acceptance_criteria"] = []
        with self.assertRaises(ValidationError):
            RoadmapContent.model_validate(bad)

    def test_dependency_on_unknown_task_rejected(self):
        bad = roadmap_content()
        bad["phases"][0]["tasks"][1]["dependencies"] = ["T99"]
        with self.assertRaises(ValidationError):
            RoadmapContent.model_validate(bad)

    def test_forward_dependency_rejected_by_schema(self):
        bad = roadmap_content()
        bad["phases"][0]["tasks"][0]["dependencies"] = ["T2"]  # T1 -> T2
        with self.assertRaises(ValidationError):
            RoadmapContent.model_validate(bad)

    def test_normalize_assigns_ids_and_orders(self):
        raw = {
            "phases": [
                {
                    "title": "Setup",
                    "objective": "x",
                    "tasks": [
                        {"title": "Init repo", "objective": "x", "why": "x",
                         "expected_output": "x", "acceptance_criteria": ["x"]},
                    ],
                },
                {
                    "title": "Domain",
                    "objective": "x",
                    "tasks": [
                        {"title": "Model", "objective": "x", "why": "x",
                         "dependencies": ["Init repo"], "expected_output": "x",
                         "acceptance_criteria": ["x"]},
                    ],
                },
            ]
        }
        norm = normalize_roadmap_content(raw)
        self.assertEqual([p["id"] for p in norm["phases"]], ["P1", "P2"])
        t1 = norm["phases"][0]["tasks"][0]
        t2 = norm["phases"][1]["tasks"][0]
        self.assertEqual(t1["id"], "T1")
        self.assertEqual(t2["id"], "T2")
        self.assertEqual(t2["dependencies"], ["T1"])  # resolved by title
        self.assertEqual(t2["phase_id"], "P2")
        RoadmapContent.model_validate(norm)  # normalized output is valid

    def test_normalize_drops_forward_and_self_dependencies(self):
        raw = {
            "phases": [
                {
                    "title": "P",
                    "objective": "x",
                    "tasks": [
                        {"title": "A", "objective": "x", "why": "x", "dependencies": ["B", "A"],
                         "expected_output": "x", "acceptance_criteria": ["x"]},
                        {"title": "B", "objective": "x", "why": "x",
                         "expected_output": "x", "acceptance_criteria": ["x"]},
                    ],
                }
            ]
        }
        norm = normalize_roadmap_content(raw)
        self.assertEqual(norm["phases"][0]["tasks"][0]["dependencies"], [])

    def test_normalize_is_idempotent(self):
        once = normalize_roadmap_content(roadmap_content())
        twice = normalize_roadmap_content(once)
        self.assertEqual(once, twice)

    def test_normalize_coerces_bad_status(self):
        raw = roadmap_content()
        raw["phases"][0]["tasks"][0]["status"] = "blocked"
        norm = normalize_roadmap_content(raw)
        self.assertEqual(norm["phases"][0]["tasks"][0]["status"], "not_started")


# --- generate guards --------------------------------------------------


class RoadmapGenerateGuardTests(AuthenticatedAPITestCase):
    def _url(self, project):
        return f"/api/projects/{project.slug}/roadmap/generate/"

    def test_unknown_project_returns_404(self):
        res = self.client.post("/api/projects/nope/roadmap/generate/")
        self.assertEqual(res.status_code, 404)

    def test_architecture_not_approved_returns_409(self):
        project = Project.objects.create(
            original_idea="x",
            stage=ProjectStage.ARCHITECTURE,
            owner=default_owner(),
            blueprint={"content": BP_CONTENT, "approved_at": NOW},
            blueprint_approved_at=APPROVED_DT,
            architecture={"content": ARCH_CONTENT},
        )
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "architecture_not_approved")

    def test_locked_stage_returns_409(self):
        project = make_roadmap_project(stage=ProjectStage.DISCOVERY)
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "invalid_workflow_state")

    def test_missing_api_key_returns_502_no_side_effects(self):
        project = make_approved_architecture_project()
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
        project.refresh_from_db()
        self.assertEqual(project.stage, ProjectStage.ARCHITECTURE)
        self.assertEqual(project.roadmap, {})

    def test_regenerate_missing_key_keeps_approval(self):
        project = make_roadmap_project(approved=True)
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 502)
        project.refresh_from_db()
        self.assertIsNotNone(project.roadmap_approved_at)


# --- structured edit ------------------------------------------------


class RoadmapUpdateTests(AuthenticatedAPITestCase):
    def _url(self, project):
        return f"/api/projects/{project.slug}/roadmap/"

    def test_edit_phases(self):
        project = make_roadmap_project()
        phases = copy.deepcopy(project.roadmap["content"]["phases"])
        phases[0]["title"] = "Groundwork"
        res = self.client.patch(self._url(project), {"content": {"phases": phases}}, format="json")
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.roadmap["content"]["phases"][0]["title"], "Groundwork")

    def test_edit_invalid_returns_400(self):
        project = make_roadmap_project()
        phases = copy.deepcopy(project.roadmap["content"]["phases"])
        phases[1]["tasks"] = []
        res = self.client.patch(self._url(project), {"content": {"phases": phases}}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_roadmap")

    def test_unknown_section_returns_400(self):
        project = make_roadmap_project()
        res = self.client.patch(self._url(project), {"content": {"milestones": []}}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("milestones", res.json()["error"]["details"]["unknown"])

    def test_edit_before_generation_returns_409(self):
        project = make_approved_architecture_project()
        res = self.client.patch(self._url(project), {"content": {"phases": []}}, format="json")
        self.assertEqual(res.status_code, 409)

    def test_edit_reindexes_and_reresolves_dependencies(self):
        project = make_roadmap_project()
        phases = copy.deepcopy(project.roadmap["content"]["phases"])
        # insert a new first task; dependencies given by title must still resolve
        phases[0]["tasks"].insert(
            0,
            {
                "title": "Choose tooling",
                "objective": "Pick the stack tools.",
                "why": "Everything builds on it.",
                "dependencies": [],
                "expected_output": "A decision doc.",
                "acceptance_criteria": ["Documented."],
            },
        )
        res = self.client.patch(self._url(project), {"content": {"phases": phases}}, format="json")
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        tasks = [t for p in project.roadmap["content"]["phases"] for t in p["tasks"]]
        self.assertEqual([t["id"] for t in tasks], ["T1", "T2", "T3", "T4", "T5"])
        self.assertEqual(tasks[0]["title"], "Choose tooling")
        # "Database schema" now T3, depends on "Project setup" now T2
        db_task = next(t for t in tasks if t["title"] == "Database schema")
        setup_task = next(t for t in tasks if t["title"] == "Project setup")
        self.assertEqual(db_task["dependencies"], [setup_task["id"]])

    def test_edit_reverts_approval_and_context(self):
        project = make_roadmap_project(approved=True)
        self.assertIn("roadmap", project.context_digest)
        phases = copy.deepcopy(project.roadmap["content"]["phases"])
        phases[0]["objective"] = "Revised objective."
        res = self.client.patch(self._url(project), {"content": {"phases": phases}}, format="json")
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertIsNone(project.roadmap_approved_at)
        self.assertNotIn("roadmap", project.context_digest)
        self.assertIn("architecture", project.context_digest)


# --- approve -------------------------------------------------------


class RoadmapApproveTests(AuthenticatedAPITestCase):
    def _url(self, project):
        return f"/api/projects/{project.slug}/roadmap/approve/"

    def test_approve_sets_timestamp_and_rebuilds_context(self):
        project = make_roadmap_project()
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertIsNotNone(project.roadmap_approved_at)
        digest = project.context_digest["roadmap"]
        self.assertEqual(len(digest["tasks"]), 4)
        self.assertEqual(digest["progress"]["total"], 4)
        self.assertEqual(digest["next_recommended_task_id"], "T1")
        self.assertEqual(
            set(project.context_digest.keys()),
            {"idea_analysis", "blueprint", "architecture", "roadmap"},
        )

    def test_approve_wrong_stage_returns_409(self):
        project = make_roadmap_project(stage=ProjectStage.ARCHITECTURE)
        res = self.client.post(self._url(project))
        self.assertEqual(res.status_code, 409)

    def test_approve_without_content_returns_409(self):
        project = make_approved_architecture_project()
        res = self.client.post(f"/api/projects/{project.slug}/roadmap/approve/")
        self.assertEqual(res.status_code, 409)


# --- task status --------------------------------------------------


class TaskStatusTests(AuthenticatedAPITestCase):
    def _url(self, project, task_id):
        return f"/api/projects/{project.slug}/roadmap/tasks/{task_id}/"

    def test_status_before_approval_returns_409(self):
        project = make_roadmap_project()  # draft
        res = self.client.patch(self._url(project, "T1"), {"status": "in_progress"}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "roadmap_not_approved")

    def test_start_task_with_no_deps(self):
        project = make_roadmap_project(approved=True)
        res = self.client.patch(self._url(project, "T1"), {"status": "in_progress"}, format="json")
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.context_digest["roadmap"]["progress"]["in_progress"], 1)
        self.assertIsNotNone(project.roadmap_approved_at)  # not reverted

    def test_cannot_start_task_with_unfinished_dependency(self):
        project = make_roadmap_project(approved=True)
        res = self.client.patch(self._url(project, "T2"), {"status": "in_progress"}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "dependencies_incomplete")
        self.assertEqual(res.json()["error"]["details"]["unfinished"], ["T1"])

    def _advance(self, project, task_id, target):
        """Walk a task through the Phase F lifecycle to ``target``."""
        chain = ["not_started", "in_progress", "ready_for_review", "completed"]
        for status in chain[1 : chain.index(target) + 1]:
            res = self.client.patch(
                self._url(project, task_id), {"status": status}, format="json"
            )
            self.assertEqual(res.status_code, 200, f"{task_id}->{status}: {res.content}")
        return res

    def test_complete_in_dependency_order(self):
        project = make_roadmap_project(approved=True)
        for tid in ("T1", "T2", "T3"):
            self._advance(project, tid, "completed")
        project.refresh_from_db()
        meta = project.context_digest["roadmap"]
        self.assertEqual(meta["progress"]["completed"], 3)
        self.assertEqual(meta["next_recommended_task_id"], "T4")

    def test_unknown_task_returns_404(self):
        project = make_roadmap_project(approved=True)
        res = self.client.patch(self._url(project, "T99"), {"status": "completed"}, format="json")
        self.assertEqual(res.status_code, 404)

    def test_bad_status_returns_400(self):
        project = make_roadmap_project(approved=True)
        res = self.client.patch(self._url(project, "T1"), {"status": "done"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_status")


# --- derived logic ----------------------------------------------


class NextTaskAndProgressTests(AuthenticatedAPITestCase):
    def test_fresh_roadmap_next_is_first_unblocked(self):
        content = roadmap_content()
        self.assertEqual(next_recommended_task(content)["next_recommended_task_id"], "T1")

    def test_next_skips_blocked_and_advances_with_progress(self):
        content = roadmap_content()
        tasks = {t["id"]: t for p in content["phases"] for t in p["tasks"]}
        tasks["T1"]["status"] = "completed"
        self.assertEqual(next_recommended_task(content)["next_recommended_task_id"], "T2")
        tasks["T2"]["status"] = "completed"
        self.assertEqual(next_recommended_task(content)["next_recommended_task_id"], "T3")

    def test_next_is_none_when_all_done(self):
        content = roadmap_content()
        for p in content["phases"]:
            for t in p["tasks"]:
                t["status"] = "completed"
        self.assertIsNone(next_recommended_task(content)["next_recommended_task_id"])

    def test_current_task_is_the_in_progress_one(self):
        content = roadmap_content()
        content["phases"][0]["tasks"][0]["status"] = "in_progress"
        self.assertEqual(next_recommended_task(content)["current_task_id"], "T1")

    def test_progress_counts_and_phase_done_flags(self):
        content = roadmap_content()
        content["phases"][0]["tasks"][0]["status"] = "completed"
        content["phases"][0]["tasks"][1]["status"] = "completed"
        prog = compute_progress(content)
        self.assertEqual(prog["completed"], 2)
        self.assertEqual(prog["percent"], 50)
        self.assertTrue(prog["phases"][0]["done"])
        self.assertFalse(prog["phases"][1]["done"])


# --- cross-phase + serializer ---------------------------------


class CrossPhaseTests(AuthenticatedAPITestCase):
    def test_architecture_locked_once_roadmap_exists(self):
        project = make_roadmap_project()  # stage = roadmap
        res = self.client.patch(
            f"/api/projects/{project.slug}/architecture/",
            {"content": {"security": ["x"]}},
            format="json",
        )
        self.assertEqual(res.status_code, 409)

    def test_serializer_exposes_roadmap_meta_not_context_digest(self):
        project = make_roadmap_project(approved=True)
        res = self.client.get(f"/api/projects/{project.slug}/")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertIn("roadmap", payload)
        self.assertIsNotNone(payload["roadmap_approved_at"])
        self.assertEqual(payload["roadmap_meta"]["next_recommended_task_id"], "T1")
        self.assertEqual(payload["roadmap_meta"]["progress"]["total"], 4)
        self.assertNotIn("context_digest", payload)

    def test_roadmap_meta_null_before_generation(self):
        project = make_approved_architecture_project()
        res = self.client.get(f"/api/projects/{project.slug}/")
        self.assertIsNone(res.json()["roadmap_meta"])
