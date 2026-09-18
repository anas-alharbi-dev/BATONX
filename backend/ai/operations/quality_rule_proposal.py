"""
quality_rule_proposal — AI proposes Data Quality RULES (decisions) from the
deterministic observations + approved context. It never produces observed
statistics and never decides pass/fail. Phase I-2.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "quality_rules/v1"

_Dimension = Literal[
    "completeness", "uniqueness", "validity", "consistency", "duplicates",
    "schema", "freshness",
]
_Assertion = Literal["not_null", "unique", "in_set", "range", "regex", "row_count_gt"]


class QualityRuleDraft(BaseModel):
    dataset_ref: str = Field(min_length=1)
    column: str = ""
    dimension: _Dimension
    assertion: _Assertion
    params: dict = Field(default_factory=dict)
    rationale: str = ""
    related_observations: list[str] = Field(default_factory=list)
    accepted_risk: bool = False


class QualityRulesDraft(BaseModel):
    rules: list[QualityRuleDraft] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You propose Data Quality RULES for a data project. A rule is a decision "
    "about what 'good' data means — not an observation.\n\n"
    "You are given the approved Data Brief, the approved interpretation of each "
    "dataset, and the deterministic quality observations (DQ-xx) computed from "
    "profiling. The observations are the ONLY evidence — do not invent data "
    "problems.\n\n"
    "For each rule use exactly one of these assertions:\n"
    "- not_null   (params: {})                       — needs a column\n"
    "- unique     (params: {})                       — needs a column\n"
    "- in_set     (params: {values: [...]})          — allowed values\n"
    "- range      (params: {min?: number, max?: number})\n"
    "- regex      (params: {pattern: '...'})         — every non-null value must match\n"
    "- row_count_gt (params: {threshold: int})       — table-level\n\n"
    "Guidance:\n"
    "- Cite the DQ ids that motivate a rule in related_observations.\n"
    "- If an observation reflects acceptable reality (e.g. an optional field is "
    "sometimes null on purpose), you may still propose the rule with "
    "accepted_risk = true, or omit it — say which in rationale.\n"
    "- Prefer a small, high-signal set. It is fine to propose zero rules if the "
    "data looks clean.\n"
    "- Every dataset_ref MUST be one of the dataset ids given below.\n\n"
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
    observations = context.get("observations") or []

    parts = [
        "DATA BRIEF",
        f"goal: {brief.get('business_goal', '')}",
        f"decision: {brief.get('decision_context', '')}",
        "",
        "DATASETS",
    ]
    for ds in datasets:
        parts.append(
            f"- {ds['id']}  '{ds['name']}' ({ds['source_type']}, "
            f"{ds.get('row_count', '?')} rows)"
        )
        interp = ds.get("interpretation") or {}
        if interp:
            parts.append(
                f"    entity: {interp.get('business_entity', '')} | "
                f"grain: {interp.get('grain', '')} | "
                f"keys: {', '.join(interp.get('key_columns', []))}"
            )
        for col in ds.get("columns", []):
            parts.append(
                f"    col {col['name']} [{col['dtype']}] "
                f"null%={col.get('null_pct', 0)} distinct%={col.get('distinct_pct', 0)}"
            )

    parts += ["", "DETERMINISTIC OBSERVATIONS (evidence — do not restate)"]
    for o in observations:
        parts.append(
            f"- {o['id']} [{o['dimension']}/{o['severity']}] "
            f"{o.get('column') or '(table)'}: {o['statement']}"
        )

    parts += ["", "Propose the Quality Rules now."]
    return "\n".join(parts)


QUALITY_RULE_PROPOSAL = Operation(
    name="quality_rule_proposal",
    system_prompt=SYSTEM_PROMPT,
    schema=QualityRulesDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
