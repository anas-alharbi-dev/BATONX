"""
Insight domain services (Phase I-4): generate (batch, AI, evidence-validated)
-> accept (explicit human action only). Acceptance never alters the underlying
AnalysisResult — it only records that a human accepts the interpretation.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone as dj_timezone

from ai.base import run_operation
from ai.exceptions import AIOperationError
from ai.operations.insight_generation import INSIGHT_GENERATION
from projects.data.insights import validate_insight_evidence
from projects.data.services import _require_data_project, next_business_id
from projects.exceptions import ProjectWorkflowError
from projects.models import AnalysisResult, Insight, Project


def _get_insight(project: Project, insight_id) -> Insight:
    from django.core.exceptions import ValidationError as DjangoValidationError

    try:
        return Insight.objects.get(id=insight_id, project=project)
    except (Insight.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ProjectWorkflowError(
            "insight_not_found", "No such Insight for this project.", status=404
        )


def generate_insights(project: Project, result_id) -> list[dict]:
    _require_data_project(project)
    from projects.data.analysis_services import _get_result

    result = _get_result(project, result_id)
    if not result.findings:
        raise ProjectWorkflowError(
            "no_findings", "This Analysis Result has no findings to interpret.", status=409
        )

    ai_ctx = {
        "findings": result.findings,
        "data_brief": (project.data_brief or {}).get("content") or {},
        "data_caveats": result.data_caveats,
    }
    draft = run_operation(INSIGHT_GENERATION, ai_ctx, project=project)
    proposed = draft.model_dump(mode="json").get("insights", [])
    if not proposed:
        raise AIOperationError(
            code="ai_invalid_output",
            message="No insights were proposed.",
            retryable=True,
        )

    for fields in proposed:
        try:
            validate_insight_evidence(result.findings, fields)
        except ValueError as error:
            raise AIOperationError(
                code="ai_invalid_output",
                message="A proposed insight could not be reconciled with the computed findings.",
                retryable=True,
                details={"fact": fields.get("fact"), "error": str(error)},
            )

    created: list[Insight] = []
    with transaction.atomic():
        for fields in proposed:
            bid = next_business_id(project, Insight, "INS")
            insight = Insight.objects.create(
                business_id=bid, project=project, analysis_result=result,
                fact=fields["fact"], interpretation=fields.get("interpretation", ""),
                recommendation=fields.get("recommendation", ""),
                confidence=fields.get("confidence", "medium"),
                supporting_finding_ids=fields["supporting_finding_ids"],
                caveats=fields.get("caveats", []),
                status=Insight.Status.DRAFT,
            )
            created.append(insight)
    return [serialize_insight(i) for i in created]


def accept_insight(project: Project, insight_id) -> dict:
    """The ONLY way an Insight becomes accepted — an explicit human action.
    Never touches AnalysisResult; acceptance is a decision about the
    interpretation, not the facts."""
    _require_data_project(project)
    insight = _get_insight(project, insight_id)
    if insight.status != Insight.Status.DRAFT:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"Cannot accept from status '{insight.status}'.", status=409,
        )
    with transaction.atomic():
        insight.status = Insight.Status.ACCEPTED
        insight.accepted_at = dj_timezone.now()
        insight.save(update_fields=["status", "accepted_at", "updated_at"])
        from projects.context import build_context_digest

        project.context_digest = build_context_digest(project)
        project.save(update_fields=["context_digest", "updated_at"])
    return serialize_insight(insight)


def serialize_insight(i: Insight) -> dict:
    return {
        "id": str(i.id),
        "business_id": i.business_id,
        "analysis_result_id": str(i.analysis_result_id),
        "fact": i.fact,
        "interpretation": i.interpretation,
        "recommendation": i.recommendation,
        "confidence": i.confidence,
        "supporting_finding_ids": i.supporting_finding_ids,
        "caveats": i.caveats,
        "status": i.status,
        "accepted_at": i.accepted_at.isoformat() if i.accepted_at else None,
        "created_at": i.created_at.isoformat(),
        "updated_at": i.updated_at.isoformat(),
    }
