"""
Phase F verification — deterministic Progress Tracking.

No AI is involved in computing progress. Every number is derived from Roadmap
task status + the dependency graph. A few tests use a fake provider only to prove
that *prompt generation* does not move task status.
"""
import unittest.mock as mock

from tests.base import AuthenticatedAPITestCase

from ai.models import AIRequestLog
from ai.providers.base import StructuredResult
from projects.progress import compute_project_progress
from projects.roadmap import ALLOWED_TRANSITIONS, can_transition
from projects.services import project_progress
from tests.test_phase4 import make_roadmap_project


def progress_url(project):
    return f"/api/projects/{project.slug}/progress/"


def task_url(project, task_id):
    return f"/api/projects/{project.slug}/roadmap/tasks/{task_id}/"


class FakeProvider:
    name = "fake"

    def __init__(self, payload):
        self.payload = payload

    def ensure_ready(self):
        pass

    def generate_structured(self, *, system, user, json_schema, timeout, prior_attempt=None):
        return StructuredResult(
            data=self.payload, provider=self.name, model="fake-1",
            input_tokens=1, output_tokens=1,
        )


class ProgressTrackingTests(AuthenticatedAPITestCase):
    def setUp(self):
        # 4 tasks: T1 <- T2 <- T3 <- T4 (chain). All not_started.
        self.project = make_roadmap_project(approved=True)

    def _advance(self, task_id, target):
        chain = ["not_started", "in_progress", "ready_for_review", "completed"]
        for status in chain[1 : chain.index(target) + 1]:
            res = self.client.patch(
                task_url(self.project, task_id), {"status": status}, format="json"
            )
            self.assertEqual(res.status_code, 200, f"{task_id}->{status}: {res.content}")

    # --- endpoint / envelope --------------------------------------------

    def test_endpoint_exists_and_shape(self):
        res = self.client.get(progress_url(self.project))
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(
            set(body.keys()),
            {
                "summary", "phases", "next_task", "blocked_tasks",
                "ready_for_review_tasks", "completed_tasks",
                "stale_context", "roadmap_stale",
            },
        )
        self.assertEqual(
            set(body["summary"].keys()),
            {
                "total_tasks", "not_started", "in_progress", "ready_for_review",
                "completed", "blocked", "completion_percentage",
            },
        )

    def test_unknown_project_returns_404_envelope(self):
        res = self.client.get("/api/projects/nope/progress/")
        self.assertEqual(res.status_code, 404)
        body = res.json()
        self.assertEqual(set(body.keys()), {"error"})
        self.assertEqual(
            set(body["error"].keys()), {"code", "message", "retryable", "details"}
        )
        self.assertEqual(body["error"]["code"], "project_not_found")

    def test_progress_requires_approved_roadmap(self):
        draft = make_roadmap_project()  # not approved
        res = self.client.get(progress_url(draft))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "roadmap_not_approved")

    def test_zero_tasks_handled(self):
        self.project.roadmap["content"] = {"phases": []}
        self.project.save(update_fields=["roadmap"])
        prog = compute_project_progress(self.project)
        self.assertEqual(
            prog["summary"],
            {
                "total_tasks": 0, "not_started": 0, "in_progress": 0,
                "ready_for_review": 0, "completed": 0, "blocked": 0,
                "completion_percentage": 0,
            },
        )
        self.assertIsNone(prog["next_task"])
        self.assertEqual(prog["phases"], [])
        self.assertEqual(prog["blocked_tasks"], [])

    # --- counts / percentage / partition ------------------------------

    def test_counts_are_deterministic_and_partition(self):
        self._advance("T1", "completed")
        self._advance("T2", "in_progress")
        a = self.client.get(progress_url(self.project)).json()
        b = self.client.get(progress_url(self.project)).json()
        self.assertEqual(a, b)
        s = a["summary"]
        self.assertEqual(
            s["not_started"] + s["in_progress"] + s["ready_for_review"]
            + s["completed"] + s["blocked"],
            s["total_tasks"],
        )
        self.assertEqual(s["total_tasks"], 4)
        self.assertEqual(s["completed"], 1)
        self.assertEqual(s["in_progress"], 1)
        # T3 blocked (dep T2 not completed), T4 blocked (dep T3 not completed)
        self.assertEqual(s["blocked"], 2)
        self.assertEqual(s["not_started"], 0)

    def test_completion_percentage(self):
        for tid in ("T1", "T2"):
            self._advance(tid, "completed")
        s = self.client.get(progress_url(self.project)).json()["summary"]
        self.assertEqual(s["completed"], 2)
        self.assertEqual(s["completion_percentage"], 50)

    def test_blocked_not_counted_as_complete(self):
        s = self.client.get(progress_url(self.project)).json()["summary"]
        self.assertEqual(s["completed"], 0)
        self.assertEqual(s["completion_percentage"], 0)
        self.assertEqual(s["blocked"], 3)  # T2, T3, T4
        self.assertEqual(s["not_started"], 1)  # T1

    # --- per phase -----------------------------------------------------

    def test_per_phase_progress(self):
        self._advance("T1", "completed")
        phases = self.client.get(progress_url(self.project)).json()["phases"]
        p1 = next(p for p in phases if p["phase_id"] == "P1")
        p2 = next(p for p in phases if p["phase_id"] == "P2")
        self.assertEqual(p1["total_tasks"], 2)
        self.assertEqual(p1["completed"], 1)
        self.assertEqual(p1["completion_percentage"], 50)
        self.assertEqual(p1["not_started"], 1)  # T2 now unblocked
        self.assertEqual(p1["blocked"], 0)
        # P2: T3 blocked (dep T2 not completed), T4 blocked (dep T3 not completed)
        self.assertEqual(p2["blocked"], 2)
        self.assertEqual(p2["total_tasks"], 2)

    # --- next task ---------------------------------------------------

    def test_next_task_is_first_unblocked(self):
        nt = self.client.get(progress_url(self.project)).json()["next_task"]
        self.assertEqual(nt["id"], "T1")
        self.assertEqual(nt["phase_title"], "Foundation")

    def test_next_task_prefers_in_progress(self):
        self._advance("T1", "in_progress")
        nt = self.client.get(progress_url(self.project)).json()["next_task"]
        self.assertEqual(nt["id"], "T1")
        self.assertEqual(nt["status"], "in_progress")

    def test_next_task_advances_after_completion(self):
        self._advance("T1", "completed")
        nt = self.client.get(progress_url(self.project)).json()["next_task"]
        self.assertEqual(nt["id"], "T2")

    def test_next_task_falls_back_to_ready_for_review(self):
        self._advance("T1", "ready_for_review")
        # nothing in_progress, nothing not_started is unblocked except... T1 is r-f-r
        # T2 blocked (dep T1 not completed). So next is the r-f-r task.
        nt = self.client.get(progress_url(self.project)).json()["next_task"]
        self.assertEqual(nt["id"], "T1")
        self.assertEqual(nt["status"], "ready_for_review")

    # --- blocked / unblock -----------------------------------------

    def test_blocked_tasks_identified(self):
        blocked = self.client.get(progress_url(self.project)).json()["blocked_tasks"]
        self.assertEqual([b["id"] for b in blocked], ["T2", "T3", "T4"])
        self.assertEqual(blocked[0]["unfinished_dependencies"], ["T1"])

    def test_completing_prerequisite_unblocks_downstream(self):
        self.assertIn(
            "T2",
            [b["id"] for b in self.client.get(progress_url(self.project)).json()["blocked_tasks"]],
        )
        self._advance("T1", "completed")
        blocked = [
            b["id"]
            for b in self.client.get(progress_url(self.project)).json()["blocked_tasks"]
        ]
        self.assertNotIn("T2", blocked)
        # and T2 can now be started
        res = self.client.patch(
            task_url(self.project, "T2"), {"status": "in_progress"}, format="json"
        )
        self.assertEqual(res.status_code, 200)

    def test_incomplete_dependency_blocks_active_transition(self):
        res = self.client.patch(
            task_url(self.project, "T2"), {"status": "in_progress"}, format="json"
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "dependencies_incomplete")
        self.assertEqual(res.json()["error"]["details"]["unfinished"], ["T1"])


class TransitionMatrixTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.project = make_roadmap_project(approved=True)

    def _patch(self, task_id, status):
        return self.client.patch(
            task_url(self.project, task_id), {"status": status}, format="json"
        )

    def test_documented_matrix(self):
        self.assertEqual(
            ALLOWED_TRANSITIONS,
            {
                "not_started": {"in_progress"},
                "in_progress": {"ready_for_review", "not_started"},
                "ready_for_review": {"completed", "in_progress"},
                "completed": {"in_progress"},
            },
        )
        self.assertTrue(can_transition("in_progress", "in_progress"))  # no-op
        self.assertFalse(can_transition("not_started", "completed"))

    def test_invalid_status_value_rejected(self):
        res = self._patch("T1", "shipped")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_status")

    def test_invalid_forward_jump_rejected(self):
        res = self._patch("T1", "completed")  # not_started -> completed
        self.assertEqual(res.status_code, 409)
        body = res.json()["error"]
        self.assertEqual(body["code"], "invalid_transition")
        self.assertEqual(body["details"]["from"], "not_started")
        self.assertEqual(body["details"]["to"], "completed")
        self.assertEqual(body["details"]["allowed"], ["in_progress"])

    def test_full_forward_lifecycle_succeeds(self):
        for status in ("in_progress", "ready_for_review", "completed"):
            self.assertEqual(self._patch("T1", status).status_code, 200, status)

    def test_documented_backward_transitions(self):
        self._patch("T1", "in_progress")
        self.assertEqual(self._patch("T1", "not_started").status_code, 200)  # undo start
        self._patch("T1", "in_progress")
        self._patch("T1", "ready_for_review")
        self.assertEqual(self._patch("T1", "in_progress").status_code, 200)  # review found issues
        self._patch("T1", "ready_for_review")
        self._patch("T1", "completed")
        self.assertEqual(self._patch("T1", "in_progress").status_code, 200)  # reopen

    def test_undocumented_backward_transitions_rejected(self):
        self._patch("T1", "in_progress")
        self._patch("T1", "ready_for_review")
        self.assertEqual(self._patch("T1", "not_started").status_code, 409)  # r-f-r -> not_started
        self._patch("T1", "completed")
        self.assertEqual(self._patch("T1", "not_started").status_code, 409)  # completed -> not_started
        self.assertEqual(self._patch("T1", "ready_for_review").status_code, 409)  # completed -> r-f-r

    def test_same_status_is_accepted_noop(self):
        res = self._patch("T1", "not_started")
        self.assertEqual(res.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(
            self.project.roadmap["content"]["phases"][0]["tasks"][0]["status"],
            "not_started",
        )


class ProgressNoAutomaticCompletionTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.project = make_roadmap_project(approved=True)

    def _t1_status(self):
        self.project.refresh_from_db()
        return self.project.roadmap["content"]["phases"][0]["tasks"][0]["status"]

    def test_build_prompt_generation_does_not_change_status(self):
        fake = FakeProvider({"prompt_markdown": "# Role\n" + "detail " * 60})
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                f"/api/projects/{self.project.slug}/roadmap/tasks/T1/build-prompt/"
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._t1_status(), "not_started")

    def test_review_prompt_generation_does_not_change_status(self):
        fake = FakeProvider({"prompt_markdown": "# Review objective\n" + "verify " * 60})
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                f"/api/projects/{self.project.slug}/roadmap/tasks/T1/review-prompt/"
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._t1_status(), "not_started")
        prog = self.client.get(progress_url(self.project)).json()
        self.assertEqual(prog["summary"]["completed"], 0)

    def test_opening_task_workspace_does_not_change_progress(self):
        before = self.client.get(progress_url(self.project)).json()
        self.client.get(f"/api/projects/{self.project.slug}/roadmap/tasks/T1/")
        after = self.client.get(progress_url(self.project)).json()
        self.assertEqual(before, after)


class ProgressStaleContextTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.project = make_roadmap_project(approved=True)

    def _advance(self, task_id, target):
        chain = ["not_started", "in_progress", "ready_for_review", "completed"]
        for status in chain[1 : chain.index(target) + 1]:
            self.client.patch(
                task_url(self.project, task_id), {"status": status}, format="json"
            )

    def test_stale_context_does_not_erase_statuses(self):
        self._advance("T1", "completed")
        self.project.refresh_from_db()
        self.project.downstream_stale = {"architecture": True, "roadmap": True}
        self.project.save(update_fields=["downstream_stale"])
        prog = self.client.get(progress_url(self.project)).json()
        self.assertEqual(prog["summary"]["completed"], 1)
        self.assertEqual([t["id"] for t in prog["completed_tasks"]], ["T1"])

    def test_stale_context_is_surfaced(self):
        self.project.downstream_stale = {"architecture": True, "roadmap": True}
        self.project.save(update_fields=["downstream_stale"])
        prog = self.client.get(progress_url(self.project)).json()
        self.assertEqual(prog["stale_context"], ["architecture", "roadmap"])
        self.assertTrue(prog["roadmap_stale"])

    def test_clean_project_has_no_stale_flags(self):
        prog = self.client.get(progress_url(self.project)).json()
        self.assertEqual(prog["stale_context"], [])
        self.assertFalse(prog["roadmap_stale"])


class ProgressUsesNoAITests(AuthenticatedAPITestCase):
    def setUp(self):
        self.project = make_roadmap_project(approved=True)

    def test_progress_and_status_change_make_no_ai_call(self):
        def boom(*a, **k):
            raise AssertionError("Progress must not touch the AI provider")

        with mock.patch("ai.base.get_provider", side_effect=boom):
            self.assertEqual(
                self.client.get(progress_url(self.project)).status_code, 200
            )
            self.assertEqual(
                self.client.patch(
                    task_url(self.project, "T1"),
                    {"status": "in_progress"},
                    format="json",
                ).status_code,
                200,
            )
        self.assertFalse(
            AIRequestLog.objects.filter(operation__startswith="progress").exists()
        )
