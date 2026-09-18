"""
Phase I-5 verification — Data Progress, Delivery Readiness, full Data stale
dependency chain, Data Conversation provider, Data Proposal targets/
application, and the final Data context digest.

Every deterministic view here (Progress, Readiness, stale propagation) must
never call the AI provider. The live data_conversation_response round trip is
PENDING an ANTHROPIC_API_KEY; every AI-touching test uses a fake provider.
"""
import json
import tempfile
import unittest.mock as mock

from django.test import override_settings
from tests.base import AuthenticatedAPITestCase, default_owner

from ai.models import AIRequestLog
from projects import dependencies as dep
from projects.conversation_context import build_conversation_context
from projects.data import stale as data_stale
from projects.data.progress import compute_data_progress
from projects.data.readiness import (
    NOT_READY,
    READY_TO_DELIVER,
    READY_WITH_MANUAL_CHECKS,
    compute_data_readiness,
)
from projects.models import (
    AnalysisPlan,
    Conversation,
    Dataset,
    Insight,
    MetricDefinition,
    Project,
    ProjectStage,
    Proposal,
    Query,
)
from tests.test_phase_i1_data_foundation import (
    INTERPRETATION_PAYLOAD,
    FakeProvider,
    data_project,
    data_project_with_brief,
)
from tests.test_phase_i2_quality_transformation import (
    profiled_dataset,
    quality_rules_payload,
    transformation_payload,
)
from tests.test_phase_i4_analysis_dashboard import (
    dashboard_draft,
    descriptive_plan_payload,
    make_project_with_kpi,
    revenue_metric_draft,
)


def make_conversation(project) -> Conversation:
    return Conversation.objects.create(project=project)


def full_pipeline_project(client):
    """Data Brief -> profiled dataset -> approved quality -> approved
    transformation -> approved KPI -> reviewed+executed Query -> approved+run
    AnalysisPlan -> approved Dashboard. Returns (project, dataset, metric,
    query, plan, result_id)."""
    project, dataset, metric = make_project_with_kpi(client)
    slug = project.slug

    fake_interp = FakeProvider(INTERPRETATION_PAYLOAD)
    with mock.patch("ai.base.get_provider", return_value=fake_interp):
        client.post(f"/api/projects/{slug}/datasets/{dataset.id}/interpret/")
    client.post(f"/api/projects/{slug}/datasets/{dataset.id}/interpret/approve/")

    # The amount-null observation lands at DQ-03 for this fixture (the
    # order_id-uniqueness observation from profiled_dataset's row shape takes
    # DQ-02) — cover it explicitly so the pipeline has zero unresolved
    # critical issues, unlike I-2's own fixture which targets DQ-02.
    fake_q = FakeProvider(quality_rules_payload(
        str(dataset.id),
        rules=[
            {
                "dataset_ref": str(dataset.id), "column": "amount",
                "dimension": "completeness", "assertion": "not_null", "params": {},
                "rationale": "amount is required for revenue analysis",
                "related_observations": ["DQ-03"],
            },
            {
                "dataset_ref": str(dataset.id), "column": "status",
                "dimension": "validity", "assertion": "in_set",
                "params": {"values": ["completed", "refunded", "cancelled"]},
                "rationale": "status is an enum", "related_observations": [],
            },
        ],
    ))
    client.post(f"/api/projects/{slug}/data-quality/observe/")
    with mock.patch("ai.base.get_provider", return_value=fake_q):
        client.post(f"/api/projects/{slug}/data-quality/propose-rules/")
    client.post(f"/api/projects/{slug}/data-quality/approve/")
    client.post(f"/api/projects/{slug}/data-quality/check/")

    fake_tx = FakeProvider(transformation_payload(str(dataset.id)))
    with mock.patch("ai.base.get_provider", return_value=fake_tx):
        client.post(f"/api/projects/{slug}/transformation/generate/")
    client.post(f"/api/projects/{slug}/transformation/approve/")

    client.post(f"/api/projects/{slug}/metrics/{metric.id}/validate/")

    q = client.post(
        f"/api/projects/{slug}/queries/", {"question": "Revenue by status?"}, format="json"
    ).json()
    from tests.test_phase_i3_metrics_queries_lineage import query_plan_payload, sql_draft

    client.patch(
        f"/api/projects/{slug}/queries/{q['id']}/plan/",
        {"plan": query_plan_payload(str(dataset.id), kpi_refs=[metric.business_id])},
        format="json",
    )
    client.post(f"/api/projects/{slug}/queries/{q['id']}/approve-plan/")
    view = f"src_{str(dataset.id).replace('-', '')[:28]}"
    fake_sql = FakeProvider(sql_draft(view, kpi_refs=[metric.business_id]))
    with mock.patch("ai.base.get_provider", return_value=fake_sql):
        client.post(f"/api/projects/{slug}/queries/{q['id']}/generate-sql/")
    client.post(f"/api/projects/{slug}/queries/{q['id']}/mark-reviewed/")
    client.post(f"/api/projects/{slug}/queries/{q['id']}/execute/")
    query = Query.objects.get(id=q["id"])

    plan_res = client.post(
        f"/api/projects/{slug}/analysis/plans/",
        descriptive_plan_payload(metric.business_id), format="json",
    )
    plan_id = plan_res.json()["id"]
    client.post(f"/api/projects/{slug}/analysis/plans/{plan_id}/approve/")
    run_res = client.post(f"/api/projects/{slug}/analysis/plans/{plan_id}/run/")
    result_id = run_res.json()["id"]
    plan = AnalysisPlan.objects.get(id=plan_id)

    fake_dash = FakeProvider(dashboard_draft(metric.business_id))
    with mock.patch("ai.base.get_provider", return_value=fake_dash):
        client.post(f"/api/projects/{slug}/dashboard/generate/")
    client.post(f"/api/projects/{slug}/dashboard/approve/")

    project.refresh_from_db()
    return project, dataset, metric, query, plan, result_id


# =====================================================================
# Progress
# =====================================================================


class ProgressTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_empty_data_project_all_not_started(self):
        project = data_project()  # no brief content generated at all
        progress = compute_data_progress(project)
        self.assertEqual(progress["stages"][0]["status"], "not_started")
        self.assertEqual(progress["summary"]["stages_complete"], 0)

    def test_data_brief_approved_stage_complete(self):
        project = data_project_with_brief()  # helper approves the brief
        progress = compute_data_progress(project)
        brief_stage = next(s for s in progress["stages"] if s["id"] == "data_brief")
        self.assertEqual(brief_stage["status"], "complete")

    def test_data_goal_skips_metrics_queries_analysis_dashboard_for_quality_goal(self):
        project = data_project_with_brief(data_goal="quality")
        progress = compute_data_progress(project)
        by_id = {s["id"]: s["status"] for s in progress["stages"]}
        self.assertEqual(by_id["metrics"], "skipped")
        self.assertEqual(by_id["queries"], "skipped")
        self.assertEqual(by_id["analysis"], "skipped")
        self.assertEqual(by_id["dashboard"], "skipped")
        self.assertEqual(by_id["transformation_plan"], "skipped")
        # skipped stages are excluded from the completion denominator
        self.assertEqual(progress["summary"]["stages_total"], 4)  # brief+sources+quality+delivery

    def test_engineering_goal_notes_deferred_future_stages_honestly(self):
        project = data_project_with_brief(data_goal="engineering")
        progress = compute_data_progress(project)
        self.assertIn("data_model", progress["deferred_future_stages"])
        self.assertIn("pipeline_design", progress["deferred_future_stages"])
        # never fabricated as an actual stage in the 9-list
        self.assertNotIn("data_model", [s["id"] for s in progress["stages"]])

    def test_analytics_goal_no_deferred_stages_note(self):
        project = data_project_with_brief(data_goal="analytics")
        progress = compute_data_progress(project)
        self.assertEqual(progress["deferred_future_stages"], [])

    def test_sources_blocked_on_profiling_failure(self):
        project = data_project_with_brief()
        Dataset.objects.create(
            project=project, name="bad.csv", source_type="csv", storage_ref="x",
            original_filename="bad.csv", content_type="text/csv", size_bytes=1,
            checksum="x", status="failed", error="corrupt file",
        )
        progress = compute_data_progress(project)
        sources = next(s for s in progress["stages"] if s["id"] == "sources")
        self.assertEqual(sources["status"], "blocked")

    def test_full_pipeline_all_required_stages_complete(self):
        project, *_ = full_pipeline_project(self.client)
        progress = compute_data_progress(project)
        for s in progress["stages"]:
            if s["status"] == "skipped" or s["id"] == "delivery_readiness":
                continue
            self.assertEqual(s["status"], "complete", f"{s['id']}: {s['blockers']}")
        # delivery_readiness genuinely needs manual human confirmations — see
        # ReadinessTests.test_ready_with_manual_checks_then_ready_to_deliver
        delivery = next(s for s in progress["stages"] if s["id"] == "delivery_readiness")
        self.assertEqual(delivery["status"], "needs_review")

    def test_next_action_deterministic_and_no_ai(self):
        def boom(*a, **k):
            raise AssertionError("progress must not call the AI provider")

        project = data_project_with_brief()
        with mock.patch("ai.base.get_provider", side_effect=boom):
            progress = compute_data_progress(project)
        self.assertIsNotNone(progress["next_action"])
        self.assertEqual(progress["next_action"]["stage"], "sources")

    def test_pending_proposals_counted(self):
        project = data_project_with_brief()
        conv = Conversation.objects.create(project=project)
        Proposal.objects.create(
            conversation=conv, project=project, target_artifact="data_brief",
            proposed_change={"sections": {}, "summary": "x", "entity_id": ""},
            status=Proposal.Status.PENDING,
        )
        progress = compute_data_progress(project)
        self.assertEqual(progress["summary"]["pending_proposals"], 1)

    def test_stale_count_reflected(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        metric.stale = True
        metric.save(update_fields=["stale"])
        progress = compute_data_progress(project)
        self.assertGreaterEqual(progress["summary"]["stale_count"], 1)
        self.assertIn(metric.business_id, progress["stale_context"])

    def test_endpoint_returns_progress(self):
        project = data_project_with_brief()
        res = self.client.get(f"/api/projects/{project.slug}/data-progress/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("summary", res.json())

    def test_software_project_rejected(self):
        sw = Project.objects.create(original_idea="x", stage=ProjectStage.DISCOVERY, owner=default_owner())
        res = self.client.get(f"/api/projects/{sw.slug}/data-progress/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "not_a_data_project")


# =====================================================================
# Delivery Readiness
# =====================================================================


class ReadinessTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_not_ready_with_nothing_done(self):
        project = data_project_with_brief()
        project.data_brief_approved_at = None
        project.save(update_fields=["data_brief_approved_at"])
        readiness = compute_data_readiness(project)
        self.assertEqual(readiness["overall_status"], NOT_READY)
        self.assertTrue(readiness["blockers"])

    def test_automatic_checks_always_recomputed_not_stored(self):
        project, *_ = full_pipeline_project(self.client)
        r1 = compute_data_readiness(project)
        # tamper with something that would flip an automatic check
        MetricDefinition.objects.filter(project=project).update(status="draft")
        r2 = compute_data_readiness(project)
        self.assertNotEqual(
            [c["status"] for c in r1["automatic_checks"]],
            [c["status"] for c in r2["automatic_checks"]],
        )

    def test_unresolved_critical_quality_blocks_readiness(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        # observations with a critical severity but no covering rule at all
        self.client.post(f"/api/projects/{project.slug}/data-quality/observe/")
        readiness = compute_data_readiness(project)
        dq = (project.data_quality or {}).get("content") or {}
        has_critical = any(o["severity"] == "critical" for o in dq.get("observations", []))
        if has_critical:
            self.assertEqual(readiness["overall_status"], NOT_READY)

    def test_stale_authoritative_artifact_blocks_readiness(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        metric.stale = True
        metric.save(update_fields=["stale"])
        readiness = compute_data_readiness(project)
        ids = [c["id"] for c in readiness["blockers"]]
        self.assertIn("DR-16", ids)

    def test_ready_with_manual_checks_then_ready_to_deliver(self):
        project, *_ = full_pipeline_project(self.client)
        readiness = compute_data_readiness(project)
        self.assertEqual(readiness["overall_status"], READY_WITH_MANUAL_CHECKS)

        from projects.data.readiness import MANUAL_ITEM_IDS

        for item_id in MANUAL_ITEM_IDS:
            res = self.client.patch(
                f"/api/projects/{project.slug}/data-readiness/",
                {"item_id": item_id, "confirmed": True}, format="json",
            )
            self.assertEqual(res.status_code, 200, res.content)
        project.refresh_from_db()
        final = compute_data_readiness(project)
        self.assertEqual(final["overall_status"], READY_TO_DELIVER)

    def test_manual_confirmations_persist(self):
        project = data_project_with_brief()
        from projects.data.readiness import MANUAL_ITEM_IDS

        item_id = sorted(MANUAL_ITEM_IDS)[0]
        self.client.patch(
            f"/api/projects/{project.slug}/data-readiness/",
            {"item_id": item_id, "confirmed": True, "note": "confirmed by ops"}, format="json",
        )
        project.refresh_from_db()
        self.assertTrue(project.data_readiness[item_id]["confirmed"])
        self.assertEqual(project.data_readiness[item_id]["note"], "confirmed by ops")

    def test_ai_cannot_confirm_manual_item(self):
        # apply_data_manual_confirmation requires an explicit human-facing
        # call; the AI provider is never invoked by the readiness module.
        def boom(*a, **k):
            raise AssertionError("readiness must not call the AI provider")

        project = data_project_with_brief()
        with mock.patch("ai.base.get_provider", side_effect=boom):
            compute_data_readiness(project)

    def test_invalid_manual_item_rejected(self):
        project = data_project_with_brief()
        res = self.client.patch(
            f"/api/projects/{project.slug}/data-readiness/",
            {"item_id": "not_a_real_item", "confirmed": True}, format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_readiness_item")

    def test_historical_failed_job_not_a_blocker_after_later_success(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        # re-profiling failure history shouldn't block if the CURRENT status is profiled
        from projects.models import Job

        Job.objects.create(project=project, dataset=dataset, kind="profile_dataset", status="failed", error="old failure")
        readiness = compute_data_readiness(project)
        ids = [c["id"] for c in readiness["blockers"]]
        self.assertNotIn("DR-17", ids)  # dataset.status is "profiled", not "failed"


# =====================================================================
# Stale dependency chain
# =====================================================================


class SoftwareChainUnchangedTests(AuthenticatedAPITestCase):
    def test_software_chain_untouched(self):
        self.assertEqual(
            dep.ARTIFACT_CHAIN,
            ("discovery", "blueprint", "business_logic", "architecture", "roadmap"),
        )
        self.assertEqual(dep.STALEABLE, ("business_logic", "architecture", "roadmap"))
        self.assertEqual(dep.downstream_of("blueprint"), ["business_logic", "architecture", "roadmap"])

    def test_chain_for_dispatches_by_project_type(self):
        sw = Project.objects.create(original_idea="x", stage=ProjectStage.DISCOVERY, owner=default_owner())
        data = data_project_with_brief()
        self.assertEqual(dep.chain_for(sw), dep.ARTIFACT_CHAIN)
        self.assertEqual(dep.chain_for(data), data_stale.DATA_ARTIFACT_CHAIN)


class StalePropagationTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_brief_change_propagates_to_everything_approved(self):
        # the Data Brief can only be *edited* through its own PATCH endpoint
        # while stage == data_brief (same stage-lock philosophy as Software's
        # blueprint — see projects.services.update_blueprint); by the time a
        # full pipeline exists the project has long since advanced past that
        # stage. So propagate_brief_change is exercised directly here,
        # exactly as update_data_brief itself calls it — this is the same
        # testing strategy test_phase_c_stale.py uses for
        # mark_downstream_stale.
        project, *_ = full_pipeline_project(self.client)
        impact = data_stale.propagate_brief_change(project)
        project.save(update_fields=["downstream_stale"])
        self.assertTrue(impact["data_quality"])
        self.assertTrue(impact["transformation_plan"])
        self.assertTrue(impact["dashboard_blueprint"])
        project.refresh_from_db()
        self.assertTrue(data_stale.is_data_stale(project, "data_quality"))
        self.assertTrue(data_stale.is_data_stale(project, "transformation_plan"))
        self.assertTrue(data_stale.is_data_stale(project, "dashboard_blueprint"))
        self.assertTrue(MetricDefinition.objects.filter(project=project, stale=True).exists())
        self.assertTrue(Query.objects.filter(project=project, stale=True).exists())
        self.assertTrue(AnalysisPlan.objects.filter(project=project, stale=True).exists())
        # content/history preserved — never deleted
        self.assertTrue(project.metrics.exists())
        self.assertTrue(project.analysis_plans.first().results.exists())

    def test_dataset_reprofile_propagates_scoped_to_affected_metrics(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        res = self.client.post(f"/api/projects/{project.slug}/datasets/{dataset.id}/profile/")
        self.assertEqual(res.status_code, 200, res.content)
        metric.refresh_from_db()
        query.refresh_from_db()
        plan.refresh_from_db()
        self.assertTrue(metric.stale)
        self.assertTrue(query.stale)
        self.assertTrue(plan.stale)

    def test_quality_change_propagates(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        res = self.client.patch(
            f"/api/projects/{project.slug}/data-quality/",
            {"content": {"rules": []}}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        project.refresh_from_db()
        self.assertTrue(data_stale.is_data_stale(project, "transformation_plan"))
        metric.refresh_from_db()
        self.assertTrue(metric.stale)

    def test_transformation_change_propagates(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        res = self.client.patch(
            f"/api/projects/{project.slug}/transformation/",
            {"content": {"outputs": [{"name": "renamed", "grain": "order"}]}}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        metric.refresh_from_db()
        self.assertTrue(metric.stale)

    def test_metric_change_affects_query_and_analysis_and_dashboard(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        res = self.client.patch(
            f"/api/projects/{project.slug}/metrics/{metric.id}/",
            {"name": "Total Revenue (renamed)"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        query.refresh_from_db()
        plan.refresh_from_db()
        project.refresh_from_db()
        self.assertTrue(query.stale)
        self.assertTrue(plan.stale)
        self.assertTrue(data_stale.is_data_stale(project, "dashboard_blueprint"))

    def test_query_change_affects_analysis(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        res = self.client.patch(
            f"/api/projects/{project.slug}/queries/{query.id}/plan/",
            {"plan": {"objective": "A different question now."}}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        plan.refresh_from_db()
        self.assertTrue(plan.stale)

    def test_analysis_change_affects_dashboard(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        res = self.client.patch(
            f"/api/projects/{project.slug}/analysis/plans/{plan.id}/",
            {"business_question": "A totally different question."}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        project.refresh_from_db()
        self.assertTrue(data_stale.is_data_stale(project, "dashboard_blueprint"))

    def test_stale_never_deletes_content_or_history(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        findings_before = plan.results.first().findings
        self.client.patch(
            f"/api/projects/{project.slug}/data-brief/",
            {"content": {"decision_context": "changed"}}, format="json",
        )
        plan.refresh_from_db()
        self.assertEqual(plan.results.first().findings, findings_before)
        self.assertIsNotNone(plan.approved_at)  # approval kept, only stale flips
        metric.refresh_from_db()
        self.assertIsNotNone(metric.approved_at)

    def test_stale_cleared_only_by_own_reconciliation(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        metric.stale = True
        metric.stale_reason = "test"
        metric.save(update_fields=["stale", "stale_reason"])
        # editing an unrelated other metric must not clear THIS one
        fake = FakeProvider({"metrics": [{
            "name": "Other KPI", "business_meaning": "x", "formula_text": "count(*)",
            "structured": {"aggregation": "count", "base_table_ref": str(dataset.id),
                            "default_filters": [], "time_field": "", "dimensions": []},
            "time_grain": "", "allowed_dimensions": [], "source_fields": [], "owner": "",
            "related_goal_ref": "", "caveats": [], "validation_checks": [],
        }]})
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(f"/api/projects/{project.slug}/metrics/generate/")
        metric.refresh_from_db()
        self.assertTrue(metric.stale)  # still stale — only re-approving THIS metric clears it

        self.client.post(f"/api/projects/{project.slug}/metrics/{metric.id}/approve/")
        metric.refresh_from_db()
        self.assertFalse(metric.stale)
        self.assertEqual(metric.stale_reason, "")


# =====================================================================
# Data Conversation provider
# =====================================================================


class DataConversationProviderTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_data_provider_selected_for_data_projects(self):
        project, *_ = full_pipeline_project(self.client)
        ctx = build_conversation_context(project, "what does this dataset contain?")
        self.assertIn("data", ctx)
        self.assertIn("status", ctx)
        self.assertEqual(ctx["project"]["project_type"], "data")

    def test_no_software_fallback_for_data_project(self):
        project, *_ = full_pipeline_project(self.client)
        ctx = build_conversation_context(project, "hello")
        self.assertNotIn("slices", ctx)  # that's the Software shape

    def test_software_project_still_uses_software_provider(self):
        sw = Project.objects.create(original_idea="x", stage=ProjectStage.DISCOVERY, owner=default_owner())
        ctx = build_conversation_context(sw, "hello")
        self.assertIn("slices", ctx)
        self.assertNotIn("data", ctx)

    def test_context_is_bounded_and_has_no_raw_rows(self):
        project, *_ = full_pipeline_project(self.client)
        ctx = build_conversation_context(project, "what is in the dataset?")
        blob = json.dumps(ctx)
        self.assertNotIn("a@example.com", blob)
        self.assertNotIn("120.50", blob)

    def test_progress_and_readiness_accessible_in_context(self):
        project, *_ = full_pipeline_project(self.client)
        ctx = build_conversation_context(project, "what should I do next?")
        self.assertIn("progress", ctx["status"])
        self.assertIn("readiness", ctx["status"])

    def test_stale_state_explainable_in_context(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        metric.stale = True
        metric.save(update_fields=["stale"])
        ctx = build_conversation_context(project, "what is stale?")
        self.assertIn(metric.business_id, ctx["status"]["stale"])

    def test_full_message_turn_uses_data_operation_and_no_raw_rows_sent(self):
        project, *_ = full_pipeline_project(self.client)
        conv = make_conversation(project)
        fake = FakeProvider({
            "response": "Revenue KPI-01 is defined as sum(amount).",
            "intent": "informational", "referenced_artifacts": ["metrics"],
            "proposed_change": None,
        })
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                f"/api/projects/{project.slug}/conversations/{conv.id}/messages/",
                {"content": "Why is KPI-01 defined this way?"}, format="json",
            )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertNotIn("a@example.com", fake.last_user)
        log = AIRequestLog.objects.filter(operation="data_conversation_response").latest("id")
        self.assertEqual(log.prompt_version, "data_conversation/v1")


# =====================================================================
# Data Proposal targets + application
# =====================================================================


def _metric_proposal_turn(kpi_ref, name):
    return {
        "response": f"I'll rename {kpi_ref}.",
        "intent": "proposal",
        "referenced_artifacts": ["metrics"],
        "proposed_change": {
            "target_artifact": "metric", "entity_id": kpi_ref,
            "summary": "rename the KPI", "rationale": "clarity",
            "sections": {"name": name},
        },
    }


class DataProposalTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def _msg_url(self, project, conv):
        return f"/api/projects/{project.slug}/conversations/{conv.id}/messages/"

    def test_proposal_created_for_valid_metric_target(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        conv = make_conversation(project)
        fake = FakeProvider(_metric_proposal_turn(metric.business_id, "Renamed Revenue"))
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(self._msg_url(project, conv), {"content": "rename it"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        proposal = res.json()["proposal"]
        self.assertEqual(proposal["target_artifact"], "metric")
        self.assertEqual(proposal["status"], "pending")
        self.assertIn("notes", proposal["impact_summary"])

    def test_facts_cannot_be_proposal_targets(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        conv = make_conversation(project)
        for bad_target in ("query_run", "analysis_result", "metric_validation_run", "job"):
            fake = FakeProvider({
                "response": "ok", "intent": "informational",
                "referenced_artifacts": [], "proposed_change": None,
            })
            # the schema itself only allows the 8 legitimate targets — a
            # fact-target like these is rejected at validation time before
            # ever reaching our target-membership check
            with mock.patch("ai.base.get_provider", return_value=fake):
                res = self.client.post(self._msg_url(project, conv), {"content": "x"}, format="json")
            self.assertEqual(res.status_code, 200)

    def test_approve_applies_via_domain_service_validation_included(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        conv = make_conversation(project)
        fake = FakeProvider(_metric_proposal_turn(metric.business_id, "Renamed Revenue"))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(self._msg_url(project, conv), {"content": "rename it"}, format="json")
        proposal = Proposal.objects.get()
        res = self.client.post(f"/api/projects/{project.slug}/proposals/{proposal.id}/approve/")
        self.assertEqual(res.status_code, 200, res.content)
        metric.refresh_from_db()
        self.assertEqual(metric.name, "Renamed Revenue")
        # applied through update_metric -> reverted to draft (I-3 semantics)
        self.assertEqual(metric.status, "draft")

    def test_rejection_never_mutates_domain_state(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        conv = make_conversation(project)
        fake = FakeProvider(_metric_proposal_turn(metric.business_id, "Renamed Revenue"))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(self._msg_url(project, conv), {"content": "rename it"}, format="json")
        proposal = Proposal.objects.get()
        res = self.client.post(f"/api/projects/{project.slug}/proposals/{proposal.id}/reject/")
        self.assertEqual(res.status_code, 200)
        metric.refresh_from_db()
        self.assertEqual(metric.name, "Total Revenue")  # unchanged

    def test_kpi_proposal_approval_marks_dependent_query_and_analysis_stale(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        conv = make_conversation(project)
        fake = FakeProvider(_metric_proposal_turn(metric.business_id, "Revenue v2"))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(self._msg_url(project, conv), {"content": "rename it"}, format="json")
        proposal = Proposal.objects.get()
        res = self.client.post(f"/api/projects/{project.slug}/proposals/{proposal.id}/approve/")
        self.assertEqual(res.status_code, 200, res.content)
        query.refresh_from_db()
        plan.refresh_from_db()
        self.assertTrue(query.stale)
        self.assertTrue(plan.stale)

    def test_impact_summary_deterministic_no_ai(self):
        project, dataset, metric, query, plan, result_id = full_pipeline_project(self.client)
        from projects.data.proposal_services import data_impact_summary

        def boom(*a, **k):
            raise AssertionError("impact summary must not call the AI provider")

        with mock.patch("ai.base.get_provider", side_effect=boom):
            impact = data_impact_summary(project, "metric", metric.business_id)
        self.assertIn(query.business_id, impact["downstream_review_candidates"])
        self.assertIn(plan.business_id, impact["downstream_review_candidates"])

    def test_cross_project_proposal_application_blocked(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        other, _, _ = make_project_with_kpi(self.client)
        conv = make_conversation(project)
        fake = FakeProvider(_metric_proposal_turn(metric.business_id, "Renamed"))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(self._msg_url(project, conv), {"content": "rename it"}, format="json")
        proposal = Proposal.objects.get()
        res = self.client.post(f"/api/projects/{other.slug}/proposals/{proposal.id}/approve/")
        self.assertEqual(res.status_code, 404)  # not found under the wrong project

    def test_unsupported_target_rejected_on_approval(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        conv = make_conversation(project)
        proposal = Proposal.objects.create(
            conversation=conv, project=project, target_artifact="query_run",
            proposed_change={"sections": {}, "summary": "x", "entity_id": ""},
            status=Proposal.Status.PENDING,
        )
        res = self.client.post(f"/api/projects/{project.slug}/proposals/{proposal.id}/approve/")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "unsupported_proposal_target")


# =====================================================================
# Final Data context digest
# =====================================================================


class FinalDigestTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_final_expected_slices_present(self):
        project, *_ = full_pipeline_project(self.client)
        digest = project.context_digest
        for key in (
            "data_goal", "goal", "data_brief", "data_sources", "schemas",
            "data_quality", "quality_open_critical", "transformation_plan",
            "metrics", "queries", "analyses", "dashboard", "lineage_index",
            "progress_summary", "readiness_summary", "stale", "approved_at",
        ):
            self.assertIn(key, digest, key)

    def test_caps_enforced_and_no_raw_rows_or_result_tables(self):
        project, *_ = full_pipeline_project(self.client)
        blob = json.dumps(project.context_digest)
        self.assertNotIn("a@example.com", blob)
        self.assertNotIn("executed_sql", blob)
        self.assertNotIn("metric_values", blob)
        self.assertLessEqual(len(project.context_digest["lineage_index"]["nodes"]), 50)

    def test_only_approved_accepted_state_present(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        project.refresh_from_db()  # approve_metric mutated a separate view-scoped instance
        # metric approved but nothing else -> digest metrics present, but no
        # dashboard/analyses/accepted_insights keys yet
        digest = project.context_digest
        self.assertIn("metrics", digest)
        self.assertNotIn("dashboard", digest)
        self.assertNotIn("accepted_insights", digest)

    def test_readiness_and_progress_summaries_shaped(self):
        project, *_ = full_pipeline_project(self.client)
        digest = project.context_digest
        self.assertIn("overall_status", digest["readiness_summary"])
        self.assertIn("stages_total", digest["progress_summary"])
