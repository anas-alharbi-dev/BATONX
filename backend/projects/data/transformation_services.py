"""
Transformation Plan domain services (Phase I-2): generate -> edit -> approve,
plus a safe local preview via the DuckDB boundary. Structured steps are the
Source of Truth; SQL is a deterministic render.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone as dj_timezone
from pydantic import ValidationError

from ai.base import run_operation
from ai.exceptions import AIOperationError
from ai.operations.transformation_proposal import TRANSFORMATION_PROPOSAL
from common.storage import local_path
from projects.context import build_context_digest
from projects.data.execution import (
    DuckDBExecution,
    QueryExecutionError,
    SqlValidationError,
)
from projects.data.services import _require_data_project, serialize_job
from projects.data.stale import (
    clear_data_stale,
    project_level_changed,
    propagate_transformation_change,
)
from projects.data.sql_render import UnsupportedOperationError, render_plan_sql
from projects.data.transformation import (
    SECTION_FIELDS,
    TransformationPlanContent,
    normalize_transformation_plan_content,
)
from projects.exceptions import ProjectWorkflowError
from projects.models import Dataset, Job, Project

_IDENT_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pydantic_details(error: ValidationError) -> list[dict]:
    return [
        {"loc": ".".join(str(p) for p in i["loc"]), "msg": i["msg"]}
        for i in error.errors()
    ]


def _content(project: Project) -> dict:
    return dict((project.transformation_plan or {}).get("content") or {})


def _source_dataset(project: Project, content: dict) -> Dataset:
    ds_id = content.get("source_dataset_id")
    try:
        ds = Dataset.objects.get(id=ds_id, project=project)
    except (Dataset.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ProjectWorkflowError(
            "invalid_transformation",
            "source_dataset_id must be a dataset in this project.",
            details={"source_dataset_id": ds_id},
        )
    if ds.status != Dataset.Status.PROFILED:
        raise ProjectWorkflowError(
            "dataset_not_profiled",
            "The source dataset must be profiled first.",
            status=409,
        )
    return ds


def _view_name(dataset: Dataset) -> str:
    return "src_" + _IDENT_SAFE.sub("", str(dataset.id))[:28]


# --- generate / edit / approve --------------------------------------


def generate_transformation_plan(project: Project) -> dict:
    _require_data_project(project)
    datasets = [d for d in project.datasets.all() if d.status == Dataset.Status.PROFILED]
    if not datasets:
        raise ProjectWorkflowError(
            "no_profiled_datasets",
            "Profile a dataset before generating a Transformation Plan.",
            status=409,
        )
    src = datasets[0]
    run = src.profiling_runs.first()
    quality = ((project.data_quality or {}).get("content") or {})
    approved_rules = [
        r for r in quality.get("rules", []) if r.get("status") == "approved"
    ]

    ai_ctx = {
        "data_brief": (project.data_brief or {}).get("content") or {},
        "dataset": {
            "id": str(src.id),
            "name": src.name,
            "source_type": src.source_type,
            "row_count": src.row_count,
        },
        "columns": [
            {"name": c["name"], "dtype": c["dtype"], "null_pct": c.get("null_pct", 0),
             "distinct_pct": c.get("distinct_pct", 0)}
            for c in ((run.columns if run else None) or [])
        ],
        "quality_rules": [
            {"id": r["id"], "assertion": r["assertion"], "column": r.get("column", ""),
             "params": r.get("params", {})}
            for r in approved_rules
        ],
    }
    draft = run_operation(TRANSFORMATION_PROPOSAL, ai_ctx, project=project)
    raw = draft.model_dump(mode="json")
    raw.setdefault("source_dataset_id", str(src.id))

    content = normalize_transformation_plan_content(raw)
    try:
        TransformationPlanContent.model_validate(content)
    except ValidationError as error:
        raise AIOperationError(
            code="ai_invalid_output",
            message="The generated Transformation Plan did not match the expected structure.",
            retryable=True,
            details=_pydantic_details(error),
        )

    was_approved = project.transformation_plan_approved_at is not None
    now = _now_iso()
    with transaction.atomic():
        project.transformation_plan = {
            "content": content,
            "generated_at": now,
            "updated_at": now,
            "approved_at": None,
        }
        project.transformation_plan_approved_at = None
        fields = ["transformation_plan", "transformation_plan_approved_at", "updated_at"]
        if was_approved:
            impact = propagate_transformation_change(project)
            if project_level_changed(impact):
                fields.append("downstream_stale")
        project.save(update_fields=fields)
    return serialize_transformation_plan(project)


def update_transformation_plan(project: Project, patch) -> dict:
    _require_data_project(project)
    current = _content(project)
    if not current:
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Generate a Transformation Plan first.", status=409
        )
    if not isinstance(patch, dict) or not patch:
        raise ProjectWorkflowError(
            "invalid_transformation", "Provide one or more sections to update."
        )
    unknown = sorted(set(patch) - set(SECTION_FIELDS))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_transformation",
            f"Unknown section(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    merged = normalize_transformation_plan_content({**current, **patch})
    try:
        validated = TransformationPlanContent.model_validate(merged)
    except ValidationError as error:
        raise ProjectWorkflowError(
            "invalid_transformation",
            "The edited plan is not valid. Check the highlighted steps.",
            details={"errors": _pydantic_details(error)},
        )

    # every op must be renderable — fail loudly, do not run anything
    _source_dataset(project, merged)
    try:
        render_plan_sql(validated.model_dump(mode="json"), source_view="src_check")
    except UnsupportedOperationError as exc:
        raise ProjectWorkflowError(
            "unsupported_operation",
            exc.message,
            status=422,
            details={"op": exc.op},
        )

    was_approved = project.transformation_plan_approved_at is not None
    with transaction.atomic():
        project.transformation_plan["content"] = validated.model_dump(mode="json")
        project.transformation_plan["updated_at"] = _now_iso()
        project.transformation_plan["approved_at"] = None
        project.transformation_plan_approved_at = None
        fields = [
            "transformation_plan",
            "transformation_plan_approved_at",
            "updated_at",
        ]
        if was_approved:
            project.context_digest = build_context_digest(project)
            fields.append("context_digest")
            impact = propagate_transformation_change(project)
            if project_level_changed(impact):
                fields.append("downstream_stale")
        project.save(update_fields=fields)
    return serialize_transformation_plan(project)


def approve_transformation_plan(project: Project) -> dict:
    _require_data_project(project)
    content = _content(project)
    if not content:
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Generate a Transformation Plan first.", status=409
        )
    _source_dataset(project, content)
    try:
        render_plan_sql(content, source_view="src_check")
    except UnsupportedOperationError as exc:
        raise ProjectWorkflowError(
            "unsupported_operation", exc.message, status=422, details={"op": exc.op}
        )

    approved_at = dj_timezone.now()
    with transaction.atomic():
        project.transformation_plan_approved_at = approved_at
        project.transformation_plan["approved_at"] = approved_at.isoformat()
        clear_data_stale(project, "transformation_plan")
        project.context_digest = build_context_digest(project)
        project.save(
            update_fields=[
                "transformation_plan",
                "transformation_plan_approved_at",
                "downstream_stale",
                "context_digest",
                "updated_at",
            ]
        )
    return serialize_transformation_plan(project)


# --- preview (safe local execution) --------------------------------


def preview_transformation(project: Project) -> dict:
    """
    Service policy: preview runs the CURRENT plan content (draft OR approved) so
    edits can be checked before approval. It never mutates the source Dataset.
    """
    _require_data_project(project)
    content = _content(project)
    if not content:
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Generate a Transformation Plan first.", status=409
        )
    src = _source_dataset(project, content)
    view = _view_name(src)

    try:
        sql = render_plan_sql(content, source_view=view)
    except UnsupportedOperationError as exc:
        raise ProjectWorkflowError(
            "unsupported_operation", exc.message, status=422, details={"op": exc.op}
        )

    job = Job.objects.create(
        project=project,
        dataset=src,
        kind=Job.Kind.RUN_TRANSFORMATION_PREVIEW,
        status=Job.Status.RUNNING,
        params={"rendered_sql": sql},
        started_at=dj_timezone.now(),
    )
    try:
        ex = DuckDBExecution()
        result = ex.run_select(
            sql,
            datasets=[(view, local_path(src.storage_ref), src.source_type)],
            max_rows=settings.DATA_QUERY_MAX_RESULT_ROWS,
        )
    except (SqlValidationError, QueryExecutionError) as exc:
        job.status = Job.Status.FAILED
        job.error = exc.message[:2000]
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise ProjectWorkflowError(
            "preview_failed",
            f"Preview failed: {exc.message}",
            status=422,
            details={"job_id": str(job.id), "code": exc.code},
        )

    output_name = ""
    outs = content.get("outputs") or []
    if outs:
        output_name = outs[-1].get("name", "")
    elif content.get("steps"):
        output_name = content["steps"][-1].get("output_name", "")

    bounded = {
        "output_name": output_name,
        "columns": result["columns"],
        "rows": result["rows"],  # already capped by the runner
        "row_count": result["row_count"],
        "truncated": result["truncated"],
        "rendered_sql": sql,
    }
    with transaction.atomic():
        job.status = Job.Status.SUCCEEDED
        job.progress = 100
        job.result_ref = bounded
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "progress", "result_ref", "finished_at"])
    return {
        "job": serialize_job(job),
        "preview": bounded,
    }


# --- serialization ------------------------------------------------


def _rendered_sql(project: Project) -> str | None:
    content = _content(project)
    if not content or not content.get("steps"):
        return None
    try:
        return render_plan_sql(content, source_view="src_preview")
    except UnsupportedOperationError:
        return None


def serialize_transformation_plan(project: Project) -> dict:
    tp = project.transformation_plan or {}
    latest_preview = (
        project.jobs.filter(kind=Job.Kind.RUN_TRANSFORMATION_PREVIEW).first()
    )
    return {
        "content": tp.get("content") or None,
        "approved": project.transformation_plan_approved_at is not None,
        "approved_at": (
            project.transformation_plan_approved_at.isoformat()
            if project.transformation_plan_approved_at
            else None
        ),
        "generated_at": tp.get("generated_at"),
        "updated_at": tp.get("updated_at"),
        "rendered_sql": _rendered_sql(project),
        "latest_preview": (
            {"job": serialize_job(latest_preview), "preview": latest_preview.result_ref}
            if latest_preview
            else None
        ),
    }
