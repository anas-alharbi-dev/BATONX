"""
transformation_proposal — AI proposes a structured Transformation Plan (Phase
I-2). BATONX compiles the steps to SQL deterministically; the AI never writes
executable SQL for the supported ops.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "transformation_plan/v1"

_Op = Literal[
    "drop_columns", "rename", "cast", "fill_na", "dedupe", "standardize_values",
    "parse_date", "derive_column", "filter_rows",
]


class TransformStepDraft(BaseModel):
    op: _Op
    params: dict = Field(default_factory=dict)
    output_name: str = Field(min_length=1)
    rationale: str = ""
    related_quality_rules: list[str] = Field(default_factory=list)


class TransformOutputDraft(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    grain: str = ""


class TransformationPlanDraft(BaseModel):
    source_dataset_id: str = Field(min_length=1)
    steps: list[TransformStepDraft] = Field(min_length=1)
    outputs: list[TransformOutputDraft] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You propose a Transformation Plan for ONE source dataset in a data project. "
    "Structured steps are authoritative — BATONX compiles them to SQL itself, so "
    "do NOT write SQL.\n\n"
    "Use only these ops (in order; each step reads the previous step's output):\n"
    "- drop_columns   params: {columns: [..]}\n"
    "- rename         params: {mapping: {old: new}}\n"
    "- cast           params: {column, to_type}   to_type in "
    "bigint|double|varchar|boolean|date|timestamp\n"
    "- fill_na        params: {column, value}\n"
    "- dedupe         params: {} or {subset: [..]}\n"
    "- standardize_values params: {column, mapping: {from: to}}\n"
    "- parse_date     params: {column, format?}   format is a strptime pattern\n"
    "- derive_column  params: {name, expression}  expression may use column "
    "names, numbers, strings, + - * / ( ), || and upper/lower/trim/length/"
    "coalesce/abs/round only\n"
    "- filter_rows    params: {column, operator, value}  operator in "
    "=|!=|<|<=|>|>=|in|not_in|is_null|is_not_null\n\n"
    "Do NOT use joins, aggregations, pivots or unions — they are not supported "
    "yet. If the cleaning you have in mind needs them, describe it in a step's "
    "rationale and stop there.\n\n"
    "Link a step to the Quality Rules it addresses via related_quality_rules "
    "(QR-xx ids). Give each output a name, a one-line description, and the grain "
    "if it is unchanged.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def build_user_prompt(context: dict) -> str:
    brief = context.get("data_brief") or {}
    ds = context.get("dataset") or {}
    rules = context.get("quality_rules") or []
    columns = context.get("columns") or []

    parts = [
        "DATA BRIEF",
        f"goal: {brief.get('business_goal', '')}",
        "",
        f"SOURCE DATASET: {ds.get('id', '')}  '{ds.get('name', '')}' "
        f"({ds.get('source_type', '')}, {ds.get('row_count', '?')} rows)",
        "COLUMNS:",
    ]
    for c in columns:
        parts.append(
            f"- {c['name']} [{c['dtype']}] null%={c.get('null_pct', 0)} "
            f"distinct%={c.get('distinct_pct', 0)}"
        )
    parts += ["", "APPROVED QUALITY RULES:"]
    if rules:
        for r in rules:
            parts.append(
                f"- {r['id']} {r['assertion']}({r.get('column') or 'table'}) "
                f"params={r.get('params', {})}"
            )
    else:
        parts.append("- (none)")
    parts += ["", "Propose the Transformation Plan now."]
    return "\n".join(parts)


TRANSFORMATION_PROPOSAL = Operation(
    name="transformation_proposal",
    system_prompt=SYSTEM_PROMPT,
    schema=TransformationPlanDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
