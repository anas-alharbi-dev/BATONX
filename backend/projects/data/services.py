"""
Data & Analytics domain services (Phase I-1).

Covers: Data Brief lifecycle, dataset upload (untrusted input → FileStore),
deterministic profiling (synchronous Job), and source interpretation.

No provider-specific code — AI operations go through ``ai.base.run_operation``.
Raw dataset bytes never touch PostgreSQL.
"""
from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import datetime, timezone

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone as dj_timezone
from pydantic import ValidationError

from ai.base import run_operation
from ai.exceptions import AIOperationError
from ai.operations.data_brief_generation import DATA_BRIEF_GENERATION
from ai.operations.source_interpretation import SOURCE_INTERPRETATION
from common.storage import build_dataset_key, get_file_store
from projects.context import build_context_digest
from projects.data.brief import (
    SECTION_FIELDS as BRIEF_SECTIONS,
    DataBriefContent,
    normalize_data_brief_content,
)
from projects.data.profiling import inferred_schema_from_columns, profile_bytes
from projects.data.sources import (
    SECTION_FIELDS as INTERP_SECTIONS,
    SourceInterpretationContent,
    normalize_source_interpretation_content,
)
from projects.data.stale import (
    clear_dataset_interpretation_stale,
    project_level_changed,
    propagate_brief_change,
    propagate_dataset_change,
)
from projects.exceptions import ProjectWorkflowError
from projects.models import Dataset, Job, ProfilingRun, Project, ProjectStage

_DATA_BRIEF_EDITABLE_STAGES = (ProjectStage.DATA_BRIEF, ProjectStage.DATA_SOURCES)

# Reject obvious non-text / container formats regardless of extension or
# Content-Type. (prefix bytes, label)
_MAGIC_REJECT = [
    (b"PK\x03\x04", "zip archive"),
    (b"PK\x05\x06", "zip archive"),
    (b"\x1f\x8b", "gzip archive"),
    (b"BZh", "bzip2 archive"),
    (b"\xfd7zXZ\x00", "xz archive"),
    (b"Rar!\x1a\x07", "rar archive"),
    (b"7z\xbc\xaf\x27\x1c", "7z archive"),
    (b"%PDF", "PDF"),
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF8", "GIF image"),
    (b"\x7fELF", "ELF executable"),
    (b"MZ", "Windows executable"),
    (b"\xca\xfe\xba\xbe", "Mach-O binary"),
    (b"\xcf\xfa\xed\xfe", "Mach-O binary"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "legacy Office / OLE"),
]

_EXT_TO_TYPE = {"csv": Dataset.SourceType.CSV, "json": Dataset.SourceType.JSON}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pydantic_details(error: ValidationError) -> list[dict]:
    return [
        {"loc": ".".join(str(p) for p in item["loc"]), "msg": item["msg"]}
        for item in error.errors()
    ]


def _require_data_project(project: Project) -> None:
    if project.project_type != "data":
        raise ProjectWorkflowError(
            "not_a_data_project",
            "This endpoint is only available for Data projects.",
            status=409,
        )


_BUSINESS_ID_RE_CACHE: dict[str, "re.Pattern"] = {}


def next_business_id(project: Project, model, prefix: str) -> str:
    """
    Deterministic ``<PREFIX>-NN`` id, unique per project, for a relational Data
    artifact (MetricDefinition -> KPI-xx, Query -> Q-xx). Computed from the
    highest existing number for this project + prefix.
    """
    import re as _re

    pat = _BUSINESS_ID_RE_CACHE.setdefault(
        prefix, _re.compile(rf"^{_re.escape(prefix)}-(\d+)$")
    )
    existing = model.objects.filter(project=project).values_list(
        "business_id", flat=True
    )
    nums = [int(m.group(1)) for e in existing if (m := pat.match(e or ""))]
    return f"{prefix}-{(max(nums, default=0) + 1):02d}"


# --- Data Brief ---------------------------------------------------------------


def generate_data_brief(project: Project) -> Project:
    _require_data_project(project)
    if project.stage not in _DATA_BRIEF_EDITABLE_STAGES:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"The Data Brief is locked at stage '{project.stage}'.",
            status=409,
        )

    context = {
        "idea": project.original_idea,
        "data_goal": project.data_goal or "analytics",
        "analysis": (project.context_digest or {}).get("idea_analysis") or {},
    }
    draft = run_operation(DATA_BRIEF_GENERATION, context, project=project)

    content = normalize_data_brief_content(
        {**draft.model_dump(mode="json"), "data_goal": project.data_goal}
    )
    try:
        validated = DataBriefContent.model_validate(content)
    except ValidationError as error:
        raise AIOperationError(
            code="ai_invalid_output",
            message="The generated Data Brief did not match the expected structure.",
            retryable=True,
            details=_pydantic_details(error),
        )

    now = _now_iso()
    with transaction.atomic():
        project.data_brief = {
            "content": validated.model_dump(mode="json"),
            "generated_at": now,
            "updated_at": now,
            "approved_at": None,
        }
        project.data_brief_approved_at = None
        project.stage = ProjectStage.DATA_BRIEF
        fields = ["data_brief", "data_brief_approved_at", "stage", "updated_at"]
        # Phase I-5: regenerating the Brief may invalidate everything
        # downstream that was already approved (usually a no-op under today's
        # stage lock — matters once the project has advanced, or a
        # Conversation proposal is applied).
        impact = propagate_brief_change(project)
        if project_level_changed(impact):
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


def update_data_brief(project: Project, content_patch) -> Project:
    _require_data_project(project)
    if project.stage != ProjectStage.DATA_BRIEF:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate a Data Brief before editing it."
            if project.stage == ProjectStage.DATA_BRIEF
            else f"The Data Brief is locked at stage '{project.stage}'.",
            status=409,
        )
    current = (project.data_brief or {}).get("content")
    if not current:
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Generate a Data Brief before editing it.", status=409
        )
    if not isinstance(content_patch, dict) or not content_patch:
        raise ProjectWorkflowError(
            "invalid_data_brief", "Provide one or more Data Brief sections to update."
        )
    unknown = sorted(set(content_patch) - set(BRIEF_SECTIONS))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_data_brief",
            f"Unknown Data Brief section(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    merged = normalize_data_brief_content(
        {**current, **content_patch, "data_goal": project.data_goal}
    )
    try:
        validated = DataBriefContent.model_validate(merged)
    except ValidationError as error:
        raise ProjectWorkflowError(
            "invalid_data_brief",
            "The edited Data Brief is not valid. Check the highlighted sections.",
            details={"errors": _pydantic_details(error)},
        )

    was_approved = project.data_brief_approved_at is not None
    with transaction.atomic():
        project.data_brief["content"] = validated.model_dump(mode="json")
        project.data_brief["updated_at"] = _now_iso()
        project.data_brief["approved_at"] = None
        project.data_brief_approved_at = None
        fields = ["data_brief", "data_brief_approved_at", "updated_at"]
        if was_approved:
            project.context_digest = build_context_digest(project)
            fields.append("context_digest")
            impact = propagate_brief_change(project)
            if project_level_changed(impact):
                fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


def approve_data_brief(project: Project) -> Project:
    _require_data_project(project)
    if project.stage != ProjectStage.DATA_BRIEF:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"There is no Data Brief to approve at stage '{project.stage}'.",
            status=409,
        )
    if not (project.data_brief or {}).get("content"):
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Generate a Data Brief before approving it.", status=409
        )

    approved_at = dj_timezone.now()
    with transaction.atomic():
        project.data_brief_approved_at = approved_at
        project.data_brief["approved_at"] = approved_at.isoformat()
        project.stage = ProjectStage.DATA_SOURCES
        project.context_digest = build_context_digest(project)
        project.save(
            update_fields=[
                "data_brief",
                "data_brief_approved_at",
                "stage",
                "context_digest",
                "updated_at",
            ]
        )
    return project


# --- Dataset upload (untrusted input) --------------------------------------


def _reject_binary(head: bytes) -> None:
    for prefix, label in _MAGIC_REJECT:
        if head.startswith(prefix):
            raise ProjectWorkflowError(
                "unsupported_file_content",
                f"This looks like a {label}. Upload a plain CSV or JSON file.",
            )
    if b"\x00" in head:
        raise ProjectWorkflowError(
            "unsupported_file_content",
            "The file contains binary data. Upload a plain CSV or JSON file.",
        )


def _validate_csv(raw: bytes) -> None:
    import csv

    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except Exception:
            raise ProjectWorkflowError("invalid_csv", "Could not read the file as text.")
    try:
        reader = csv.reader(io.StringIO(text[:262144]))
        header = next(reader, None)
    except csv.Error as exc:
        raise ProjectWorkflowError("invalid_csv", f"Not a readable CSV: {exc}")
    if not header or all((c or "").strip() == "" for c in header):
        raise ProjectWorkflowError("invalid_csv", "The CSV has no usable header row.")
    # a couple of data rows should parse without exploding
    for _ in range(5):
        try:
            next(reader, None)
        except csv.Error as exc:
            raise ProjectWorkflowError("invalid_csv", f"Malformed CSV: {exc}")


def _validate_json(raw: bytes) -> None:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProjectWorkflowError("invalid_json", f"Not valid JSON: {exc}")
    if isinstance(parsed, dict):
        for key in ("data", "rows", "records", "items", "results"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
    if not isinstance(parsed, list) or not parsed:
        raise ProjectWorkflowError(
            "invalid_json", "JSON must be a non-empty array of objects."
        )
    if not all(isinstance(item, dict) for item in parsed[:50]):
        raise ProjectWorkflowError(
            "invalid_json", "Each item in the JSON array must be an object."
        )


def upload_dataset(project: Project, uploaded_file, name: str | None) -> Dataset:
    _require_data_project(project)
    if not project.data_brief_approved_at:
        raise ProjectWorkflowError(
            "data_brief_not_approved",
            "Approve the Data Brief before adding data sources.",
            status=409,
        )
    if uploaded_file is None:
        raise ProjectWorkflowError("no_file", "Attach a CSV or JSON file to upload.")

    max_bytes = settings.DATA_MAX_UPLOAD_BYTES
    if getattr(uploaded_file, "size", 0) and uploaded_file.size > max_bytes:
        raise ProjectWorkflowError(
            "file_too_large",
            f"The file exceeds the {max_bytes // (1024 * 1024)} MB limit.",
            details={"max_bytes": max_bytes},
        )

    original = (getattr(uploaded_file, "name", "") or "").strip()
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in settings.DATA_ALLOWED_SOURCE_TYPES:
        raise ProjectWorkflowError(
            "unsupported_source_type",
            "Only .csv and .json files are supported.",
            details={"allowed": list(settings.DATA_ALLOWED_SOURCE_TYPES)},
        )

    # Read with a hard byte cap; compute the checksum while reading.
    hasher = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0
    for chunk in uploaded_file.chunks(chunk_size=1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise ProjectWorkflowError(
                "file_too_large",
                f"The file exceeds the {max_bytes // (1024 * 1024)} MB limit.",
                details={"max_bytes": max_bytes},
            )
        hasher.update(chunk)
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        raise ProjectWorkflowError("empty_file", "The uploaded file is empty.")
    checksum = hasher.hexdigest()

    _reject_binary(raw[:8192])
    if ext == "csv":
        _validate_csv(raw)
    else:
        _validate_json(raw)

    dataset_id = uuid.uuid4()
    key = build_dataset_key(project.id, dataset_id, checksum, ext)
    store = get_file_store()
    store.save(key, io.BytesIO(raw))

    try:
        dataset = Dataset.objects.create(
            id=dataset_id,
            project=project,
            name=(name or original or "dataset").strip()[:200],
            source_type=_EXT_TO_TYPE[ext],
            storage_ref=key,
            original_filename=original[:300],  # metadata only
            content_type=(getattr(uploaded_file, "content_type", "") or "")[:120],
            size_bytes=len(raw),
            checksum=checksum,
            status=Dataset.Status.UPLOADED,
        )
    except Exception:
        store.delete(key)  # no orphan on failure
        raise
    return dataset


def list_datasets(project: Project) -> list[Dataset]:
    _require_data_project(project)
    return list(project.datasets.all())


def get_dataset(project: Project, dataset_id) -> Dataset:
    _require_data_project(project)
    try:
        return Dataset.objects.get(id=dataset_id, project=project)
    except (Dataset.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ProjectWorkflowError(
            "dataset_not_found", "No such dataset for this project.", status=404
        )


def get_job(project: Project, job_id) -> Job:
    _require_data_project(project)
    try:
        return Job.objects.get(id=job_id, project=project)
    except (Job.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ProjectWorkflowError(
            "job_not_found", "No such job for this project.", status=404
        )


# --- Deterministic profiling (synchronous Job) ---------------------------


def run_dataset_profiling(project: Project, dataset_id) -> dict:
    dataset = get_dataset(project, dataset_id)
    if dataset.status == Dataset.Status.PROFILING:
        raise ProjectWorkflowError(
            "profiling_in_progress", "Profiling is already running for this dataset.", status=409
        )
    # Phase I-5: a re-profile is the only "this dataset may have changed"
    # signal the current MVP has (there is no separate replace/version
    # mechanism — see DATA_ARTIFACT_CHAIN's docstring). profiling_stale is
    # true only for the duration of the re-run, resolved by its own
    # completion below.
    is_reprofile = dataset.status == Dataset.Status.PROFILED

    job = Job.objects.create(
        project=project,
        dataset=dataset,
        kind=Job.Kind.PROFILE_DATASET,
        status=Job.Status.RUNNING,
        params={"dataset_id": str(dataset.id)},
        started_at=dj_timezone.now(),
    )
    dataset.status = Dataset.Status.PROFILING
    dataset.error = ""
    if is_reprofile:
        dataset.profiling_stale = True
    dataset.save(update_fields=["status", "error", "profiling_stale", "updated_at"])

    try:
        with get_file_store().open(dataset.storage_ref) as fh:
            raw = fh.read()
        result = profile_bytes(raw, dataset.source_type)
    except Exception as exc:  # noqa: BLE001 - every profiling failure is recorded
        message = str(exc)[:2000] or exc.__class__.__name__
        dataset.status = Dataset.Status.FAILED
        dataset.error = message
        dataset.save(update_fields=["status", "error", "updated_at"])
        job.status = Job.Status.FAILED
        job.error = message
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise ProjectWorkflowError(
            "profiling_failed",
            f"Profiling failed: {message}",
            status=422,
            details={"job_id": str(job.id)},
        )

    with transaction.atomic():
        run = ProfilingRun.objects.create(
            dataset=dataset,
            job=job,
            table_stats=result["table_stats"],
            columns=result["columns"],
        )
        table = result["table_stats"]
        dataset.row_count = table["row_count"]
        dataset.column_count = table["column_count"]
        dataset.inferred_schema = inferred_schema_from_columns(result["columns"])
        dataset.sampled = table["sampled"]
        dataset.delimiter = (result.get("delimiter") or None)
        dataset.encoding = (result.get("encoding") or None)
        dataset.status = Dataset.Status.PROFILED
        dataset.profiled_at = dj_timezone.now()
        dataset.error = ""
        dataset.profiling_stale = False
        dataset.save()

        job.status = Job.Status.SUCCEEDED
        job.progress = 100
        job.result_ref = {"profiling_run": str(run.id)}
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "progress", "result_ref", "finished_at"])

        if is_reprofile:
            impact = propagate_dataset_change(dataset, project=project)
            if project_level_changed(impact):
                project.save(update_fields=["downstream_stale"])

    return serialize_dataset_detail(dataset, run, job)


# --- Source interpretation --------------------------------------------------


def _profile_summary_for_ai(run: ProfilingRun) -> list[dict]:
    """Bounded per-column summary for the AI — stats only, samples already
    capped/redacted by the profiler. No raw rows."""
    out = []
    for col in run.columns:
        entry = {
            "name": col["name"],
            "dtype": col["dtype"],
            "null_pct": col["null_pct"],
            "distinct_pct": col["distinct_pct"],
            "probable_key": col["probable_key"],
            "top_values": (col.get("top_values") or [])[:5],
            "sample": col.get("sample") or [],
        }
        if col.get("numeric_range"):
            entry["numeric_range"] = col["numeric_range"]
        if col.get("date_range"):
            entry["date_range"] = col["date_range"]
        out.append(entry)
    return out


def generate_source_interpretation(project: Project, dataset_id) -> dict:
    dataset = get_dataset(project, dataset_id)
    if dataset.status != Dataset.Status.PROFILED:
        raise ProjectWorkflowError(
            "dataset_not_profiled",
            "Profile this dataset before interpreting it.",
            status=409,
        )
    run = dataset.profiling_runs.first()
    if run is None:
        raise ProjectWorkflowError(
            "dataset_not_profiled", "Profile this dataset before interpreting it.", status=409
        )

    context = {
        "data_brief": (project.data_brief or {}).get("content") or {},
        "dataset": {"name": dataset.name, "source_type": dataset.source_type},
        "profile_table": run.table_stats,
        "profile_columns": _profile_summary_for_ai(run),
    }
    draft = run_operation(SOURCE_INTERPRETATION, context, project=project)

    content = normalize_source_interpretation_content(draft.model_dump(mode="json"))
    try:
        validated = SourceInterpretationContent.model_validate(content)
    except ValidationError as error:
        raise AIOperationError(
            code="ai_invalid_output",
            message="The generated interpretation did not match the expected structure.",
            retryable=True,
            details=_pydantic_details(error),
        )

    now = _now_iso()
    with transaction.atomic():
        dataset.interpretation = {
            "content": validated.model_dump(mode="json"),
            "generated_at": now,
            "updated_at": now,
            "approved_at": None,
        }
        dataset.interpretation_approved_at = None
        dataset.save(update_fields=["interpretation", "interpretation_approved_at", "updated_at"])
    return serialize_dataset(dataset)


def update_source_interpretation(project: Project, dataset_id, content_patch) -> dict:
    dataset = get_dataset(project, dataset_id)
    current = (dataset.interpretation or {}).get("content")
    if not current:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate an interpretation before editing it.",
            status=409,
        )
    if not isinstance(content_patch, dict) or not content_patch:
        raise ProjectWorkflowError(
            "invalid_source_interpretation",
            "Provide one or more interpretation sections to update.",
        )
    unknown = sorted(set(content_patch) - set(INTERP_SECTIONS))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_source_interpretation",
            f"Unknown section(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    merged = normalize_source_interpretation_content({**current, **content_patch})
    try:
        validated = SourceInterpretationContent.model_validate(merged)
    except ValidationError as error:
        raise ProjectWorkflowError(
            "invalid_source_interpretation",
            "The edited interpretation is not valid.",
            details={"errors": _pydantic_details(error)},
        )

    was_approved = dataset.interpretation_approved_at is not None
    with transaction.atomic():
        dataset.interpretation["content"] = validated.model_dump(mode="json")
        dataset.interpretation["updated_at"] = _now_iso()
        dataset.interpretation["approved_at"] = None
        dataset.interpretation_approved_at = None
        dataset.save(
            update_fields=["interpretation", "interpretation_approved_at", "updated_at"]
        )
        if was_approved:
            project.context_digest = build_context_digest(project)
            project.save(update_fields=["context_digest", "updated_at"])
    return serialize_dataset(dataset)


def approve_source_interpretation(project: Project, dataset_id) -> dict:
    dataset = get_dataset(project, dataset_id)
    if not (dataset.interpretation or {}).get("content"):
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate an interpretation before approving it.",
            status=409,
        )
    approved_at = dj_timezone.now()
    with transaction.atomic():
        dataset.interpretation_approved_at = approved_at
        dataset.interpretation["approved_at"] = approved_at.isoformat()
        dataset.save(update_fields=["interpretation", "interpretation_approved_at", "updated_at"])
        # the human re-confirming the interpretation is its own reconciliation
        clear_dataset_interpretation_stale(dataset)
        project.context_digest = build_context_digest(project)
        project.save(update_fields=["context_digest", "updated_at"])
    return serialize_dataset(dataset)


# --- serialization ---------------------------------------------------------


def serialize_dataset(ds: Dataset) -> dict:
    latest = ds.profiling_runs.first()
    return {
        "id": str(ds.id),
        "name": ds.name,
        "source_type": ds.source_type,
        "original_filename": ds.original_filename,
        "content_type": ds.content_type,
        "size_bytes": ds.size_bytes,
        "encoding": ds.encoding,
        "delimiter": ds.delimiter,
        "row_count": ds.row_count,
        "column_count": ds.column_count,
        "inferred_schema": ds.inferred_schema,
        "sampled": ds.sampled,
        "status": ds.status,
        "profiling_stale": ds.profiling_stale,
        "error": ds.error,
        "supersedes": str(ds.supersedes_id) if ds.supersedes_id else None,
        "uploaded_at": ds.uploaded_at.isoformat(),
        "profiled_at": ds.profiled_at.isoformat() if ds.profiled_at else None,
        "interpretation": ds.interpretation or {},
        "interpretation_approved_at": (
            ds.interpretation_approved_at.isoformat()
            if ds.interpretation_approved_at
            else None
        ),
        "interpretation_stale": ds.interpretation_stale,
        "latest_profiling_run_id": str(latest.id) if latest else None,
    }


def serialize_profiling_run(run: ProfilingRun) -> dict:
    return {
        "id": str(run.id),
        "table_stats": run.table_stats,
        "columns": run.columns,
        "created_at": run.created_at.isoformat(),
    }


def serialize_job(job: Job) -> dict:
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "params": job.params,
        "result_ref": job.result_ref,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def serialize_dataset_detail(ds: Dataset, run: ProfilingRun | None = None, job: Job | None = None) -> dict:
    if run is None:
        run = ds.profiling_runs.first()
    return {
        "dataset": serialize_dataset(ds),
        "profiling_run": serialize_profiling_run(run) if run else None,
        "job": serialize_job(job) if job else None,
    }
