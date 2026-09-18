"""
data_brief_generation — turn a data-project idea + goal into a structured Data
Brief (Phase I-1). Same shape as every VYRA operation: an ``Operation`` +
a Pydantic output schema. Provider-agnostic; no provider-specific code.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "data_brief/v1"


class DataBriefDraft(BaseModel):
    business_goal: str = Field(min_length=1)
    decision_context: str = Field(min_length=1)
    audience: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    candidate_sources: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You are BATONX's data-project brief author. Turn a described data or "
    "analytics need into a structured Data Brief that a data team could scope "
    "work from.\n\n"
    "Rules specific to the Data Brief:\n"
    "- business_goal: the outcome the data work must enable, in one or two "
    "sentences. Not a task list.\n"
    "- decision_context: the concrete decision(s) or action(s) this analysis "
    "will inform, and who acts on them.\n"
    "- audience: the roles that will consume the result (e.g. 'Head of Sales', "
    "'Growth team').\n"
    "- success_criteria: how the team will know the work succeeded — measurable "
    "or clearly checkable statements.\n"
    "- constraints: time, data-access, tooling, privacy, or budget limits that "
    "are already known.\n"
    "- candidate_sources: data sources the user named or clearly implied (files, "
    "systems, tables). Do not invent sources.\n"
    "- out_of_scope: things a reader might expect but that are deliberately "
    "excluded for now.\n\n"
    "Ground everything in what the user actually said. Do not invent goals, "
    "audiences, sources, or metrics that were not stated or clearly implied.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _lines(label: str, items) -> list[str]:
    items = items or []
    if not items:
        return [f"{label}: (none)"]
    return [f"{label}:", *(f"- {item}" for item in items)]


def build_user_prompt(context: dict) -> str:
    analysis = context.get("analysis") or {}
    parts = [
        'Data need (raw):\n"""',
        context.get("idea", ""),
        '"""',
        "",
        f"Data goal / mode: {context.get('data_goal', 'analytics')}",
        f"Domain: {analysis.get('domain', 'unknown')}",
        "",
        *_lines("Known", analysis.get("known")),
        "",
        *_lines("Unknown / undecided", analysis.get("unknowns")),
        "",
        "Produce the Data Brief.",
    ]
    return "\n".join(parts)


DATA_BRIEF_GENERATION = Operation(
    name="data_brief_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=DataBriefDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
