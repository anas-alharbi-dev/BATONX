"""
Deterministic Delivery Readiness (Phase I-5) — the Data analogue of
``projects.ship_checklist``, same philosophy, deliberately not called "Ship":
a Data project is delivered/handed off, not shipped as running software.

No AI. Automatic checks derive from real stored state; historical failed Jobs
are never blockers on their own — only the LATEST run of each kind matters
(a later successful run supersedes an earlier failure). Manual items are
human-only confirmations; only they persist, in ``Project.data_readiness``
(``{item_id: {confirmed, confirmed_at, note}}``), same shape as
``ship_checklist``.
"""
from __future__ import annotations

from django.utils import timezone as dj_timezone

from projects.data.progress import _required_stages
from projects.data.quality import critical_unresolved_count
from projects.data.stale import data_stale_artifacts
from projects.exceptions import ProjectWorkflowError

NOT_READY = "NOT_READY"
READY_WITH_MANUAL_CHECKS = "READY_WITH_MANUAL_CHECKS"
READY_TO_DELIVER = "READY_TO_DELIVER"

# (item_id, category, title, why VYRA cannot verify this itself)
MANUAL_ITEMS: tuple[tuple[str, str, str, str], ...] = (
    (
        "source_access_confirmed",
        "Data Foundation",
        "Source access / ownership confirmed",
        "VYRA cannot verify who owns or has rights to the source data.",
    ),
    (
        "sample_outputs_validated",
        "Data Foundation",
        "Sample outputs validated against known figures",
        "VYRA cannot compare computed numbers to an external source of truth.",
    ),
    (
        "kpi_signoff",
        "Metrics",
        "KPI definitions signed off by stakeholders",
        "Whether a KPI definition is the RIGHT business decision is a human judgment.",
    ),
    (
        "analysis_findings_reviewed",
        "Analysis",
        "Analysis findings reviewed",
        "VYRA cannot judge whether a finding is decision-ready for this audience.",
    ),
    (
        "dashboard_reviewed_with_audience",
        "Dashboard",
        "Dashboard reviewed with intended audience",
        "VYRA has no way to observe a stakeholder review session.",
    ),
    (
        "pii_handling_reviewed",
        "Governance",
        "PII / data-handling reviewed",
        "VYRA flags likely-PII columns heuristically; a human must confirm handling is compliant.",
    ),
    (
        "handoff_runbook_prepared",
        "Operations",
        "Handoff / runbook notes prepared",
        "Operational handoff documentation is a human deliverable.",
    ),
    (
        "downstream_consumers_notified",
        "Operations",
        "Downstream consumers notified",
        "VYRA does not know who consumes this data outside the project.",
    ),
    (
        "retention_cost_reviewed",
        "Operations",
        "Retention / cost considerations reviewed",
        "VYRA has no visibility into storage/retention policy or cost.",
    ),
)
MANUAL_ITEM_IDS: frozenset[str] = frozenset(item[0] for item in MANUAL_ITEMS)
MAX_NOTE_LEN = 500


def _check(cid, category, title, ok, *, required=True, warn_if=False, evidence="", action=""):
    status = "pass" if ok else ("warning" if warn_if else "fail")
    return {
        "id": cid, "category": category, "title": title, "kind": "automatic",
        "status": status, "required": required, "evidence": evidence, "action": action,
    }


def _automatic_checks(project) -> list[dict]:
    from projects.data.stale import (
        stale_analysis_plan_ids,
        stale_dataset_interpretation_ids,
        stale_metric_ids,
        stale_query_ids,
    )

    required = set(_required_stages(project))
    checks = []

    checks.append(_check(
        "DR-01", "Data Foundation", "Data Brief approved",
        bool(project.data_brief_approved_at),
        evidence=(
            f"Approved {project.data_brief_approved_at.isoformat()}"
            if project.data_brief_approved_at else "The Data Brief has not been approved."
        ),
        action="Approve the Data Brief.",
    ))

    datasets = list(project.datasets.all())
    checks.append(_check(
        "DR-02", "Data Foundation", "At least one dataset exists",
        bool(datasets),
        evidence=f"{len(datasets)} dataset(s)." if datasets else "No datasets uploaded.",
        action="Upload a dataset.",
    ))
    active = datasets  # no archival concept yet — every uploaded dataset is "active"
    unprofiled = [d for d in active if d.status != "profiled"]
    checks.append(_check(
        "DR-03", "Data Foundation", "All active datasets profiled",
        bool(active) and not unprofiled,
        evidence=(
            f"{len(unprofiled)} dataset(s) not profiled: " + ", ".join(d.name for d in unprofiled)
            if unprofiled else ("No datasets yet." if not active else "All datasets profiled.")
        ),
        action="Profile every uploaded dataset.",
    ))
    reprofiling = [d for d in active if d.profiling_stale]
    checks.append(_check(
        "DR-04", "Data Foundation", "No dataset mid-reprofile (profiling_stale)",
        not reprofiling, required=False, warn_if=True,
        evidence=(
            f"{len(reprofiling)} dataset(s) currently re-profiling."
            if reprofiling else "None."
        ),
        action="Wait for re-profiling to finish.",
    ))
    unapproved_interp = [d for d in active if d.status == "profiled" and not d.interpretation_approved_at]
    checks.append(_check(
        "DR-05", "Data Foundation", "Required Source Interpretations approved",
        not unapproved_interp,
        evidence=(
            f"{len(unapproved_interp)} dataset(s) without an approved interpretation."
            if unapproved_interp else "All profiled datasets have an approved interpretation."
        ),
        action="Approve the remaining source interpretations.",
    ))

    dq = (project.data_quality or {}).get("content") or {}
    checks.append(_check(
        "DR-06", "Data Quality", "Quality Rules approved",
        bool(project.data_quality_approved_at),
        evidence=(
            f"Approved {project.data_quality_approved_at.isoformat()}"
            if project.data_quality_approved_at else "Quality Rules have not been approved."
        ),
        action="Approve the Quality Rules.",
    ))
    unresolved = critical_unresolved_count(dq)
    checks.append(_check(
        "DR-07", "Data Quality",
        "No unresolved critical quality issue without a passing rule or accepted risk",
        unresolved == 0,
        evidence=(
            f"{unresolved} unresolved critical issue(s)."
            if unresolved else "No unresolved critical issues."
        ),
        action="Add a covering rule or explicitly accept the risk.",
    ))

    if "transformation_plan" in required:
        checks.append(_check(
            "DR-08", "Transformation", "Transformation Plan approved",
            bool(project.transformation_plan_approved_at),
            evidence=(
                f"Approved {project.transformation_plan_approved_at.isoformat()}"
                if project.transformation_plan_approved_at
                else "The Transformation Plan has not been approved."
            ),
            action="Approve the Transformation Plan.",
        ))

    if "metrics" in required:
        metrics = list(project.metrics.all())
        unapproved_m = [m for m in metrics if m.status != "approved"]
        checks.append(_check(
            "DR-09", "Metrics", "Required Metrics approved",
            bool(metrics) and not unapproved_m,
            evidence=(
                f"{len(unapproved_m)} KPI(s) not approved."
                if unapproved_m else (
                    "No KPIs defined." if not metrics else "All KPIs approved."
                )
            ),
            action="Approve the remaining KPIs.",
        ))
        unvalidated = [m for m in metrics if m.status == "approved" and not m.validation_runs.filter(passed=True).exists()]
        checks.append(_check(
            "DR-10", "Metrics", "Required Metrics successfully validated",
            not unvalidated,
            evidence=(
                f"{len(unvalidated)} approved KPI(s) with no successful validation."
                if unvalidated else "Every approved KPI has a successful validation."
            ),
            action="Validate the remaining KPIs.",
        ))

    if "queries" in required:
        queries = list(project.queries.all())
        not_reviewed = [q for q in queries if q.status not in ("reviewed", "executed")]
        checks.append(_check(
            "DR-11", "Queries", "Required Queries human-reviewed",
            not not_reviewed,
            evidence=(
                f"{len(not_reviewed)} quer{'y' if len(not_reviewed) == 1 else 'ies'} not reviewed."
                if not_reviewed else ("No queries." if not queries else "All queries reviewed.")
            ),
            action="Review and mark the remaining queries reviewed.",
        ))
        not_executed = [q for q in queries if q.status == "reviewed"]
        checks.append(_check(
            "DR-12", "Queries", "Required Query executions completed where needed",
            not not_executed, required=False, warn_if=bool(not_executed),
            evidence=(
                f"{len(not_executed)} reviewed quer{'y' if len(not_executed) == 1 else 'ies'} not yet executed."
                if not_executed else "Every reviewed query has been executed."
            ),
            action="Execute the remaining reviewed queries.",
        ))

    if "analysis" in required:
        plans = list(project.analysis_plans.all())
        unapproved_p = [p for p in plans if p.status != "approved"]
        checks.append(_check(
            "DR-13", "Analysis", "Required Analysis Plans approved",
            bool(plans) and not unapproved_p,
            evidence=(
                f"{len(unapproved_p)} Analysis Plan(s) not approved."
                if unapproved_p else ("No Analysis Plans." if not plans else "All approved.")
            ),
            action="Approve the remaining Analysis Plans.",
        ))
        unrun = [p for p in plans if not p.results.exists()]
        checks.append(_check(
            "DR-14", "Analysis", "Required Analysis Results exist",
            not unrun,
            evidence=(
                f"{len(unrun)} approved plan(s) never run."
                if unrun else "Every plan has at least one result."
            ),
            action="Run the remaining Analysis Plans.",
        ))

    if "dashboard" in required:
        checks.append(_check(
            "DR-15", "Dashboard", "Required Dashboard Blueprint approved",
            bool(project.dashboard_blueprint_approved_at),
            evidence=(
                f"Approved {project.dashboard_blueprint_approved_at.isoformat()}"
                if project.dashboard_blueprint_approved_at
                else "The Dashboard Blueprint has not been approved."
            ),
            action="Approve the Dashboard Blueprint.",
        ))

    stale = (
        data_stale_artifacts(project)
        + stale_dataset_interpretation_ids(project)
        + stale_metric_ids(project)
        + stale_query_ids(project)
        + stale_analysis_plan_ids(project)
    )
    checks.append(_check(
        "DR-16", "Context Consistency", "No stale authoritative artifact",
        not stale,
        evidence=(
            f"{len(stale)} stale item(s): " + ", ".join(stale[:10])
            if stale else "Nothing is flagged stale."
        ),
        action="Regenerate/re-approve (or re-run) each stale artifact.",
    ))

    # Only the LATEST run of each relevant kind matters — a later success
    # supersedes an earlier failure; historical failures are never blockers.
    latest_profile_failed = any(
        d.status == "failed" for d in active
    )
    checks.append(_check(
        "DR-17", "Jobs", "No failed required Job currently blocking delivery",
        not latest_profile_failed,
        evidence=(
            "One or more datasets are currently in a failed profiling state."
            if latest_profile_failed else "No blocking job failures."
        ),
        action="Re-run profiling for the failed dataset(s).",
    ))

    pending_proposals = project.proposals.filter(status="pending").count()
    checks.append(_check(
        "DR-18", "Governance", "No pending required Proposal blocking authoritative state",
        pending_proposals == 0, required=False, warn_if=pending_proposals > 0,
        evidence=(
            f"{pending_proposals} pending proposal(s)."
            if pending_proposals else "No pending proposals."
        ),
        action="Approve or reject the pending proposal(s).",
    ))

    return checks


def _manual_checks(project) -> list[dict]:
    stored = project.data_readiness or {}
    out = []
    for item_id, category, title, why in MANUAL_ITEMS:
        entry = stored.get(item_id) or {}
        out.append({
            "id": item_id, "category": category, "title": title, "kind": "manual",
            "required": True, "confirmed": bool(entry.get("confirmed")),
            "confirmed_at": entry.get("confirmed_at"), "note": entry.get("note", ""),
            "why_manual": why,
        })
    return out


def _overall(auto: list[dict], manual: list[dict]) -> str:
    if any(c["required"] and c["status"] == "fail" for c in auto):
        return NOT_READY
    all_confirmed = all(c["confirmed"] for c in manual if c["required"])
    return READY_TO_DELIVER if all_confirmed else READY_WITH_MANUAL_CHECKS


def _summary_sentence(overall: str, blockers: list[dict], pending_manual: int) -> str:
    if overall == NOT_READY:
        n = len(blockers)
        return (
            f"{n} required readiness check{'s' if n != 1 else ''} "
            f"{'are' if n != 1 else 'is'} failing. Resolve "
            f"{'them' if n != 1 else 'it'} before delivery."
        )
    if overall == READY_WITH_MANUAL_CHECKS:
        return (
            f"Every automatic check passes. {pending_manual} manual "
            f"confirmation{'s' if pending_manual != 1 else ''} "
            f"remain{'s' if pending_manual == 1 else ''} before this project is "
            "ready to deliver."
        )
    return (
        "Every automatic check passes and all manual confirmations are "
        "complete. This project is ready to deliver."
    )


def compute_data_readiness(project) -> dict:
    """The full derived Delivery Readiness. Pure function of stored state."""
    from projects.data.services import _require_data_project

    _require_data_project(project)
    auto = _automatic_checks(project)
    manual = _manual_checks(project)
    overall = _overall(auto, manual)

    blockers = [
        {"id": c["id"], "title": c["title"], "evidence": c["evidence"]}
        for c in auto if c["required"] and c["status"] == "fail"
    ]
    warnings = [
        {"id": c["id"], "title": c["title"], "evidence": c["evidence"]}
        for c in auto if c["status"] == "warning"
    ]
    pending_manual = sum(1 for c in manual if c["required"] and not c["confirmed"])

    return {
        "overall_status": overall,
        "readiness_summary": _summary_sentence(overall, blockers, pending_manual),
        "automatic_checks": auto,
        "manual_checks": manual,
        "blockers": blockers,
        "warnings": warnings,
        "pending_manual_confirmations": pending_manual,
    }


def apply_data_manual_confirmation(project, item_id: str, confirmed, note=None) -> tuple[dict, bool]:
    """Persist ONE manual confirmation. Only manual items are writable —
    automatic checks are always derived, never stored, so AI or a client can
    never influence them by writing here."""
    from projects.data.services import _require_data_project

    _require_data_project(project)
    if item_id not in MANUAL_ITEM_IDS:
        raise ValueError(item_id)

    confirmed = bool(confirmed)
    note = (str(note).strip()[:MAX_NOTE_LEN]) if note else ""

    stored = dict(project.data_readiness or {})
    stored[item_id] = {
        "confirmed": confirmed,
        "confirmed_at": dj_timezone.now().isoformat() if confirmed else None,
        "note": note,
    }
    project.data_readiness = stored
    return stored, confirmed


def confirm_data_readiness_item(project, item_id, confirmed, note=None) -> dict:
    """View-facing wrapper: persist ONE manual confirmation, then return the
    recomputed Delivery Readiness. No stage mutation — Data has no terminal
    'delivered' stage gate to advance (unlike Software's Ship Checklist)."""
    if not isinstance(item_id, str) or not item_id:
        raise ProjectWorkflowError(
            "invalid_readiness_item", "A manual readiness item id is required."
        )
    try:
        apply_data_manual_confirmation(project, item_id, confirmed, note)
    except ValueError:
        raise ProjectWorkflowError(
            "invalid_readiness_item",
            f"'{item_id}' is not a manual Delivery Readiness item.",
            details={"item_id": item_id},
        )
    project.save(update_fields=["data_readiness", "updated_at"])
    return compute_data_readiness(project)
