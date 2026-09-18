"""
Data Lineage v1 (Phase I-3) — deterministic reference resolution. No graph
database, no AI: every edge below comes from a stored, typed reference already
on an artifact (dataset_ref, related_observations, related_quality_rules,
base_table_ref, related_goal_ref, kpi_refs, ...).

    Business Goal -> Dataset -> Transformation Step -> KPI -> Query
    Dataset -> Quality Observation -> Quality Rule -> Transformation Step

``resolve_lineage`` does a small BFS over this edge list — the graphs involved
are a handful of nodes, so a graph database would be over-engineering.
"""
from __future__ import annotations

from collections import defaultdict

GOAL_NODE = "data_brief"


def _collect_edges(project) -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []

    datasets = list(project.datasets.all())
    dataset_ids = {str(d.id) for d in datasets}
    has_goal = bool((project.data_brief or {}).get("content"))

    for d in datasets:
        if has_goal:
            edges.append((GOAL_NODE, str(d.id), "informs"))

    quality = (project.data_quality or {}).get("content") or {}
    for obs in quality.get("observations", []):
        ds = obs.get("dataset_ref")
        if ds in dataset_ids:
            edges.append((ds, obs["id"], "profiled_into"))
    for rule in quality.get("rules", []):
        for obs_id in rule.get("related_observations", []):
            edges.append((obs_id, rule["id"], "evidence_for"))

    tp = (project.transformation_plan or {}).get("content") or {}
    src = tp.get("source_dataset_id")
    for step in tp.get("steps", []):
        if src in dataset_ids:
            edges.append((src, step["id"], "transforms"))
        for qr in step.get("related_quality_rules", []):
            edges.append((qr, step["id"], "addressed_by"))

    for m in project.metrics.all():
        base = (m.structured or {}).get("base_table_ref")
        if base in dataset_ids:
            edges.append((base, m.business_id, "computed_from"))
        if m.related_goal_ref and has_goal:
            edges.append((GOAL_NODE, m.business_id, "supports_goal"))

    for q in project.queries.all():
        base = (q.plan or {}).get("base_table_ref")
        if base in dataset_ids:
            edges.append((base, q.business_id, "queried"))
        for kpi_ref in q.kpi_refs or []:
            edges.append((kpi_ref, q.business_id, "used_by"))

    # Phase I-4 — Analysis Plan / Result / Insight / Dashboard Panel. Every
    # edge below comes from a stored ref already on the artifact; there is no
    # AI-generated edge and no edge invented from free text.
    for plan in project.analysis_plans.all():
        for kpi_ref in plan.required_metrics or []:
            edges.append((kpi_ref, plan.business_id, "analyzed_by"))
        for result in plan.results.all():
            # AnalysisResult has no business_id of its own (it's an immutable
            # run, not a decision) — its real DB id is the addressable node.
            edges.append((plan.business_id, str(result.id), "produced"))
            for insight in result.insights.all():
                edges.append((str(result.id), insight.business_id, "interpreted_by"))

    dashboard = (project.dashboard_blueprint or {}).get("content") or {}
    for panel in dashboard.get("panels", []):
        panel_id = panel.get("id")
        if not panel_id:
            continue
        for kpi_ref in panel.get("metric_refs", []):
            edges.append((kpi_ref, panel_id, "visualized_by"))
        for insight_ref in panel.get("insight_refs", []):
            edges.append((insight_ref, panel_id, "informs_panel"))

    return edges


def _walk(adjacency: dict[str, list[str]], start: str) -> set[str]:
    seen: set[str] = set()
    queue = [start]
    while queue:
        cur = queue.pop(0)
        for nxt in adjacency.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def resolve_lineage(project, node: str) -> dict:
    """
    Deterministic. Returns ``{node, exists, upstream: [...], downstream: [...],
    edges: [{from, to, type}, ...]}``. An unknown node returns empty lists with
    ``exists: False`` — never an error; lineage is a read-only derived view.
    """
    edges = _collect_edges(project)
    forward: dict[str, list[str]] = defaultdict(list)
    backward: dict[str, list[str]] = defaultdict(list)
    all_nodes: set[str] = {GOAL_NODE} if (project.data_brief or {}).get("content") else set()
    for frm, to, _type in edges:
        forward[frm].append(to)
        backward[to].append(frm)
        all_nodes.add(frm)
        all_nodes.add(to)

    upstream = sorted(_walk(backward, node))
    downstream = sorted(_walk(forward, node))
    closure = {node, *upstream, *downstream}

    return {
        "node": node,
        "exists": node in all_nodes,
        "upstream": upstream,
        "downstream": downstream,
        "edges": [
            {"from": frm, "to": to, "type": typ}
            for frm, to, typ in edges
            if frm in closure and to in closure
        ],
    }
