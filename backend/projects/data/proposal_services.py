"""
Data Proposal targets + application (Phase I-5).

Mirrors ``projects.conversation_services``'s Software `_SUPPORTED_TARGETS` /
`_APPLY` design exactly, but for the 8 Data human-decision artifacts. A
proposal is applied ONLY through the artifact's own existing domain service —
never by writing JSON/model fields directly from Conversation code — so
validation, normalization, stale propagation and project isolation all stay
centralized in one place per artifact.

Four targets are Project-level singular artifacts (apply_fn(project, sections)
-> Project|dict, same shape as Software's apply functions); four are
multi-instance entities addressed by a business id or dataset id
(apply_fn(project, entity_id, sections) -> dict) — ``entity_id`` comes from
the AI's ``DataProposedChange.entity_id`` and is resolved to the row's real
primary key here, never trusted as a raw id straight from the model.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError

from projects.data.analysis_services import update_analysis_plan
from projects.data.dashboard_services import update_dashboard_blueprint
from projects.data.metrics_services import update_metric
from projects.data.query_services import update_query_plan
from projects.data.quality_services import update_data_quality
from projects.data.services import update_data_brief, update_source_interpretation
from projects.data.transformation_services import update_transformation_plan
from projects.exceptions import ProjectWorkflowError
from projects.models import AnalysisPlan, Dataset, MetricDefinition, Query

# Kept in sync with ai.operations.data_conversation_response.DATA_PROPOSAL_TARGETS.
DATA_PROPOSAL_TARGETS = (
    "data_brief",
    "source_interpretation",
    "data_quality",
    "transformation_plan",
    "metric",
    "query_plan",
    "analysis_plan",
    "dashboard_blueprint",
)

# Targets whose apply_fn is (project, sections) -> Project|dict.
_PROJECT_LEVEL_APPLY = {
    "data_brief": update_data_brief,
    "data_quality": update_data_quality,
    "transformation_plan": update_transformation_plan,
    "dashboard_blueprint": update_dashboard_blueprint,
}

# Targets whose apply_fn is (project, entity_pk, sections) -> dict, plus how
# to resolve a human-facing entity_id (a business id, or a dataset id) to the
# row's real primary key, scoped to THIS project (never cross-project).
_ENTITY_LEVEL_APPLY = {
    "source_interpretation": update_source_interpretation,
    "metric": update_metric,
    "query_plan": update_query_plan,
    "analysis_plan": update_analysis_plan,
}


def _resolve_entity_pk(project, target: str, entity_id: str):
    entity_id = (entity_id or "").strip()
    if not entity_id:
        raise ProjectWorkflowError(
            "invalid_proposal_entity", f"{target} proposals require an entity_id.", status=422,
        )
    try:
        if target == "source_interpretation":
            return Dataset.objects.get(project=project, id=entity_id).id
        if target == "metric":
            return MetricDefinition.objects.get(project=project, business_id=entity_id).id
        if target == "query_plan":
            return Query.objects.get(project=project, business_id=entity_id).id
        if target == "analysis_plan":
            return AnalysisPlan.objects.get(project=project, business_id=entity_id).id
    except (
        Dataset.DoesNotExist, MetricDefinition.DoesNotExist,
        Query.DoesNotExist, AnalysisPlan.DoesNotExist,
        ValueError, TypeError, DjangoValidationError,
    ):
        raise ProjectWorkflowError(
            "invalid_proposal_entity",
            f"No {target} entity {entity_id!r} in this project.",
            status=422,
            details={"target_artifact": target, "entity_id": entity_id},
        )
    raise ProjectWorkflowError("unsupported_proposal_target", f"Unknown target: {target}", status=422)


def apply_data_proposal(project, target: str, entity_id: str, sections: dict):
    """Apply through the artifact's own domain service. Any validation/
    workflow error from that service propagates unchanged — nothing was
    mutated if it raises. Returns whatever that service returns (a dict
    summary, or a Project for data_brief)."""
    if target in _PROJECT_LEVEL_APPLY:
        return _PROJECT_LEVEL_APPLY[target](project, sections)
    if target in _ENTITY_LEVEL_APPLY:
        pk = _resolve_entity_pk(project, target, entity_id)
        return _ENTITY_LEVEL_APPLY[target](project, pk, sections)
    raise ProjectWorkflowError(
        "unsupported_proposal_target", f"Proposals cannot modify '{target}'.", status=422,
        details={"target_artifact": target},
    )


# --- impact summary (deterministic, lineage + stale-chain based) ----------


def _project_level_impact(project, target: str) -> list[str]:
    """Mirrors the exact scoping ``projects.data.stale``'s propagate_*
    functions use for project-level artifacts — a preview, not a mutation."""
    affected: list[str] = []
    if target == "data_brief":
        if project.data_quality_approved_at:
            affected.append("data_quality")
        if project.transformation_plan_approved_at:
            affected.append("transformation_plan")
        affected += list(
            project.metrics.filter(status="approved").values_list("business_id", flat=True)
        )
        affected += list(
            project.queries.filter(status__in=["reviewed", "executed"]).values_list("business_id", flat=True)
        )
        affected += list(
            project.analysis_plans.filter(status="approved").values_list("business_id", flat=True)
        )
        if project.dashboard_blueprint_approved_at:
            affected.append("dashboard_blueprint")
    elif target == "data_quality":
        if project.transformation_plan_approved_at:
            affected.append("transformation_plan")
        affected += list(
            project.metrics.filter(status="approved").values_list("business_id", flat=True)
        )
        affected += list(
            project.queries.filter(status__in=["reviewed", "executed"]).values_list("business_id", flat=True)
        )
        affected += list(
            project.analysis_plans.filter(status="approved").values_list("business_id", flat=True)
        )
        if project.dashboard_blueprint_approved_at:
            affected.append("dashboard_blueprint")
    elif target == "transformation_plan":
        affected += list(
            project.metrics.filter(status="approved").values_list("business_id", flat=True)
        )
        affected += list(
            project.queries.filter(status__in=["reviewed", "executed"]).values_list("business_id", flat=True)
        )
        affected += list(
            project.analysis_plans.filter(status="approved").values_list("business_id", flat=True)
        )
        if project.dashboard_blueprint_approved_at:
            affected.append("dashboard_blueprint")
    return affected


def data_impact_summary(project, target: str, entity_id: str = "") -> dict:
    """Deterministic. Uses the Data dependency chain (project-level targets)
    or the Data Lineage index (entity-scoped targets — reuses
    ``resolve_lineage``'s downstream set directly, no separate graph)."""
    if target in DATA_PROPOSAL_TARGETS and target in _PROJECT_LEVEL_APPLY:
        downstream = _project_level_impact(project, target)
    elif target == "source_interpretation":
        # informational-only in this MVP — nothing downstream computationally
        # depends on interpretation content (documented in stale.py)
        downstream = []
    elif target in ("metric", "query_plan", "analysis_plan"):
        from projects.data.lineage import resolve_lineage

        node = entity_id or ""
        downstream = resolve_lineage(project, node)["downstream"] if node else []
    else:
        downstream = []

    notes = [
        f"Applying this reverts {target.replace('_', ' ')} to a state needing "
        "re-review (re-approve, re-review, or re-run, depending on the "
        "artifact) — its history and prior facts are kept, never deleted.",
    ]
    if downstream:
        notes.append(
            "These downstream items may need review (kept, not deleted, not "
            "unapproved): " + ", ".join(downstream) + "."
        )
    else:
        notes.append("No downstream artifacts would be affected yet.")
    notes.append(
        "Deterministic history (profiling, quality checks, metric "
        "validations, query runs, analysis results, insights) is preserved."
    )
    return {
        "target_artifact": target,
        "entity_id": entity_id,
        "downstream_review_candidates": downstream,
        "stale_propagation_possible": bool(downstream),
        "notes": notes,
    }
