"""
Data stale dependency chain (Phase I-5) — the Data analogue of
``projects.dependencies``, kept as a separate module rather than an in-place
extension of that file: ``projects.dependencies`` stays byte-equivalent for
Software (nothing there is imported or modified by anything below), and Data
has fundamentally different shape needs — four artifacts are Project-level
singular JSON (reuse ``Project.downstream_stale``, same dict, disjoint key
names, zero schema cost); four are multi-instance relational rows
(``Dataset.interpretation_*``, ``MetricDefinition``, ``Query``,
``AnalysisPlan``), which get their own ``stale``/``stale_reason``/
``stale_since`` columns so *which* KPI/Query/Plan is affected is never lost.

Meaning of "stale" is identical to Software's: *previously approved/valid, but
an upstream approved decision may have changed since, so it may now be
inconsistent.* Content, approval timestamps, and all history
(QualityCheckRun / MetricValidationRun / QueryRun / AnalysisResult / Insight)
are never touched or deleted — only the flag. A stale artifact/entity becomes
fresh again ONLY through its own reconciliation lifecycle (see the
``clear_*`` functions) — never automatically just because something upstream
changed.

No graph database: every propagation function below is a handful of ORM
filters, run synchronously in the same request that changed the upstream
artifact.
"""
from __future__ import annotations

from django.utils import timezone as dj_timezone

# Ordered, conceptual Data artifact chain (Phase I-5 implemented MVP). Data
# Model / Pipeline Design are intentionally NOT included — they don't exist
# yet; nothing here may reference them.
DATA_ARTIFACT_CHAIN: tuple[str, ...] = (
    "data_brief",
    "source_interpretation",
    "data_quality",
    "transformation_plan",
    "metrics",
    "queries",
    "analysis_plan",
    "dashboard_blueprint",
)

# The 4 nodes that are single Project-level JSON artifacts and can reuse
# Project.downstream_stale directly (their key names never collide with the
# Software chain's: business_logic/architecture/roadmap vs. these).
DATA_PROJECT_LEVEL_STALEABLE: tuple[str, ...] = (
    "data_quality",
    "transformation_plan",
    "dashboard_blueprint",
)
DATA_APPROVED_AT_ATTR: dict[str, str] = {
    "data_brief": "data_brief_approved_at",
    "data_quality": "data_quality_approved_at",
    "transformation_plan": "transformation_plan_approved_at",
    "dashboard_blueprint": "dashboard_blueprint_approved_at",
}

# The 4 nodes that are multi-instance / per-row and use entity-level fields
# instead (Dataset.interpretation_stale, or MetricDefinition/Query/
# AnalysisPlan.stale). Not project-level flags — see module docstring.
DATA_ENTITY_LEVEL_STALEABLE: tuple[str, ...] = (
    "source_interpretation",
    "metrics",
    "queries",
    "analysis_plan",
)


def downstream_of(artifact: str) -> list[str]:
    """Data-chain nodes strictly downstream of ``artifact``. Mirrors
    ``projects.dependencies.downstream_of`` in shape; separate function
    because it walks a separate chain."""
    if artifact not in DATA_ARTIFACT_CHAIN:
        return []
    after = DATA_ARTIFACT_CHAIN[DATA_ARTIFACT_CHAIN.index(artifact) + 1 :]
    return list(after)


# --- project-level (singular JSON artifact) stale ------------------------


def _mark_project_level(project, name: str, reason: str = "") -> bool:
    if name not in DATA_PROJECT_LEVEL_STALEABLE:
        return False
    attr = DATA_APPROVED_AT_ATTR[name]
    if not getattr(project, attr, None):
        return False  # never approved -> nothing to flag, no noise
    stale = dict(project.downstream_stale or {})
    if stale.get(name) is True:
        return False
    stale[name] = True
    project.downstream_stale = stale
    return True


def clear_data_stale(project, artifact: str) -> bool:
    """Clear exactly one project-level Data artifact's stale flag. Same
    ``project.downstream_stale`` dict Software uses — key names never
    collide."""
    stale = dict(project.downstream_stale or {})
    if artifact in stale:
        stale.pop(artifact)
        project.downstream_stale = stale
        return True
    return False


def is_data_stale(project, artifact: str) -> bool:
    return bool((project.downstream_stale or {}).get(artifact))


def project_level_changed(impact: dict) -> bool:
    """True if a ``propagate_*`` result touched any project-level (Project.
    downstream_stale-backed) artifact — the caller's cue to add
    'downstream_stale' to its own ``save(update_fields=...)``."""
    return any(impact.get(k) for k in DATA_PROJECT_LEVEL_STALEABLE)


def data_stale_artifacts(project) -> list[str]:
    """Only the Data project-level names currently flagged (a subset of
    ``project.downstream_stale`` — Software keys, if any exist on a Data
    project, which they never do, are excluded by construction since the two
    key sets are disjoint)."""
    flagged = {name for name, flag in (project.downstream_stale or {}).items() if flag}
    return [a for a in DATA_PROJECT_LEVEL_STALEABLE if a in flagged]


# --- entity-level (multi-instance) stale ----------------------------------


def _mark_entities_stale(queryset, reason: str) -> list[str]:
    """Sets stale=True on every not-already-stale row in ``queryset``.
    Returns the business ids actually changed (empty if none)."""
    now = dj_timezone.now()
    changed = []
    for obj in queryset:
        if not obj.stale:
            obj.stale = True
            obj.stale_reason = reason
            obj.stale_since = now
            obj.save(update_fields=["stale", "stale_reason", "stale_since"])
            changed.append(obj.business_id)
    return changed


def clear_metric_stale(metric) -> bool:
    if not metric.stale:
        return False
    metric.stale = False
    metric.stale_reason = ""
    metric.stale_since = None
    metric.save(update_fields=["stale", "stale_reason", "stale_since"])
    return True


def clear_query_stale(query) -> bool:
    if not query.stale:
        return False
    query.stale = False
    query.stale_reason = ""
    query.stale_since = None
    query.save(update_fields=["stale", "stale_reason", "stale_since"])
    return True


def clear_analysis_plan_stale(plan) -> bool:
    if not plan.stale:
        return False
    plan.stale = False
    plan.stale_reason = ""
    plan.stale_since = None
    plan.save(update_fields=["stale", "stale_reason", "stale_since"])
    return True


def clear_dataset_interpretation_stale(dataset) -> bool:
    if not dataset.interpretation_stale:
        return False
    dataset.interpretation_stale = False
    dataset.save(update_fields=["interpretation_stale"])
    return True


def stale_metric_ids(project) -> list[str]:
    return list(project.metrics.filter(stale=True).values_list("business_id", flat=True))


def stale_query_ids(project) -> list[str]:
    return list(project.queries.filter(stale=True).values_list("business_id", flat=True))


def stale_analysis_plan_ids(project) -> list[str]:
    return list(project.analysis_plans.filter(stale=True).values_list("business_id", flat=True))


def stale_dataset_interpretation_ids(project) -> list[str]:
    return [str(d.id) for d in project.datasets.filter(interpretation_stale=True)]


# --- propagation (one function per "thing that changed") -------------------
#
# Scoping policy, documented once: where a real stored reference lets us
# identify exactly which downstream rows are affected (a KPI's business_id
# inside Query.kpi_refs / AnalysisPlan.required_metrics / a dashboard panel's
# metric_refs; a dataset id inside MetricDefinition.structured.base_table_ref
# or Query.plan.base_table_ref), propagation is SCOPED to those rows. Where no
# such reference exists (Quality Rules and the Transformation Plan are single
# Project-level artifacts that can affect any downstream metric/query/analysis
# without a way to know which in advance; an Analysis Plan has no stored
# back-reference from a dashboard panel), propagation is GLOBAL across the
# category — the safe default for a review flag is to over-mark rather than
# silently miss something that may be inconsistent.


def propagate_brief_change(project) -> dict:
    """Data Brief changed -> everything downstream, globally (no natural
    scope for a project-wide decision)."""
    reason = "The Data Brief changed."
    interp_ids = []
    for ds in project.datasets.filter(interpretation_approved_at__isnull=False):
        if not ds.interpretation_stale:
            ds.interpretation_stale = True
            ds.save(update_fields=["interpretation_stale"])
        interp_ids.append(str(ds.id))
    return {
        "source_interpretation": interp_ids,
        "data_quality": _mark_project_level(project, "data_quality", reason),
        "transformation_plan": _mark_project_level(project, "transformation_plan", reason),
        "metrics": _mark_entities_stale(project.metrics.filter(status="approved"), reason),
        "queries": _mark_entities_stale(
            project.queries.filter(status__in=["reviewed", "executed"]), reason
        ),
        "analysis_plan": _mark_entities_stale(
            project.analysis_plans.filter(status="approved"), reason
        ),
        "dashboard_blueprint": _mark_project_level(project, "dashboard_blueprint", reason),
    }


def propagate_dataset_change(dataset, project=None) -> dict:
    """A dataset was re-profiled (replaced / schema may differ). Scoped to
    metrics/queries whose base_table_ref is this dataset, plus whatever those
    KPIs touch downstream. ``project``, when given, MUST be the exact
    instance the caller will ``.save()`` afterward — ``dataset.project``
    fetches a separate, uncached instance via the FK and mutating that one
    would be silently lost."""
    project = project or dataset.project
    reason = f"Dataset {dataset.name} was re-profiled — schema may have changed."
    interp_changed = False
    if dataset.interpretation_approved_at and not dataset.interpretation_stale:
        dataset.interpretation_stale = True
        dataset.save(update_fields=["interpretation_stale"])
        interp_changed = True

    dq_changed = _mark_project_level(project, "data_quality", reason)
    tx_changed = _mark_project_level(project, "transformation_plan", reason)

    affected_metrics = project.metrics.filter(
        status="approved", structured__base_table_ref=str(dataset.id)
    )
    metric_ids = _mark_entities_stale(affected_metrics, reason)
    kpi_refs = set(metric_ids)

    # queries either reference this dataset directly (plan.base_table_ref) or
    # reference one of the KPIs just marked stale
    affected_queries = [
        q
        for q in project.queries.filter(status__in=["reviewed", "executed"])
        if (q.plan or {}).get("base_table_ref") == str(dataset.id)
        or (kpi_refs & set(q.kpi_refs or []))
    ]
    query_ids = _mark_entities_stale(affected_queries, reason)

    affected_plans = [
        p
        for p in project.analysis_plans.filter(status="approved")
        if kpi_refs & set(p.required_metrics or [])
    ]
    plan_ids = _mark_entities_stale(affected_plans, reason)

    dash = (project.dashboard_blueprint or {}).get("content") or {}
    touches_dashboard = any(
        kpi_refs & set(p.get("metric_refs") or []) for p in dash.get("panels", [])
    )
    dash_changed = _mark_project_level(project, "dashboard_blueprint", reason) if touches_dashboard else False

    return {
        "source_interpretation": [str(dataset.id)] if interp_changed else [],
        "data_quality": dq_changed,
        "transformation_plan": tx_changed,
        "metrics": metric_ids,
        "queries": query_ids,
        "analysis_plan": plan_ids,
        "dashboard_blueprint": dash_changed,
    }


def propagate_quality_change(project) -> dict:
    """Quality Rules changed -> transformation + metrics/queries/analysis/
    dashboard, globally (no per-rule scope is reliable — see module docstring
    policy note)."""
    reason = "Quality Rules changed."
    return {
        "transformation_plan": _mark_project_level(project, "transformation_plan", reason),
        "metrics": _mark_entities_stale(project.metrics.filter(status="approved"), reason),
        "queries": _mark_entities_stale(
            project.queries.filter(status__in=["reviewed", "executed"]), reason
        ),
        "analysis_plan": _mark_entities_stale(
            project.analysis_plans.filter(status="approved"), reason
        ),
        "dashboard_blueprint": _mark_project_level(project, "dashboard_blueprint", reason),
    }


def propagate_transformation_change(project) -> dict:
    """Transformation Plan changed -> metrics/queries/analysis/dashboard,
    globally (metrics cannot reference transformation *outputs* in this MVP —
    see I-3's documented limitation — so there is no finer scope available)."""
    reason = "The Transformation Plan changed."
    return {
        "metrics": _mark_entities_stale(project.metrics.filter(status="approved"), reason),
        "queries": _mark_entities_stale(
            project.queries.filter(status__in=["reviewed", "executed"]), reason
        ),
        "analysis_plan": _mark_entities_stale(
            project.analysis_plans.filter(status="approved"), reason
        ),
        "dashboard_blueprint": _mark_project_level(project, "dashboard_blueprint", reason),
    }


def propagate_metric_change(metric, project=None) -> dict:
    """One KPI edited -> dependent Query rows (kpi_refs), dependent
    AnalysisPlan rows (required_metrics), Dashboard IF a panel actually
    references it — all scoped by a real stored reference. ``project``, when
    given, MUST be the exact instance the caller will ``.save()`` afterward —
    see ``propagate_dataset_change``'s note on why ``metric.project`` alone
    is not safe to mutate."""
    project = project or metric.project
    ref = metric.business_id
    reason = f"{ref} changed."

    dep_queries = [
        q for q in project.queries.filter(status__in=["reviewed", "executed"])
        if ref in (q.kpi_refs or [])
    ]
    query_ids = _mark_entities_stale(dep_queries, reason)

    dep_plans = [
        p for p in project.analysis_plans.filter(status="approved")
        if ref in (p.required_metrics or [])
    ]
    plan_ids = _mark_entities_stale(dep_plans, reason)

    dash = (project.dashboard_blueprint or {}).get("content") or {}
    touches_dashboard = any(ref in (p.get("metric_refs") or []) for p in dash.get("panels", []))
    dash_changed = _mark_project_level(project, "dashboard_blueprint", reason) if touches_dashboard else False

    return {"queries": query_ids, "analysis_plan": plan_ids, "dashboard_blueprint": dash_changed}


def propagate_query_change(query, kpi_refs=None, project=None) -> dict:
    """A Query's plan/SQL changed (semantically — i.e. it was reviewed or
    executed before) -> dependent Analysis Plans. No direct Query->Plan
    reference exists (documented in I-4's lineage design); 'dependent' means
    the AnalysisPlan requires at least one KPI this query also referenced —
    the same indirect bridge ``lineage.py`` uses. ``kpi_refs`` lets the caller
    pass the *pre-edit* refs (what downstream actually relied on); defaults to
    the query's current ``kpi_refs``. ``project``, when given, MUST be the
    exact instance the caller will ``.save()`` afterward — see
    ``propagate_dataset_change``'s note."""
    project = project or query.project
    shared_kpis = set(query.kpi_refs if kpi_refs is None else kpi_refs)
    reason = f"{query.business_id} changed."
    dep_plans = (
        [
            p for p in project.analysis_plans.filter(status="approved")
            if shared_kpis & set(p.required_metrics or [])
        ]
        if shared_kpis
        else []
    )
    return {"analysis_plan": _mark_entities_stale(dep_plans, reason)}


def propagate_analysis_plan_change(plan, project=None) -> dict:
    """An Analysis Plan changed -> Dashboard. No stored panel->plan reference
    exists (panels reference KPIs/Insights, not a plan id), so this is marked
    globally if the dashboard is approved — matches the chain's own example
    literally rather than inventing an unscoped guess. ``project``, when
    given, MUST be the exact instance the caller will ``.save()`` afterward —
    see ``propagate_dataset_change``'s note."""
    project = project or plan.project
    reason = f"{plan.business_id} changed."
    return {"dashboard_blueprint": _mark_project_level(project, "dashboard_blueprint", reason)}
