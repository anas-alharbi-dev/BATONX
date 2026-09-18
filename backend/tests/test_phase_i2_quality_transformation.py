"""
Phase I-2 verification — Data Quality, Transformation Plan, DuckDB sandbox.

Generated SQL (BATONX's own renderer included) is treated as untrusted input.
The live quality_rule_proposal / transformation_proposal round trips are PENDING
an ANTHROPIC_API_KEY; every AI-touching test uses a fake provider.
"""
import json
import tempfile
import time
import unittest.mock as mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from tests.base import AuthenticatedAPITestCase, default_owner

from ai.models import AIRequestLog
from ai.providers.base import StructuredResult
from common.storage import local_path
from projects.data.execution import (
    DuckDBExecution,
    QueryExecutionError,
    SqlValidationError,
    validate_select_only,
)
from projects.data.quality import derive_observations, normalize_data_quality_content
from projects.data.sql_render import UnsupportedOperationError, render_plan_sql
from projects.data.transformation import normalize_transformation_plan_content
from projects.models import Dataset, Job, ProfilingRun, Project, ProjectStage, QualityCheckRun
from tests.test_phase_i1_data_foundation import (
    FakeProvider,
    data_project_with_brief,
    uploaded_dataset,
)

CSV = (
    b"order_id,customer_email,amount,status,ordered_at\n"
    b"1,a@example.com,120.50,completed,2026-01-05\n"
    b"2,b@example.com,,completed,2026-01-06\n"
    b"3,c@example.com,-4.00,refunded,2026-01-07\n"
    b"1,a@example.com,120.50,completed,2026-01-05\n"
)


def profiled_dataset(client, project) -> Dataset:
    ds = uploaded_dataset(client, project, content=CSV, filename="orders.csv")
    res = client.post(
        f"/api/projects/{project.slug}/datasets/{ds.id}/profile/"
    )
    assert res.status_code == 200, res.content
    ds.refresh_from_db()
    return ds


def quality_rules_payload(dataset_id, rules=None):
    return {
        "rules": rules
        if rules is not None
        else [
            {
                "dataset_ref": dataset_id,
                "column": "amount",
                "dimension": "completeness",
                "assertion": "not_null",
                "params": {},
                "rationale": "amount is required for revenue analysis",
                "related_observations": ["DQ-02"],
            },
            {
                "dataset_ref": dataset_id,
                "column": "status",
                "dimension": "validity",
                "assertion": "in_set",
                "params": {"values": ["completed", "refunded", "cancelled"]},
                "rationale": "status is an enum",
                "related_observations": [],
            },
        ]
    }


def transformation_payload(dataset_id):
    return {
        "source_dataset_id": dataset_id,
        "steps": [
            {
                "op": "filter_rows",
                "params": {"column": "amount", "operator": "is_not_null"},
                "output_name": "with_amount",
                "rationale": "drop rows missing amount",
                "related_quality_rules": ["QR-01"],
            },
            {
                "op": "dedupe",
                "params": {},
                "output_name": "deduped",
                "rationale": "remove duplicate order rows",
            },
            {
                "op": "cast",
                "params": {"column": "amount", "to_type": "double"},
                "output_name": "typed",
                "rationale": "amount as number",
            },
        ],
        "outputs": [
            {"name": "clean_orders", "description": "cleaned orders", "grain": "one row per order"}
        ],
    }


# =====================================================================
# SQL validation (BATONX-enforced) — no DB / no DuckDB execution
# =====================================================================


class SqlValidationTests(AuthenticatedAPITestCase):
    def test_plain_select_and_with_allowed(self):
        validate_select_only("SELECT 1")
        validate_select_only("WITH a AS (SELECT 1) SELECT * FROM a")
        validate_select_only("  \n  select * from \"src_x\" where a > 1  ")

    def test_rejects_exact_code(self):
        cases = {
            "multiple_statements": ["SELECT 1; SELECT 2", "SELECT 1;SELECT 2;"],
            "non_select_statement": [
                "CREATE TABLE t(a int)",
                "PRAGMA version",
                "pragma database_list",
                "EXPLAIN SELECT 1",
                "DELETE FROM t",
                "UPDATE t SET a = 1",
            ],
            "forbidden_function": [
                "SELECT * FROM read_csv('x')",
                "SELECT * FROM read_csv_auto('x.csv')",
                "SELECT * FROM read_parquet('x.pq')",
                "SELECT * FROM glob('/etc/*')",
                "SELECT * FROM READ_JSON ('x')",
            ],
            "forbidden_reference": [
                "SELECT * FROM 'https://evil.com/x.csv'",
                "SELECT '/etc/passwd'",
                "SELECT * FROM \"src\" WHERE path = '../secret'",
                "select 's3://bucket/key'",
            ],
        }
        for code, sqls in cases.items():
            for sql in sqls:
                with self.assertRaises(SqlValidationError, msg=sql) as cm:
                    validate_select_only(sql)
                self.assertEqual(cm.exception.code, code, sql)

    def test_rejects_bypass_attempts_any_code(self):
        blocked = {
            "multiple_statements",
            "non_select_statement",
            "forbidden_keyword",
            "forbidden_function",
            "forbidden_reference",
            "invalid_sql",
        }
        for sql in [
            "SELECT 1 /* x */ ; drop table t",
            "select * from t; insert into t values (1)",
            "SELECT 1 UNION SELECT 1; ATTACH 'x.db' AS y",
            "select 1 where 1=1 -- \n; set threads=1",
            "SeLeCt 1;\n\n\tDrOp TaBlE t",
            "/* multi\nline */ INSERT INTO t VALUES (1)",
            "SELECT case when 1=1 then (copy foo to 'x') end",
            "SELECT (SELECT 1 FROM (attach 'x' as y))",
            "WITH x AS (SELECT 1) SELECT * FROM x; PRAGMA version",
        ]:
            with self.assertRaises(SqlValidationError, msg=sql) as cm:
                validate_select_only(sql)
            self.assertIn(cm.exception.code, blocked, sql)

    def test_comment_and_case_and_whitespace_bypass_blocked(self):
        for sql in [
            "SeLeCt 1;\n\n\tDrOp TaBlE t",
            "SELECT 1 --harmless\n; PRAGMA version",
            "/* multi\nline */ INSERT INTO t VALUES (1)",
            "select /*x*/ 1 /*y*/ ; /*z*/ set threads = 1",
        ]:
            with self.assertRaises(SqlValidationError, msg=sql):
                validate_select_only(sql)

    def test_quoted_semicolon_not_a_second_statement(self):
        validate_select_only("SELECT ';' AS a, 'a;b' AS b")


# =====================================================================
# DuckDB hardening (verified against installed version) — real execution
# =====================================================================


class DuckDBSandboxTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = f"{self.tmp}/data.csv"
        open(self.f, "w").write("a,b\n1,x\n2,y\n3,z\n")
        self.ds = [("src_t", self.f, "csv")]
        self.ex = DuckDBExecution()

    def _run(self, sql, **kw):
        return self.ex.run_select(sql, datasets=self.ds, **kw)

    def test_select_over_registered_view_works(self):
        res = self._run('SELECT count(*) AS n FROM "src_t"')
        self.assertEqual(res["rows"][0][0], 3)

    def test_external_access_disabled_blocks_file_read(self):
        with self.assertRaises((QueryExecutionError, SqlValidationError)):
            self._run(f"SELECT * FROM read_csv('{self.f}')")

    def test_install_and_load_blocked(self):
        for sql in ["INSTALL httpfs", "LOAD httpfs"]:
            with self.assertRaises(SqlValidationError):
                validate_select_only(sql)

    def test_set_and_pragma_and_ddl_blocked_by_validator(self):
        for sql in [
            "SET enable_external_access=true",
            "PRAGMA database_list",
            "ATTACH ':memory:' AS x",
            "COPY (SELECT 1) TO '/tmp/o.csv'",
            "CREATE TABLE evil AS SELECT 1",
            "CALL pragma_version()",
        ]:
            with self.assertRaises(SqlValidationError):
                validate_select_only(sql)

    def test_only_registered_views_exist(self):
        with self.assertRaises(QueryExecutionError):
            self._run('SELECT * FROM "some_other_table"')

    def test_result_row_cap(self):
        res = self._run(
            'SELECT * FROM range(1000) t("n")', max_rows=10
        )
        self.assertEqual(res["row_count"], 10)
        self.assertTrue(res["truncated"])

    def test_timeout_terminates_runaway_query(self):
        started = time.monotonic()
        with override_settings(DATA_QUERY_TIMEOUT_SECONDS=1.5):
            ex = DuckDBExecution()
            with self.assertRaises(QueryExecutionError) as cm:
                ex.run_select(
                    "SELECT count(*) FROM range(100000000000) a, range(1000000) b",
                    datasets=self.ds,
                )
        self.assertEqual(cm.exception.code, "query_timeout")
        self.assertLess(time.monotonic() - started, 8)  # actually stopped

    def test_limits_are_configured(self):
        ex = DuckDBExecution()
        self.assertEqual(ex.limits["memory_limit"], "256MB")
        self.assertEqual(ex.limits["threads"], 2)
        self.assertEqual(ex.limits["max_temp_size"], "512MB")


# =====================================================================
# Data Quality observations (deterministic, no AI)
# =====================================================================


class QualityObservationTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()
        self.dataset = profiled_dataset(self.client, self.project)

    def tearDown(self):
        self.override.disable()

    def test_derive_observations_is_deterministic_and_evidence_backed(self):
        run = self.dataset.profiling_runs.first()
        pr = {"table_stats": run.table_stats, "columns": run.columns}
        a = derive_observations("ds", pr)
        b = derive_observations("ds", pr)
        self.assertEqual(a, b)
        ids = [o["id"] for o in a]
        self.assertEqual(ids, sorted(ids))
        self.assertTrue(all(o["id"].startswith("DQ-") for o in a))
        kinds = {(o["dimension"], o.get("column")) for o in a}
        self.assertIn(("duplicates", ""), kinds)  # duplicate_row_count == 1
        self.assertIn(("completeness", "amount"), kinds)  # amount has a null
        for o in a:
            self.assertTrue(o["evidence"])  # every observation cites profiling facts

    def test_observe_endpoint_makes_no_ai_call(self):
        def boom(*a, **k):
            raise AssertionError("observations must not call the AI provider")

        with mock.patch("ai.base.get_provider", side_effect=boom):
            res = self.client.post(
                f"/api/projects/{self.project.slug}/data-quality/observe/"
            )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(AIRequestLog.objects.exists())
        body = res.json()
        self.assertGreater(len(body["content"]["observations"]), 0)
        self.assertEqual(body["content"]["rules"], [])
        self.assertFalse(body["approved"])

    def test_observe_requires_a_profiled_dataset(self):
        empty = data_project_with_brief()
        res = self.client.post(
            f"/api/projects/{empty.slug}/data-quality/observe/"
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "no_profiled_datasets")


# =====================================================================
# Data Quality rules (AI-proposed, approved) + checks (deterministic)
# =====================================================================


class QualityRuleAndCheckTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()
        self.dataset = profiled_dataset(self.client, self.project)
        self.slug = self.project.slug
        self.client.post(f"/api/projects/{self.slug}/data-quality/observe/")

    def tearDown(self):
        self.override.disable()

    def _propose(self, rules=None):
        fake = FakeProvider(quality_rules_payload(str(self.dataset.id), rules))
        with mock.patch("ai.base.get_provider", return_value=fake):
            return self.client.post(
                f"/api/projects/{self.slug}/data-quality/propose-rules/"
            )

    def test_rules_are_ai_proposed_with_deterministic_ids(self):
        res = self._propose()
        self.assertEqual(res.status_code, 200)
        rules = res.json()["content"]["rules"]
        self.assertEqual([r["id"] for r in rules], ["QR-01", "QR-02"])
        self.assertTrue(all(r["status"] == "draft" for r in rules))
        log = AIRequestLog.objects.filter(operation="quality_rule_proposal").latest("id")
        self.assertEqual(log.prompt_version, "quality_rules/v1")

    def test_propose_requires_observations(self):
        p2 = data_project_with_brief()
        profiled_dataset(self.client, p2)
        fake = FakeProvider(quality_rules_payload("x"))
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                f"/api/projects/{p2.slug}/data-quality/propose-rules/"
            )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "no_observations")

    def test_rule_targeting_foreign_dataset_rejected(self):
        other = data_project_with_brief()
        other_ds = profiled_dataset(self.client, other)
        res = self._propose(
            rules=[
                {
                    "dataset_ref": str(other_ds.id),
                    "column": "amount",
                    "dimension": "completeness",
                    "assertion": "not_null",
                    "params": {},
                }
            ]
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_quality_rule")

    def test_invalid_rule_params_rejected_on_edit(self):
        self._propose()
        res = self.client.patch(
            f"/api/projects/{self.slug}/data-quality/",
            {
                "content": {
                    "rules": [
                        {
                            "dataset_ref": str(self.dataset.id),
                            "column": "status",
                            "dimension": "validity",
                            "assertion": "in_set",
                            "params": {},  # missing values
                        }
                    ]
                }
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_data_quality")

    def test_check_requires_approval(self):
        self._propose()
        res = self.client.post(f"/api/projects/{self.slug}/data-quality/check/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "quality_rules_not_approved")

    def test_full_lifecycle_check_uses_real_data_no_ai_decision(self):
        self._propose()
        res = self.client.post(f"/api/projects/{self.slug}/data-quality/approve/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["approved"])

        def boom(*a, **k):
            raise AssertionError("quality checks must not call the AI provider")

        with mock.patch("ai.base.get_provider", side_effect=boom):
            res = self.client.post(f"/api/projects/{self.slug}/data-quality/check/")
        self.assertEqual(res.status_code, 200)
        run = res.json()["latest_check_run"]
        by_rule = {r["rule_id"]: r for r in run["results"]}
        # amount has 1 null -> not_null fails with failing_row_count == 1
        self.assertFalse(by_rule["QR-01"]["passed"])
        self.assertEqual(by_rule["QR-01"]["failing_row_count"], 1)
        # status only has completed/refunded -> in_set passes
        self.assertTrue(by_rule["QR-02"]["passed"])
        self.assertEqual(by_rule["QR-02"]["failing_row_count"], 0)
        self.assertEqual(run["summary"]["total"], 2)
        self.assertEqual(run["summary"]["failed"], 1)
        self.assertEqual(QualityCheckRun.objects.filter(project=self.project).count(), 1)
        job = Job.objects.filter(kind="run_quality_checks").latest("created_at")
        self.assertEqual(job.status, "succeeded")

    def test_failure_samples_are_capped_and_pii_redacted(self):
        # a rule that fails on many rows against a PII column
        rules = [
            {
                "dataset_ref": str(self.dataset.id),
                "column": "customer_email",
                "dimension": "validity",
                "assertion": "regex",
                "params": {"pattern": "^NOPE$"},  # nothing matches -> all rows fail
            }
        ]
        self._propose(rules=rules)
        self.client.post(f"/api/projects/{self.slug}/data-quality/approve/")
        with override_settings(DATA_QUERY_MAX_FAILURE_SAMPLES=2):
            res = self.client.post(f"/api/projects/{self.slug}/data-quality/check/")
        result = res.json()["latest_check_run"]["results"][0]
        self.assertFalse(result["passed"])
        self.assertEqual(result["failing_row_count"], 4)
        self.assertLessEqual(len(result["sample_failures"]), 2)
        for row in result["sample_failures"]:
            self.assertEqual(row["customer_email"], "***")  # PII redacted

    def test_check_run_history_is_immutable(self):
        self._propose()
        self.client.post(f"/api/projects/{self.slug}/data-quality/approve/")
        self.client.post(f"/api/projects/{self.slug}/data-quality/check/")
        first = QualityCheckRun.objects.get(project=self.project)
        summary = dict(first.summary)
        self.client.post(f"/api/projects/{self.slug}/data-quality/check/")
        first.refresh_from_db()
        self.assertEqual(first.summary, summary)
        self.assertEqual(QualityCheckRun.objects.filter(project=self.project).count(), 2)


# =====================================================================
# Transformation Plan + renderer + preview
# =====================================================================


class TransformationTests(AuthenticatedAPITestCase):
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
        fake = FakeProvider(payload or transformation_payload(str(self.dataset.id)))
        with mock.patch("ai.base.get_provider", return_value=fake):
            return self.client.post(
                f"/api/projects/{self.slug}/transformation/generate/"
            )

    def test_generate_assigns_tx_ids_and_records_prompt_version(self):
        res = self._generate()
        self.assertEqual(res.status_code, 200)
        steps = res.json()["content"]["steps"]
        self.assertEqual([s["id"] for s in steps], ["TX-01", "TX-02", "TX-03"])
        self.assertEqual(steps[0]["related_quality_rules"], ["QR-01"])
        log = AIRequestLog.objects.filter(operation="transformation_proposal").latest("id")
        self.assertEqual(log.prompt_version, "transformation_plan/v1")
        self.assertIn("WITH", res.json()["rendered_sql"])

    def test_renderer_is_deterministic(self):
        content = normalize_transformation_plan_content(
            transformation_payload(str(self.dataset.id))
        )
        a = render_plan_sql(content, source_view="src_x")
        b = render_plan_sql(content, source_view="src_x")
        self.assertEqual(a, b)
        validate_select_only(a)  # renderer output passes the untrusted-SQL gate

    def test_unknown_op_rejected_by_schema(self):
        res = self._generate(
            {
                "source_dataset_id": str(self.dataset.id),
                "steps": [
                    {"op": "join", "params": {}, "output_name": "j"}
                ],
            }
        )
        self.assertEqual(res.status_code, 502)  # AI produced an invalid plan
        self.assertEqual(res.json()["error"]["code"], "ai_invalid_output")

    def test_unsupported_render_fails_safely(self):
        self._generate()
        res = self.client.patch(
            f"/api/projects/{self.slug}/transformation/",
            {
                "content": {
                    "source_dataset_id": str(self.dataset.id),
                    "steps": [
                        {
                            "op": "derive_column",
                            "params": {
                                "name": "x",
                                "expression": "evil_udf(customer_email)",
                            },
                            "output_name": "d",
                        }
                    ],
                }
            },
            format="json",
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "unsupported_operation")

    def test_edit_reverts_to_draft_and_approve(self):
        self._generate()
        self.client.post(f"/api/projects/{self.slug}/transformation/approve/")
        self.project.refresh_from_db()
        self.assertIsNotNone(self.project.transformation_plan_approved_at)

        res = self.client.patch(
            f"/api/projects/{self.slug}/transformation/",
            {"content": {"outputs": [{"name": "renamed", "grain": "order"}]}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["approved"])
        self.project.refresh_from_db()
        self.assertIsNone(self.project.transformation_plan_approved_at)

    def test_preview_runs_locally_and_does_not_mutate_source(self):
        self._generate()
        before = self.dataset.profiling_runs.first().table_stats
        res = self.client.post(f"/api/projects/{self.slug}/transformation/preview/")
        self.assertEqual(res.status_code, 200, res.content)
        preview = res.json()["preview"]
        # filter(is_not_null amount) + dedupe on 4 rows (1 null, 1 dup) -> 2 rows
        self.assertEqual(preview["row_count"], 2)
        self.assertIn("amount", preview["columns"])
        job = Job.objects.filter(kind="run_transformation_preview").latest("created_at")
        self.assertEqual(job.status, "succeeded")
        # source dataset + its profiling run are untouched
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.status, "profiled")
        self.assertEqual(self.dataset.profiling_runs.first().table_stats, before)
        self.assertEqual(ProfilingRun.objects.filter(dataset=self.dataset).count(), 1)

    def test_preview_treats_rendered_sql_through_the_untrusted_gate(self):
        self._generate()
        with mock.patch(
            "projects.data.transformation_services.render_plan_sql",
            return_value="SELECT * FROM read_csv('/etc/passwd')",
        ):
            res = self.client.post(
                f"/api/projects/{self.slug}/transformation/preview/"
            )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "preview_failed")
        job = Job.objects.filter(kind="run_transformation_preview").latest("created_at")
        self.assertEqual(job.status, "failed")


# =====================================================================
# Data context + traceability
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

    def test_approved_quality_and_transformation_enter_digest_without_raw_rows(self):
        self.client.post(f"/api/projects/{self.slug}/data-quality/observe/")
        fake = FakeProvider(quality_rules_payload(str(self.dataset.id)))
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(f"/api/projects/{self.slug}/data-quality/propose-rules/")
        self.client.post(f"/api/projects/{self.slug}/data-quality/approve/")

        fake2 = FakeProvider(transformation_payload(str(self.dataset.id)))
        with mock.patch("ai.base.get_provider", return_value=fake2):
            self.client.post(f"/api/projects/{self.slug}/transformation/generate/")
        self.client.post(f"/api/projects/{self.slug}/transformation/approve/")

        self.project.refresh_from_db()
        digest = self.project.context_digest
        self.assertIn("data_quality", digest)
        self.assertEqual(
            [r["id"] for r in digest["data_quality"]["rules"]], ["QR-01", "QR-02"]
        )
        self.assertIn("data_quality", digest)
        self.assertIn("transformation_plan", digest)
        self.assertEqual(
            digest["transformation_plan"]["steps"][0]["related_quality_rules"], ["QR-01"]
        )
        blob = json.dumps(digest)
        # no raw row values / PII / failure samples — rule *params* (e.g. an
        # allowed-value set) are decisions and may legitimately appear.
        self.assertNotIn("a@example.com", blob)
        self.assertNotIn("120.50", blob)
        self.assertNotIn("2026-01-05", blob)
        self.assertNotIn("sample_failures", blob)

    def test_unapproved_quality_not_in_digest(self):
        self.client.post(f"/api/projects/{self.slug}/data-quality/observe/")
        self.project.refresh_from_db()
        self.assertNotIn("data_quality", self.project.context_digest)


# =====================================================================
# Software isolation
# =====================================================================


class SoftwareIsolationTests(AuthenticatedAPITestCase):
    def test_software_serializer_still_shaped_and_digest_unchanged(self):
        sw = Project.objects.create(
            original_idea="A todo app",
            stage=ProjectStage.DISCOVERY,
            owner=default_owner(),
            discovery={"questions": [], "answers": {}, "generated_at": "x", "answered_at": None},
        )
        res = self.client.get(f"/api/projects/{sw.slug}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["data_quality"], {})
        self.assertEqual(body["transformation_plan"], {})
        self.assertIsNone(body["data_quality_approved_at"])
        from projects.context import build_context_digest

        self.assertEqual(build_context_digest(sw), {})

    def test_data_quality_endpoint_rejects_software_project(self):
        sw = Project.objects.create(original_idea="x", stage=ProjectStage.DISCOVERY, owner=default_owner())
        res = self.client.post(f"/api/projects/{sw.slug}/data-quality/observe/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "not_a_data_project")
