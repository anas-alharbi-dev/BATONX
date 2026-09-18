"""
Phase I-1 verification — Data Project foundation.

Covers: project_type=data creation path, Project.data_goal, Data Brief lifecycle,
FileStore isolation, upload validation/security, deterministic profiling (no AI),
immutable profiling history, source interpretation, minimal data context digest,
synchronous Job lifecycle, and Software isolation.

The live data_brief_generation / source_interpretation round trips are PENDING an
ANTHROPIC_API_KEY; every AI-touching test uses a fake provider.
"""
import io
import json
import tempfile
import unittest.mock as mock
import uuid
from pathlib import Path

from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from tests.base import AuthenticatedAPITestCase, default_owner

from ai.models import AIRequestLog
from ai.providers.base import StructuredResult
from common.storage import LocalFileStore, build_dataset_key
from projects.context import build_context_digest
from projects.data.profiling import profile_bytes
from projects.models import (
    Dataset,
    Job,
    ProfilingRun,
    Project,
    ProjectStage,
)


# --- fakes / fixtures -----------------------------------------------------


class FakeProvider:
    name = "fake"

    def __init__(self, payload):
        self.payload = payload
        self.last_user = None
        self.last_system = None
        self.calls = 0

    def ensure_ready(self):
        pass

    def generate_structured(self, *, system, user, json_schema, timeout, prior_attempt=None):
        self.calls += 1
        self.last_user = user
        self.last_system = system
        return StructuredResult(
            data=self.payload, provider=self.name, model="fake-1",
            input_tokens=1, output_tokens=1,
        )


IDEA_ANALYSIS_PAYLOAD = {
    "domain": "retail analytics",
    "product_type_guess": "analysis",
    "known": ["a monthly sales export is available"],
    "unknowns": ["which KPIs matter most"],
    "assumptions": [],
}

DATA_BRIEF_PAYLOAD = {
    "business_goal": "Understand why revenue fell in Q4.",
    "decision_context": "The exec team decides where to focus next quarter.",
    "audience": ["Head of Sales"],
    "success_criteria": ["We can attribute the Q4 revenue change to segments."],
    "constraints": ["Only the uploaded sales export is available."],
    "candidate_sources": ["sales.csv"],
    "out_of_scope": ["Forecasting future revenue"],
}

INTERPRETATION_PAYLOAD = {
    "business_entity": "a sales order",
    "grain": "one row is one placed order",
    "key_columns": ["order_id"],
    "column_meanings": [
        {"column": "order_id", "meaning": "unique identifier for the order"},
        {"column": "amount", "meaning": "order total in USD"},
    ],
    "caveats": ["amount has some null values; order_id is not unique (duplicate rows)"],
    "sensitivity_flags": [{"column": "customer_email", "kind": "email", "note": ""}],
}

CSV_BYTES = (
    b"order_id,customer_email,amount,status,ordered_at\n"
    b"1,a@example.com,120.50,completed,2026-01-05\n"
    b"2,b@example.com,,completed,2026-01-06\n"
    b"3,c@example.com,80.00,refunded,2026-01-07\n"
    b"1,a@example.com,120.50,completed,2026-01-05\n"
)

JSON_BYTES = json.dumps(
    [
        {"id": 1, "name": "Ann", "score": 9.5},
        {"id": 2, "name": "Bo", "score": 7.0},
        {"id": 3, "name": "Cy", "score": 8.25},
    ]
).encode()

ZIP_BYTES = b"PK\x03\x04" + b"\x00" * 64


def data_project(**overrides) -> Project:
    data = {
        "original_idea": "Analyse our Q4 sales export to explain the revenue drop.",
        "project_type": "data",
        "data_goal": "analytics",
        "stage": ProjectStage.DATA_BRIEF,
        "owner": default_owner(),
        "context_digest": {"idea_analysis": IDEA_ANALYSIS_PAYLOAD},
    }
    data.update(overrides)
    return Project.objects.create(**data)


def data_project_with_brief(**overrides) -> Project:
    project = data_project(**overrides)
    from projects.data.brief import DataBriefContent, normalize_data_brief_content

    content = DataBriefContent.model_validate(
        normalize_data_brief_content({**DATA_BRIEF_PAYLOAD, "data_goal": "analytics"})
    ).model_dump(mode="json")
    project.data_brief = {
        "content": content,
        "generated_at": "2026-09-10T00:00:00+00:00",
        "updated_at": "2026-09-10T00:00:00+00:00",
        "approved_at": "2026-09-10T00:00:00+00:00",
    }
    from django.utils import timezone as dj_tz

    project.data_brief_approved_at = dj_tz.now()
    project.stage = ProjectStage.DATA_SOURCES
    project.save(update_fields=["data_brief", "data_brief_approved_at", "stage"])
    return project


def upload(client, project, content=CSV_BYTES, filename="sales.csv", ctype="text/csv"):
    return client.post(
        f"/api/projects/{project.slug}/datasets/",
        {"file": SimpleUploadedFile(filename, content, content_type=ctype)},
        format="multipart",
    )


def uploaded_dataset(client, project, **kw) -> Dataset:
    res = upload(client, project, **kw)
    assert res.status_code == 201, res.content
    return Dataset.objects.get(id=res.json()["id"])


# --- project creation / data_goal --------------------------------------


class ProjectCreationTests(AuthenticatedAPITestCase):
    def test_software_creation_unchanged_missing_key(self):
        res = self.client.post(
            "/api/projects/", {"idea": "A dentist scheduling app"}, format="json"
        )
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
        self.assertEqual(Project.objects.count(), 0)

    def test_software_project_rejects_data_goal(self):
        res = self.client.post(
            "/api/projects/",
            {"idea": "A todo app", "project_type": "software", "data_goal": "analytics"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_project_type")
        self.assertEqual(Project.objects.count(), 0)

    def test_invalid_project_type_rejected(self):
        res = self.client.post(
            "/api/projects/",
            {"idea": "Something", "project_type": "spreadsheet"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_project_type")

    def test_invalid_data_goal_rejected(self):
        fake = FakeProvider(IDEA_ANALYSIS_PAYLOAD)
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                "/api/projects/",
                {"idea": "Analyse sales", "project_type": "data", "data_goal": "wat"},
                format="json",
            )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_data_goal")
        self.assertEqual(Project.objects.count(), 0)

    def test_data_project_creation_enters_data_brief_stage(self):
        fake = FakeProvider(IDEA_ANALYSIS_PAYLOAD)
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                "/api/projects/",
                {"idea": "Analyse our Q4 sales export", "project_type": "data"},
                format="json",
            )
        self.assertEqual(res.status_code, 201)
        body = res.json()["project"]
        self.assertEqual(body["project_type"], "data")
        self.assertEqual(body["data_goal"], "analytics")  # default
        self.assertEqual(body["stage"], "data_brief")
        self.assertEqual(body["discovery"], {})  # software pipeline NOT reused
        self.assertEqual(fake.calls, 1)  # idea_analysis only

    def test_data_project_creation_missing_key_creates_nothing(self):
        res = self.client.post(
            "/api/projects/",
            {"idea": "Analyse sales", "project_type": "data", "data_goal": "bi"},
            format="json",
        )
        self.assertEqual(res.status_code, 502)
        self.assertEqual(Project.objects.count(), 0)


# --- Data Brief lifecycle -------------------------------------------


class DataBriefTests(AuthenticatedAPITestCase):
    def _url(self, project, suffix=""):
        return f"/api/projects/{project.slug}/data-brief/{suffix}"

    def test_generate_edit_approve(self):
        project = data_project()
        fake = FakeProvider(DATA_BRIEF_PAYLOAD)
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(self._url(project, "generate/"))
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["data_brief"]["content"]["business_goal"], DATA_BRIEF_PAYLOAD["business_goal"])
        self.assertIsNone(body["data_brief_approved_at"])

        res = self.client.patch(
            self._url(project),
            {"content": {"audience": ["Head of Sales", "Growth team"]}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json()["data_brief"]["content"]["audience"], ["Head of Sales", "Growth team"]
        )

        res = self.client.post(self._url(project, "approve/"))
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNotNone(body["data_brief_approved_at"])
        self.assertEqual(body["stage"], "data_sources")

    def test_generate_missing_key_502(self):
        project = data_project()
        res = self.client.post(self._url(project, "generate/"))
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
        project.refresh_from_db()
        self.assertEqual(project.data_brief, {})

    def test_generate_records_prompt_version(self):
        project = data_project()
        fake = FakeProvider(DATA_BRIEF_PAYLOAD)
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(self._url(project, "generate/"))
        log = AIRequestLog.objects.filter(operation="data_brief_generation").latest("id")
        self.assertEqual(log.prompt_version, "data_brief/v1")
        self.assertEqual(log.provider, "fake")

    def test_invalid_section_rejected(self):
        project = data_project()
        fake = FakeProvider(DATA_BRIEF_PAYLOAD)
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(self._url(project, "generate/"))
        res = self.client.patch(
            self._url(project), {"content": {"nonsense": 1}}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_data_brief")

    def test_software_project_cannot_use_data_brief(self):
        sw = Project.objects.create(original_idea="x", stage=ProjectStage.DISCOVERY, owner=default_owner())
        res = self.client.post(self._url(sw, "generate/"))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "not_a_data_project")


# --- FileStore isolation ------------------------------------------


class FileStoreTests(AuthenticatedAPITestCase):
    def test_rejects_traversal_and_absolute_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileStore(tmp)
            for bad in ("../escape", "a/../../b", "/etc/passwd", "a/./b", "..", "a//b"):
                with self.assertRaises(ValueError, msg=bad):
                    store.save(bad, io.BytesIO(b"x"))

    def test_save_open_roundtrip_confined_to_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileStore(tmp)
            key = build_dataset_key(uuid.uuid4(), uuid.uuid4(), "a" * 64, "csv")
            store.save(key, io.BytesIO(b"hello"))
            resolved = (Path(tmp) / key).resolve()
            self.assertTrue(str(resolved).startswith(str(Path(tmp).resolve())))
            with store.open(key) as fh:
                self.assertEqual(fh.read(), b"hello")

    def test_upload_storage_key_is_id_derived_not_filename_derived(self):
        """The storage key is built only from project id + dataset id + checksum;
        the user's filename never appears in it (and Django itself has already
        reduced the filename to a basename before we see it)."""
        import re

        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(DATA_STORAGE_ROOT=tmp):
                project = data_project_with_brief()
                ds = uploaded_dataset(
                    self.client, project, filename="../../etc/secret weird!.csv"
                )
                self.assertNotIn("secret", ds.storage_ref)
                self.assertNotIn("weird", ds.storage_ref)
                self.assertNotIn("..", ds.storage_ref)
                self.assertRegex(
                    ds.storage_ref,
                    r"^projects/[0-9a-f-]{36}/datasets/[0-9a-f-]{36}/[0-9a-f]{64}/data\.csv$",
                )
                resolved = (Path(tmp) / ds.storage_ref).resolve()
                self.assertTrue(str(resolved).startswith(str(Path(tmp).resolve())))
                self.assertTrue(resolved.is_file())
                # whatever basename Django kept is stored only as metadata
                self.assertTrue(re.search(r"\.csv$", ds.original_filename))


# --- upload validation / security --------------------------------


class UploadValidationTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()

    def tearDown(self):
        self.override.disable()

    def _url(self):
        return f"/api/projects/{self.project.slug}/datasets/"

    def test_upload_before_brief_approval_rejected(self):
        raw_project = data_project()  # brief not approved
        res = upload(self.client, raw_project)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "data_brief_not_approved")

    def test_csv_upload_succeeds(self):
        res = upload(self.client, self.project)
        self.assertEqual(res.status_code, 201)
        ds = Dataset.objects.get(id=res.json()["id"])
        self.assertEqual(ds.source_type, "csv")
        self.assertEqual(ds.status, "uploaded")
        self.assertEqual(ds.size_bytes, len(CSV_BYTES))
        self.assertEqual(len(ds.checksum), 64)

    def test_json_upload_succeeds(self):
        res = upload(self.client, self.project, JSON_BYTES, "people.json", "application/json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Dataset.objects.get(id=res.json()["id"]).source_type, "json")

    def test_size_limit_enforced(self):
        with override_settings(DATA_MAX_UPLOAD_BYTES=10):
            res = upload(self.client, self.project)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "file_too_large")
        self.assertEqual(Dataset.objects.count(), 0)

    def test_unsupported_extension_rejected(self):
        res = upload(self.client, self.project, b"a,b\n1,2\n", "data.tsv", "text/tab-separated-values")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "unsupported_source_type")

    def test_archive_rejected_by_content_not_extension(self):
        res = upload(self.client, self.project, ZIP_BYTES, "data.csv", "text/csv")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "unsupported_file_content")
        self.assertEqual(Dataset.objects.count(), 0)

    def test_binary_with_nul_bytes_rejected(self):
        res = upload(self.client, self.project, b"col\n\x00\x01\x02binary", "data.csv")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "unsupported_file_content")

    def test_malformed_csv_rejected(self):
        res = upload(self.client, self.project, b"\n\n\n", "empty.csv")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_csv")

    def test_invalid_json_rejected(self):
        res = upload(self.client, self.project, b"{not json", "bad.json", "application/json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_json")

    def test_json_not_array_rejected(self):
        res = upload(self.client, self.project, b'{"a": 1}', "obj.json", "application/json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_json")

    def test_raw_bytes_not_stored_in_postgres(self):
        ds = uploaded_dataset(self.client, self.project)
        # nothing on the row (or any related row) holds the file body
        blob = json.dumps(
            {
                "dataset": {
                    k: str(v)
                    for k, v in ds.__dict__.items()
                    if not k.startswith("_")
                }
            }
        )
        self.assertNotIn("a@example.com", blob)
        self.assertNotIn("refunded,2026", blob)
        # the bytes live in the FileStore, on disk, under the storage root
        resolved = (Path(self.tmp) / ds.storage_ref).resolve()
        self.assertTrue(resolved.is_file())
        self.assertEqual(resolved.read_bytes(), CSV_BYTES)


# --- profiling (deterministic, no AI) ----------------------------


class ProfilingTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()
        self.dataset = uploaded_dataset(self.client, self.project)

    def tearDown(self):
        self.override.disable()

    def _profile_url(self, ds=None):
        ds = ds or self.dataset
        return f"/api/projects/{self.project.slug}/datasets/{ds.id}/profile/"

    def test_profile_bytes_is_pure_and_deterministic(self):
        a = profile_bytes(CSV_BYTES, "csv")
        b = profile_bytes(CSV_BYTES, "csv")
        self.assertEqual(a, b)
        self.assertEqual(a["table_stats"]["row_count"], 4)
        self.assertEqual(a["table_stats"]["column_count"], 5)
        self.assertEqual(a["table_stats"]["duplicate_row_count"], 1)
        by_name = {c["name"]: c for c in a["columns"]}
        self.assertEqual(by_name["amount"]["dtype"], "float")
        self.assertEqual(by_name["amount"]["null_count"], 1)
        self.assertFalse(by_name["order_id"]["probable_key"])  # duplicate rows
        self.assertEqual(by_name["customer_email"]["sensitivity"], "pii_likely")
        # PII values are redacted in samples / top values
        self.assertTrue(all(v == "***" for v in by_name["customer_email"]["sample"]))

    def test_profile_endpoint_makes_no_ai_call(self):
        def boom(*a, **k):
            raise AssertionError("profiling must not touch the AI provider")

        with mock.patch("ai.base.get_provider", side_effect=boom):
            res = self.client.post(self._profile_url())
        self.assertEqual(res.status_code, 200)
        self.assertFalse(
            AIRequestLog.objects.filter(operation="").exists()
        )
        self.assertFalse(AIRequestLog.objects.exists())

    def test_profile_updates_dataset_headline_and_creates_run(self):
        res = self.client.post(self._profile_url())
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["dataset"]["status"], "profiled")
        self.assertEqual(body["dataset"]["row_count"], 4)
        self.assertEqual(body["dataset"]["column_count"], 5)
        self.assertIsNotNone(body["dataset"]["profiled_at"])
        self.assertEqual(body["job"]["status"], "succeeded")
        self.assertEqual(body["job"]["kind"], "profile_dataset")
        self.assertIn("profiling_run", body["job"]["result_ref"])
        self.assertEqual(ProfilingRun.objects.filter(dataset=self.dataset).count(), 1)

    def test_profiling_history_is_immutable(self):
        self.client.post(self._profile_url())
        first = ProfilingRun.objects.get(dataset=self.dataset)
        first_stats = dict(first.table_stats)
        self.client.post(self._profile_url())
        self.assertEqual(ProfilingRun.objects.filter(dataset=self.dataset).count(), 2)
        first.refresh_from_db()
        self.assertEqual(first.table_stats, first_stats)  # untouched
        self.assertEqual(Job.objects.filter(kind="profile_dataset").count(), 2)

    def test_job_failure_is_recorded(self):
        with mock.patch(
            "projects.data.services.profile_bytes", side_effect=RuntimeError("boom")
        ):
            res = self.client.post(self._profile_url())
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "profiling_failed")
        job = Job.objects.filter(kind="profile_dataset").latest("created_at")
        self.assertEqual(job.status, "failed")
        self.assertIn("boom", job.error)
        self.assertIsNotNone(job.finished_at)
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.status, "failed")
        self.assertIn("boom", self.dataset.error)

    def test_job_detail_endpoint_and_project_isolation(self):
        self.client.post(self._profile_url())
        job = Job.objects.latest("created_at")
        res = self.client.get(f"/api/projects/{self.project.slug}/jobs/{job.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "succeeded")
        other = data_project_with_brief()
        res = self.client.get(f"/api/projects/{other.slug}/jobs/{job.id}/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "job_not_found")

    def test_dataset_scoped_to_project(self):
        other = data_project_with_brief()
        res = self.client.get(
            f"/api/projects/{other.slug}/datasets/{self.dataset.id}/"
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "dataset_not_found")


# --- source interpretation --------------------------------------


class SourceInterpretationTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_STORAGE_ROOT=self.tmp)
        self.override.enable()
        self.project = data_project_with_brief()
        self.dataset = uploaded_dataset(self.client, self.project)

    def tearDown(self):
        self.override.disable()

    def _base(self):
        return f"/api/projects/{self.project.slug}/datasets/{self.dataset.id}"

    def _profile(self):
        self.client.post(f"{self._base()}/profile/")

    def test_cannot_interpret_before_profiling(self):
        res = self.client.post(f"{self._base()}/interpret/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "dataset_not_profiled")

    def test_interpretation_uses_stats_not_raw_rows(self):
        self._profile()
        fake = FakeProvider(INTERPRETATION_PAYLOAD)
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(f"{self._base()}/interpret/")
        self.assertEqual(res.status_code, 200)
        prompt = fake.last_user
        self.assertIn("COLUMN PROFILE", prompt)
        self.assertIn("nulls=", prompt)
        self.assertIn("distinct=", prompt)
        self.assertIn("probable_key=", prompt)
        # the raw file / whole rows are never handed to the model
        self.assertNotIn(CSV_BYTES.decode(), prompt)
        self.assertNotIn("1,a@example.com,120.50,completed,2026-01-05", prompt)
        # PII values are redacted even in the (bounded, <=5) sample
        self.assertNotIn("a@example.com", prompt)
        # each column's sample is capped
        for line in prompt.splitlines():
            if "sample=" in line:
                sample_part = line.split("sample=", 1)[1]
                self.assertLessEqual(len(sample_part.split(", ")), 5)

    def test_generate_edit_approve_and_context(self):
        self._profile()
        fake = FakeProvider(INTERPRETATION_PAYLOAD)
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(f"{self._base()}/interpret/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json()["interpretation"]["content"]["business_entity"], "a sales order"
        )
        self.assertIsNone(res.json()["interpretation_approved_at"])

        res = self.client.patch(
            f"{self._base()}/interpretation/",
            {"content": {"grain": "one row = one order line"}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)

        res = self.client.post(f"{self._base()}/interpret/approve/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(res.json()["interpretation_approved_at"])

        self.project.refresh_from_db()
        digest = self.project.context_digest
        self.assertIn("data_brief", digest)
        self.assertIn("data_sources", digest)
        src = digest["data_sources"][0]
        self.assertEqual(src["name"], "sales.csv")
        self.assertIn("interpretation", src)
        self.assertEqual(src["interpretation"]["business_entity"], "a sales order")
        # headline facts + column names/types only — never raw rows
        blob = json.dumps(digest)
        self.assertNotIn("a@example.com", blob)
        self.assertNotIn("120.50", blob)
        self.assertNotIn("refunded", blob)

    def test_interpretation_missing_key_502(self):
        self._profile()
        res = self.client.post(f"{self._base()}/interpret/")
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")


# --- data context + software isolation --------------------------


class ContextAndIsolationTests(AuthenticatedAPITestCase):
    def test_data_digest_only_when_approved(self):
        project = data_project()  # brief not approved
        digest = build_context_digest(project)
        self.assertNotIn("data_brief", digest)
        self.assertIn("idea_analysis", digest)

    def test_build_context_digest_dispatches_by_project_type(self):
        project = data_project_with_brief()
        digest = build_context_digest(project)
        self.assertIn("data_brief", digest)
        # no software keys leak into a data digest
        for k in ("blueprint", "architecture", "roadmap", "business_logic"):
            self.assertNotIn(k, digest)

    def test_software_project_serializer_and_digest_unchanged(self):
        sw = Project.objects.create(
            original_idea="A todo app",
            stage=ProjectStage.DISCOVERY,
            owner=default_owner(),
            discovery={"questions": [], "answers": {}, "generated_at": "x", "answered_at": None},
        )
        res = self.client.get(f"/api/projects/{sw.slug}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["project_type"], "software")
        self.assertEqual(body["data_goal"], "")
        self.assertEqual(body["data_brief"], {})
        self.assertIsNone(body["data_brief_approved_at"])
        # software digest builder still runs for software projects
        self.assertEqual(build_context_digest(sw), {})

    def test_conversation_still_works_for_software(self):
        sw = Project.objects.create(original_idea="A todo app", stage=ProjectStage.DISCOVERY, owner=default_owner())
        res = self.client.post(f"/api/projects/{sw.slug}/conversations/")
        self.assertEqual(res.status_code, 201)
        cid = res.json()["id"]
        res = self.client.get(f"/api/projects/{sw.slug}/conversations/{cid}/")
        self.assertEqual(res.status_code, 200)
