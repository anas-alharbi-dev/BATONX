"""
Pre-I-4 targeted correctness fixes, verified in isolation before I-4 feature
work begins:

  1. context_digest freshness after query execution — queries[].status must
     read "executed", not remain stale at "reviewed".
  2. malformed UUID input to existing I-1/I-2 Data lookup paths must return
     the uniform 4xx envelope, never an uncaught 500.
"""
import tempfile
import unittest.mock as mock

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import override_settings
from tests.base import AuthenticatedAPITestCase

from projects.data.services import get_dataset, get_job
from projects.data.transformation_services import _source_dataset
from projects.exceptions import ProjectWorkflowError
from projects.models import MetricDefinition
from tests.test_phase_i1_data_foundation import FakeProvider, data_project_with_brief
from tests.test_phase_i2_quality_transformation import profiled_dataset
from tests.test_phase_i3_metrics_queries_lineage import (
    metric_draft,
    query_plan_payload,
    sql_draft,
)


# =====================================================================
# Fix 1: context_digest freshness after query execution
# =====================================================================


class QueryDigestFreshnessTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()
        self.dataset = profiled_dataset(self.client, self.project)
        self.slug = self.project.slug

    def tearDown(self):
        self.override.disable()

    def _reviewed_query(self):
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
        return q["id"]

    def test_digest_status_reflects_executed_after_execution(self):
        qid = self._reviewed_query()

        self.project.refresh_from_db()
        pre_status = self.project.context_digest["queries"][0]["status"]
        self.assertEqual(pre_status, "reviewed")

        res = self.client.post(f"/api/projects/{self.slug}/queries/{qid}/execute/")
        self.assertEqual(res.status_code, 200, res.content)

        self.project.refresh_from_db()
        post_status = self.project.context_digest["queries"][0]["status"]
        self.assertEqual(post_status, "executed")

    def test_digest_still_excludes_rows_sql_and_results_after_execution(self):
        qid = self._reviewed_query()
        self.client.post(f"/api/projects/{self.slug}/queries/{qid}/execute/")

        self.project.refresh_from_db()
        import json

        digest = self.project.context_digest
        # only the already-allowed concise query fields — never run payloads
        self.assertEqual(
            set(digest["queries"][0].keys()), {"id", "question", "kpi_refs", "status"}
        )
        blob = json.dumps(digest)
        self.assertNotIn("executed_sql", blob)
        # the query's own generated SQL text must not appear either
        self.assertNotIn("SELECT", blob)

    def test_re_execution_keeps_digest_status_executed(self):
        qid = self._reviewed_query()
        self.client.post(f"/api/projects/{self.slug}/queries/{qid}/execute/")
        self.client.post(f"/api/projects/{self.slug}/queries/{qid}/execute/")
        self.project.refresh_from_db()
        self.assertEqual(self.project.context_digest["queries"][0]["status"], "executed")


# =====================================================================
# Fix 2: malformed UUID input on existing I-1/I-2 Data lookup paths
# =====================================================================


class MalformedUuidTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()

    def tearDown(self):
        self.override.disable()

    def test_get_dataset_with_malformed_id_raises_controlled_404(self):
        with self.assertRaises(ProjectWorkflowError) as cm:
            get_dataset(self.project, "not-a-real-uuid")
        self.assertEqual(cm.exception.code, "dataset_not_found")
        self.assertEqual(cm.exception.status, 404)

    def test_get_job_with_malformed_id_raises_controlled_404(self):
        with self.assertRaises(ProjectWorkflowError) as cm:
            get_job(self.project, "not-a-real-uuid")
        self.assertEqual(cm.exception.code, "job_not_found")
        self.assertEqual(cm.exception.status, 404)

    def test_source_dataset_with_malformed_id_raises_controlled_400(self):
        with self.assertRaises(ProjectWorkflowError) as cm:
            _source_dataset(self.project, {"source_dataset_id": "not-a-real-uuid"})
        self.assertEqual(cm.exception.code, "invalid_transformation")
        self.assertEqual(cm.exception.status, 400)

    def test_malformed_id_never_raises_uncaught_django_validation_error(self):
        # the underlying failure mode this whole fix targets — confirm it is
        # actually intercepted, not just coincidentally absent
        for fn, arg in (
            (lambda: get_dataset(self.project, "!!!not-a-uuid!!!"), None),
            (lambda: get_job(self.project, "!!!not-a-uuid!!!"), None),
        ):
            try:
                fn()
            except ProjectWorkflowError:
                pass
            except DjangoValidationError:
                self.fail("DjangoValidationError leaked past the service boundary")

    def test_transformation_patch_with_malformed_source_dataset_id_is_4xx_not_500(self):
        dataset = profiled_dataset(self.client, self.project)
        fake = FakeProvider(
            {
                "source_dataset_id": str(dataset.id),
                "steps": [
                    {"op": "dedupe", "params": {}, "output_name": "deduped", "rationale": "dedupe"}
                ],
                "outputs": [{"name": "clean", "description": "", "grain": "one row per order"}],
            }
        )
        with mock.patch("ai.base.get_provider", return_value=fake):
            gen = self.client.post(f"/api/projects/{self.project.slug}/transformation/generate/")
        self.assertEqual(gen.status_code, 200, gen.content)

        res = self.client.patch(
            f"/api/projects/{self.project.slug}/transformation/",
            {"content": {"source_dataset_id": "not-a-real-uuid"}},
            format="json",
        )
        self.assertLess(res.status_code, 500)
        self.assertGreaterEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_transformation")
