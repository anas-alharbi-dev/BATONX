"""
sql_generation — AI writes ONE SELECT query from an APPROVED Query Plan +
approved KPI definitions + the real dataset schema (Phase I-3).

Generated SQL is untrusted, exactly like any other input. The service layer
re-validates it through the identical Phase I-2
``projects.data.execution.validate_select_only`` gate before it is ever
persisted or executed — this operation does not weaken that gate in any way.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "sql_generation/v1"


class SqlGenerationDraft(BaseModel):
    sql: str = Field(min_length=1, description="A single DuckDB SELECT/WITH query.")
    explanation: str = Field(min_length=1)
    referenced_kpi_ids: list[str] = Field(default_factory=list)
    referenced_fields: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You write ONE DuckDB SELECT query that answers an APPROVED Query Plan.\n\n"
    "Hard rules:\n"
    "- Output exactly one statement: SELECT or WITH ... SELECT. No DDL, DML, "
    "PRAGMA, SET, ATTACH, COPY, INSTALL, LOAD, or any multi-statement SQL.\n"
    "- Query ONLY the single view named in the plan's base_table_ref — it is "
    "already registered for you under that exact name, quoted as an "
    "identifier. Never reference a file path, URL, or any read_csv/read_json/"
    "read_parquet-style function — those are blocked and will be rejected.\n"
    "- Use only the column names given in the schema below. Do not invent "
    "columns.\n"
    "- If the plan lists required_kpi_refs, implement each KPI's approved "
    "formula faithfully — same aggregation, same filters, same ratio-null "
    "handling (guard divide-by-zero with a CASE, resulting in NULL not an "
    "error).\n"
    "- Group by the plan's dimensions where relevant; respect the plan's sort "
    "and grain.\n\n"
    "In referenced_kpi_ids list every KPI id your SQL actually implements. In "
    "referenced_fields list every real column you used. explanation is a short "
    "plain-language description of what the query computes.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _lines(label: str, items) -> list[str]:
    items = items or []
    if not items:
        return [f"{label}: (none)"]
    return [f"{label}:", *(f"- {it}" for it in items)]


def build_user_prompt(context: dict) -> str:
    plan = context.get("plan") or {}
    view = context.get("view_name", "")
    columns = context.get("columns") or []
    kpis = context.get("kpis") or []

    parts = [
        f"BASE VIEW (already registered — query it by this exact name): \"{view}\"",
        "COLUMNS:",
        *[f"- {c['name']} [{c['dtype']}]" for c in columns],
        "",
        "QUERY PLAN (approved)",
        f"objective: {plan.get('objective', '')}",
        f"base_table_ref: {plan.get('base_table_ref', '')} (this is the view above)",
        f"grain: {plan.get('grain', '')}",
        f"expected_result_shape: {plan.get('expected_result_shape', '')}",
        *_lines("required_fields", plan.get("required_fields")),
        *_lines("dimensions", plan.get("dimensions")),
        *_lines("sort", plan.get("sort")),
        *_lines("assumptions", plan.get("assumptions")),
        "",
        "REQUIRED KPI DEFINITIONS (approved — implement faithfully)",
    ]
    if kpis:
        for k in kpis:
            parts.append(
                f"- {k['business_id']} {k['name']}: {k['formula_text']} "
                f"(structured: {k['structured']})"
            )
    else:
        parts.append("- (none)")

    parts += ["", "Write the SQL now."]
    return "\n".join(parts)


SQL_GENERATION = Operation(
    name="sql_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=SqlGenerationDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
