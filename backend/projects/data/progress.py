"""
Deterministic Data Progress (Phase I-5) — the Data analogue of
``projects.progress``, but stage/artifact based rather than task based (a Data
project has no Roadmap). No AI: every status here is derived from stored,
authoritative state.

Nine implemented-MVP stages. Data Model and Pipeline Design are NOT stages
here — they are not implemented; nothing below may claim they are complete.
Which of the 9 stages are actually *required* (vs. optional/skipped) depends
on ``Project.data_goal`` — see ``_REQUIRED_STAGES_BY_GOAL``. A goal that would
eventually need Data Model / Pipeline Design (engineering, warehouse, mixed)
gets an honest ``deferred_future_stages`` note; it never fabricates those
stages as present.
"""
from __future__ import annotations

from projects.data.quality import critical_unresolved_count
from projects.data.stale import is_data_stale

STAGES: tuple[tuple[str, str], ...] = (
    ("data_brief", "Data Brief"),
    ("sources", "Sources & Profiling"),
    ("data_quality", "Data Quality"),
    ("transformation_plan", "Transformation Plan"),
    ("metrics", "Metrics / KPIs"),
    ("queries", "Queries"),
    ("analysis", "Analysis & Insights"),
    ("dashboard", "Dashboard Blueprint"),
    ("delivery_readiness", "Delivery Readiness"),
)

# Which of the 9 stages are REQUIRED for a given data_goal. Stages not listed
# are reported with status "skipped" and excluded from the completion
# denominator — never silently marked complete. "quality"/"engineering"/
# "warehouse" don't require Metrics/Queries/Analysis/Dashboard in this MVP
# (their value is the data foundation, not the analysis layer); Delivery
# Readiness is always required as the final gate.
_REQUIRED_STAGES_BY_GOAL: dict[str, tuple[str, ...]] = {
    "analytics": (
        "data_brief", "sources", "data_quality", "transformation_plan",
        "metrics", "queries", "analysis", "dashboard", "delivery_readiness",
    ),
    "bi": (
        "data_brief", "sources", "data_quality", "transformation_plan",
        "metrics", "queries", "analysis", "dashboard", "delivery_readiness",
    ),
    "mixed": (
        "data_brief", "sources", "data_quality", "transformation_plan",
        "metrics", "queries", "analysis", "dashboard", "delivery_readiness",
    ),
    "quality": ("data_brief", "sources", "data_quality", "delivery_readiness"),
    "engineering": (
        "data_brief", "sources", "data_quality", "transformation_plan", "delivery_readiness",
    ),
    "warehouse": (
        "data_brief", "sources", "data_quality", "transformation_plan", "delivery_readiness",
    ),
}
_DEFAULT_REQUIRED = _REQUIRED_STAGES_BY_GOAL["analytics"]

# goals whose eventual full workflow would need Data Model / Pipeline Design —
# not implemented yet; surfaced as an honest, transparent note only.
_GOALS_WANTING_FUTURE_STAGES = frozenset({"engineering", "warehouse", "mixed"})


def _required_stages(project) -> tuple[str, ...]:
    return _REQUIRED_STAGES_BY_GOAL.get(project.data_goal, _DEFAULT_REQUIRED)


# --- per-stage status -----------------------------------------------------


def _data_brief_status(project) -> tuple[str, list[str]]:
    if not (project.data_brief or {}).get("content"):
        return "not_started", []
    if not project.data_brief_approved_at:
        return "needs_review", ["Data Brief generated but not approved."]
    return "complete", []


def _sources_status(project) -> tuple[str, list[str]]:
    datasets = list(project.datasets.all())
    if not datasets:
        return "not_started", []
    profiled = [d for d in datasets if d.status == "profiled"]
    failed = [d for d in datasets if d.status == "failed"]
    if not profiled:
        if failed:
            return "blocked", [f"{d.name}: profiling failed — {d.error}" for d in failed]
        return "in_progress", []
    unapproved = [d for d in profiled if not d.interpretation_approved_at]
    if unapproved:
        return "needs_review", [f"{d.name}: source interpretation not approved" for d in unapproved]
    stale = [d for d in profiled if d.interpretation_stale]
    if stale:
        return "needs_review", [f"{d.name}: source interpretation is stale" for d in stale]
    return "complete", []


def _data_quality_status(project) -> tuple[str, list[str]]:
    dq = (project.data_quality or {}).get("content") or {}
    if not dq.get("observations"):
        return "not_started", []
    if not dq.get("rules"):
        return "in_progress", ["Observations derived — propose quality rules next."]
    if not project.data_quality_approved_at:
        return "needs_review", ["Quality rules proposed but not approved."]
    if is_data_stale(project, "data_quality"):
        return "needs_review", ["Data Quality is stale — an upstream artifact changed."]
    unresolved = critical_unresolved_count(dq)
    if unresolved:
        return "blocked", [f"{unresolved} unresolved critical quality issue(s)."]
    if not project.quality_check_runs.exists():
        return "needs_review", ["Approved rules have not been checked against the data yet."]
    return "complete", []


def _transformation_status(project) -> tuple[str, list[str]]:
    content = (project.transformation_plan or {}).get("content")
    if not content:
        return "not_started", []
    if not project.transformation_plan_approved_at:
        return "needs_review", ["Transformation Plan generated but not approved."]
    if is_data_stale(project, "transformation_plan"):
        return "needs_review", ["Transformation Plan is stale — an upstream artifact changed."]
    return "complete", []


def _metrics_status(project) -> tuple[str, list[str]]:
    metrics = list(project.metrics.all())
    if not metrics:
        return "not_started", []
    draft = [m for m in metrics if m.status != "approved"]
    if draft:
        return "needs_review", [f"{m.business_id} not approved." for m in draft]
    stale = [m for m in metrics if m.stale]
    if stale:
        return "needs_review", [f"{m.business_id} is stale." for m in stale]
    unvalidated = [m for m in metrics if not m.validation_runs.filter(passed=True).exists()]
    if unvalidated:
        return "needs_review", [f"{m.business_id} has no successful validation." for m in unvalidated]
    return "complete", []


def _queries_status(project) -> tuple[str, list[str]]:
    queries = list(project.queries.all())
    if not queries:
        return "not_started", []
    not_ready = [q for q in queries if q.status not in ("reviewed", "executed")]
    if not_ready:
        return "needs_review", [f"{q.business_id} not yet reviewed." for q in not_ready]
    stale = [q for q in queries if q.stale]
    if stale:
        return "needs_review", [f"{q.business_id} is stale." for q in stale]
    return "complete", []


def _analysis_status(project) -> tuple[str, list[str]]:
    plans = list(project.analysis_plans.all())
    if not plans:
        return "not_started", []
    draft = [p for p in plans if p.status != "approved"]
    if draft:
        return "needs_review", [f"{p.business_id} not approved." for p in draft]
    unrun = [p for p in plans if not p.results.exists()]
    if unrun:
        return "needs_review", [f"{p.business_id} approved but never run." for p in unrun]
    stale = [p for p in plans if p.stale]
    if stale:
        return "needs_review", [f"{p.business_id} is stale." for p in stale]
    # Insight acceptance policy: if insights were generated for a plan's
    # latest result, at least one must be accepted (insights themselves have
    # no "reject" state — declining to accept any of them is not a decision
    # VYRA can treat as final without a human confirming it via acceptance).
    unresolved = []
    for p in plans:
        latest = p.results.first()
        if latest and latest.insights.exists() and not latest.insights.filter(status="accepted").exists():
            unresolved.append(p.business_id)
    if unresolved:
        return "needs_review", [f"{pid}: generated insights are not yet accepted." for pid in unresolved]
    return "complete", []


def _dashboard_status(project) -> tuple[str, list[str]]:
    content = (project.dashboard_blueprint or {}).get("content")
    if not content:
        return "not_started", []
    if not project.dashboard_blueprint_approved_at:
        return "needs_review", ["Dashboard Blueprint generated but not approved."]
    if is_data_stale(project, "dashboard_blueprint"):
        return "needs_review", ["Dashboard Blueprint is stale — an upstream artifact changed."]
    return "complete", []


def _delivery_readiness_status(project) -> tuple[str, list[str]]:
    from projects.data.readiness import READY_TO_DELIVER, compute_data_readiness

    readiness = compute_data_readiness(project)
    if readiness["overall_status"] == READY_TO_DELIVER:
        return "complete", []
    blockers = [b["title"] for b in readiness["blockers"]]
    if blockers:
        return "blocked", blockers
    return "needs_review", [f"{readiness['pending_manual_confirmations']} manual confirmation(s) pending."]


_STATUS_FN = {
    "data_brief": _data_brief_status,
    "sources": _sources_status,
    "data_quality": _data_quality_status,
    "transformation_plan": _transformation_status,
    "metrics": _metrics_status,
    "queries": _queries_status,
    "analysis": _analysis_status,
    "dashboard": _dashboard_status,
    "delivery_readiness": _delivery_readiness_status,
}

_HREF = {
    "data_brief": "data-overview",
    "sources": "data-sources",
    "data_quality": "data-quality",
    "transformation_plan": "data-build",
    "metrics": "data-metrics",
    "queries": "data-queries",
    "analysis": "data-analysis",
    "dashboard": "data-analysis",
    "delivery_readiness": "data-readiness",
}

_NEXT_ACTION_LABEL = {
    "data_brief": "Approve the Data Brief",
    "sources": "Profile a dataset",
    "data_quality": "Review Quality Rules",
    "transformation_plan": "Approve the Transformation Plan",
    "metrics": "Review KPI definitions",
    "queries": "Review Query SQL",
    "analysis": "Run the Analysis Plan",
    "dashboard": "Review the Dashboard Blueprint",
    "delivery_readiness": "Complete Delivery Readiness",
}


def _next_action(project, stages: list[dict]) -> dict | None:
    """First non-complete, non-skipped stage, with a specific deterministic
    label where a concrete blocking entity is known."""
    for s in stages:
        if s["status"] in ("complete", "skipped"):
            continue
        label = _NEXT_ACTION_LABEL[s["id"]]
        if s["blockers"]:
            first = s["blockers"][0]
            # blockers are "{business_id} ...": lift the id into a specific label
            bid = first.split(" ", 1)[0].split(":", 1)[0]
            if s["id"] == "metrics" and bid.startswith("KPI-"):
                label = f"Approve or validate {bid}"
            elif s["id"] == "queries" and bid.startswith("Q-"):
                label = f"Mark {bid} reviewed"
            elif s["id"] == "analysis" and bid.startswith("AN-"):
                label = f"Run {bid}" if "never run" in first else f"Review {bid}"
        return {"stage": s["id"], "label": label, "href": _HREF[s["id"]]}
    return None


def compute_data_progress(project) -> dict:
    """The authoritative operational view of Data MVP status. Pure function of
    stored project state. Always viewable — even "not_started" is useful
    signal, unlike Software's task-based progress which needs an approved
    Roadmap to mean anything."""
    from projects.data.services import _require_data_project

    _require_data_project(project)
    required = set(_required_stages(project))

    stages = []
    for stage_id, name in STAGES:
        if stage_id not in required:
            stages.append({"id": stage_id, "name": name, "status": "skipped", "blockers": []})
            continue
        status, blockers = _STATUS_FN[stage_id](project)
        stages.append({"id": stage_id, "name": name, "status": status, "blockers": blockers})

    counted = [s for s in stages if s["status"] != "skipped"]
    total = len(counted)
    complete = sum(1 for s in counted if s["status"] == "complete")
    in_review = sum(1 for s in counted if s["status"] == "needs_review")
    blocked = sum(1 for s in counted if s["status"] == "blocked")
    skipped = len(stages) - total

    dq = (project.data_quality or {}).get("content") or {}
    open_critical = critical_unresolved_count(dq)
    pending_proposals = project.proposals.filter(status="pending").count()

    from projects.data.stale import (
        data_stale_artifacts,
        stale_analysis_plan_ids,
        stale_dataset_interpretation_ids,
        stale_metric_ids,
        stale_query_ids,
    )

    stale_context = (
        data_stale_artifacts(project)
        + [f"dataset:{d}" for d in stale_dataset_interpretation_ids(project)]
        + stale_metric_ids(project)
        + stale_query_ids(project)
        + stale_analysis_plan_ids(project)
    )

    summary = {
        "stages_total": total,
        "stages_complete": complete,
        "stages_in_review": in_review,
        "stages_blocked": blocked,
        "stages_skipped": skipped,
        "completion_percentage": round(complete / total * 100) if total else 0,
        "open_critical_quality": open_critical,
        "pending_proposals": pending_proposals,
        "stale_count": len(stale_context),
    }

    return {
        "summary": summary,
        "stages": stages,
        "next_action": _next_action(project, stages),
        "stale_context": stale_context,
        "deferred_future_stages": (
            ["data_model", "pipeline_design"] if project.data_goal in _GOALS_WANTING_FUTURE_STAGES else []
        ),
    }
