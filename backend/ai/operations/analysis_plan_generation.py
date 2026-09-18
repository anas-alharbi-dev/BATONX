"""
analysis_plan_generation — AI proposes ONE structured Analysis Plan (Phase
I-4). It must reference only real, approved KPIs and real dimensions/fields —
the service layer re-validates every reference before anything is persisted.
Never given raw rows, only approved artifacts and headline dataset metadata.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "analysis_plan/v1"

_Method = Literal["descriptive", "trend", "segmentation", "comparison", "funnel"]
_FilterOp = Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"]


class FilterDraft(BaseModel):
    field: str = Field(min_length=1)
    operator: _FilterOp
    value: object = None


class ComparisonDraft(BaseModel):
    label: str = Field(min_length=1)
    time_range: Optional[dict] = None
    filters: list[FilterDraft] = Field(default_factory=list)


class AnalysisPlanDraft(BaseModel):
    business_question: str = Field(min_length=1)
    method: _Method
    hypotheses: list[str] = Field(default_factory=list)
    required_metrics: list[str] = Field(
        default_factory=list, description="MUST be exact approved KPI business ids (e.g. KPI-01)"
    )
    segments: list[str] = Field(default_factory=list)
    comparisons: list[ComparisonDraft] = Field(default_factory=list)
    time_range: Optional[dict] = None
    expected_outputs: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You propose ONE Analysis Plan for a data project. You are given the "
    "approved Data Brief, the approved KPI/metric definitions (with their real "
    "dimensions), reviewed Query metadata, an approved Transformation summary, "
    "and real dataset schemas.\n\n"
    "CRITICAL: every entry in required_metrics MUST be an EXACT KPI business id "
    "listed below (e.g. 'KPI-01') — never invent one. Every segment and every "
    "comparison filter field MUST be a real dimension/column already listed for "
    "one of those KPIs. If the data you would need does not exist, choose a "
    "different, answerable business_question instead.\n\n"
    "Pick exactly one method and follow its shape:\n"
    "- descriptive: current state of one or more metrics, optionally broken "
    "down by ONE segment. comparisons: leave empty.\n"
    "- trend: change over time. comparisons MUST have EXACTLY 2 entries "
    "(a baseline and a comparison period), each with a time_range "
    "{start, end}.\n"
    "- segmentation: breakdown by ONE dimension. segments MUST be non-empty.\n"
    "- comparison: two groups compared head to head. comparisons MUST have "
    "EXACTLY 2 entries, each with filters describing that group.\n"
    "- funnel: an ordered sequence of steps over the same dataset. comparisons "
    "MUST have AT LEAST 2 entries in order, each with at least one filter "
    "(filters accumulate step over step).\n\n"
    "hypotheses are plain-language guesses this analysis will help check — "
    "phrase them as questions or hypotheses to investigate, never as settled "
    "facts. expected_outputs describes what a completed run should produce, in "
    "plain language.\n\n"
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
    queries = context.get("queries") or []
    quality_rules = context.get("quality_rules") or []
    hint = context.get("business_question_hint") or ""

    parts = [
        "DATA BRIEF",
        f"goal: {brief.get('business_goal', '')}",
        f"decision: {brief.get('decision_context', '')}",
        *_lines("success_criteria", brief.get("success_criteria")),
        "",
        "APPROVED KPIs (required_metrics must be exactly one of these ids)",
    ]
    for m in metrics:
        s = m.get("structured", {})
        parts.append(
            f"- {m['business_id']} {m['name']}: {m.get('formula_text', '')} "
            f"(aggregation={s.get('aggregation')}, time_field={s.get('time_field') or 'none'}, "
            f"base_table_ref={s.get('base_table_ref')})"
        )
        if m.get("allowed_dimensions"):
            parts.append(f"    dimensions: {', '.join(m['allowed_dimensions'])}")

    parts += ["", "REVIEWED QUERIES (context only)"]
    if queries:
        for q in queries:
            parts.append(f"- {q['business_id']} [{q['status']}]: {q['question']}")
    else:
        parts.append("- (none)")

    parts += ["", "APPROVED QUALITY RULES"]
    if quality_rules:
        for r in quality_rules:
            parts.append(f"- {r['id']} {r['assertion']}({r.get('column') or 'table'})")
    else:
        parts.append("- (none)")

    if hint:
        parts += ["", f"HUMAN-PROVIDED QUESTION HINT: {hint}"]

    parts += ["", "Propose the Analysis Plan now."]
    return "\n".join(parts)


ANALYSIS_PLAN_GENERATION = Operation(
    name="analysis_plan_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=AnalysisPlanDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
