"""
Phase C verification — downstream stale / dependency policy.

The policy module (``projects.dependencies``) is exercised directly, plus the
service integration is checked to be a no-op under today's stage locks and to
clear correctly on regenerate / re-approve. No migration; no workflow redesign.
"""
import unittest.mock as mock

from tests.base import AuthenticatedAPITestCase

from projects import dependencies as dep
from projects.models import GeneratedPrompt, Project, ProjectStage
from projects.services import (
    approve_architecture,
    approve_roadmap,
    generate_blueprint,
    update_blueprint,
)
from tests.test_phase3 import make_arch_project
from tests.test_phase4 import make_approved_architecture_project, make_roadmap_project


class DependencyMapTests(AuthenticatedAPITestCase):
    def test_downstream_of(self):
        self.assertEqual(
            dep.downstream_of("discovery"),
            ["business_logic", "architecture", "roadmap"],
        )
        self.assertEqual(
            dep.downstream_of("blueprint"),
            ["business_logic", "architecture", "roadmap"],
        )
        self.assertEqual(
            dep.downstream_of("business_logic"), ["architecture", "roadmap"]
        )
        self.assertEqual(dep.downstream_of("architecture"), ["roadmap"])
        self.assertEqual(dep.downstream_of("roadmap"), [])
        self.assertEqual(dep.downstream_of("nonexistent"), [])

    def test_chain_and_staleable_are_the_single_edit_points(self):
        self.assertEqual(
            dep.ARTIFACT_CHAIN,
            ("discovery", "blueprint", "business_logic", "architecture", "roadmap"),
        )
        self.assertEqual(
            dep.STALEABLE, ("business_logic", "architecture", "roadmap")
        )


class MarkStaleTests(AuthenticatedAPITestCase):
    def test_marks_only_approved_downstream(self):
        project = make_roadmap_project(approved=True)  # bp + arch + roadmap approved
        changed = dep.mark_downstream_stale(project, "blueprint")
        self.assertTrue(changed)
        self.assertEqual(project.downstream_stale, {"architecture": True, "roadmap": True})

    def test_does_not_mark_unapproved_downstream(self):
        # bp + arch approved, NO roadmap
        project = make_approved_architecture_project()
        changed = dep.mark_downstream_stale(project, "blueprint")
        self.assertTrue(changed)
        self.assertEqual(project.downstream_stale, {"architecture": True})  # roadmap absent

    def test_architecture_change_marks_only_roadmap(self):
        project = make_roadmap_project(approved=True)
        dep.mark_downstream_stale(project, "architecture")
        self.assertEqual(project.downstream_stale, {"roadmap": True})
        self.assertNotIn("architecture", project.downstream_stale)
        self.assertNotIn("blueprint", project.downstream_stale)

    def test_roadmap_change_marks_nothing(self):
        project = make_roadmap_project(approved=True)
        self.assertFalse(dep.mark_downstream_stale(project, "roadmap"))
        self.assertEqual(project.downstream_stale, {})

    def test_idempotent(self):
        project = make_roadmap_project(approved=True)
        self.assertTrue(dep.mark_downstream_stale(project, "blueprint"))
        self.assertFalse(dep.mark_downstream_stale(project, "blueprint"))  # already set


class ClearStaleTests(AuthenticatedAPITestCase):
    def test_clears_only_the_named_flag(self):
        project = make_roadmap_project(approved=True)
        project.downstream_stale = {"architecture": True, "roadmap": True}
        changed = dep.clear_stale(project, "architecture")
        self.assertTrue(changed)
        self.assertEqual(project.downstream_stale, {"roadmap": True})  # roadmap kept

    def test_clear_absent_flag_is_noop(self):
        project = make_roadmap_project(approved=True)
        project.downstream_stale = {"roadmap": True}
        self.assertFalse(dep.clear_stale(project, "architecture"))
        self.assertEqual(project.downstream_stale, {"roadmap": True})

    def test_inspect_helpers(self):
        project = make_roadmap_project(approved=True)
        project.downstream_stale = {"roadmap": True}
        self.assertTrue(dep.is_stale(project, "roadmap"))
        self.assertFalse(dep.is_stale(project, "architecture"))
        self.assertEqual(dep.stale_artifacts(project), ["roadmap"])


class StageLocksUnchangedTests(AuthenticatedAPITestCase):
    """The new marking calls must not weaken any existing 409 stage lock."""

    def test_regenerate_blueprint_after_roadmap_still_409(self):
        project = make_roadmap_project(approved=True)  # stage = roadmap
        res = self.client.post(f"/api/projects/{project.slug}/blueprint/generate/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "invalid_workflow_state")
        project.refresh_from_db()
        self.assertEqual(project.downstream_stale, {})  # nothing marked

    def test_edit_blueprint_after_roadmap_still_409(self):
        project = make_roadmap_project(approved=True)
        res = self.client.patch(
            f"/api/projects/{project.slug}/blueprint/",
            {"content": {"problem": "changed"}},
            format="json",
        )
        self.assertEqual(res.status_code, 409)
        project.refresh_from_db()
        self.assertEqual(project.downstream_stale, {})

    def test_edit_architecture_after_roadmap_still_409(self):
        project = make_roadmap_project(approved=True)
        res = self.client.patch(
            f"/api/projects/{project.slug}/architecture/",
            {"content": {"security": ["x"]}},
            format="json",
        )
        self.assertEqual(res.status_code, 409)
        project.refresh_from_db()
        self.assertEqual(project.downstream_stale, {})

    def test_normal_blueprint_edit_at_its_own_stage_marks_nothing(self):
        # stage = blueprint, nothing downstream approved yet
        project = make_arch_project()  # stage=architecture, bp approved, arch draft
        project.stage = ProjectStage.BLUEPRINT
        project.save(update_fields=["stage"])
        res = self.client.patch(
            f"/api/projects/{project.slug}/blueprint/",
            {"content": {"problem": "A tighter problem statement."}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.downstream_stale, {})


class ReconciliationTests(AuthenticatedAPITestCase):
    """Regenerate / re-approve clears the right flag (bypassing locks at the
    service layer, since no current UI flow can produce a stale project)."""

    def test_approve_architecture_clears_architecture_keeps_roadmap(self):
        project = make_arch_project()  # stage=architecture, arch draft, bp approved
        project.downstream_stale = {"architecture": True, "roadmap": True}
        project.save(update_fields=["downstream_stale"])
        content_before = project.architecture["content"]

        project = approve_architecture(project)

        self.assertEqual(project.downstream_stale, {"roadmap": True})
        self.assertIsNotNone(project.architecture_approved_at)  # not unapproved
        self.assertEqual(project.architecture["content"], content_before)  # preserved

    def test_approve_roadmap_clears_roadmap(self):
        project = make_roadmap_project()  # stage=roadmap, roadmap draft
        project.downstream_stale = {"roadmap": True}
        project.save(update_fields=["downstream_stale"])
        project = approve_roadmap(project)
        self.assertEqual(project.downstream_stale, {})
        self.assertIsNotNone(project.roadmap_approved_at)


class PreservationTests(AuthenticatedAPITestCase):
    def test_marking_stale_never_touches_approval_or_content(self):
        project = make_roadmap_project(approved=True)
        arch_content = project.architecture["content"]
        arch_approved = project.architecture_approved_at
        rm_approved = project.roadmap_approved_at

        dep.mark_downstream_stale(project, "blueprint")

        self.assertEqual(project.architecture["content"], arch_content)
        self.assertEqual(project.architecture_approved_at, arch_approved)
        self.assertEqual(project.roadmap_approved_at, rm_approved)

    def test_generated_prompt_history_untouched_by_stale_marking(self):
        project = make_roadmap_project(approved=True)
        prompt = GeneratedPrompt.objects.create(
            project=project,
            task_id="T1",
            task_title="Project setup",
            kind="build",
            content="x" * 300,
            context_snapshot={"task": {"id": "T1"}},
            model="claude-sonnet-5",
        )
        dep.mark_downstream_stale(project, "blueprint")
        project.downstream_stale = {"architecture": True, "roadmap": True}
        project.save(update_fields=["downstream_stale"])

        prompt.refresh_from_db()
        self.assertEqual(GeneratedPrompt.objects.count(), 1)
        self.assertEqual(prompt.content, "x" * 300)
        self.assertEqual(prompt.context_snapshot, {"task": {"id": "T1"}})


class BackendControlledTests(AuthenticatedAPITestCase):
    def test_project_detail_exposes_downstream_stale_read_only(self):
        project = make_roadmap_project(approved=True)
        res = self.client.get(f"/api/projects/{project.slug}/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("downstream_stale", res.json())
        self.assertEqual(res.json()["downstream_stale"], {})

    def test_no_endpoint_lets_the_client_set_downstream_stale(self):
        project = make_roadmap_project(approved=True)
        # the project-detail route is GET-only
        res = self.client.patch(
            f"/api/projects/{project.slug}/",
            {"downstream_stale": {"architecture": True}},
            format="json",
        )
        self.assertIn(res.status_code, (403, 404, 405))
        project.refresh_from_db()
        self.assertEqual(project.downstream_stale, {})


class BusinessLogicReadinessTests(AuthenticatedAPITestCase):
    """Adding a mid-chain node in the next phase must not require rewriting the
    policy - only ARTIFACT_CHAIN / STALEABLE change."""

    def test_inserting_business_logic_node_behaves(self):
        with mock.patch.object(
            dep,
            "ARTIFACT_CHAIN",
            ("discovery", "blueprint", "business_logic", "architecture", "roadmap"),
        ), mock.patch.object(
            dep, "STALEABLE", ("business_logic", "architecture", "roadmap")
        ):
            self.assertEqual(
                dep.downstream_of("blueprint"),
                ["business_logic", "architecture", "roadmap"],
            )
            self.assertEqual(
                dep.downstream_of("business_logic"), ["architecture", "roadmap"]
            )
            self.assertEqual(dep.downstream_of("architecture"), ["roadmap"])

    def test_mark_downstream_ignores_unknown_approval_attr(self):
        # a chain node with no *_approved_at mapping is simply never marked
        project = make_roadmap_project(approved=True)
        with mock.patch.object(
            dep,
            "ARTIFACT_CHAIN",
            ("discovery", "blueprint", "business_logic", "architecture", "roadmap"),
        ), mock.patch.object(
            dep, "STALEABLE", ("business_logic", "architecture", "roadmap")
        ):
            dep.mark_downstream_stale(project, "blueprint")
        # business_logic has no _APPROVED_AT_ATTR entry -> not marked; arch/roadmap are
        self.assertEqual(
            project.downstream_stale, {"architecture": True, "roadmap": True}
        )
