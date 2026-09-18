"""
Dashboard Blueprint structured grammar (Phase I-4) — a Project-level design
artifact (Blueprint/Architecture-style, like the Transformation Plan), not a
dashboard engine and not tied to any BI tool. ``VIZ-xx`` panel ids are
server-assigned, deterministic, and reassigned fresh on every save (same
pattern as Quality's rule ids / Transformation's step ids).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

VizType = Literal[
    "kpi_card", "line", "bar", "stacked_bar", "table", "scatter", "funnel", "heatmap"
]


class DashboardPanel(BaseModel):
    id: str = ""  # server-assigned, VIZ-xx
    title: str = Field(min_length=1)
    viz_type: VizType
    metric_refs: list[str] = Field(default_factory=list)
    dimension: str = ""
    comparison: str = ""
    drilldowns: list[str] = Field(default_factory=list)
    anomaly_view: bool = False
    # KPI-xx panels visualize; INS-xx insights (if any) this panel is informed
    # by — a real stored ref, used by the lineage extension. Optional: a panel
    # need not be tied to any specific insight.
    insight_refs: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("metric_refs")
    @classmethod
    def _require_metric(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("each panel needs at least one metric_ref")
        return v


class DashboardBlueprintContent(BaseModel):
    audience: str = Field(min_length=1)
    decision_use_case: str = Field(min_length=1)
    refresh_cadence: str = ""
    global_filters: list[str] = Field(default_factory=list)
    panels: list[DashboardPanel] = Field(default_factory=list)
    layout: str = ""

    @field_validator("panels")
    @classmethod
    def _require_panels(cls, v: list[DashboardPanel]) -> list[DashboardPanel]:
        if not v:
            raise ValueError("at least one panel is required")
        return v


SECTION_FIELDS = tuple(DashboardBlueprintContent.model_fields.keys())


def assign_viz_ids(content: dict) -> dict:
    """Fresh, deterministic VIZ-01, VIZ-02, ... in panel order — reassigned on
    every save, matching the Quality rule-id / Transformation step-id
    pattern."""
    content = dict(content)
    panels = []
    for i, p in enumerate(content.get("panels") or [], start=1):
        p = dict(p)
        p["id"] = f"VIZ-{i:02d}"
        panels.append(p)
    content["panels"] = panels
    return content


def normalize_dashboard_blueprint_content(data: dict) -> dict:
    return assign_viz_ids(data)
