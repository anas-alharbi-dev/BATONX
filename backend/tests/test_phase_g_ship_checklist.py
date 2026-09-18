"""
Phase G verification — deterministic Ship Checklist (Software MVP completion).

No AI is involved in evaluating readiness. Automatic checks derive from stored
project state (approvals, Phase C stale flags, Phase F progress); manual
confirmations persist in ``Project.ship_checklist``.
"""
import unittest.mock as mock

from tests.base import AuthenticatedAPITestCase

from ai.models import AIRequestLog
from projects.models import ProjectStage
from projects.ship_checklist import (
    MANUAL_ITEM_IDS,
    NOT_READY,
    READY_TO_SHIP,
    READY_WITH_MANUAL_CHECKS,
    compute_ship_checklist,
)
from projects.services import set_task_status
from tests.test_phase4 import make_roadmap_project


def checklist_url(project):
    return f"/api/projects/{project.slug}/ship-checklist/"


def complete_all_tasks(project):
    for phase in project.roadmap["content"]["phases"]:
        for task in phase["tasks"]:
            for status in ("in_progress", "ready_for_review", "completed"):
                set_task_status(project, task["id"], status)
    project.refresh_from_db()
    return project


def ready_project():
    """Approved BP/Arch/Roadmap (BL not applicable — grandfathered) + all tasks done."""
    project = make_roadmap_project(approved=True)
    return complete_all_tasks(project)


def confirm_all_manuals(client, project):
    for item_id in MANUAL_ITEM_IDS:
        res = client.patch(
            checklist_url(project), {"item_id": item_id, "confirmed": True}, format="json"
        )
        assert res.status_code == 200, res.content
    project.refresh_from_db()


class ShipChecklistEndpointTests(AuthenticatedAPITestCase):
    def test_get_endpoint_exists_and_shape(self):
        project = make_roadmap_project(approved=True)
        res = self.client.get(checklist_url(project))
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(
            set(body.keys()),
            {
                "overall_status", "readiness_summary", "stage", "progress",
                "automatic_checks", "manual_checks", "blockers", "warnings",
                "stale_context", "roadmap_stale", "pending_manual_confirmations",
            },
        )
        self.assertTrue(all(c["kind"] == "automatic" for c in body["automatic_checks"]))
        self.assertTrue(all(c["kind"] == "manual" for c in body["manual_checks"]))
        self.assertEqual(len(body["manual_checks"]), 9)

    def test_unknown_project_returns_404_envelope(self):
        res = self.client.get("/api/projects/nope/ship-checklist/")
        self.assertEqual(res.status_code, 404)
        body = res.json()
        self.assertEqual(set(body.keys()), {"error"})
        self.assertEqual(
            set(body["error"].keys()), {"code", "message", "retryable", "details"}
        )
        self.assertEqual(body["error"]["code"], "project_not_found")

    def test_works_with_no_ai_key_and_makes_no_ai_call(self):
        project = ready_project()

        def boom(*a, **k):
            raise AssertionError("Ship Checklist must not touch the AI provider")

        with mock.patch("ai.base.get_provider", side_effect=boom):
            self.assertEqual(self.client.get(checklist_url(project)).status_code, 200)
            res = self.client.patch(
                checklist_url(project),
                {"item_id": "tests_verified", "confirmed": True},
                format="json",
            )
            self.assertEqual(res.status_code, 200)
        self.assertFalse(
            AIRequestLog.objects.filter(operation__startswith="ship").exists()
        )


class AutomaticCheckTests(AuthenticatedAPITestCase):
    def _auto(self, project):
        body = self.client.get(checklist_url(project)).json()
        return {c["id"]: c for c in body["automatic_checks"]}, body

    def test_derives_from_project_state(self):
        project = ready_project()
        auto, body = self._auto(project)
        required = [c for c in auto.values() if c["required"]]
        self.assertTrue(all(c["status"] == "pass" for c in required))
        self.assertEqual(auto["SC-12"]["status"], "warning")  # review not ingestible
        self.assertFalse(auto["SC-12"]["required"])
        self.assertEqual(body["overall_status"], READY_WITH_MANUAL_CHECKS)

    def test_incomplete_task_is_not_ready(self):
        project = make_roadmap_project(approved=True)
        set_task_status(project, "T1", "in_progress")
        auto, body = self._auto(project)
        self.assertEqual(auto["SC-06"]["status"], "fail")
        self.assertEqual(body["overall_status"], NOT_READY)
        self.assertIn("SC-06", [b["id"] for b in body["blockers"]])

    def test_blocked_task_is_not_ready(self):
        project = make_roadmap_project(approved=True)  # T2..T4 blocked by deps
        auto, body = self._auto(project)
        self.assertEqual(auto["SC-07"]["status"], "fail")
        self.assertEqual(body["overall_status"], NOT_READY)

    def test_ready_for_review_task_is_not_ready(self):
        project = make_roadmap_project(approved=True)
        set_task_status(project, "T1", "in_progress")
        set_task_status(project, "T1", "ready_for_review")
        auto, body = self._auto(project)
        self.assertEqual(auto["SC-08"]["status"], "fail")
        self.assertEqual(body["overall_status"], NOT_READY)

    def test_stale_business_logic_is_not_ready(self):
        project = ready_project()
        project.downstream_stale = {"business_logic": True}
        project.save(update_fields=["downstream_stale"])
        auto, body = self._auto(project)
        self.assertEqual(auto["SC-09"]["status"], "fail")
        self.assertEqual(body["overall_status"], NOT_READY)

    def test_stale_architecture_is_not_ready(self):
        project = ready_project()
        project.downstream_stale = {"architecture": True}
        project.save(update_fields=["downstream_stale"])
        auto, body = self._auto(project)
        self.assertEqual(auto["SC-10"]["status"], "fail")
        self.assertEqual(body["overall_status"], NOT_READY)

    def test_stale_roadmap_is_not_ready(self):
        project = ready_project()
        project.downstream_stale = {"roadmap": True}
        project.save(update_fields=["downstream_stale"])
        auto, body = self._auto(project)
        self.assertEqual(auto["SC-11"]["status"], "fail")
        self.assertTrue(body["roadmap_stale"])
        self.assertEqual(body["overall_status"], NOT_READY)

    def test_incomplete_artifact_approval_is_not_ready(self):
        project = make_roadmap_project()  # draft roadmap, not approved
        auto, body = self._auto(project)
        self.assertEqual(auto["SC-05"]["status"], "fail")
        self.assertEqual(body["overall_status"], NOT_READY)

    def test_full_completion_passes_implementation_checks(self):
        project = ready_project()
        auto, body = self._auto(project)
        for cid in ("SC-06", "SC-07", "SC-08"):
            self.assertEqual(auto[cid]["status"], "pass", cid)
        self.assertEqual(body["progress"]["completion_percentage"], 100)

    def test_open_questions_surface_as_warning_not_blocker(self):
        project = ready_project()
        project.business_logic = {
            "content": {"open_questions": ["Is there a hard order cap?"]},
        }
        project.business_logic_approved_at = project.roadmap_approved_at
        project.save(update_fields=["business_logic", "business_logic_approved_at"])
        auto, body = self._auto(project)
        self.assertEqual(auto["SC-03"]["status"], "warning")
        self.assertFalse(auto["SC-03"]["required"])
        self.assertIn("SC-03", [w["id"] for w in body["warnings"]])
        # a warning does not block readiness
        self.assertEqual(body["overall_status"], READY_WITH_MANUAL_CHECKS)


class ManualConfirmationTests(AuthenticatedAPITestCase):
    def test_manuals_start_unconfirmed(self):
        project = ready_project()
        body = self.client.get(checklist_url(project)).json()
        self.assertTrue(all(not c["confirmed"] for c in body["manual_checks"]))
        self.assertEqual(body["pending_manual_confirmations"], 9)

    def test_automatic_pass_plus_pending_manuals_is_ready_with_manual_checks(self):
        project = ready_project()
        body = self.client.get(checklist_url(project)).json()
        self.assertEqual(body["overall_status"], READY_WITH_MANUAL_CHECKS)

    def test_confirming_all_manuals_reaches_ready_to_ship(self):
        project = ready_project()
        confirm_all_manuals(self.client, project)
        body = self.client.get(checklist_url(project)).json()
        self.assertEqual(body["overall_status"], READY_TO_SHIP)
        self.assertEqual(body["pending_manual_confirmations"], 0)

    def test_invalid_item_rejected(self):
        project = ready_project()
        res = self.client.patch(
            checklist_url(project),
            {"item_id": "not_a_real_item", "confirmed": True},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_checklist_item")

    def test_missing_item_id_rejected(self):
        project = ready_project()
        res = self.client.patch(
            checklist_url(project), {"confirmed": True}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_checklist_item")

    def test_automatic_check_id_is_not_a_valid_manual_item(self):
        project = ready_project()
        res = self.client.patch(
            checklist_url(project),
            {"item_id": "SC-01", "confirmed": True},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_checklist_item")
        project.refresh_from_db()
        self.assertNotIn("SC-01", project.ship_checklist)

    def test_confirmation_persists_and_survives_reload(self):
        project = ready_project()
        self.client.patch(
            checklist_url(project),
            {"item_id": "deployment_readiness_confirmed", "confirmed": True, "note": "prod live"},
            format="json",
        )
        project.refresh_from_db()
        entry = project.ship_checklist["deployment_readiness_confirmed"]
        self.assertTrue(entry["confirmed"])
        self.assertIsNotNone(entry["confirmed_at"])
        self.assertEqual(entry["note"], "prod live")
        # a fresh GET still reports it confirmed
        body = self.client.get(checklist_url(project)).json()
        item = next(
            c for c in body["manual_checks"] if c["id"] == "deployment_readiness_confirmed"
        )
        self.assertTrue(item["confirmed"])
        self.assertEqual(item["note"], "prod live")

    def test_confirmation_can_be_unset(self):
        project = ready_project()
        url = checklist_url(project)
        self.client.patch(url, {"item_id": "tests_verified", "confirmed": True}, format="json")
        self.client.patch(url, {"item_id": "tests_verified", "confirmed": False}, format="json")
        project.refresh_from_db()
        entry = project.ship_checklist["tests_verified"]
        self.assertFalse(entry["confirmed"])
        self.assertIsNone(entry["confirmed_at"])

    def test_long_note_is_truncated(self):
        project = ready_project()
        self.client.patch(
            checklist_url(project),
            {"item_id": "secrets_reviewed", "confirmed": True, "note": "x" * 900},
            format="json",
        )
        project.refresh_from_db()
        self.assertEqual(len(project.ship_checklist["secrets_reviewed"]["note"]), 500)


class StageBehaviourTests(AuthenticatedAPITestCase):
    def test_opening_checklist_does_not_change_stage(self):
        project = ready_project()
        self.assertEqual(project.stage, ProjectStage.ROADMAP)
        self.client.get(checklist_url(project))
        project.refresh_from_db()
        self.assertEqual(project.stage, ProjectStage.ROADMAP)

    def test_partial_manual_confirmation_does_not_change_stage(self):
        project = ready_project()
        self.client.patch(
            checklist_url(project),
            {"item_id": "tests_verified", "confirmed": True},
            format="json",
        )
        project.refresh_from_db()
        self.assertEqual(project.stage, ProjectStage.ROADMAP)

    def test_reaching_ready_to_ship_advances_stage_to_ship(self):
        project = ready_project()
        confirm_all_manuals(self.client, project)
        project.refresh_from_db()
        self.assertEqual(project.stage, ProjectStage.SHIP)

    def test_stage_does_not_regress_after_ship(self):
        project = ready_project()
        confirm_all_manuals(self.client, project)
        project.refresh_from_db()
        self.assertEqual(project.stage, ProjectStage.SHIP)
        # reopen a task: checklist result regresses, stage stays 'ship'
        set_task_status(project, "T4", "in_progress")
        body = self.client.get(checklist_url(project)).json()
        self.assertEqual(body["overall_status"], NOT_READY)
        project.refresh_from_db()
        self.assertEqual(project.stage, ProjectStage.SHIP)


class RegressionAndPersistenceTests(AuthenticatedAPITestCase):
    def test_task_regression_after_confirmation_returns_not_ready(self):
        project = ready_project()
        confirm_all_manuals(self.client, project)
        self.assertEqual(
            self.client.get(checklist_url(project)).json()["overall_status"],
            READY_TO_SHIP,
        )
        set_task_status(project, "T4", "in_progress")
        body = self.client.get(checklist_url(project)).json()
        self.assertEqual(body["overall_status"], NOT_READY)

    def test_stale_after_confirmation_returns_not_ready_without_erasing_confirmations(self):
        project = ready_project()
        confirm_all_manuals(self.client, project)
        project.refresh_from_db()
        project.downstream_stale = {"architecture": True}
        project.save(update_fields=["downstream_stale"])
        body = self.client.get(checklist_url(project)).json()
        self.assertEqual(body["overall_status"], NOT_READY)
        # confirmations are preserved, not silently deleted
        self.assertTrue(all(c["confirmed"] for c in body["manual_checks"]))
        project.refresh_from_db()
        self.assertEqual(len(project.ship_checklist), 9)

    def test_progress_logic_is_reused_not_duplicated(self):
        import projects.ship_checklist as sc

        src = __import__("inspect").getsource(sc)
        self.assertIn("from projects.progress import compute_project_progress", src)
        # no re-implementation of task bucketing in the ship module
        self.assertNotIn('t["status"] == "completed"', src)

    def test_build_and_review_prompt_and_progress_unchanged(self):
        project = make_roadmap_project(approved=True)
        # build prompt still 502 without a key
        r1 = self.client.post(
            f"/api/projects/{project.slug}/roadmap/tasks/T1/build-prompt/"
        )
        self.assertEqual(r1.status_code, 502)
        # progress endpoint still works and is unchanged in shape
        r2 = self.client.get(f"/api/projects/{project.slug}/progress/")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("summary", r2.json())


class ComputeShipChecklistUnitTests(AuthenticatedAPITestCase):
    def test_pure_function_no_side_effects(self):
        project = ready_project()
        before_stage = project.stage
        result = compute_ship_checklist(project)
        project.refresh_from_db()
        self.assertEqual(project.stage, before_stage)
        self.assertEqual(project.ship_checklist, {})
        self.assertEqual(result["overall_status"], READY_WITH_MANUAL_CHECKS)

    def test_grandfathered_project_bl_check_is_not_applicable(self):
        project = ready_project()  # has architecture content, no approved BL
        auto = {c["id"]: c for c in compute_ship_checklist(project)["automatic_checks"]}
        self.assertEqual(auto["SC-02"]["status"], "pass")
        self.assertIn("Not applicable", auto["SC-02"]["evidence"])
