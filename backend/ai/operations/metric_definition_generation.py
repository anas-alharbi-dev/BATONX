"""
metric_definition_generation — AI proposes structured KPI definitions (Phase
I-3). It must reference only real dataset ids and real column names — the
service layer re-validates every reference against the project's actual schema
before anything is persisted; nothing invented survives.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "metric_definition/v1"

_Agg = Literal["sum", "count", "count_distinct", "avg", "min", "max", "ratio"]
_FilterOp = Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"]


class MeasureDraft(BaseModel):
    field: str = Field(min_length=1)


class FilterDraft(BaseModel):
    field: str = Field(min_length=1)
    operator: _FilterOp
    value: object = None


class StructuredDraft(BaseModel):
    aggregation: _Agg
    base_table_ref: str = Field(min_length=1, description="MUST be one of the dataset ids given below")
    measure: Optional[MeasureDraft] = None
    numerator: Optional[MeasureDraft] = None
    denominator: Optional[MeasureDraft] = None
    default_filters: list[FilterDraft] = Field(default_factory=list)
    time_field: str = ""
    dimensions: list[str] = Field(default_factory=list)


class MetricDraft(BaseModel):
    name: str = Field(min_length=1)
    business_meaning: str = ""
    formula_text: str = Field(min_length=1)
    structured: StructuredDraft
    time_grain: str = ""
    allowed_dimensions: list[str] = Field(default_factory=list)
    source_fields: list[str] = Field(default_factory=list)
    owner: str = ""
    related_goal_ref: str = ""
    caveats: list[str] = Field(default_factory=list)
    validation_checks: list[str] = Field(default_factory=list)


class MetricsDraft(BaseModel):
    metrics: list[MetricDraft] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You propose KPI / metric definitions for a data project. You are given the "
    "approved Data Brief, approved dataset interpretations, approved Quality "
    "Rules, the approved Transformation Plan summary (if any), and, for each "
    "dataset, its real column names and types.\n\n"
    "CRITICAL: base_table_ref must be EXACTLY one of the dataset ids listed "
    "below. Every field you reference (measure.field, numerator.field, "
    "denominator.field, filter fields, time_field, dimensions) MUST be an "
    "EXACT column name that exists on that dataset. Never invent a table or "
    "column that is not listed — if the data you'd need does not exist, omit "
    "that metric instead.\n\n"
    "Use exactly one aggregation per metric:\n"
    "- sum / avg / min / max   -> needs a 'measure' field\n"
    "- count                   -> measure is optional (counts rows)\n"
    "- count_distinct          -> needs a 'measure' field (the column to count "
    "distinct values of)\n"
    "- ratio                   -> needs BOTH 'numerator' and 'denominator' "
    "measures; do not set 'measure' for a ratio\n\n"
    "formula_text is the plain-language formula a human reads (e.g. 'sum(amount) "
    "for completed orders'). business_meaning explains why this KPI matters. "
    "caveats note anything a reader must know (e.g. a filter that limits scope). "
    "Prefer a small, high-signal set of metrics grounded in the Data Brief's "
    "success criteria.\n\n"
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
    datasets = context.get("datasets") or []
    quality_rules = context.get("quality_rules") or []
    transformation = context.get("transformation") or {}

    parts = [
        "DATA BRIEF",
        f"goal: {brief.get('business_goal', '')}",
        f"decision: {brief.get('decision_context', '')}",
        *_lines("success_criteria", brief.get("success_criteria")),
        "",
        "AVAILABLE DATASETS (base_table_ref must be one of these ids)",
    ]
    for ds in datasets:
        parts.append(f"- id={ds['id']}  name='{ds['name']}' ({ds.get('row_count', '?')} rows)")
        interp = ds.get("interpretation") or {}
        if interp:
            parts.append(
                f"    entity: {interp.get('business_entity', '')} | "
                f"grain: {interp.get('grain', '')}"
            )
        for col in ds.get("columns", []):
            parts.append(f"    column {col['name']} [{col['dtype']}]")

    parts += ["", "APPROVED QUALITY RULES"]
    if quality_rules:
        for r in quality_rules:
            parts.append(f"- {r['id']} {r['assertion']}({r.get('column') or 'table'})")
    else:
        parts.append("- (none)")

    if transformation:
        parts += [
            "",
            "APPROVED TRANSFORMATION (summary)",
            f"outputs: {', '.join(o.get('name', '') for o in transformation.get('outputs', []))}",
        ]

    parts += ["", "Propose the KPI definitions now."]
    return "\n".join(parts)


METRIC_DEFINITION_GENERATION = Operation(
    name="metric_definition_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=MetricsDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
