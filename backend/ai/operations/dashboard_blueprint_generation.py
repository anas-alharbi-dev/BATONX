"""
dashboard_blueprint_generation — AI proposes a generic Dashboard Blueprint
(Phase I-4): which panels, showing which approved KPIs, for which audience and
decision. No BI-tool-specific output, no dashboard engine — a structured
design artifact only. Every metric_ref must resolve to a real, approved KPI;
the service layer re-validates before persisting.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "dashboard_blueprint/v1"

_VizType = Literal[
    "kpi_card", "line", "bar", "stacked_bar", "table", "scatter", "funnel", "heatmap"
]


class PanelDraft(BaseModel):
    title: str = Field(min_length=1)
    viz_type: _VizType
    metric_refs: list[str] = Field(
        min_length=1, description="MUST be exact approved KPI business ids"
    )
    dimension: str = ""
    comparison: str = ""
    drilldowns: list[str] = Field(default_factory=list)
    anomaly_view: bool = False
    insight_refs: list[str] = Field(
        default_factory=list, description="Exact accepted Insight business ids this panel reflects, if any"
    )
    notes: str = ""


class DashboardBlueprintDraft(BaseModel):
    audience: str = Field(min_length=1)
    decision_use_case: str = Field(min_length=1)
    refresh_cadence: str = ""
    global_filters: list[str] = Field(default_factory=list)
    panels: list[PanelDraft] = Field(min_length=1)
    layout: str = ""


SYSTEM_PROMPT = (
    "You design a GENERIC Dashboard Blueprint for a data project — a structured "
    "plan, not a working dashboard, and not tied to any specific BI tool "
    "(no Power BI/Tableau-specific output).\n\n"
    "CRITICAL: every metric_ref MUST be an EXACT approved KPI business id "
    "listed below. Never invent one — if you'd need a metric that isn't "
    "approved, omit that panel instead. insight_refs, if used, MUST be exact "
    "accepted Insight ids from the list given (may be empty).\n\n"
    "Choose viz_type per panel from: kpi_card, line, bar, stacked_bar, table, "
    "scatter, funnel, heatmap. Use kpi_card for a single headline number, line "
    "for trends over time, bar/stacked_bar for comparisons/segments, table for "
    "detail, funnel for step conversion, heatmap for a two-dimensional "
    "breakdown, scatter for a relationship between two metrics.\n\n"
    "Ground the design in the given audience and decision_use_case — every "
    "panel should help that audience make that decision. Keep the panel count "
    "focused (typically 4-10), not exhaustive.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _lines(label: str, items) -> list[str]:
    items = items or []
    if not items:
        return [f"{label}: (none)"]
    return [f"{label}:", *(f"- {it}" for it in items)]


def build_user_prompt(context: dict) -> str:
    brief = context.get("data_brief") or {}
    metrics = context.get("metrics") or []
    analyses = context.get("analyses") or []
    insights = context.get("insights") or []

    parts = [
        f"DATA BRIEF GOAL: {brief.get('business_goal', '')}",
        f"AUDIENCE HINT: {', '.join(brief.get('audience', []) or [])}",
        f"DECISION CONTEXT HINT: {brief.get('decision_context', '')}",
        "",
        "APPROVED KPIs (metric_refs must be exactly one of these ids)",
    ]
    for m in metrics:
        parts.append(f"- {m['business_id']} {m['name']}: {m.get('formula_text', '')}")

    parts += ["", "ANALYSIS RESULTS (bounded summaries)"]
    if analyses:
        for a in analyses:
            parts.append(f"- {a['business_id']} [{a['method']}] {a['business_question']}")
            for s in a.get("headline_statements", []):
                parts.append(f"    {s}")
    else:
        parts.append("- (none)")

    parts += ["", "ACCEPTED INSIGHTS (insight_refs must be exactly one of these ids, if used)"]
    if insights:
        for i in insights:
            parts.append(f"- {i['business_id']}: {i['interpretation']}")
    else:
        parts.append("- (none)")

    parts += ["", "Design the Dashboard Blueprint now."]
    return "\n".join(parts)


DASHBOARD_BLUEPRINT_GENERATION = Operation(
    name="dashboard_blueprint_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=DashboardBlueprintDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
