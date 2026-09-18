"""
Phase 5 verification tests (Roadmap -> Task Workspace -> Build Prompt).

Deterministic paths only: the context-selection layer, the Task Workspace
payload + guards, the Build Prompt generate guards (roadmap approved, task
exists, not blocked, AI-first), prompt persistence + history + cascade, and
context isolation (no secrets / no context_digest). The live
build_prompt_generation round trip is PENDING an ANTHROPIC_API_KEY.
"""
import json

from pydantic import ValidationError
from tests.base import AuthenticatedAPITestCase

from ai.operations.build_prompt_generation import BuildPrompt
from projects.context_selection import assemble_task_context
from projects.models import GeneratedPrompt, Project, ProjectStage
from tests.test_phase4 import make_approved_architecture_project, make_roadmap_project


def deep_text(obj) -> str:
    return json.dumps(obj, default=str).lower()


class ContextSelectionTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.project = make_roadmap_project(approved=True)
        self.roadmap = self.project.roadmap["content"]

    def test_unknown_task_returns_none(self):
        self.assertIsNone(assemble_task_context(self.project, "T999"))

    def test_includes_task_phase_and_dependencies(self):
        ctx = assemble_task_context(self.project, "T3")  # "Supplier catalog API", dep T2
        self.assertEqual(ctx["task"]["id"], "T3")
        self.assertEqual(ctx["task"]["phase_title"], "Core domain")
        self.assertEqual([d["id"] for d in ctx["dependencies"]], ["T2"])
        self.assertIn("expected_output", ctx["dependencies"][0])
        self.assertIn("status", ctx["dependencies"][0])

    def test_resolves_requirement_ids(self):
        ctx = assemble_task_context(self.project, "T3")  # requirements: ["FR1"]
        self.assertEqual([r["id"] for r in ctx["requirements"]], ["FR1"])
        self.assertEqual(ctx["requirements"][0]["priority"], "must")

    def test_falls_back_to_must_requirements_when_task_has_none(self):
        ctx = assemble_task_context(self.project, "T1")  # no requirement refs
        ids = {r["id"] for r in ctx["requirements"]}
        self.assertTrue(ids)  # must-priority FRs pulled in
        self.assertTrue(all(r["priority"] == "must" for r in ctx["requirements"]))

    def test_architecture_spine_always_present(self):
        ctx = assemble_task_context(self.project, "T1")["architecture"]
        for key in ("style", "frontend", "backend", "database", "auth"):
            self.assertTrue(ctx[key], key)
        self.assertTrue(ctx["key_decisions"])
        self.assertTrue(ctx["constraints"])

    def test_keyword_filter_selects_relevant_components(self):
        ctx = assemble_task_context(self.project, "T3")  # "Supplier catalog API"
        names = {c["name"] for c in ctx["architecture"]["components"]}
        self.assertIn("Catalog service", names)
        areas = {a["name"] for a in ctx["architecture"]["api_areas"]}
        self.assertIn("Catalog API", areas)

    def test_is_deterministic(self):
        a = assemble_task_context(self.project, "T3")
        b = assemble_task_context(self.project, "T3")
        self.assertEqual(a, b)

    def test_contains_no_secrets_or_digest(self):
        ctx = assemble_task_context(self.project, "T3")
        blob = deep_text(ctx)
        self.assertNotIn("anthropic", blob)
        self.assertNotIn("sk-ant", blob)
        self.assertNotIn("context_digest", blob)
        self.assertNotIn("api_key", blob)


class TaskWorkspaceTests(AuthenticatedAPITestCase):
    def _url(self, project, task_id):
        return f"/api/projects/{project.slug}/roadmap/tasks/{task_id}/"

    def test_unknown_project_returns_404(self):
        res = self.client.get("/api/projects/nope/roadmap/tasks/T1/")
        self.assertEqual(res.status_code, 404)

    def test_roadmap_not_approved_returns_409(self):
        project = make_roadmap_project()  # draft
        res = self.client.get(self._url(project, "T1"))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "roadmap_not_approved")

    def test_unknown_task_returns_404(self):
        project = make_roadmap_project(approved=True)
        res = self.client.get(self._url(project, "T404"))
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "task_not_found")

    def test_workspace_payload_shape(self):
        project = make_roadmap_project(approved=True)
        res = self.client.get(self._url(project, "T3"))
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["task"]["id"], "T3")
        self.assertEqual(body["phase"]["title"], "Core domain")
        self.assertNotIn("tasks", body["phase"])  # trimmed phase
        self.assertEqual(body["blocked"], True)  # dep T2 not completed
        self.assertEqual(body["unfinished_dependencies"], ["T2"])
        self.assertIn("relevant_context", body)
        self.assertEqual(body["prompts"], [])
        self.assertNotIn("context_digest", deep_text(body))

    def test_unblocked_task_not_flagged(self):
        project = make_roadmap_project(approved=True)
        body = self.client.get(self._url(project, "T1")).json()
        self.assertFalse(body["blocked"])
        self.assertEqual(body["unfinished_dependencies"], [])


class BuildPromptGenerateTests(AuthenticatedAPITestCase):
    def _url(self, project, task_id):
        return f"/api/projects/{project.slug}/roadmap/tasks/{task_id}/build-prompt/"

    def test_roadmap_not_approved_returns_409(self):
        project = make_roadmap_project()
        res = self.client.post(self._url(project, "T1"))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "roadmap_not_approved")

    def test_unknown_task_returns_404(self):
        project = make_roadmap_project(approved=True)
        res = self.client.post(self._url(project, "T404"))
        self.assertEqual(res.status_code, 404)

    def test_blocked_task_returns_409_and_persists_nothing(self):
        project = make_roadmap_project(approved=True)
        res = self.client.post(self._url(project, "T3"))  # dep T2 not completed
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "task_blocked")
        self.assertEqual(res.json()["error"]["details"]["unfinished"], ["T2"])
        self.assertEqual(GeneratedPrompt.objects.count(), 0)

    def test_missing_key_returns_502_and_persists_nothing(self):
        project = make_roadmap_project(approved=True)
        res = self.client.post(self._url(project, "T1"))  # unblocked
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
        self.assertEqual(GeneratedPrompt.objects.count(), 0)

    def test_generation_attempt_does_not_change_task_status(self):
        project = make_roadmap_project(approved=True)
        before = project.roadmap["content"]["phases"][0]["tasks"][0]["status"]
        self.client.post(self._url(project, "T1"))  # 502, no key
        project.refresh_from_db()
        after = project.roadmap["content"]["phases"][0]["tasks"][0]["status"]
        self.assertEqual(before, after)


class PromptPersistenceTests(AuthenticatedAPITestCase):
    def _make_prompt(self, project, task_id="T1", content="x" * 300):
        return GeneratedPrompt.objects.create(
            project=project,
            task_id=task_id,
            task_title="Project setup",
            kind=GeneratedPrompt.Kind.BUILD,
            content=content,
            context_snapshot={"task": {"id": task_id}, "architecture": {"style": "monolith"}},
            model="claude-sonnet-5",
        )

    def test_workspace_returns_prompt_history_newest_first(self):
        project = make_roadmap_project(approved=True)
        older = self._make_prompt(project, content="older " * 60)
        newer = self._make_prompt(project, content="newer " * 60)
        GeneratedPrompt.objects.filter(pk=older.pk).update(
            created_at="2020-01-01T00:00:00+00:00"
        )
        body = self.client.get(
            f"/api/projects/{project.slug}/roadmap/tasks/T1/"
        ).json()
        ids = [p["id"] for p in body["prompts"]]
        self.assertEqual(ids, [newer.id, older.id])
        self.assertEqual(
            set(body["prompts"][0].keys()),
            {"id", "kind", "content", "model", "created_at"},
        )

    def test_prompts_scoped_to_task(self):
        project = make_roadmap_project(approved=True)
        self._make_prompt(project, task_id="T1")
        self._make_prompt(project, task_id="T2")
        body = self.client.get(
            f"/api/projects/{project.slug}/roadmap/tasks/T1/"
        ).json()
        self.assertEqual(len(body["prompts"]), 1)

    def test_deleting_project_cascades_prompts(self):
        project = make_roadmap_project(approved=True)
        self._make_prompt(project)
        project.delete()
        self.assertEqual(GeneratedPrompt.objects.count(), 0)

    def test_context_snapshot_has_no_secrets(self):
        project = make_roadmap_project(approved=True)
        prompt = self._make_prompt(project)
        blob = deep_text(prompt.context_snapshot)
        self.assertNotIn("anthropic", blob)
        self.assertNotIn("context_digest", blob)


class BuildPromptSchemaTests(AuthenticatedAPITestCase):
    def test_short_prompt_rejected(self):
        with self.assertRaises(ValidationError):
            BuildPrompt.model_validate({"prompt_markdown": "too short"})

    def test_full_prompt_accepted(self):
        model = BuildPrompt.model_validate({"prompt_markdown": "# Role\n" + "detail " * 60})
        self.assertTrue(model.prompt_markdown)


class Phase5RegressionTests(AuthenticatedAPITestCase):
    def test_roadmap_still_editable_after_prompt_generated(self):
        project = make_roadmap_project(approved=True)
        GeneratedPrompt.objects.create(
            project=project, task_id="T1", task_title="Project setup",
            kind="build", content="x" * 300, context_snapshot={}, model="m",
        )
        phases = project.roadmap["content"]["phases"]
        phases[0]["title"] = "Groundwork"
        res = self.client.patch(
            f"/api/projects/{project.slug}/roadmap/",
            {"content": {"phases": phases}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(GeneratedPrompt.objects.count(), 1)  # history untouched

    def test_project_serializer_unaffected(self):
        project = make_approved_architecture_project()
        res = self.client.get(f"/api/projects/{project.slug}/")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("prompts", res.json())
        self.assertNotIn("context_digest", res.json())
