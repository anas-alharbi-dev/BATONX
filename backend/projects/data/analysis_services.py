"""
Analysis Plan domain services (Phase I-4):

  question -> Analysis Plan (human-authored or AI-drafted, approved) -> Run
  (deterministic compilation + execution via the Phase I-2/I-3 DuckDB
  boundary) -> immutable AnalysisResult.

AI never computes or alters a number — see ``analysis_execution.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone as dj_timezone
from pydantic import ValidationError

from ai.base import run_operation
from ai.exceptions import AIOperationError
from ai.operations.analysis_plan_generation import ANALYSIS_PLAN_GENERATION
from projects.context import build_context_digest
from projects.data.analysis import AnalysisPlanContent, EDITABLE_FIELDS
from projects.data.analysis_execution import (
    UnsupportedAnalysisError,
    build_data_caveats,
    compile_analysis,
)
from projects.data.execution import (
    DuckDBExecution,
    QueryExecutionError,
    SqlValidationError,
)
from projects.data.services import _require_data_project, next_business_id
from projects.data.stale import (
    clear_analysis_plan_stale,
    project_level_changed,
    propagate_analysis_plan_change,
)
from projects.exceptions import ProjectWorkflowError
from projects.models import (
    AnalysisPlan,
    AnalysisResult,
    Dataset,
    Job,
    MetricDefinition,
    Project,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pydantic_details(error: ValidationError) -> list[dict]:
    return [
        {"loc": ".".join(str(p) for p in i["loc"]), "msg": i["msg"]}
        for i in error.errors()
    ]


def _get_plan(project: Project, plan_id) -> AnalysisPlan:
    try:
        return AnalysisPlan.objects.get(id=plan_id, project=project)
    except (AnalysisPlan.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ProjectWorkflowError(
            "analysis_plan_not_found", "No such Analysis Plan for this project.", status=404
        )


def _get_result(project: Project, result_id) -> AnalysisResult:
    try:
        return AnalysisResult.objects.get(id=result_id, project=project)
    except (AnalysisResult.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ProjectWorkflowError(
            "analysis_result_not_found", "No such Analysis Result for this project.", status=404
        )


# --- reference validation (project-isolated, DB-aware) -------------------


def _resolve_required_metrics(project: Project, required_metrics: list[str]) -> list[MetricDefinition]:
    metrics = []
    for ref in required_metrics:
        try:
            m = MetricDefinition.objects.get(
                project=project, business_id=ref, status=MetricDefinition.Status.APPROVED
            )
        except MetricDefinition.DoesNotExist:
            raise ValueError(
                f"required_metrics references an unknown or unapproved KPI: {ref!r}"
            )
        metrics.append(m)
    return metrics


def _available_fields(project: Project, metrics: list[MetricDefinition]) -> set[str]:
    fields: set[str] = set()
    for m in metrics:
        fields.update(m.allowed_dimensions)
        fields.update(m.source_fields)
        ds_id = (m.structured or {}).get("base_table_ref")
        try:
            ds = Dataset.objects.get(id=ds_id, project=project)
        except (Dataset.DoesNotExist, ValueError, TypeError, DjangoValidationError):
            continue
        fields.update(c["name"] for c in (ds.inferred_schema or []))
    return fields


def _datasets_by_metric(project: Project, metrics: list[MetricDefinition]) -> dict[str, Dataset]:
    out = {}
    for m in metrics:
        ds_id = (m.structured or {}).get("base_table_ref")
        try:
            ds = Dataset.objects.get(id=ds_id, project=project)
        except (Dataset.DoesNotExist, ValueError, TypeError, DjangoValidationError):
            raise ValueError(f"KPI {m.business_id}'s base_table_ref is not a dataset in this project.")
        if ds.status != Dataset.Status.PROFILED:
            raise ValueError(f"KPI {m.business_id}'s base dataset must be profiled.")
        out[m.business_id] = ds
    return out


def validate_plan_references(project: Project, content: AnalysisPlanContent) -> dict:
    """
    Raises ``ValueError`` naming the first bad reference. Required metrics
    must exist, belong to THIS project, and be approved (project isolation is
    implicit in the ``project=project`` filter — a cross-project id simply
    does not resolve). Segments and comparison-filter fields must exist on the
    referenced KPIs' dimensions or real dataset schema. Whether each metric
    has a *passing* validation run is soft-preferred, not enforced — returned
    as informational metadata only.
    """
    metrics = _resolve_required_metrics(project, content.required_metrics)
    available = _available_fields(project, metrics)
    for seg in content.segments:
        if seg not in available:
            raise ValueError(
                f"segment {seg!r} does not exist on the referenced KPIs' dimensions/dataset schema"
            )
    for c in content.comparisons:
        for f in c.filters:
            if f.field not in available:
                raise ValueError(
                    f"comparison filter field {f.field!r} does not exist on the "
                    "referenced KPIs' dimensions/dataset schema"
                )
    return {
        "metrics_validated": {
            m.business_id: m.validation_runs.filter(passed=True).exists() for m in metrics
        },
    }


# --- create / generate / edit / approve -----------------------------------


def create_analysis_plan(project: Project, payload: dict) -> dict:
    _require_data_project(project)
    if not isinstance(payload, dict):
        raise ProjectWorkflowError("invalid_analysis_plan", "Provide a plan body.")
    try:
        content = AnalysisPlanContent.model_validate(payload)
        validate_plan_references(project, content)
    except (ValidationError, ValueError) as error:
        details = (
            _pydantic_details(error) if isinstance(error, ValidationError)
            else [{"loc": "plan", "msg": str(error)}]
        )
        raise ProjectWorkflowError(
            "invalid_analysis_plan", "The Analysis Plan is not valid.", details={"errors": details}
        )

    bid = next_business_id(project, AnalysisPlan, "AN")
    plan = AnalysisPlan.objects.create(
        business_id=bid, project=project,
        business_question=content.business_question,
        hypotheses=content.hypotheses,
        required_metrics=content.required_metrics,
        segments=content.segments,
        comparisons=[c.model_dump(mode="json") for c in content.comparisons],
        time_range=content.time_range or {},
        method=content.method,
        expected_outputs=content.expected_outputs,
        status=AnalysisPlan.Status.DRAFT,
    )
    return serialize_analysis_plan(plan)


def _ai_context(project: Project) -> dict:
    approved_metrics = [
        {
            "business_id": m.business_id, "name": m.name, "formula_text": m.formula_text,
            "allowed_dimensions": m.allowed_dimensions, "time_grain": m.time_grain,
            "structured": m.structured,
        }
        for m in project.metrics.filter(status=MetricDefinition.Status.APPROVED)
    ]
    reviewed_queries = [
        {"business_id": q.business_id, "question": q.question, "kpi_refs": q.kpi_refs, "status": q.status}
        for q in project.queries.filter(status__in=["reviewed", "executed"])
    ]
    quality = (project.data_quality or {}).get("content") or {}
    transformation = (
        (project.transformation_plan or {}).get("content")
        if project.transformation_plan_approved_at else None
    ) or {}
    datasets = [
        {
            "id": str(d.id), "name": d.name, "row_count": d.row_count,
            "columns": [{"name": c["name"], "dtype": c["dtype"]} for c in (d.inferred_schema or [])],
        }
        for d in project.datasets.filter(status=Dataset.Status.PROFILED)
    ]
    return {
        "data_brief": (project.data_brief or {}).get("content") or {},
        "metrics": approved_metrics,
        "queries": reviewed_queries,
        "quality_rules": [r for r in quality.get("rules", []) if r.get("status") == "approved"],
        "transformation": transformation,
        "datasets": datasets,
    }


def generate_analysis_plan(project: Project, business_question: str | None = None) -> dict:
    _require_data_project(project)
    if not project.metrics.filter(status=MetricDefinition.Status.APPROVED).exists():
        raise ProjectWorkflowError(
            "no_approved_metrics", "Approve at least one KPI before generating an Analysis Plan.",
            status=409,
        )
    ai_ctx = _ai_context(project)
    ai_ctx["business_question_hint"] = (business_question or "").strip()
    draft = run_operation(ANALYSIS_PLAN_GENERATION, ai_ctx, project=project)
    raw = draft.model_dump(mode="json")

    try:
        content = AnalysisPlanContent.model_validate(raw)
        validate_plan_references(project, content)
    except (ValidationError, ValueError) as error:
        raise AIOperationError(
            code="ai_invalid_output",
            message="The proposed Analysis Plan referenced data that does not exist or is malformed.",
            retryable=True,
            details={"error": str(error)},
        )

    bid = next_business_id(project, AnalysisPlan, "AN")
    plan = AnalysisPlan.objects.create(
        business_id=bid, project=project,
        business_question=content.business_question,
        hypotheses=content.hypotheses,
        required_metrics=content.required_metrics,
        segments=content.segments,
        comparisons=[c.model_dump(mode="json") for c in content.comparisons],
        time_range=content.time_range or {},
        method=content.method,
        expected_outputs=content.expected_outputs,
        status=AnalysisPlan.Status.DRAFT,
    )
    return serialize_analysis_plan(plan)


def list_analysis_plans(project: Project) -> list[dict]:
    _require_data_project(project)
    return [serialize_analysis_plan(p) for p in project.analysis_plans.all()]


def get_analysis_plan(project: Project, plan_id) -> dict:
    _require_data_project(project)
    return serialize_analysis_plan(_get_plan(project, plan_id))


def update_analysis_plan(project: Project, plan_id, patch: dict) -> dict:
    _require_data_project(project)
    plan = _get_plan(project, plan_id)
    if not isinstance(patch, dict) or not patch:
        raise ProjectWorkflowError("invalid_analysis_plan", "Provide fields to update.")
    unknown = sorted(set(patch) - set(EDITABLE_FIELDS))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_analysis_plan", f"Unknown field(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    current = {
        "business_question": plan.business_question,
        "method": plan.method,
        "hypotheses": plan.hypotheses,
        "required_metrics": plan.required_metrics,
        "segments": plan.segments,
        "comparisons": plan.comparisons,
        "time_range": plan.time_range or None,
        "expected_outputs": plan.expected_outputs,
    }
    merged = {**current, **patch}
    try:
        content = AnalysisPlanContent.model_validate(merged)
        validate_plan_references(project, content)
    except (ValidationError, ValueError) as error:
        details = (
            _pydantic_details(error) if isinstance(error, ValidationError)
            else [{"loc": "plan", "msg": str(error)}]
        )
        raise ProjectWorkflowError(
            "invalid_analysis_plan", "The edited Analysis Plan is not valid.",
            details={"errors": details},
        )

    was_approved = plan.status == AnalysisPlan.Status.APPROVED
    with transaction.atomic():
        plan.business_question = content.business_question
        plan.method = content.method
        plan.hypotheses = content.hypotheses
        plan.required_metrics = content.required_metrics
        plan.segments = content.segments
        plan.comparisons = [c.model_dump(mode="json") for c in content.comparisons]
        plan.time_range = content.time_range or {}
        plan.expected_outputs = content.expected_outputs
        # editing an approved plan always reverts it to draft. Past
        # AnalysisResults are separate immutable rows (FK to this plan) and
        # are never touched, deleted, or mutated by this.
        plan.status = AnalysisPlan.Status.DRAFT
        plan.approved_at = None
        plan.save()
        if was_approved:
            project.context_digest = build_context_digest(project)
            fields = ["context_digest", "updated_at"]
            # this plan was authoritative and just changed -> Dashboard needs
            # review (no direct panel<->plan ref exists, see stale.py policy)
            impact = propagate_analysis_plan_change(plan, project=project)
            if project_level_changed(impact):
                fields.append("downstream_stale")
            project.save(update_fields=fields)
    return serialize_analysis_plan(plan)


def approve_analysis_plan(project: Project, plan_id) -> dict:
    _require_data_project(project)
    plan = _get_plan(project, plan_id)
    if plan.status != AnalysisPlan.Status.DRAFT:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"The plan cannot be approved from status '{plan.status}'.", status=409,
        )
    with transaction.atomic():
        plan.status = AnalysisPlan.Status.APPROVED
        plan.approved_at = dj_timezone.now()
        plan.save(update_fields=["status", "approved_at", "updated_at"])
    return serialize_analysis_plan(plan)


# --- run (deterministic execution) -----------------------------------------


def run_analysis_plan(project: Project, plan_id) -> dict:
    _require_data_project(project)
    plan = _get_plan(project, plan_id)
    if plan.status != AnalysisPlan.Status.APPROVED:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Approve the Analysis Plan before running it.", status=409,
        )

    try:
        content = AnalysisPlanContent.model_validate({
            "business_question": plan.business_question,
            "method": plan.method,
            "hypotheses": plan.hypotheses,
            "required_metrics": plan.required_metrics,
            "segments": plan.segments,
            "comparisons": plan.comparisons,
            "time_range": plan.time_range or None,
            "expected_outputs": plan.expected_outputs,
        })
        validate_plan_references(project, content)
        metrics = _resolve_required_metrics(project, content.required_metrics)
        datasets_by_metric = _datasets_by_metric(project, metrics)
    except (ValidationError, ValueError) as error:
        raise ProjectWorkflowError(
            "invalid_analysis_plan",
            f"The plan is no longer valid against current data: {error}", status=409,
        )

    job = Job.objects.create(
        project=project, kind=Job.Kind.RUN_ANALYSIS, status=Job.Status.RUNNING,
        started_at=dj_timezone.now(), params={"analysis_plan_id": str(plan.id)},
    )

    try:
        queries, datasets, finalize = compile_analysis(
            project, plan.business_id, content, metrics, datasets_by_metric
        )
    except UnsupportedAnalysisError as exc:
        job.status = Job.Status.FAILED
        job.error = exc.message[:2000]
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise ProjectWorkflowError(
            "unsupported_analysis", exc.message, status=422, details=exc.details,
        )

    try:
        ex = DuckDBExecution()
        raw_results = ex.run_many(queries, datasets=datasets)
    except (SqlValidationError, QueryExecutionError) as exc:
        job.status = Job.Status.FAILED
        job.error = exc.message[:2000]
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise ProjectWorkflowError(
            "analysis_execution_failed", f"Execution failed: {exc.message}", status=422,
            details={"job_id": str(job.id), "code": exc.code},
        )

    findings = finalize(raw_results)
    fields_used = _available_fields(project, metrics) & (
        set(content.segments) | {f.field for c in content.comparisons for f in c.filters}
    )
    caveats = build_data_caveats(project, list(datasets_by_metric.values()), fields_used)

    with transaction.atomic():
        result = AnalysisResult.objects.create(
            project=project, plan=plan, job=job, findings=findings, data_caveats=caveats,
        )
        job.status = Job.Status.SUCCEEDED
        job.progress = 100
        job.result_ref = {"analysis_result": str(result.id)}
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "progress", "result_ref", "finished_at"])
        # a fresh successful run is this plan's own reconciliation step —
        # "re-run Analysis after upstream changes" clears it, not mere
        # re-approval
        clear_analysis_plan_stale(plan)
        # a plan with >=1 result becomes digest-eligible (bounded, factual-only
        # summary) regardless of the plan's current draft/approved status
        project.context_digest = build_context_digest(project)
        project.save(update_fields=["context_digest", "updated_at"])
    return serialize_analysis_result(result)


# --- serialization -----------------------------------------------------


def serialize_analysis_result(result: AnalysisResult) -> dict:
    from projects.data.insights_services import serialize_insight

    return {
        "id": str(result.id),
        "plan_id": str(result.plan_id),
        "plan_business_id": result.plan.business_id,
        "job_id": str(result.job_id) if result.job_id else None,
        "findings": result.findings,
        "data_caveats": result.data_caveats,
        "created_at": result.created_at.isoformat(),
        "insights": [serialize_insight(i) for i in result.insights.all()],
    }


def serialize_analysis_plan(plan: AnalysisPlan) -> dict:
    results = list(plan.results.all()[:20])
    return {
        "id": str(plan.id),
        "business_id": plan.business_id,
        "business_question": plan.business_question,
        "method": plan.method,
        "hypotheses": plan.hypotheses,
        "required_metrics": plan.required_metrics,
        "segments": plan.segments,
        "comparisons": plan.comparisons,
        "time_range": plan.time_range,
        "expected_outputs": plan.expected_outputs,
        "status": plan.status,
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        "stale": plan.stale,
        "stale_reason": plan.stale_reason,
        "stale_since": plan.stale_since.isoformat() if plan.stale_since else None,
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
        "results": [
            {
                "id": str(r.id), "created_at": r.created_at.isoformat(),
                "findings_count": len(r.findings),
            }
            for r in results
        ],
        "latest_result_id": str(results[0].id) if results else None,
    }
