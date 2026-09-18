"""
Dashboard Blueprint domain services (Phase I-4): generate -> edit -> approve,
then a generic Dashboard Build Prompt from the approved blueprint. A design
artifact only — no dashboard engine, no BI-tool-specific execution.
"""
from __future__ import annotations

from datetime import datetime, timezone

from django.db import transaction
from django.utils import timezone as dj_timezone
from pydantic import ValidationError

from ai.base import run_operation
from ai.exceptions import AIOperationError
from ai.operations.dashboard_blueprint_generation import DASHBOARD_BLUEPRINT_GENERATION
from ai.operations.dashboard_build_prompt_generation import DASHBOARD_BUILD_PROMPT_GENERATION
from ai.client import get_model
from projects.context import build_context_digest
from projects.data.dashboard import (
    SECTION_FIELDS,
    DashboardBlueprintContent,
    normalize_dashboard_blueprint_content,
)
from projects.data.stale import clear_data_stale
from projects.exceptions import ProjectWorkflowError
from projects.models import DashboardBuildPrompt, Insight, MetricDefinition, Project


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pydantic_details(error: ValidationError) -> list[dict]:
    return [
        {"loc": ".".join(str(p) for p in i["loc"]), "msg": i["msg"]}
        for i in error.errors()
    ]


def _content(project: Project) -> dict:
    return dict((project.dashboard_blueprint or {}).get("content") or {})


def _validate_references(project: Project, content: DashboardBlueprintContent) -> None:
    approved_kpis = set(
        project.metrics.filter(status=MetricDefinition.Status.APPROVED).values_list(
            "business_id", flat=True
        )
    )
    accepted_insights = set(
        project.insights.filter(status=Insight.Status.ACCEPTED).values_list(
            "business_id", flat=True
        )
    )
    for p in content.panels:
        for ref in p.metric_refs:
            if ref not in approved_kpis:
                raise ValueError(f"panel {p.title!r} references an unapproved/unknown KPI: {ref!r}")
        for ref in p.insight_refs:
            if ref not in accepted_insights:
                raise ValueError(
                    f"panel {p.title!r} references an insight that is not accepted: {ref!r}"
                )


def _ai_context(project: Project) -> dict:
    metrics = [
        {"business_id": m.business_id, "name": m.name, "formula_text": m.formula_text}
        for m in project.metrics.filter(status=MetricDefinition.Status.APPROVED)
    ]
    analyses = []
    for plan in project.analysis_plans.all():
        latest = plan.results.first()
        if not latest:
            continue
        analyses.append({
            "business_id": plan.business_id, "method": plan.method,
            "business_question": plan.business_question,
            "headline_statements": [f["statement"] for f in latest.findings[:2]],
        })
    insights = [
        {"business_id": i.business_id, "interpretation": i.interpretation}
        for i in project.insights.filter(status=Insight.Status.ACCEPTED)
    ]
    return {
        "data_brief": (project.data_brief or {}).get("content") or {},
        "metrics": metrics,
        "analyses": analyses,
        "insights": insights,
    }


def generate_dashboard_blueprint(project: Project) -> dict:
    from projects.data.services import _require_data_project

    _require_data_project(project)
    if not project.metrics.filter(status=MetricDefinition.Status.APPROVED).exists():
        raise ProjectWorkflowError(
            "no_approved_metrics",
            "Approve at least one KPI before generating a Dashboard Blueprint.",
            status=409,
        )
    draft = run_operation(DASHBOARD_BLUEPRINT_GENERATION, _ai_context(project), project=project)
    raw = draft.model_dump(mode="json")

    try:
        content = DashboardBlueprintContent.model_validate(raw)
        _validate_references(project, content)
    except (ValidationError, ValueError) as error:
        raise AIOperationError(
            code="ai_invalid_output",
            message="The proposed Dashboard Blueprint referenced data that does not exist.",
            retryable=True,
            details={"error": str(error)},
        )

    normalized = normalize_dashboard_blueprint_content(content.model_dump(mode="json"))
    with transaction.atomic():
        project.dashboard_blueprint = {
            "content": normalized, "generated_at": _now_iso(),
            "updated_at": _now_iso(), "approved_at": None,
        }
        project.dashboard_blueprint_approved_at = None
        project.save(update_fields=["dashboard_blueprint", "dashboard_blueprint_approved_at", "updated_at"])
    return serialize_dashboard(project)


def update_dashboard_blueprint(project: Project, patch) -> dict:
    from projects.data.services import _require_data_project

    _require_data_project(project)
    current = _content(project)
    if not current:
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Generate a Dashboard Blueprint first.", status=409
        )
    if not isinstance(patch, dict) or not patch:
        raise ProjectWorkflowError("invalid_dashboard", "Provide one or more sections to update.")
    unknown = sorted(set(patch) - set(SECTION_FIELDS))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_dashboard", f"Unknown section(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    merged = {**current, **patch}
    try:
        validated = DashboardBlueprintContent.model_validate(merged)
        _validate_references(project, validated)
    except (ValidationError, ValueError) as error:
        details = (
            _pydantic_details(error) if isinstance(error, ValidationError)
            else [{"loc": "content", "msg": str(error)}]
        )
        raise ProjectWorkflowError(
            "invalid_dashboard", "The edited Dashboard Blueprint is not valid.",
            details={"errors": details},
        )

    normalized = normalize_dashboard_blueprint_content(validated.model_dump(mode="json"))
    was_approved = project.dashboard_blueprint_approved_at is not None
    with transaction.atomic():
        project.dashboard_blueprint["content"] = normalized
        project.dashboard_blueprint["updated_at"] = _now_iso()
        project.dashboard_blueprint["approved_at"] = None
        project.dashboard_blueprint_approved_at = None
        fields = ["dashboard_blueprint", "dashboard_blueprint_approved_at", "updated_at"]
        if was_approved:
            project.context_digest = build_context_digest(project)
            fields.append("context_digest")
        project.save(update_fields=fields)
    return serialize_dashboard(project)


def approve_dashboard_blueprint(project: Project) -> dict:
    from projects.data.services import _require_data_project

    _require_data_project(project)
    if not _content(project):
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Generate a Dashboard Blueprint first.", status=409
        )
    with transaction.atomic():
        now = dj_timezone.now()
        project.dashboard_blueprint["approved_at"] = now.isoformat()
        project.dashboard_blueprint_approved_at = now
        # re-approving is this artifact's own reconciliation step (dashboard
        # is terminal in the chain — nothing propagates further from here)
        clear_data_stale(project, "dashboard_blueprint")
        project.context_digest = build_context_digest(project)
        project.save(update_fields=[
            "dashboard_blueprint", "dashboard_blueprint_approved_at",
            "downstream_stale", "context_digest", "updated_at",
        ])
    return serialize_dashboard(project)


def generate_dashboard_build_prompt(project: Project) -> dict:
    from projects.data.services import _require_data_project

    _require_data_project(project)
    if not project.dashboard_blueprint_approved_at:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Approve the Dashboard Blueprint before generating a build prompt.", status=409,
        )
    content = _content(project)
    refs = {r for p in content.get("panels", []) for r in p.get("metric_refs", [])}
    metrics = [
        {"business_id": m.business_id, "name": m.name, "formula_text": m.formula_text}
        for m in project.metrics.filter(business_id__in=refs, status=MetricDefinition.Status.APPROVED)
    ]
    ai_ctx = {"blueprint": content, "metrics": metrics}
    result = run_operation(DASHBOARD_BUILD_PROMPT_GENERATION, ai_ctx, project=project)
    text = result.prompt_markdown.strip()

    with transaction.atomic():
        DashboardBuildPrompt.objects.create(
            project=project, content=text, context_snapshot=ai_ctx, model=get_model(),
        )
    return serialize_dashboard(project)


def serialize_dashboard(project: Project) -> dict:
    latest = project.dashboard_build_prompts.first()
    return {
        "content": _content(project) or None,
        "approved": bool(project.dashboard_blueprint_approved_at),
        "approved_at": (
            project.dashboard_blueprint_approved_at.isoformat()
            if project.dashboard_blueprint_approved_at else None
        ),
        "generated_at": (project.dashboard_blueprint or {}).get("generated_at"),
        "updated_at": (project.dashboard_blueprint or {}).get("updated_at"),
        "latest_build_prompt": (
            {
                "id": str(latest.id), "content": latest.content,
                "model": latest.model, "created_at": latest.created_at.isoformat(),
            }
            if latest else None
        ),
    }
