"""
Data Project Context digest (Phase I-1, minimal).

Concise authoritative summaries only — approved Data Brief, approved Source
Interpretations, and headline Dataset/profile facts. NEVER raw rows. The full
Phase I data context (quality rules, transformations, KPIs, lineage, ...) is
added in later phases.
"""
from __future__ import annotations

_MAX_COLUMNS = 60


def build_data_digest(project) -> dict:
    digest: dict = {}

    analysis = (project.context_digest or {}).get("idea_analysis")
    if analysis:
        digest["idea_analysis"] = analysis

    # Phase I-5: a simple, always-present project setting (not gated on brief
    # approval) + a redundant human-readable alias once the brief is approved.
    digest["data_goal"] = project.data_goal

    brief = (project.data_brief or {}).get("content")
    if project.data_brief_approved_at and brief:
        digest["data_brief"] = {
            "business_goal": brief["business_goal"],
            "decision_context": brief["decision_context"],
            "audience": brief.get("audience", []),
            "success_criteria": brief.get("success_criteria", []),
            "constraints": brief.get("constraints", []),
            "candidate_sources": brief.get("candidate_sources", []),
            "data_goal": project.data_goal,
            "approved_at": project.data_brief_approved_at.isoformat(),
        }
        digest["goal"] = brief["business_goal"]

    dq = (project.data_quality or {}).get("content")
    if project.data_quality_approved_at and dq:
        from projects.data.quality import critical_unresolved_count

        digest["data_quality"] = {
            "rules": [
                {
                    "id": r["id"],
                    "dataset": r["dataset_ref"],
                    "column": r.get("column", ""),
                    "assertion": r["assertion"],
                    "params": r.get("params", {}),
                    "accepted_risk": bool(r.get("accepted_risk")),
                }
                for r in dq.get("rules", [])
            ],
            "unresolved_critical": critical_unresolved_count(dq),
            "approved_at": project.data_quality_approved_at.isoformat(),
        }

    tp = (project.transformation_plan or {}).get("content")
    if project.transformation_plan_approved_at and tp:
        digest["transformation_plan"] = {
            "source_dataset_id": tp.get("source_dataset_id"),
            "steps": [
                {
                    "id": s["id"],
                    "op": s["op"],
                    "output": s.get("output_name", ""),
                    "related_quality_rules": s.get("related_quality_rules", []),
                }
                for s in tp.get("steps", [])
            ],
            "outputs": [
                {"name": o.get("name", ""), "grain": o.get("grain", "")}
                for o in tp.get("outputs", [])
            ],
            "approved_at": project.transformation_plan_approved_at.isoformat(),
        }

    metrics = list(project.metrics.filter(status="approved"))
    if metrics:
        digest["metrics"] = [
            {
                "id": m.business_id,
                "name": m.name,
                "business_meaning": m.business_meaning,
                "formula_text": m.formula_text,
                "source_fields": m.source_fields,
                "time_grain": m.time_grain,
                "allowed_dimensions": m.allowed_dimensions,
                "latest_validation": (
                    "passed"
                    if (r := m.validation_runs.first()) and r.passed
                    else "failed"
                    if r
                    else "not_validated"
                ),
            }
            for m in metrics
        ]

    # Only queries that reached at least "reviewed" are meaningful project
    # memory — a draft plan or unreviewed SQL isn't authoritative yet.
    reviewed_queries = list(
        project.queries.filter(status__in=["reviewed", "executed"])
    )
    if reviewed_queries:
        digest["queries"] = [
            {
                "id": q.business_id,
                "question": q.question,
                "kpi_refs": q.kpi_refs,
                "status": q.status,
            }
            for q in reviewed_queries
        ]

    # Phase I-4 — bounded, factual-only summaries. An analysis enters the
    # digest once it has actually produced at least one immutable
    # AnalysisResult (regardless of the plan's current draft/approved status —
    # a plan edited back to draft after running still has valid past facts
    # worth remembering, same rationale as Query's status__in gate above).
    analyses = [p for p in project.analysis_plans.all() if p.results.exists()]
    if analyses:
        digest["analyses"] = [
            {
                "id": p.business_id,
                "business_question": p.business_question,
                "method": p.method,
                "status": p.status,
                "latest_result_summary": {
                    "result_id": str(latest.id),
                    "created_at": latest.created_at.isoformat(),
                    "findings_count": len(latest.findings),
                    # bounded, deterministic — the finding statements
                    # themselves, never metric_values/breakdown/raw rows
                    "headline_statements": [f["statement"] for f in latest.findings[:2]],
                },
            }
            for p in analyses
            for latest in [p.results.first()]
        ]

    accepted_insights = list(project.insights.filter(status="accepted"))
    if accepted_insights:
        digest["accepted_insights"] = [
            {
                "id": i.business_id,
                "supporting_finding_ids": i.supporting_finding_ids,
                "interpretation": i.interpretation,
                "recommendation": i.recommendation,
            }
            for i in accepted_insights
        ]

    dash = (project.dashboard_blueprint or {}).get("content")
    if project.dashboard_blueprint_approved_at and dash:
        digest["dashboard"] = {
            "audience": dash.get("audience", ""),
            "decision_use_case": dash.get("decision_use_case", ""),
            "panels": [
                {"id": p["id"], "viz_type": p["viz_type"], "metric_refs": p.get("metric_refs", [])}
                for p in dash.get("panels", [])
            ],
            "approved_at": project.dashboard_blueprint_approved_at.isoformat(),
        }

    sources = []
    for ds in project.datasets.all():
        entry = {
            "dataset": str(ds.id),
            "name": ds.name,
            "source_type": ds.source_type,
            "status": ds.status,
            "row_count": ds.row_count,
            "column_count": ds.column_count,
            "sampled": ds.sampled,
            "columns": [
                {
                    "name": c["name"],
                    "dtype": c["dtype"],
                    "nullable": c.get("nullable"),
                    "sensitivity": c.get("sensitivity"),
                }
                for c in (ds.inferred_schema or [])[:_MAX_COLUMNS]
            ],
        }
        interp = (ds.interpretation or {}).get("content")
        if ds.interpretation_approved_at and interp:
            entry["interpretation"] = {
                "business_entity": interp["business_entity"],
                "grain": interp["grain"],
                "key_columns": interp.get("key_columns", []),
                "caveats": interp.get("caveats", []),
                "sensitivity_flags": [
                    {"column": f["column"], "kind": f["kind"]}
                    for f in interp.get("sensitivity_flags", [])
                ],
                "approved_at": ds.interpretation_approved_at.isoformat(),
            }
        sources.append(entry)
    if sources:
        digest["data_sources"] = sources
        # lighter, columns-only index alongside the fuller data_sources entries
        digest["schemas"] = [
            {"dataset": e["dataset"], "columns": [c["name"] for c in e["columns"]]}
            for e in sources
        ]

    # Phase I-5 — final summary slices. Bounded, deterministic, never raw.
    dq_current = (project.data_quality or {}).get("content") or {}
    if dq_current:
        from projects.data.quality import critical_unresolved_count

        digest["quality_open_critical"] = critical_unresolved_count(dq_current)

    from projects.data.progress import compute_data_progress
    from projects.data.readiness import compute_data_readiness
    from projects.data.stale import (
        data_stale_artifacts,
        stale_analysis_plan_ids,
        stale_dataset_interpretation_ids,
        stale_metric_ids,
        stale_query_ids,
    )

    progress = compute_data_progress(project)
    digest["progress_summary"] = progress["summary"]

    readiness = compute_data_readiness(project)
    digest["readiness_summary"] = {
        "overall_status": readiness["overall_status"],
        "pending_manual_confirmations": readiness["pending_manual_confirmations"],
        "blocker_count": len(readiness["blockers"]),
    }

    digest["stale"] = (
        data_stale_artifacts(project)
        + stale_metric_ids(project)
        + stale_query_ids(project)
        + stale_analysis_plan_ids(project)
        + [f"dataset:{d}" for d in stale_dataset_interpretation_ids(project)]
    )[:50]

    # a small, bounded pointer — not a graph dump. Use GET .../lineage/ with
    # any of these business ids to trace what feeds/depends on it.
    node_ids = (
        (["data_brief"] if project.data_brief_approved_at else [])
        + [str(d.id) for d in project.datasets.filter(status="profiled")]
        + [m.business_id for m in project.metrics.filter(status="approved")]
        + [q.business_id for q in project.queries.filter(status__in=["reviewed", "executed"])]
        + [p.business_id for p in analyses]
        + [i.business_id for i in accepted_insights]
    )
    digest["lineage_index"] = {"nodes": node_ids[:50]}

    digest["approved_at"] = {
        name: ts.isoformat()
        for name, ts in (
            ("data_brief", project.data_brief_approved_at),
            ("data_quality", project.data_quality_approved_at),
            ("transformation_plan", project.transformation_plan_approved_at),
            ("dashboard_blueprint", project.dashboard_blueprint_approved_at),
        )
        if ts
    }

    return digest
