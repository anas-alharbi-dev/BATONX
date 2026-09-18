"""
Phase I-4 verification — Analysis Plan, deterministic Analysis execution,
Analysis Result, evidence-grounded Insight, Dashboard Blueprint, generic
Dashboard Build Prompt, and their lineage/context extensions.

Every numeric fact in a Finding is produced by real DuckDB execution over the
same boundary Phase I-2/I-3 hardened — never by AI. The live
analysis_plan_generation / insight_generation / dashboard_blueprint_generation
/ dashboard_build_prompt_generation round trips are PENDING an
ANTHROPIC_API_KEY; every AI-touching test uses a fake provider.
"""
import tempfile
import unittest.mock as mock

from django.test import override_settings
from pydantic import ValidationError
from tests.base import AuthenticatedAPITestCase, default_owner

from ai.models import AIRequestLog
from projects.data.analysis import AnalysisPlanContent
from projects.data.insights import validate_insight_evidence
from projects.data.lineage import resolve_lineage
from projects.models import (
    AnalysisPlan,
    AnalysisResult,
    Insight,
    MetricDefinition,
    Project,
    ProjectStage,
)
from tests.test_phase_i1_data_foundation import FakeProvider, data_project_with_brief
from tests.test_phase_i2_quality_transformation import profiled_dataset


# =====================================================================
# fixtures
# =====================================================================


def revenue_metric_draft(dataset_id, **overrides):
    payload = {
        "name": "Total Revenue",
        "business_meaning": "Total amount across all orders",
        "formula_text": "sum(amount)",
        "structured": {
            "aggregation": "sum", "base_table_ref": dataset_id,
            "measure": {"field": "amount"}, "default_filters": [],
            "time_field": "ordered_at", "dimensions": ["status"],
        },
        "time_grain": "day", "allowed_dimensions": ["status"],
        "source_fields": ["amount"], "owner": "", "related_goal_ref": "",
        "caveats": [], "validation_checks": [],
    }
    payload.update(overrides)
    return {"metrics": [payload]}


def order_count_metric_draft(dataset_id, **overrides):
    payload = {
        "name": "Order Count",
        "business_meaning": "Number of orders",
        "formula_text": "count(*)",
        "structured": {
            "aggregation": "count", "base_table_ref": dataset_id,
            "default_filters": [], "time_field": "ordered_at",
            "dimensions": ["status"],
        },
        "time_grain": "day", "allowed_dimensions": ["status"],
        "source_fields": [], "owner": "", "related_goal_ref": "",
        "caveats": [], "validation_checks": [],
    }
    payload.update(overrides)
    return {"metrics": [payload]}


def make_project_with_kpi(client, metric_draft_fn=revenue_metric_draft):
    project = data_project_with_brief()
    dataset = profiled_dataset(client, project)
    fake = FakeProvider(metric_draft_fn(str(dataset.id)))
    with mock.patch("ai.base.get_provider", return_value=fake):
        client.post(f"/api/projects/{project.slug}/metrics/generate/")
    metric = MetricDefinition.objects.get(project=project)
    client.post(f"/api/projects/{project.slug}/metrics/{metric.id}/approve/")
    return project, dataset, metric


def descriptive_plan_payload(kpi_ref, segments=None):
    return {
        "business_question": "What is total revenue?",
        "method": "descriptive",
        "hypotheses": [],
        "required_metrics": [kpi_ref],
        "segments": segments or [],
        "comparisons": [],
        "expected_outputs": ["a headline revenue number"],
    }


def trend_plan_payload(kpi_ref):
    return {
        "business_question": "How did revenue change?",
        "method": "trend",
        "required_metrics": [kpi_ref],
        "comparisons": [
            {"label": "Jan 5", "time_range": {"start": "2026-01-05", "end": "2026-01-05"}},
            {"label": "Jan 6-7", "time_range": {"start": "2026-01-06", "end": "2026-01-07"}},
        ],
        "expected_outputs": ["a % change"],
    }


def segmentation_plan_payload(kpi_ref):
    return {
        "business_question": "Which status has the most revenue?",
        "method": "segmentation",
        "required_metrics": [kpi_ref],
        "segments": ["status"],
        "expected_outputs": ["a ranked breakdown by status"],
    }


def comparison_plan_payload(kpi_ref):
    return {
        "business_question": "Completed vs refunded order count?",
        "method": "comparison",
        "required_metrics": [kpi_ref],
        "comparisons": [
            {"label": "completed", "filters": [{"field": "status", "operator": "eq", "value": "completed"}]},
            {"label": "refunded", "filters": [{"field": "status", "operator": "eq", "value": "refunded"}]},
        ],
        "expected_outputs": ["a comparison"],
    }


def funnel_plan_payload(kpi_ref):
    return {
        "business_question": "What share of orders complete?",
        "method": "funnel",
        "required_metrics": [kpi_ref],
        "comparisons": [
            {"label": "all orders", "filters": [{"field": "order_id", "operator": "gt", "value": 0}]},
            {"label": "completed", "filters": [{"field": "status", "operator": "eq", "value": "completed"}]},
        ],
        "expected_outputs": ["a conversion rate"],
    }


# =====================================================================
# AnalysisPlanContent — pure schema validation (no DB)
# =====================================================================


class AnalysisPlanContentTests(AuthenticatedAPITestCase):
    def test_trend_requires_exactly_two_time_ranged_comparisons(self):
        with self.assertRaises(ValidationError):
            AnalysisPlanContent.model_validate({
                "business_question": "q", "method": "trend", "required_metrics": ["KPI-01"],
                "comparisons": [{"label": "only one"}],
            })
        with self.assertRaises(ValidationError):
            AnalysisPlanContent.model_validate({
                "business_question": "q", "method": "trend", "required_metrics": ["KPI-01"],
                "comparisons": [{"label": "a"}, {"label": "b"}],  # no time_range
            })
        AnalysisPlanContent.model_validate({
            "business_question": "q", "method": "trend", "required_metrics": ["KPI-01"],
            "comparisons": [
                {"label": "a", "time_range": {"start": "2026-01-01", "end": "2026-01-02"}},
                {"label": "b", "time_range": {"start": "2026-02-01", "end": "2026-02-02"}},
            ],
        })

    def test_segmentation_requires_segments(self):
        with self.assertRaises(ValidationError):
            AnalysisPlanContent.model_validate({
                "business_question": "q", "method": "segmentation", "required_metrics": ["KPI-01"],
            })

    def test_funnel_requires_at_least_two_filtered_steps(self):
        with self.assertRaises(ValidationError):
            AnalysisPlanContent.model_validate({
                "business_question": "q", "method": "funnel", "required_metrics": ["KPI-01"],
                "comparisons": [{"label": "step1", "filters": [{"field": "a", "operator": "eq", "value": 1}]}],
            })

    def test_required_metrics_must_be_non_empty(self):
        with self.assertRaises(ValidationError):
            AnalysisPlanContent.model_validate({
                "business_question": "q", "method": "descriptive", "required_metrics": [],
            })


# =====================================================================
# Analysis Plan lifecycle
# =====================================================================


class AnalysisPlanLifecycleTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project, self.dataset, self.metric = make_project_with_kpi(self.client)
        self.slug = self.project.slug

    def tearDown(self):
        self.override.disable()

    def test_create_assigns_deterministic_an_ids(self):
        r1 = self.client.post(
            f"/api/projects/{self.slug}/analysis/plans/",
            descriptive_plan_payload(self.metric.business_id), format="json",
        )
        r2 = self.client.post(
            f"/api/projects/{self.slug}/analysis/plans/",
            descriptive_plan_payload(self.metric.business_id), format="json",
        )
        self.assertEqual(r1.json()["business_id"], "AN-01")
        self.assertEqual(r2.json()["business_id"], "AN-02")

    def test_unapproved_kpi_ref_rejected(self):
        res = self.client.post(
            f"/api/projects/{self.slug}/analysis/plans/",
            descriptive_plan_payload("KPI-99"), format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_analysis_plan")

    def test_cross_project_kpi_ref_rejected(self):
        # business ids are only unique per project (both projects independently
        # start at KPI-01) — to genuinely test cross-project isolation, use a
        # second KPI in `other` whose id ("KPI-02") does NOT exist at all in
        # self.project, rather than one that would coincidentally collide.
        other, other_dataset, _ = make_project_with_kpi(self.client)
        fake = FakeProvider(order_count_metric_draft(str(other_dataset.id)))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(f"/api/projects/{other.slug}/metrics/generate/")
        second_metric = MetricDefinition.objects.get(project=other, name="Order Count")
        self.client.post(f"/api/projects/{other.slug}/metrics/{second_metric.id}/approve/")
        self.assertEqual(second_metric.business_id, "KPI-02")

        res = self.client.post(
            f"/api/projects/{self.slug}/analysis/plans/",
            descriptive_plan_payload(second_metric.business_id), format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_analysis_plan")

    def test_invalid_segment_dimension_rejected(self):
        res = self.client.post(
            f"/api/projects/{self.slug}/analysis/plans/",
            descriptive_plan_payload(self.metric.business_id, segments=["not_a_real_column"]),
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_analysis_plan")

    def test_lifecycle_draft_to_approved(self):
        res = self.client.post(
            f"/api/projects/{self.slug}/analysis/plans/",
            descriptive_plan_payload(self.metric.business_id), format="json",
        )
        plan_id = res.json()["id"]
        self.assertEqual(res.json()["status"], "draft")

        res = self.client.post(f"/api/projects/{self.slug}/analysis/plans/{plan_id}/approve/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "approved")

    def test_run_requires_approved(self):
        res = self.client.post(
            f"/api/projects/{self.slug}/analysis/plans/",
            descriptive_plan_payload(self.metric.business_id), format="json",
        )
        plan_id = res.json()["id"]
        res = self.client.post(f"/api/projects/{self.slug}/analysis/plans/{plan_id}/run/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "invalid_workflow_state")

    def test_edit_approved_plan_reverts_to_draft_and_keeps_old_results(self):
        res = self.client.post(
            f"/api/projects/{self.slug}/analysis/plans/",
            descriptive_plan_payload(self.metric.business_id), format="json",
        )
        plan_id = res.json()["id"]
        self.client.post(f"/api/projects/{self.slug}/analysis/plans/{plan_id}/approve/")
        run_res = self.client.post(f"/api/projects/{self.slug}/analysis/plans/{plan_id}/run/")
        self.assertEqual(run_res.status_code, 200, run_res.content)
        result_id = run_res.json()["id"]

        res = self.client.patch(
            f"/api/projects/{self.slug}/analysis/plans/{plan_id}/",
            {"business_question": "A different question"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["status"], "draft")

        # the old AnalysisResult is untouched
        old = AnalysisResult.objects.get(id=result_id)
        self.assertTrue(old.findings)
        get_res = self.client.get(f"/api/projects/{self.slug}/analysis/results/{result_id}/")
        self.assertEqual(get_res.status_code, 200)


# =====================================================================
# Deterministic Analysis execution
# =====================================================================


class AnalysisExecutionTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def _approved_plan(self, project, payload):
        res = self.client.post(
            f"/api/projects/{project.slug}/analysis/plans/", payload, format="json"
        )
        self.assertEqual(res.status_code, 200, res.content)
        plan_id = res.json()["id"]
        self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/approve/")
        return plan_id

    def test_descriptive_run_computes_real_sum_no_ai(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        plan_id = self._approved_plan(
            project, descriptive_plan_payload(metric.business_id, segments=["status"])
        )

        def boom(*a, **k):
            raise AssertionError("analysis execution must not call the AI provider")

        with mock.patch("ai.base.get_provider", side_effect=boom):
            res = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/")
        self.assertEqual(res.status_code, 200, res.content)
        findings = res.json()["findings"]
        self.assertEqual(findings[0]["id"], "F-01")
        # sum(amount): 120.50 + null(skipped) + -4.00 + 120.50 = 237.00
        self.assertAlmostEqual(findings[0]["metric_values"]["value"], 237.0, places=2)
        self.assertIn("237.00", findings[0]["statement"])
        self.assertTrue(findings[0]["breakdown"])
        self.assertEqual(findings[0]["evidence"]["kpi_refs"], [metric.business_id])
        self.assertEqual(findings[0]["evidence"]["analysis_plan_ref"], "AN-01")

    def test_trend_run_computes_real_pct_change(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        plan_id = self._approved_plan(project, trend_plan_payload(metric.business_id))
        res = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/")
        self.assertEqual(res.status_code, 200, res.content)
        f = res.json()["findings"][0]
        # baseline (Jan 5): 120.50 * 2 = 241.00 ; comparison (Jan 6-7): null + -4.00 = -4.00
        self.assertAlmostEqual(f["metric_values"]["baseline"], 241.0, places=2)
        self.assertAlmostEqual(f["metric_values"]["comparison"], -4.0, places=2)
        self.assertIn("decreased", f["statement"])

    def test_trend_without_time_field_is_unsupported_analysis(self):
        project, dataset, metric = make_project_with_kpi(
            self.client,
            metric_draft_fn=lambda ds_id: revenue_metric_draft(
                ds_id, structured={
                    "aggregation": "sum", "base_table_ref": ds_id,
                    "measure": {"field": "amount"}, "default_filters": [],
                    "time_field": "", "dimensions": ["status"],
                },
            ),
        )
        plan_id = self._approved_plan(project, trend_plan_payload(metric.business_id))
        res = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "unsupported_analysis")

    def test_segmentation_run_ranks_breakdown(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        plan_id = self._approved_plan(project, segmentation_plan_payload(metric.business_id))
        res = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/")
        self.assertEqual(res.status_code, 200, res.content)
        f = res.json()["findings"][0]
        self.assertTrue(f["breakdown"])
        values = [b["value"] for b in f["breakdown"]]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_comparison_run_counts_each_group(self):
        project, dataset, metric = make_project_with_kpi(
            self.client, metric_draft_fn=order_count_metric_draft
        )
        plan_id = self._approved_plan(project, comparison_plan_payload(metric.business_id))
        res = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/")
        self.assertEqual(res.status_code, 200, res.content)
        f = res.json()["findings"][0]
        self.assertEqual(f["metric_values"]["left"], 3)
        self.assertEqual(f["metric_values"]["right"], 1)
        self.assertEqual(f["metric_values"]["left_label"], "completed")
        self.assertEqual(f["metric_values"]["right_label"], "refunded")

    def test_funnel_run_computes_conversion(self):
        project, dataset, metric = make_project_with_kpi(
            self.client, metric_draft_fn=order_count_metric_draft
        )
        plan_id = self._approved_plan(project, funnel_plan_payload(metric.business_id))
        res = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/")
        self.assertEqual(res.status_code, 200, res.content)
        f = res.json()["findings"][0]
        self.assertEqual(f["metric_values"]["step_counts"], [4, 3])
        self.assertAlmostEqual(f["metric_values"]["overall_conversion_pct"], 75.0, places=1)

    def test_result_history_is_immutable_on_rerun(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        plan_id = self._approved_plan(project, descriptive_plan_payload(metric.business_id))
        r1 = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/").json()
        r2 = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/").json()
        self.assertNotEqual(r1["id"], r2["id"])
        self.assertEqual(AnalysisResult.objects.filter(plan_id=plan_id).count(), 2)
        # source dataset is untouched
        dataset.refresh_from_db()
        self.assertEqual(dataset.status, "profiled")

    def test_job_failure_recorded_on_execution_error(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        plan_id = self._approved_plan(project, descriptive_plan_payload(metric.business_id))
        with mock.patch(
            "projects.data.analysis_services.compile_analysis",
            side_effect=lambda *a, **k: (
                [("q1", "SELECT * FROM read_csv('/etc/passwd')")], [], lambda results: []
            ),
        ):
            res = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "analysis_execution_failed")
        from projects.models import Job

        job = Job.objects.filter(kind="run_analysis").latest("created_at")
        self.assertEqual(job.status, "failed")


# =====================================================================
# Insights: evidence validator (the critical boundary)
# =====================================================================


class EvidenceValidatorTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.findings = [
            {
                "id": "F-01", "statement": "Total Revenue is 237.00.",
                "metric_values": {"value": 237.0}, "breakdown": [],
            },
            {
                "id": "F-02", "statement": "Revenue decreased by 12.4% from Q3 to Q4.",
                "metric_values": {"pct_change": -12.4}, "breakdown": [],
            },
        ]

    def test_requires_non_empty_supporting_finding_ids(self):
        with self.assertRaises(ValueError):
            validate_insight_evidence(self.findings, {
                "fact": "Total Revenue is 237.00.", "interpretation": "x",
                "supporting_finding_ids": [],
            })

    def test_rejects_dangling_finding_ref(self):
        with self.assertRaises(ValueError):
            validate_insight_evidence(self.findings, {
                "fact": "Total Revenue is 237.00.", "interpretation": "x",
                "supporting_finding_ids": ["F-99"],
            })

    def test_fact_must_exactly_match_a_referenced_statement(self):
        with self.assertRaises(ValueError):
            validate_insight_evidence(self.findings, {
                "fact": "Total Revenue is about 240.", "interpretation": "x",
                "supporting_finding_ids": ["F-01"],
            })
        # exact match passes
        validate_insight_evidence(self.findings, {
            "fact": "Total Revenue is 237.00.", "interpretation": "Revenue is healthy.",
            "supporting_finding_ids": ["F-01"],
        })

    def test_rejects_unreconcilable_number_in_interpretation(self):
        with self.assertRaises(ValueError):
            validate_insight_evidence(self.findings, {
                "fact": "Revenue decreased by 12.4% from Q3 to Q4.",
                "interpretation": "This is actually a 50% decline in real terms.",
                "supporting_finding_ids": ["F-02"],
            })

    def test_allows_number_that_appears_in_evidence(self):
        validate_insight_evidence(self.findings, {
            "fact": "Revenue decreased by 12.4% from Q3 to Q4.",
            "interpretation": "The 12.4% decline is notable.",
            "supporting_finding_ids": ["F-02"],
        })

    def test_rejects_causal_wording_in_fact_or_interpretation(self):
        with self.assertRaises(ValueError):
            validate_insight_evidence(self.findings, {
                "fact": "Revenue decreased by 12.4% from Q3 to Q4.",
                "interpretation": "The onboarding change caused the decline.",
                "supporting_finding_ids": ["F-02"],
            })

    def test_causal_wording_allowed_in_recommendation_as_advisory(self):
        # recommendation is not scanned — this must NOT raise
        validate_insight_evidence(self.findings, {
            "fact": "Revenue decreased by 12.4% from Q3 to Q4.",
            "interpretation": "The decline is concentrated in Q4.",
            "recommendation": "Investigate whether the onboarding change contributed to the decline.",
            "supporting_finding_ids": ["F-02"],
        })


class InsightServiceTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project, self.dataset, self.metric = make_project_with_kpi(self.client)
        self.slug = self.project.slug
        plan_res = self.client.post(
            f"/api/projects/{self.slug}/analysis/plans/",
            descriptive_plan_payload(self.metric.business_id), format="json",
        )
        self.plan_id = plan_res.json()["id"]
        self.client.post(f"/api/projects/{self.slug}/analysis/plans/{self.plan_id}/approve/")
        run_res = self.client.post(f"/api/projects/{self.slug}/analysis/plans/{self.plan_id}/run/")
        self.result = run_res.json()
        self.result_id = self.result["id"]
        self.statement = self.result["findings"][0]["statement"]

    def tearDown(self):
        self.override.disable()

    def _generate(self, insights):
        fake = FakeProvider({"insights": insights})
        with mock.patch("ai.base.get_provider", return_value=fake):
            return self.client.post(
                f"/api/projects/{self.slug}/analysis/results/{self.result_id}/insights/generate/"
            )

    def test_generate_persists_valid_insight_with_deterministic_id(self):
        res = self._generate([{
            "fact": self.statement, "interpretation": "Revenue looks healthy.",
            "recommendation": "Consider a Q1 promotion.", "confidence": "medium",
            "supporting_finding_ids": ["F-01"], "caveats": [],
        }])
        self.assertEqual(res.status_code, 200, res.content)
        insights = res.json()
        self.assertEqual(insights[0]["business_id"], "INS-01")
        self.assertEqual(insights[0]["status"], "draft")
        log = AIRequestLog.objects.filter(operation="insight_generation").latest("id")
        self.assertEqual(log.prompt_version, "insight/v1")

    def test_generate_rejects_batch_with_dangling_evidence(self):
        res = self._generate([{
            "fact": self.statement, "interpretation": "x", "confidence": "low",
            "supporting_finding_ids": ["F-99"], "caveats": [],
        }])
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "ai_invalid_output")
        self.assertEqual(Insight.objects.count(), 0)

    def test_generate_rejects_batch_with_fabricated_fact(self):
        res = self._generate([{
            "fact": "Total Revenue is 999999.00.", "interpretation": "x", "confidence": "low",
            "supporting_finding_ids": ["F-01"], "caveats": [],
        }])
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "ai_invalid_output")
        self.assertEqual(Insight.objects.count(), 0)

    def test_ai_cannot_auto_accept_and_explicit_accept_required(self):
        self._generate([{
            "fact": self.statement, "interpretation": "Revenue looks healthy.",
            "confidence": "medium", "supporting_finding_ids": ["F-01"], "caveats": [],
        }])
        insight = Insight.objects.get(project=self.project)
        self.assertEqual(insight.status, "draft")
        self.assertIsNone(insight.accepted_at)

        res = self.client.post(f"/api/projects/{self.slug}/analysis/insights/{insight.id}/accept/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "accepted")
        insight.refresh_from_db()
        self.assertIsNotNone(insight.accepted_at)

    def test_acceptance_never_modifies_analysis_result(self):
        self._generate([{
            "fact": self.statement, "interpretation": "Revenue looks healthy.",
            "confidence": "medium", "supporting_finding_ids": ["F-01"], "caveats": [],
        }])
        insight = Insight.objects.get(project=self.project)
        before = AnalysisResult.objects.get(id=self.result_id).findings
        self.client.post(f"/api/projects/{self.slug}/analysis/insights/{insight.id}/accept/")
        after = AnalysisResult.objects.get(id=self.result_id).findings
        self.assertEqual(before, after)

    def test_ai_sees_findings_not_raw_dataset_rows(self):
        captured = {}

        def fake_generate_structured(*, system, user, json_schema, timeout, prior_attempt=None):
            captured["user"] = user
            from ai.providers.base import StructuredResult

            return StructuredResult(
                data={"insights": [{
                    "fact": self.statement, "interpretation": "ok", "confidence": "low",
                    "supporting_finding_ids": ["F-01"], "caveats": [],
                }]},
                provider="fake", model="fake-1", input_tokens=1, output_tokens=1,
            )

        fake = mock.Mock()
        fake.name = "fake"
        fake.ensure_ready = mock.Mock()
        fake.generate_structured = fake_generate_structured
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                f"/api/projects/{self.slug}/analysis/results/{self.result_id}/insights/generate/"
            )
        self.assertNotIn("a@example.com", captured["user"])
        self.assertNotIn("120.50", captured["user"])


# =====================================================================
# Dashboard Blueprint
# =====================================================================


def dashboard_draft(kpi_ref, insight_ref=None):
    return {
        "audience": "Head of Sales",
        "decision_use_case": "Decide where to focus next quarter",
        "refresh_cadence": "daily",
        "global_filters": [],
        "panels": [
            {
                "title": "Total Revenue", "viz_type": "kpi_card",
                "metric_refs": [kpi_ref], "dimension": "", "comparison": "",
                "drilldowns": [], "anomaly_view": False,
                "insight_refs": [insight_ref] if insight_ref else [],
                "notes": "",
            },
        ],
        "layout": "single column",
    }


class DashboardLifecycleTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project, self.dataset, self.metric = make_project_with_kpi(self.client)
        self.slug = self.project.slug

    def tearDown(self):
        self.override.disable()

    def _generate(self, draft=None):
        fake = FakeProvider(draft or dashboard_draft(self.metric.business_id))
        with mock.patch("ai.base.get_provider", return_value=fake):
            return self.client.post(f"/api/projects/{self.slug}/dashboard/generate/")

    def test_generate_assigns_viz_ids(self):
        res = self._generate()
        self.assertEqual(res.status_code, 200, res.content)
        panels = res.json()["content"]["panels"]
        self.assertEqual([p["id"] for p in panels], ["VIZ-01"])
        log = AIRequestLog.objects.filter(operation="dashboard_blueprint_generation").latest("id")
        self.assertEqual(log.prompt_version, "dashboard_blueprint/v1")

    def test_generate_rejects_unapproved_metric_ref(self):
        res = self._generate(dashboard_draft("KPI-99"))
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "ai_invalid_output")

    def test_lifecycle_approve_and_edit_reverts_to_draft(self):
        self._generate()
        res = self.client.post(f"/api/projects/{self.slug}/dashboard/approve/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["approved"])

        res = self.client.patch(
            f"/api/projects/{self.slug}/dashboard/",
            {"content": {"refresh_cadence": "weekly"}}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(res.json()["approved"])

    def test_build_prompt_requires_approval(self):
        self._generate()
        res = self.client.post(f"/api/projects/{self.slug}/dashboard/build-prompt/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "invalid_workflow_state")

    def test_build_prompt_uses_approved_blueprint_no_fabrication(self):
        self._generate()
        self.client.post(f"/api/projects/{self.slug}/dashboard/approve/")

        fake = FakeProvider({"prompt_markdown": "# Dashboard Build Prompt\n\n" + "x" * 200})
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(f"/api/projects/{self.slug}/dashboard/build-prompt/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIsNotNone(res.json()["latest_build_prompt"])
        self.assertIn(self.metric.business_id, fake.last_user)
        # no raw rows in the context sent to the AI
        self.assertNotIn("a@example.com", fake.last_user)


# =====================================================================
# Lineage extension (Phase I-4)
# =====================================================================


class LineageExtensionTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_kpi_to_plan_to_result_to_insight_edges_resolve(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        plan_res = self.client.post(
            f"/api/projects/{project.slug}/analysis/plans/",
            descriptive_plan_payload(metric.business_id), format="json",
        )
        plan_id = plan_res.json()["id"]
        plan_business_id = plan_res.json()["business_id"]
        self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/approve/")
        run_res = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/")
        result_id = run_res.json()["id"]
        statement = run_res.json()["findings"][0]["statement"]

        fake = FakeProvider({"insights": [{
            "fact": statement, "interpretation": "ok", "confidence": "low",
            "supporting_finding_ids": ["F-01"], "caveats": [],
        }]})
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                f"/api/projects/{project.slug}/analysis/results/{result_id}/insights/generate/"
            )
        insight = Insight.objects.get(project=project)

        result = resolve_lineage(project, metric.business_id)
        self.assertIn(plan_business_id, result["downstream"])
        self.assertIn(result_id, result["downstream"])
        self.assertIn(insight.business_id, result["downstream"])

        result2 = resolve_lineage(project, insight.business_id)
        self.assertIn(metric.business_id, result2["upstream"])
        self.assertIn(plan_business_id, result2["upstream"])

    def test_kpi_to_dashboard_panel_edge_resolves(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        fake = FakeProvider(dashboard_draft(metric.business_id))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(f"/api/projects/{project.slug}/dashboard/generate/")
        project.refresh_from_db()  # dashboard_blueprint is a field on this row
        result = resolve_lineage(project, metric.business_id)
        self.assertIn("VIZ-01", result["downstream"])


# =====================================================================
# Context digest extensions
# =====================================================================


class ContextDigestTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_analysis_enters_digest_only_after_a_run_and_draft_insight_excluded(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        plan_res = self.client.post(
            f"/api/projects/{project.slug}/analysis/plans/",
            descriptive_plan_payload(metric.business_id), format="json",
        )
        plan_id = plan_res.json()["id"]

        project.refresh_from_db()
        self.assertNotIn("analyses", project.context_digest)

        self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/approve/")
        run_res = self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/")
        statement = run_res.json()["findings"][0]["statement"]

        fake = FakeProvider({"insights": [{
            "fact": statement, "interpretation": "ok", "confidence": "low",
            "supporting_finding_ids": ["F-01"], "caveats": [],
        }]})
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                f"/api/projects/{project.slug}/analysis/results/{run_res.json()['id']}/insights/generate/"
            )

        project.refresh_from_db()
        self.assertIn("analyses", project.context_digest)
        self.assertEqual(project.context_digest["analyses"][0]["id"], "AN-01")
        self.assertIn(statement, project.context_digest["analyses"][0]["latest_result_summary"]["headline_statements"])
        # draft insight must NOT be in the digest
        self.assertNotIn("accepted_insights", project.context_digest)

        insight = Insight.objects.get(project=project)
        self.client.post(f"/api/projects/{project.slug}/analysis/insights/{insight.id}/accept/")
        project.refresh_from_db()
        self.assertIn("accepted_insights", project.context_digest)
        self.assertEqual(project.context_digest["accepted_insights"][0]["id"], insight.business_id)

    def test_digest_never_contains_raw_rows_or_metric_values(self):
        import json

        project, dataset, metric = make_project_with_kpi(self.client)
        plan_res = self.client.post(
            f"/api/projects/{project.slug}/analysis/plans/",
            descriptive_plan_payload(metric.business_id), format="json",
        )
        plan_id = plan_res.json()["id"]
        self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/approve/")
        self.client.post(f"/api/projects/{project.slug}/analysis/plans/{plan_id}/run/")

        project.refresh_from_db()
        digest = project.context_digest
        # the analyses slice is exactly the bounded summary shape — no
        # metric_values/breakdown/evidence dump
        self.assertEqual(
            set(digest["analyses"][0]["latest_result_summary"].keys()),
            {"result_id", "created_at", "findings_count", "headline_statements"},
        )
        blob = json.dumps(digest)
        self.assertNotIn("a@example.com", blob)
        self.assertNotIn("metric_values", blob)
        self.assertNotIn("breakdown", blob)
        self.assertNotIn("evidence", blob)

    def test_dashboard_only_enters_digest_when_approved(self):
        project, dataset, metric = make_project_with_kpi(self.client)
        fake = FakeProvider(dashboard_draft(metric.business_id))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(f"/api/projects/{project.slug}/dashboard/generate/")
        project.refresh_from_db()
        self.assertNotIn("dashboard", project.context_digest)

        self.client.post(f"/api/projects/{project.slug}/dashboard/approve/")
        project.refresh_from_db()
        self.assertIn("dashboard", project.context_digest)
        self.assertEqual(project.context_digest["dashboard"]["panels"][0]["id"], "VIZ-01")


# =====================================================================
# Software isolation
# =====================================================================


class SoftwareIsolationTests(AuthenticatedAPITestCase):
    def test_analysis_dashboard_endpoints_reject_software_project(self):
        sw = Project.objects.create(original_idea="x", stage=ProjectStage.DISCOVERY, owner=default_owner())
        res = self.client.post(f"/api/projects/{sw.slug}/analysis/plans/generate/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "not_a_data_project")

        res = self.client.post(f"/api/projects/{sw.slug}/dashboard/generate/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "not_a_data_project")

    def test_software_project_serializer_unaffected(self):
        sw = Project.objects.create(original_idea="x", stage=ProjectStage.DISCOVERY, owner=default_owner())
        res = self.client.get(f"/api/projects/{sw.slug}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["dashboard_blueprint"], {})
        self.assertIsNone(body["dashboard_blueprint_approved_at"])
