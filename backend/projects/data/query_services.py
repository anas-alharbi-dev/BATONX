"""
Query domain services (Phase I-3):

  question -> Query Plan (human, approved) -> SQL (AI, gated by the Phase I-2
  security validator) -> AI review (advisory) -> human "reviewed" -> execute
  (only reviewed SQL; DuckDB boundary; bounded, immutable result).

Multi-dataset joins are explicitly deferred (``QueryPlanContent.joins`` must be
empty) — Phase I-3 queries operate over a single project-scoped dataset.
"""
from __future__ import annotations

from datetime import datetime, timezone

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone as dj_timezone
from pydantic import ValidationError

from ai.base import run_operation
from ai.exceptions import AIOperationError
from ai.operations.sql_generation import SQL_GENERATION
from ai.operations.sql_review import SQL_REVIEW
from common.storage import local_path
from projects.context import build_context_digest
from projects.data.execution import (
    DuckDBExecution,
    QueryExecutionError,
    SqlValidationError,
    validate_select_only,
)
from projects.data.query import PLAN_FIELDS, QueryPlanContent
from projects.data.services import _require_data_project, next_business_id
from projects.data.sql_safe import view_name
from projects.data.stale import propagate_query_change
from projects.exceptions import ProjectWorkflowError
from projects.models import Dataset, Job, MetricDefinition, Project, Query, QueryRun


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pydantic_details(error: ValidationError) -> list[dict]:
    return [
        {"loc": ".".join(str(p) for p in i["loc"]), "msg": i["msg"]}
        for i in error.errors()
    ]


def _get_query(project: Project, query_id) -> Query:
    try:
        return Query.objects.get(id=query_id, project=project)
    except (Query.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ProjectWorkflowError(
            "query_not_found", "No such query for this project.", status=404
        )


def _base_dataset(project: Project, plan: dict) -> Dataset:
    ref = plan.get("base_table_ref")
    try:
        ds = Dataset.objects.get(id=ref, project=project)
    except (Dataset.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ProjectWorkflowError(
            "invalid_query_plan",
            "base_table_ref must be a dataset in this project.",
            details={"base_table_ref": ref},
        )
    if ds.status != Dataset.Status.PROFILED:
        raise ProjectWorkflowError(
            "dataset_not_profiled", "The base dataset must be profiled.", status=409
        )
    return ds


# --- create / plan -----------------------------------------------------


def create_query(project: Project, question) -> dict:
    _require_data_project(project)
    question = (question or "").strip()
    if not question:
        raise ProjectWorkflowError("empty_question", "Describe the business question.")
    bid = next_business_id(project, Query, "Q")
    query = Query.objects.create(
        business_id=bid, project=project, question=question, plan={},
        status=Query.Status.DRAFT_PLAN,
    )
    return serialize_query(query)


def list_queries(project: Project) -> list[dict]:
    _require_data_project(project)
    return [serialize_query(q) for q in project.queries.all()]


def update_query_plan(project: Project, query_id, plan_patch) -> dict:
    _require_data_project(project)
    query = _get_query(project, query_id)
    if not isinstance(plan_patch, dict) or not plan_patch:
        raise ProjectWorkflowError("invalid_query_plan", "Provide plan fields to update.")
    unknown = sorted(set(plan_patch) - set(PLAN_FIELDS))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_query_plan",
            f"Unknown plan field(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    merged = {**(query.plan or {}), **plan_patch}
    try:
        validated = QueryPlanContent.model_validate(merged)
    except ValidationError as error:
        raise ProjectWorkflowError(
            "invalid_query_plan",
            "The plan is not valid.",
            details={"errors": _pydantic_details(error)},
        )
    _base_dataset(project, validated.model_dump(mode="json"))
    for ref in validated.required_kpi_refs:
        if not MetricDefinition.objects.filter(
            project=project, business_id=ref, status=MetricDefinition.Status.APPROVED
        ).exists():
            raise ProjectWorkflowError(
                "invalid_query_plan",
                f"required_kpi_refs must be approved KPIs of this project: {ref} is not.",
                details={"kpi_ref": ref},
            )

    with transaction.atomic():
        was_authoritative = query.status in (Query.Status.REVIEWED, Query.Status.EXECUTED)
        old_kpi_refs = list(query.kpi_refs or [])
        query.plan = validated.model_dump(mode="json")
        query.kpi_refs = validated.required_kpi_refs
        # editing the plan always reverts everything downstream — never
        # silently keep stale SQL/review/execution state around a changed plan
        if query.status != Query.Status.DRAFT_PLAN:
            query.sql = ""
            query.review = {}
            query.status = Query.Status.DRAFT_PLAN
        query.save()
        if was_authoritative:
            # this query was reviewed/executed and just changed -> whatever
            # depended on the KPIs it used to reference needs review
            propagate_query_change(query, kpi_refs=old_kpi_refs, project=project)
    return serialize_query(query)


def approve_query_plan(project: Project, query_id) -> dict:
    _require_data_project(project)
    query = _get_query(project, query_id)
    if query.status != Query.Status.DRAFT_PLAN:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"The plan cannot be approved from status '{query.status}'.",
            status=409,
        )
    if not query.plan:
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Fill in the Query Plan first.", status=409
        )
    with transaction.atomic():
        query.plan_approved_at = dj_timezone.now()
        query.status = Query.Status.PLAN_APPROVED
        query.save(update_fields=["plan_approved_at", "status", "updated_at"])
    return serialize_query(query)


# --- SQL generation (untrusted output, re-validated) -------------------


def generate_query_sql(project: Project, query_id) -> dict:
    _require_data_project(project)
    query = _get_query(project, query_id)
    if query.status != Query.Status.PLAN_APPROVED:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Approve the Query Plan before generating SQL.",
            status=409,
        )
    dataset = _base_dataset(project, query.plan)
    view = view_name("src", dataset.id)
    kpis = MetricDefinition.objects.filter(
        project=project, business_id__in=query.plan.get("required_kpi_refs", []),
    )

    ai_ctx = {
        "plan": query.plan,
        "view_name": view,
        "columns": dataset.inferred_schema or [],
        "kpis": [
            {"business_id": k.business_id, "name": k.name, "formula_text": k.formula_text,
             "structured": k.structured}
            for k in kpis
        ],
    }
    draft = run_operation(SQL_GENERATION, ai_ctx, project=project)

    try:
        validate_select_only(draft.sql)
    except SqlValidationError as exc:
        raise ProjectWorkflowError(
            "unsafe_generated_sql",
            f"The generated SQL was rejected: {exc.message}",
            status=422,
            details={"code": exc.code},
        )

    with transaction.atomic():
        query.sql = draft.sql.strip()
        query.review = {
            "generation": {
                "explanation": draft.explanation,
                "referenced_kpi_ids": draft.referenced_kpi_ids,
                "referenced_fields": draft.referenced_fields,
            }
        }
        query.status = Query.Status.SQL_GENERATED
        query.save(update_fields=["sql", "review", "status", "updated_at"])
    return serialize_query(query)


# --- AI review (advisory) + explicit human reviewed ---------------------


def review_query_sql(project: Project, query_id) -> dict:
    _require_data_project(project)
    query = _get_query(project, query_id)
    if query.status not in (Query.Status.SQL_GENERATED, Query.Status.REVIEWED):
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Generate SQL before requesting a review.", status=409
        )
    kpis = MetricDefinition.objects.filter(
        project=project, business_id__in=query.plan.get("required_kpi_refs", []),
    )
    ai_ctx = {
        "plan": query.plan,
        "sql": query.sql,
        "kpis": [
            {"business_id": k.business_id, "name": k.name, "formula_text": k.formula_text}
            for k in kpis
        ],
    }
    draft = run_operation(SQL_REVIEW, ai_ctx, project=project)

    with transaction.atomic():
        review = dict(query.review or {})
        review["ai"] = draft.model_dump(mode="json")
        # AI review is advisory ONLY — it can never set human_reviewed.
        review["human_reviewed"] = review.get("human_reviewed", False)
        query.review = review
        query.save(update_fields=["review", "updated_at"])
    return serialize_query(query)


def mark_query_reviewed(project: Project, query_id) -> dict:
    """The ONLY way a query becomes reviewed — an explicit human action."""
    _require_data_project(project)
    query = _get_query(project, query_id)
    if query.status != Query.Status.SQL_GENERATED:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"Cannot mark reviewed from status '{query.status}'.",
            status=409,
        )
    with transaction.atomic():
        review = dict(query.review or {})
        review["human_reviewed"] = True
        review["human_reviewed_at"] = _now_iso()
        query.review = review
        query.status = Query.Status.REVIEWED
        # marking reviewed is this query's own reconciliation step
        query.stale = False
        query.stale_reason = ""
        query.stale_since = None
        query.save(update_fields=["review", "status", "stale", "stale_reason", "stale_since", "updated_at"])
        project.context_digest = build_context_digest(project)
        project.save(update_fields=["context_digest", "updated_at"])
    return serialize_query(query)


# --- execution (only reviewed SQL; DuckDB boundary; bounded) -----------


def execute_query(project: Project, query_id) -> dict:
    _require_data_project(project)
    query = _get_query(project, query_id)
    if query.status not in (Query.Status.REVIEWED, Query.Status.EXECUTED):
        raise ProjectWorkflowError(
            "query_not_reviewed",
            "Mark this query's SQL as reviewed before executing it.",
            status=409,
        )
    dataset = _base_dataset(project, query.plan)
    view = view_name("src", dataset.id)

    job = Job.objects.create(
        project=project, dataset=dataset, kind=Job.Kind.EXECUTE_QUERY,
        status=Job.Status.RUNNING, started_at=dj_timezone.now(),
        params={"query_id": str(query.id)},
    )
    try:
        # re-validate the exact same gate immediately before running — SQL is
        # untrusted no matter how long ago it was reviewed
        validate_select_only(query.sql)
        ex = DuckDBExecution()
        result = ex.run_select(
            query.sql,
            datasets=[(view, local_path(dataset.storage_ref), dataset.source_type)],
            max_rows=settings.DATA_QUERY_MAX_RESULT_ROWS,
        )
    except (SqlValidationError, QueryExecutionError) as exc:
        job.status = Job.Status.FAILED
        job.error = exc.message[:2000]
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise ProjectWorkflowError(
            "query_execution_failed",
            f"Execution failed: {exc.message}",
            status=422,
            details={"job_id": str(job.id), "code": exc.code},
        )

    with transaction.atomic():
        run = QueryRun.objects.create(
            query=query, job=job, executed_sql=query.sql,
            columns=result["columns"], rows=result["rows"],
            row_count=result["row_count"], truncated=result["truncated"],
        )
        job.status = Job.Status.SUCCEEDED
        job.progress = 100
        job.result_ref = {"query_run": str(run.id)}
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "progress", "result_ref", "finished_at"])
        query.status = Query.Status.EXECUTED
        query.last_run_job = job
        query.save(update_fields=["status", "last_run_job", "updated_at"])
        # keep the digest's queries[].status metadata current — never the
        # run's rows/SQL/columns, just the already-allowed concise fields
        project.context_digest = build_context_digest(project)
        project.save(update_fields=["context_digest", "updated_at"])
    return serialize_query(query)


# --- serialization -------------------------------------------------


def serialize_query_run(run: QueryRun) -> dict:
    return {
        "id": str(run.id),
        "executed_sql": run.executed_sql,
        "columns": run.columns,
        "rows": run.rows,
        "row_count": run.row_count,
        "truncated": run.truncated,
        "created_at": run.created_at.isoformat(),
    }


def serialize_query(q: Query) -> dict:
    latest_run = q.runs.first()
    return {
        "id": str(q.id),
        "business_id": q.business_id,
        "question": q.question,
        "plan": q.plan,
        "plan_approved_at": q.plan_approved_at.isoformat() if q.plan_approved_at else None,
        "sql": q.sql,
        "dialect": q.dialect,
        "kpi_refs": q.kpi_refs,
        "review": q.review,
        "status": q.status,
        "stale": q.stale,
        "stale_reason": q.stale_reason,
        "stale_since": q.stale_since.isoformat() if q.stale_since else None,
        "created_at": q.created_at.isoformat(),
        "updated_at": q.updated_at.isoformat(),
        "latest_run": serialize_query_run(latest_run) if latest_run else None,
    }
