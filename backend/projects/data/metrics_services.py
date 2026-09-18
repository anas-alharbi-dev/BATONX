"""
Metric / KPI domain services (Phase I-3): generate (batch) -> review/edit ->
approve (per metric) -> validate (deterministic, DuckDB). Definition != Result:
no computed value is ever stored on ``MetricDefinition``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone as dj_timezone
from pydantic import ValidationError

from ai.base import run_operation
from ai.exceptions import AIOperationError
from ai.operations.metric_definition_generation import METRIC_DEFINITION_GENERATION
from common.storage import local_path
from projects.context import build_context_digest
from projects.data.execution import (
    DuckDBExecution,
    QueryExecutionError,
    SqlValidationError,
)
from projects.data.metrics import (
    EDITABLE_FIELDS,
    MetricFields,
    MetricStructured,
    validate_references,
)
from projects.data.sql_safe import quote_ident, sql_literal, view_name
from projects.data.services import _require_data_project, next_business_id
from projects.data.stale import project_level_changed, propagate_metric_change
from projects.exceptions import ProjectWorkflowError
from projects.models import Dataset, Job, MetricDefinition, MetricValidationRun, Project


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pydantic_details(error: ValidationError) -> list[dict]:
    return [
        {"loc": ".".join(str(p) for p in i["loc"]), "msg": i["msg"]}
        for i in error.errors()
    ]


def available_schema(project: Project) -> dict[str, set[str]]:
    """``{dataset_id: {column names}}`` for every PROFILED dataset — the only
    references a metric (or a query) may use in Phase I-3."""
    return {
        str(d.id): {c["name"] for c in (d.inferred_schema or [])}
        for d in project.datasets.filter(status=Dataset.Status.PROFILED)
    }


def _get_metric(project: Project, metric_id) -> MetricDefinition:
    try:
        return MetricDefinition.objects.get(id=metric_id, project=project)
    except (MetricDefinition.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ProjectWorkflowError(
            "metric_not_found", "No such metric for this project.", status=404
        )


# --- generation (batch) -----------------------------------------------


def generate_metrics(project: Project) -> list[dict]:
    _require_data_project(project)
    schema = available_schema(project)
    if not schema:
        raise ProjectWorkflowError(
            "no_profiled_datasets",
            "Profile at least one dataset before generating metrics.",
            status=409,
        )

    def _ds_ctx(d: Dataset) -> dict:
        return {
            "id": str(d.id),
            "name": d.name,
            "row_count": d.row_count,
            "columns": [{"name": c["name"], "dtype": c["dtype"]} for c in (d.inferred_schema or [])],
            "interpretation": (
                (d.interpretation or {}).get("content")
                if d.interpretation_approved_at
                else None
            ),
        }

    quality = (project.data_quality or {}).get("content") or {}
    transformation = (
        (project.transformation_plan or {}).get("content")
        if project.transformation_plan_approved_at
        else None
    ) or {}

    ai_ctx = {
        "data_brief": (project.data_brief or {}).get("content") or {},
        "datasets": [_ds_ctx(d) for d in project.datasets.filter(status=Dataset.Status.PROFILED)],
        "quality_rules": [r for r in quality.get("rules", []) if r.get("status") == "approved"],
        "transformation": transformation,
    }
    draft = run_operation(METRIC_DEFINITION_GENERATION, ai_ctx, project=project)
    proposed = draft.model_dump(mode="json").get("metrics", [])

    validated: list[MetricFields] = []
    for raw in proposed:
        try:
            fields = MetricFields.model_validate(raw)
            validate_references(fields.structured, schema)
        except (ValidationError, ValueError) as error:
            raise AIOperationError(
                code="ai_invalid_output",
                message="A proposed metric referenced data that does not exist.",
                retryable=True,
                details={"metric": raw.get("name"), "error": str(error)},
            )
        validated.append(fields)

    created: list[MetricDefinition] = []
    with transaction.atomic():
        for fields in validated:
            bid = next_business_id(project, MetricDefinition, "KPI")
            metric = MetricDefinition.objects.create(
                business_id=bid,
                project=project,
                name=fields.name,
                business_meaning=fields.business_meaning,
                formula_text=fields.formula_text,
                structured=fields.structured.model_dump(mode="json"),
                time_grain=fields.time_grain,
                allowed_dimensions=fields.allowed_dimensions,
                source_fields=fields.source_fields,
                owner=fields.owner,
                related_goal_ref=fields.related_goal_ref,
                caveats=fields.caveats,
                validation_checks=fields.validation_checks,
                status=MetricDefinition.Status.DRAFT,
            )
            created.append(metric)
    return [serialize_metric(m) for m in created]


def list_metrics(project: Project) -> list[dict]:
    _require_data_project(project)
    return [serialize_metric(m) for m in project.metrics.all()]


def update_metric(project: Project, metric_id, patch) -> dict:
    _require_data_project(project)
    metric = _get_metric(project, metric_id)
    if not isinstance(patch, dict) or not patch:
        raise ProjectWorkflowError("invalid_metric", "Provide fields to update.")
    unknown = sorted(set(patch) - set(EDITABLE_FIELDS))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_metric",
            f"Unknown field(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    current = {
        "name": metric.name,
        "business_meaning": metric.business_meaning,
        "formula_text": metric.formula_text,
        "structured": metric.structured,
        "time_grain": metric.time_grain,
        "allowed_dimensions": metric.allowed_dimensions,
        "source_fields": metric.source_fields,
        "owner": metric.owner,
        "related_goal_ref": metric.related_goal_ref,
        "caveats": metric.caveats,
        "validation_checks": metric.validation_checks,
    }
    merged = {**current, **patch}
    try:
        fields = MetricFields.model_validate(merged)
        validate_references(fields.structured, available_schema(project))
    except (ValidationError, ValueError) as error:
        details = (
            _pydantic_details(error)
            if isinstance(error, ValidationError)
            else [{"loc": "structured", "msg": str(error)}]
        )
        raise ProjectWorkflowError(
            "invalid_metric", "The edited metric is not valid.", details={"errors": details}
        )

    was_approved = metric.status == MetricDefinition.Status.APPROVED
    with transaction.atomic():
        metric.name = fields.name
        metric.business_meaning = fields.business_meaning
        metric.formula_text = fields.formula_text
        metric.structured = fields.structured.model_dump(mode="json")
        metric.time_grain = fields.time_grain
        metric.allowed_dimensions = fields.allowed_dimensions
        metric.source_fields = fields.source_fields
        metric.owner = fields.owner
        metric.related_goal_ref = fields.related_goal_ref
        metric.caveats = fields.caveats
        metric.validation_checks = fields.validation_checks
        metric.status = MetricDefinition.Status.DRAFT
        metric.approved_at = None
        metric.save()
        if was_approved:
            project.context_digest = build_context_digest(project)
            fields = ["context_digest", "updated_at"]
            # this KPI was authoritative and just changed -> whatever
            # depended on it (by real stored reference) needs review
            impact = propagate_metric_change(metric, project=project)
            if project_level_changed(impact):
                fields.append("downstream_stale")
            project.save(update_fields=fields)
    return serialize_metric(metric)


def approve_metric(project: Project, metric_id) -> dict:
    _require_data_project(project)
    metric = _get_metric(project, metric_id)
    with transaction.atomic():
        metric.status = MetricDefinition.Status.APPROVED
        metric.approved_at = dj_timezone.now()
        # re-approving is this KPI's own reconciliation step
        metric.stale = False
        metric.stale_reason = ""
        metric.stale_since = None
        metric.save(update_fields=["status", "approved_at", "stale", "stale_reason", "stale_since", "updated_at"])
        project.context_digest = build_context_digest(project)
        project.save(update_fields=["context_digest", "updated_at"])
    return serialize_metric(metric)


# --- deterministic validation -----------------------------------------


def _build_validation_sql(structured: dict, view: str) -> str:
    s = MetricStructured.model_validate(structured)
    where = ""
    if s.default_filters:
        clauses = []
        for f in s.default_filters:
            col = quote_ident(f.field)
            if f.operator == "eq":
                clauses.append(f"{col} = {sql_literal(f.value)}")
            elif f.operator == "ne":
                clauses.append(f"{col} != {sql_literal(f.value)}")
            elif f.operator == "lt":
                clauses.append(f"{col} < {sql_literal(f.value)}")
            elif f.operator == "lte":
                clauses.append(f"{col} <= {sql_literal(f.value)}")
            elif f.operator == "gt":
                clauses.append(f"{col} > {sql_literal(f.value)}")
            elif f.operator == "gte":
                clauses.append(f"{col} >= {sql_literal(f.value)}")
            elif f.operator in ("in", "not_in"):
                vals = ", ".join(sql_literal(v) for v in f.value)
                clauses.append(f"{col} {'NOT IN' if f.operator == 'not_in' else 'IN'} ({vals})")
        where = " WHERE " + " AND ".join(clauses)

    if s.aggregation == "ratio":
        num = quote_ident(s.numerator.field)
        den = quote_ident(s.denominator.field)
        expr = (
            f"CASE WHEN sum({den}) = 0 OR sum({den}) IS NULL THEN NULL "
            f"ELSE sum({num}) / sum({den}) END"
        )
    elif s.aggregation == "count":
        expr = "count(*)" if not s.measure else f"count({quote_ident(s.measure.field)})"
    elif s.aggregation == "count_distinct":
        expr = f"count(DISTINCT {quote_ident(s.measure.field)})"
    else:  # sum / avg / min / max
        expr = f"{s.aggregation}({quote_ident(s.measure.field)})"

    return f'SELECT {expr} AS value, count(*) AS row_count FROM "{view}"{where}'


def validate_metric(project: Project, metric_id) -> dict:
    _require_data_project(project)
    metric = _get_metric(project, metric_id)
    dataset_id = metric.structured.get("base_table_ref")
    try:
        dataset = Dataset.objects.get(id=dataset_id, project=project)
    except (Dataset.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ProjectWorkflowError(
            "invalid_metric",
            "The metric's base_table_ref is not a dataset in this project.",
        )
    if dataset.status != Dataset.Status.PROFILED:
        raise ProjectWorkflowError(
            "dataset_not_profiled", "The base dataset must be profiled.", status=409
        )

    job = Job.objects.create(
        project=project,
        dataset=dataset,
        kind=Job.Kind.VALIDATE_METRIC,
        status=Job.Status.RUNNING,
        started_at=dj_timezone.now(),
    )
    view = view_name("src", dataset.id)
    sql = ""
    run_result: dict = {}
    passed = False
    error = ""
    try:
        sql = _build_validation_sql(metric.structured, view)
        ex = DuckDBExecution()
        result = ex.run_select(
            sql, datasets=[(view, local_path(dataset.storage_ref), dataset.source_type)]
        )
        value = (result["rows"][0][0]) if result["rows"] else None
        row_count = (result["rows"][0][1]) if result["rows"] else 0
        run_result = {"value": value, "row_count": row_count, "null_result": value is None}
        passed = True
    except (SqlValidationError, QueryExecutionError) as exc:
        error = exc.message
    except ValidationError as exc:
        error = f"invalid structured definition: {exc}"

    with transaction.atomic():
        run = MetricValidationRun.objects.create(
            metric=metric, job=job, query_sql=sql,
            result=run_result, passed=passed, error=error,
        )
        job.status = Job.Status.SUCCEEDED if passed else Job.Status.FAILED
        job.progress = 100
        job.result_ref = {"metric_validation_run": str(run.id)}
        if not passed:
            job.error = error[:2000]
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "progress", "result_ref", "error", "finished_at"])
    return serialize_metric(metric)


# --- serialization -----------------------------------------------------


def serialize_validation_run(run: MetricValidationRun) -> dict:
    return {
        "id": str(run.id),
        "query_sql": run.query_sql,
        "result": run.result,
        "passed": run.passed,
        "error": run.error,
        "created_at": run.created_at.isoformat(),
    }


def serialize_metric(m: MetricDefinition) -> dict:
    latest = m.validation_runs.first()
    return {
        "id": str(m.id),
        "business_id": m.business_id,
        "name": m.name,
        "business_meaning": m.business_meaning,
        "formula_text": m.formula_text,
        "structured": m.structured,
        "time_grain": m.time_grain,
        "allowed_dimensions": m.allowed_dimensions,
        "source_fields": m.source_fields,
        "owner": m.owner,
        "related_goal_ref": m.related_goal_ref,
        "caveats": m.caveats,
        "validation_checks": m.validation_checks,
        "status": m.status,
        "approved_at": m.approved_at.isoformat() if m.approved_at else None,
        "stale": m.stale,
        "stale_reason": m.stale_reason,
        "stale_since": m.stale_since.isoformat() if m.stale_since else None,
        "created_at": m.created_at.isoformat(),
        "updated_at": m.updated_at.isoformat(),
        "latest_validation": serialize_validation_run(latest) if latest else None,
    }
