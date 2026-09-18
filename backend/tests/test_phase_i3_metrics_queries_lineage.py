"""
Phase I-3 verification — Metric/KPI, Query Workflow, and Data Lineage.

Generated SQL (AI sql_generation) is untrusted exactly like transformation
output in Phase I-2 and is re-validated through the same
``projects.data.execution.validate_select_only`` gate. The live
metric_definition_generation / sql_generation / sql_review round trips are
PENDING an ANTHROPIC_API_KEY; every AI-touching test uses a fake provider.
"""
import tempfile
import unittest.mock as mock

from django.test import override_settings
from tests.base import AuthenticatedAPITestCase, default_owner

from ai.models import AIRequestLog
from projects.data.lineage import resolve_lineage
from projects.data.metrics import MetricStructured, validate_references
from projects.data.sql_safe import quote_ident, sql_literal, view_name
from projects.models import (
    Job,
    MetricDefinition,
    MetricValidationRun,
    Project,
    ProjectStage,
    Query,
    QueryRun,
)
from tests.test_phase_i1_data_foundation import FakeProvider, data_project_with_brief
from tests.test_phase_i2_quality_transformation import profiled_dataset

# profiled_dataset() (from I-2) uploads this CSV as "orders.csv":
#   order_id,customer_email,amount,status,ordered_at
#   1,a@example.com,120.50,completed,2026-01-05
#   2,b@example.com,,completed,2026-01-06
#   3,c@example.com,-4.00,refunded,2026-01-07
#   1,a@example.com,120.50,completed,2026-01-05


def metric_draft(dataset_id, **overrides):
    payload = {
        "name": "Total Revenue",
        "business_meaning": "Total amount across all orders",
        "formula_text": "sum(amount)",
        "structured": {
            "aggregation": "sum",
            "base_table_ref": dataset_id,
            "measure": {"field": "amount"},
            "default_filters": [],
            "time_field": "ordered_at",
            "dimensions": ["status"],
        },
        "time_grain": "day",
        "allowed_dimensions": ["status"],
        "source_fields": ["amount"],
        "owner": "",
        "related_goal_ref": "",
        "caveats": [],
        "validation_checks": [],
    }
    payload.update(overrides)
    return {"metrics": [payload]}


def query_plan_payload(dataset_id, kpi_refs=None):
    return {
        "objective": "Total revenue per status",
        "required_kpi_refs": kpi_refs or [],
        "required_fields": ["amount", "status"],
        "base_table_ref": dataset_id,
        "grain": "one row per status",
        "dimensions": ["status"],
        "filters": [],
        "sort": ["status"],
        "expected_result_shape": "one row per status with a total",
        "assumptions": [],
    }


def sql_draft(view, kpi_refs=None):
    return {
        "sql": f'SELECT status, sum(amount) AS total FROM "{view}" GROUP BY status',
        "explanation": "Sums amount grouped by status.",
        "referenced_kpi_ids": kpi_refs or [],
        "referenced_fields": ["status", "amount"],
    }


def review_draft(recommendation="looks_good"):
    return {
        "alignment_notes": "Matches the plan's objective and grain.",
        "kpi_compliance_notes": "Implements the KPI formula faithfully.",
        "risks": [],
        "double_counting_risk": False,
        "null_handling_notes": "No nulls expected in status.",
        "performance_notes": "Trivial aggregate over a small table.",
        "scope_notes": "",
        "recommendation": recommendation,
    }


# =====================================================================
# sql_safe helpers (shared by metric validation + query execution)
# =====================================================================


class SqlSafeTests(AuthenticatedAPITestCase):
    def test_view_name_is_stable_and_identifier_safe(self):
        a = view_name("src", "abc-123-def")
        b = view_name("src", "abc-123-def")
        self.assertEqual(a, b)
        self.assertTrue(a.replace("_", "").isalnum())

    def test_quote_ident_rejects_unsafe_names(self):
        self.assertEqual(quote_ident("amount"), '"amount"')
        with self.assertRaises(Exception):
            quote_ident('amount" OR 1=1 --')

    def test_sql_literal_escapes_quotes_and_passes_numbers_through(self):
        self.assertEqual(sql_literal("O'Brien"), "'O''Brien'")
        self.assertEqual(sql_literal(5), "5")
        self.assertEqual(sql_literal(True), "TRUE")
        self.assertEqual(sql_literal(None), "NULL")


# =====================================================================
# Metric structured grammar (deterministic)
# =====================================================================


class MetricGrammarTests(AuthenticatedAPITestCase):
    def test_ratio_requires_numerator_and_denominator(self):
        with self.assertRaises(Exception):
            MetricStructured.model_validate(
                {"aggregation": "ratio", "base_table_ref": "d1", "measure": {"field": "x"}}
            )
        MetricStructured.model_validate(
            {
                "aggregation": "ratio",
                "base_table_ref": "d1",
                "numerator": {"field": "a"},
                "denominator": {"field": "b"},
            }
        )

    def test_non_count_non_ratio_requires_measure(self):
        with self.assertRaises(Exception):
            MetricStructured.model_validate({"aggregation": "sum", "base_table_ref": "d1"})

    def test_count_does_not_require_measure(self):
        MetricStructured.model_validate({"aggregation": "count", "base_table_ref": "d1"})

    def test_validate_references_rejects_unknown_table_and_field(self):
        s = MetricStructured.model_validate(
            {"aggregation": "sum", "base_table_ref": "d1", "measure": {"field": "amount"}}
        )
        with self.assertRaises(ValueError):
            validate_references(s, {"other": {"amount"}})
        with self.assertRaises(ValueError):
            validate_references(s, {"d1": {"other_field"}})
        validate_references(s, {"d1": {"amount"}})  # no error


# =====================================================================
# Metric generation / edit / approve / validate — via API
# =====================================================================


class MetricLifecycleTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()
        self.dataset = profiled_dataset(self.client, self.project)
        self.slug = self.project.slug

    def tearDown(self):
        self.override.disable()

    def _generate(self, payload=None):
        fake = FakeProvider(payload or metric_draft(str(self.dataset.id)))
        with mock.patch("ai.base.get_provider", return_value=fake):
            return self.client.post(f"/api/projects/{self.slug}/metrics/generate/")

    def test_generate_assigns_kpi_ids_and_records_prompt_version(self):
        res = self._generate()
        self.assertEqual(res.status_code, 200, res.content)
        metrics = res.json()
        self.assertEqual([m["business_id"] for m in metrics], ["KPI-01"])
        self.assertEqual(metrics[0]["status"], "draft")
        log = AIRequestLog.objects.filter(operation="metric_definition_generation").latest("id")
        self.assertEqual(log.prompt_version, "metric_definition/v1")

    def test_generate_requires_a_profiled_dataset(self):
        empty = data_project_with_brief()
        res = self._generate_for(empty)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "no_profiled_datasets")

    def _generate_for(self, project):
        fake = FakeProvider(metric_draft("nonexistent"))
        with mock.patch("ai.base.get_provider", return_value=fake):
            return self.client.post(f"/api/projects/{project.slug}/metrics/generate/")

    def test_metric_referencing_unknown_field_rejects_whole_batch(self):
        bad = metric_draft(str(self.dataset.id))
        bad["metrics"][0]["structured"]["measure"]["field"] = "not_a_real_column"
        res = self._generate(bad)
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "ai_invalid_output")
        self.assertEqual(MetricDefinition.objects.count(), 0)

    def test_metric_referencing_unknown_dataset_rejects_whole_batch(self):
        res = self._generate(metric_draft("not-a-real-dataset-id"))
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "ai_invalid_output")
        self.assertEqual(MetricDefinition.objects.count(), 0)

    def test_edit_reverts_approved_metric_to_draft(self):
        self._generate()
        metric_id = MetricDefinition.objects.get(project=self.project).id
        res = self.client.post(f"/api/projects/{self.slug}/metrics/{metric_id}/approve/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "approved")

        res = self.client.patch(
            f"/api/projects/{self.slug}/metrics/{metric_id}/",
            {"name": "Total Revenue (Updated)"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "draft")
        self.assertIsNone(res.json()["approved_at"])

    def test_edit_with_bad_reference_rejected(self):
        self._generate()
        metric_id = MetricDefinition.objects.get(project=self.project).id
        res = self.client.patch(
            f"/api/projects/{self.slug}/metrics/{metric_id}/",
            {"structured": {
                "aggregation": "sum", "base_table_ref": str(self.dataset.id),
                "measure": {"field": "not_a_column"},
            }},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_metric")

    def test_validate_metric_runs_real_duckdb_and_is_immutable_history(self):
        self._generate()
        metric_id = MetricDefinition.objects.get(project=self.project).id
        res = self.client.post(f"/api/projects/{self.slug}/metrics/{metric_id}/validate/")
        self.assertEqual(res.status_code, 200, res.content)
        latest = res.json()["latest_validation"]
        self.assertTrue(latest["passed"])
        # sum(amount) over 120.50 + null + (-4.00) + 120.50 = 237.00
        # (null is skipped by SQL sum, not coerced to 0)
        self.assertAlmostEqual(latest["result"]["value"], 237.00, places=2)
        self.assertEqual(latest["result"]["row_count"], 4)
        self.assertEqual(MetricValidationRun.objects.filter(metric_id=metric_id).count(), 1)

        self.client.post(f"/api/projects/{self.slug}/metrics/{metric_id}/validate/")
        self.assertEqual(MetricValidationRun.objects.filter(metric_id=metric_id).count(), 2)

    def test_validation_is_never_ai_decided(self):
        self._generate()
        metric_id = MetricDefinition.objects.get(project=self.project).id

        def boom(*a, **k):
            raise AssertionError("metric validation must not call the AI provider")

        with mock.patch("ai.base.get_provider", side_effect=boom):
            res = self.client.post(f"/api/projects/{self.slug}/metrics/{metric_id}/validate/")
        self.assertEqual(res.status_code, 200)


# =====================================================================
# Query workflow: plan -> approve -> generate SQL -> review -> execute
# =====================================================================


class QueryWorkflowTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()
        self.dataset = profiled_dataset(self.client, self.project)
        self.slug = self.project.slug

    def tearDown(self):
        self.override.disable()

    def _approved_kpi(self):
        fake = FakeProvider(metric_draft(str(self.dataset.id)))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(f"/api/projects/{self.slug}/metrics/generate/")
        metric = MetricDefinition.objects.get(project=self.project)
        self.client.post(f"/api/projects/{self.slug}/metrics/{metric.id}/approve/")
        return metric

    def _create_query(self, question="What is revenue per status?"):
        res = self.client.post(
            f"/api/projects/{self.slug}/queries/", {"question": question}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_create_assigns_q_id_and_starts_draft_plan(self):
        q = self._create_query()
        self.assertEqual(q["business_id"], "Q-01")
        self.assertEqual(q["status"], "draft_plan")
        self.assertEqual(q["plan"], {})

    def test_empty_question_rejected(self):
        res = self.client.post(f"/api/projects/{self.slug}/queries/", {"question": "  "}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "empty_question")

    def test_plan_rejects_nonexistent_base_table_ref(self):
        q = self._create_query()
        res = self.client.patch(
            f"/api/projects/{self.slug}/queries/{q['id']}/plan/",
            {"plan": query_plan_payload("not-a-dataset")},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_query_plan")

    def test_plan_rejects_joins(self):
        q = self._create_query()
        plan = query_plan_payload(str(self.dataset.id))
        plan["joins"] = [{"dataset": "x"}]
        res = self.client.patch(
            f"/api/projects/{self.slug}/queries/{q['id']}/plan/",
            {"plan": plan},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_query_plan")

    def test_plan_rejects_unapproved_kpi_ref(self):
        q = self._create_query()
        res = self.client.patch(
            f"/api/projects/{self.slug}/queries/{q['id']}/plan/",
            {"plan": query_plan_payload(str(self.dataset.id), kpi_refs=["KPI-01"])},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_query_plan")

    def test_full_workflow_to_execution(self):
        kpi = self._approved_kpi()
        q = self._create_query()
        qid = q["id"]

        res = self.client.patch(
            f"/api/projects/{self.slug}/queries/{qid}/plan/",
            {"plan": query_plan_payload(str(self.dataset.id), kpi_refs=[kpi.business_id])},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["status"], "draft_plan")

        res = self.client.post(f"/api/projects/{self.slug}/queries/{qid}/approve-plan/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "plan_approved")

        view = f"src_{str(self.dataset.id).replace('-', '')[:28]}"
        fake_sql = FakeProvider(sql_draft(view, kpi_refs=[kpi.business_id]))
        with mock.patch("ai.base.get_provider", return_value=fake_sql):
            res = self.client.post(f"/api/projects/{self.slug}/queries/{qid}/generate-sql/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["status"], "sql_generated")
        self.assertIn("SELECT", res.json()["sql"])

        fake_review = FakeProvider(review_draft())
        with mock.patch("ai.base.get_provider", return_value=fake_review):
            res = self.client.post(f"/api/projects/{self.slug}/queries/{qid}/review/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(res.json()["review"]["human_reviewed"])
        # AI review alone never advances status
        self.assertEqual(res.json()["status"], "sql_generated")

        res = self.client.post(f"/api/projects/{self.slug}/queries/{qid}/execute/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "query_not_reviewed")

        res = self.client.post(f"/api/projects/{self.slug}/queries/{qid}/mark-reviewed/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["review"]["human_reviewed"])
        self.assertEqual(res.json()["status"], "reviewed")

        def boom(*a, **k):
            raise AssertionError("query execution must not call the AI provider")

        with mock.patch("ai.base.get_provider", side_effect=boom):
            res = self.client.post(f"/api/projects/{self.slug}/queries/{qid}/execute/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["status"], "executed")
        run = res.json()["latest_run"]
        self.assertIn("status", run["columns"])
        self.assertEqual(QueryRun.objects.filter(query_id=qid).count(), 1)
        job = Job.objects.filter(kind="execute_query").latest("created_at")
        self.assertEqual(job.status, "succeeded")

        # re-execute from EXECUTED is allowed and creates a new immutable run
        res = self.client.post(f"/api/projects/{self.slug}/queries/{qid}/execute/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(QueryRun.objects.filter(query_id=qid).count(), 2)

    def test_editing_plan_after_sql_generated_reverts_to_draft_plan(self):
        kpi = self._approved_kpi()
        q = self._create_query()
        qid = q["id"]
        self.client.patch(
            f"/api/projects/{self.slug}/queries/{qid}/plan/",
            {"plan": query_plan_payload(str(self.dataset.id), kpi_refs=[kpi.business_id])},
            format="json",
        )
        self.client.post(f"/api/projects/{self.slug}/queries/{qid}/approve-plan/")
        view = f"src_{str(self.dataset.id).replace('-', '')[:28]}"
        fake_sql = FakeProvider(sql_draft(view, kpi_refs=[kpi.business_id]))
        with mock.patch("ai.base.get_provider", return_value=fake_sql):
            self.client.post(f"/api/projects/{self.slug}/queries/{qid}/generate-sql/")

        res = self.client.patch(
            f"/api/projects/{self.slug}/queries/{qid}/plan/",
            {"plan": {"objective": "A different question entirely"}},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["status"], "draft_plan")
        self.assertEqual(res.json()["sql"], "")
        self.assertEqual(res.json()["review"], {})

    def test_generate_sql_gated_on_plan_approved(self):
        q = self._create_query()
        res = self.client.post(f"/api/projects/{self.slug}/queries/{q['id']}/generate-sql/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "invalid_workflow_state")

    def test_unsafe_generated_sql_rejected_and_not_persisted(self):
        q = self._create_query()
        self.client.patch(
            f"/api/projects/{self.slug}/queries/{q['id']}/plan/",
            {"plan": query_plan_payload(str(self.dataset.id))},
            format="json",
        )
        self.client.post(f"/api/projects/{self.slug}/queries/{q['id']}/approve-plan/")
        unsafe = sql_draft("x")
        unsafe["sql"] = "SELECT * FROM read_csv('/etc/passwd')"
        fake_sql = FakeProvider(unsafe)
        with mock.patch("ai.base.get_provider", return_value=fake_sql):
            res = self.client.post(f"/api/projects/{self.slug}/queries/{q['id']}/generate-sql/")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "unsafe_generated_sql")
        q_obj = Query.objects.get(id=q["id"])
        self.assertEqual(q_obj.sql, "")
        self.assertEqual(q_obj.status, Query.Status.PLAN_APPROVED)

    def test_execute_re_validates_sql_defense_in_depth(self):
        q = self._create_query()
        self.client.patch(
            f"/api/projects/{self.slug}/queries/{q['id']}/plan/",
            {"plan": query_plan_payload(str(self.dataset.id))},
            format="json",
        )
        self.client.post(f"/api/projects/{self.slug}/queries/{q['id']}/approve-plan/")
        view = f"src_{str(self.dataset.id).replace('-', '')[:28]}"
        fake_sql = FakeProvider(sql_draft(view))
        with mock.patch("ai.base.get_provider", return_value=fake_sql):
            self.client.post(f"/api/projects/{self.slug}/queries/{q['id']}/generate-sql/")
        self.client.post(f"/api/projects/{self.slug}/queries/{q['id']}/mark-reviewed/")

        query_obj = Query.objects.get(id=q["id"])
        query_obj.sql = "SELECT * FROM read_csv('/etc/passwd')"
        query_obj.save(update_fields=["sql"])

        res = self.client.post(f"/api/projects/{self.slug}/queries/{q['id']}/execute/")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "query_execution_failed")
        job = Job.objects.filter(kind="execute_query").latest("created_at")
        self.assertEqual(job.status, "failed")


# =====================================================================
# Data Lineage (deterministic BFS over stored references)
# =====================================================================


class LineageTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()
        self.dataset = profiled_dataset(self.client, self.project)
        self.slug = self.project.slug

    def tearDown(self):
        self.override.disable()

    def test_unknown_node_returns_empty_without_error(self):
        result = resolve_lineage(self.project, "nope")
        self.assertFalse(result["exists"])
        self.assertEqual(result["upstream"], [])
        self.assertEqual(result["downstream"], [])

    def test_dataset_upstream_is_goal_and_downstream_includes_kpi_and_query(self):
        fake = FakeProvider(metric_draft(str(self.dataset.id)))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(f"/api/projects/{self.slug}/metrics/generate/")
        metric = MetricDefinition.objects.get(project=self.project)
        self.client.post(f"/api/projects/{self.slug}/metrics/{metric.id}/approve/")

        res = self.client.post(f"/api/projects/{self.slug}/queries/", {"question": "q"}, format="json")
        qid = res.json()["id"]
        self.client.patch(
            f"/api/projects/{self.slug}/queries/{qid}/plan/",
            {"plan": query_plan_payload(str(self.dataset.id), kpi_refs=[metric.business_id])},
            format="json",
        )

        result = resolve_lineage(self.project, str(self.dataset.id))
        self.assertIn("data_brief", result["upstream"])
        self.assertIn(metric.business_id, result["downstream"])
        # the query references the dataset via plan.base_table_ref
        q_business_id = Query.objects.get(id=qid).business_id
        self.assertIn(q_business_id, result["downstream"])

    def test_lineage_endpoint_returns_edges(self):
        res = self.client.get(
            f"/api/projects/{self.slug}/lineage/", {"node": str(self.dataset.id)}
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["exists"])
        self.assertIsInstance(body["edges"], list)


# =====================================================================
# Data context digest (approved-only, no raw values)
# =====================================================================


class DataContextTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()
        self.dataset = profiled_dataset(self.client, self.project)
        self.slug = self.project.slug

    def tearDown(self):
        self.override.disable()

    def test_unapproved_metric_and_unreviewed_query_absent_from_digest(self):
        fake = FakeProvider(metric_draft(str(self.dataset.id)))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(f"/api/projects/{self.slug}/metrics/generate/")
        self.client.post(f"/api/projects/{self.slug}/queries/", {"question": "q"}, format="json")

        self.project.refresh_from_db()
        digest = self.project.context_digest
        self.assertNotIn("metrics", digest)
        self.assertNotIn("queries", digest)

    def test_approved_metric_and_reviewed_query_enter_digest(self):
        fake = FakeProvider(metric_draft(str(self.dataset.id)))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(f"/api/projects/{self.slug}/metrics/generate/")
        metric = MetricDefinition.objects.get(project=self.project)
        self.client.post(f"/api/projects/{self.slug}/metrics/{metric.id}/approve/")

        q = self.client.post(
            f"/api/projects/{self.slug}/queries/", {"question": "Revenue?"}, format="json"
        ).json()
        self.client.patch(
            f"/api/projects/{self.slug}/queries/{q['id']}/plan/",
            {"plan": query_plan_payload(str(self.dataset.id), kpi_refs=[metric.business_id])},
            format="json",
        )
        self.client.post(f"/api/projects/{self.slug}/queries/{q['id']}/approve-plan/")
        view = f"src_{str(self.dataset.id).replace('-', '')[:28]}"
        fake_sql = FakeProvider(sql_draft(view, kpi_refs=[metric.business_id]))
        with mock.patch("ai.base.get_provider", return_value=fake_sql):
            self.client.post(f"/api/projects/{self.slug}/queries/{q['id']}/generate-sql/")
        self.client.post(f"/api/projects/{self.slug}/queries/{q['id']}/mark-reviewed/")

        self.project.refresh_from_db()
        digest = self.project.context_digest
        self.assertIn("metrics", digest)
        self.assertEqual(digest["metrics"][0]["id"], metric.business_id)
        self.assertIn("queries", digest)
        self.assertEqual(digest["queries"][0]["id"], "Q-01")
        self.assertEqual(digest["queries"][0]["status"], "reviewed")


# =====================================================================
# Software isolation
# =====================================================================


class SoftwareIsolationTests(AuthenticatedAPITestCase):
    def test_metrics_and_queries_endpoints_reject_software_project(self):
        sw = Project.objects.create(original_idea="x", stage=ProjectStage.DISCOVERY, owner=default_owner())
        res = self.client.post(f"/api/projects/{sw.slug}/metrics/generate/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "not_a_data_project")

        res = self.client.post(
            f"/api/projects/{sw.slug}/queries/", {"question": "x"}, format="json"
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "not_a_data_project")

    def test_lineage_endpoint_on_software_project(self):
        sw = Project.objects.create(original_idea="x", stage=ProjectStage.DISCOVERY, owner=default_owner())
        res = self.client.get(f"/api/projects/{sw.slug}/lineage/", {"node": "x"})
        # lineage is read-only over whatever the project has; a software
        # project simply has no data-project fields to walk.
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["exists"])
