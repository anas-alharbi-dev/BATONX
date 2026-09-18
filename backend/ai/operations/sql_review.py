"""
sql_review — AI inspects generated SQL against the Query Plan and KPI
definitions (Phase I-3). Advisory only: it cannot execute or approve anything.
Only an explicit human action marks a query "reviewed" — see
``projects.data.query_services.mark_query_reviewed``.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "sql_review/v1"


class SqlReviewDraft(BaseModel):
    alignment_notes: str = Field(min_length=1, description="Does the SQL match the plan's objective/grain?")
    kpi_compliance_notes: str = ""
    risks: list[str] = Field(default_factory=list)
    double_counting_risk: bool = False
    null_handling_notes: str = ""
    performance_notes: str = ""
    scope_notes: str = ""
    recommendation: Literal["looks_good", "needs_changes"]


SYSTEM_PROMPT = (
    "You review a generated SQL query against its Query Plan and any required "
    "KPI definitions. You are advisory only — you cannot execute, approve, or "
    "mark anything reviewed; a human does that.\n\n"
    "Check:\n"
    "- alignment: does the SQL actually answer the plan's objective, at the "
    "right grain?\n"
    "- KPI compliance: does it implement each required KPI's approved "
    "aggregation/filters/ratio-null-handling faithfully?\n"
    "- source-field correctness, filters, joins, aggregation behavior\n"
    "- ratio safety (divide-by-zero handled?), possible double-counting\n"
    "- null handling, obvious performance concerns\n"
    "- scope creep — does it do more or less than the plan asked for?\n\n"
    "Be specific and concrete. recommendation is \"looks_good\" only if you have "
    "no material concern; otherwise \"needs_changes\" and explain why in risks.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def build_user_prompt(context: dict) -> str:
    plan = context.get("plan") or {}
    sql = context.get("sql", "")
    kpis = context.get("kpis") or []

    parts = [
        "QUERY PLAN",
        f"objective: {plan.get('objective', '')}",
        f"grain: {plan.get('grain', '')}",
        f"expected_result_shape: {plan.get('expected_result_shape', '')}",
        "",
        "REQUIRED KPIs",
    ]
    if kpis:
        for k in kpis:
            parts.append(f"- {k['business_id']} {k['name']}: {k['formula_text']}")
    else:
        parts.append("- (none)")
    parts += ["", "SQL TO REVIEW", sql, "", "Review this SQL now."]
    return "\n".join(parts)


SQL_REVIEW = Operation(
    name="sql_review",
    system_prompt=SYSTEM_PROMPT,
    schema=SqlReviewDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
