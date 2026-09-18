"""
source_interpretation — AI proposes what a profiled dataset means (Phase I-1).

Input is the Data Brief + column names + inferred schema + a BOUNDED
deterministic profiling summary (null rates, distinct counts, capped top values,
tiny capped/redacted samples). NO unrestricted raw rows. The AI must not invent
or alter any statistic.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "source_interpretation/v1"


class ColumnMeaningDraft(BaseModel):
    column: str = Field(min_length=1)
    meaning: str = Field(min_length=1)


class SensitivityFlagDraft(BaseModel):
    column: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    note: str = ""


class SourceInterpretationDraft(BaseModel):
    business_entity: str = Field(min_length=1)
    grain: str = Field(min_length=1)
    key_columns: list[str] = Field(default_factory=list)
    column_meanings: list[ColumnMeaningDraft] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    sensitivity_flags: list[SensitivityFlagDraft] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You interpret ONE dataset for a data project, using only its metadata and "
    "deterministic profiling statistics. You are given column names, inferred "
    "types, null rates, distinct counts, whether a column is a probable key, "
    "capped top values, and a tiny sample (some values may be redacted). You do "
    "NOT see the full data.\n\n"
    "Produce:\n"
    "- business_entity: what one row of this dataset represents in business "
    "terms (e.g. 'a customer order line').\n"
    "- grain: 'one row = ...' — the level of detail.\n"
    "- key_columns: columns that most likely identify a row (use the "
    "probable-key and distinct-ratio hints).\n"
    "- column_meanings: a short plain-language meaning for each meaningful "
    "column. Skip columns whose purpose is unclear rather than guessing.\n"
    "- caveats: anything a consumer must know — high null rates, ambiguous "
    "columns, likely duplicates, suspected mixed units, uncertainty about the "
    "grain. If you cannot tell what a column is, say so here.\n"
    "- sensitivity_flags: columns that look like personal or sensitive data "
    "from their name or stats (email, phone, name, national id, financial). "
    "Flag conservatively.\n\n"
    "Never invent a statistic and never contradict the numbers you are given. "
    "If the profiling summary and the Data Brief disagree, note it in caveats.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _brief_lines(brief: dict) -> list[str]:
    if not brief:
        return ["Data Brief: (not available)"]
    return [
        "Data Brief:",
        f"  goal: {brief.get('business_goal', '')}",
        f"  decision: {brief.get('decision_context', '')}",
        f"  audience: {', '.join(brief.get('audience', []))}",
    ]


def build_user_prompt(context: dict) -> str:
    brief = context.get("data_brief") or {}
    dataset = context.get("dataset") or {}
    columns = context.get("profile_columns") or []
    table = context.get("profile_table") or {}

    parts = [
        *_brief_lines(brief),
        "",
        f"Dataset: {dataset.get('name', '')}  "
        f"({dataset.get('source_type', '')}, {table.get('row_count', '?')} rows, "
        f"{table.get('column_count', '?')} columns"
        + (", SAMPLED" if table.get("sampled") else "")
        + ")",
        f"Duplicate rows: {table.get('duplicate_row_count', 0)}",
        "",
        "COLUMN PROFILE (deterministic — do not change these numbers):",
    ]
    for col in columns:
        line = (
            f"- {col.get('name')} [{col.get('dtype')}] "
            f"nulls={col.get('null_pct', 0)}% distinct={col.get('distinct_pct', 0)}% "
            f"probable_key={bool(col.get('probable_key'))}"
        )
        rng = col.get("numeric_range") or col.get("date_range")
        if rng:
            line += f" range={rng}"
        top = col.get("top_values") or []
        if top:
            line += "  top=" + "; ".join(
                f"{t.get('value')}({t.get('count')})" for t in top[:5]
            )
        sample = col.get("sample") or []
        if sample:
            line += "  sample=" + ", ".join(str(s) for s in sample)
        parts.append(line)

    parts += [
        "",
        "Interpret this dataset. Do not restate the numbers; explain what the "
        "dataset is and how to use it.",
    ]
    return "\n".join(parts)


SOURCE_INTERPRETATION = Operation(
    name="source_interpretation",
    system_prompt=SYSTEM_PROMPT,
    schema=SourceInterpretationDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
