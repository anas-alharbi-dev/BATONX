"""
blueprint_generation — turn the idea + analysis + discovery answers into a
structured Product Blueprint.

Same shape as every VYRA operation: an ``Operation`` (instruction template) + a
Pydantic output schema. The model does NOT assign requirement ids — the domain
layer does that after generation (see ``projects.blueprint``).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES


class Priority(str, Enum):
    MUST = "must"
    SHOULD = "should"
    COULD = "could"


class UserRoleDraft(BaseModel):
    name: str = Field(min_length=1, description="Role name, e.g. 'Supplier'.")
    description: str = Field(min_length=1, description="What this role does in the product.")


class RequirementDraft(BaseModel):
    text: str = Field(min_length=3, description="One testable capability the system must provide.")
    priority: Priority = Field(default=Priority.SHOULD)


class UserFlowDraft(BaseModel):
    name: str = Field(min_length=1, description="Short flow name, e.g. 'Place an order'.")
    steps: list[str] = Field(min_length=1, description="Ordered steps, user-visible.")


class BlueprintDraft(BaseModel):
    product_summary: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    solution: str = Field(min_length=1)
    target_users: list[str] = Field(min_length=1)
    user_roles: list[UserRoleDraft] = Field(min_length=1)
    core_features: list[str] = Field(min_length=1)
    mvp_features: list[str] = Field(min_length=1)
    future_features: list[str] = Field(default_factory=list)
    functional_requirements: list[RequirementDraft] = Field(min_length=1)
    business_rules: list[str] = Field(default_factory=list)
    user_flows: list[UserFlowDraft] = Field(min_length=1)
    out_of_scope: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You are VYRA's product architect. Turn a software idea, its analysis, and "
    "the user's discovery answers into a structured Product Blueprint that a "
    "developer could build from.\n\n"
    "Rules specific to the Blueprint:\n"
    "- Ground every section in the idea and the discovery answers. If the answers "
    "settled a question, reflect that decision; do not re-open it.\n"
    "- mvp_features is a tight subset of core_features - only what is needed for a "
    "first useful release. Push everything else to future_features.\n"
    "- functional_requirements are testable capabilities ('The system lets a "
    "supplier publish a price list'), each tagged must / should / could.\n"
    "- business_rules are constraints and invariants, not features.\n"
    "- user_flows are the 2-4 flows that matter most, as ordered user-visible steps.\n"
    "- out_of_scope names things a reader might expect but that are deliberately "
    "excluded for now.\n\n"
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
    discovery = context.get("discovery") or {}
    questions = discovery.get("questions") or []
    answers = discovery.get("answers") or {}

    qa_lines: list[str] = []
    for question in questions:
        raw = answers.get(question["id"])
        rendered = ", ".join(raw) if isinstance(raw, list) else (raw or "(no answer)")
        qa_lines.append(f"- {question['question']}\n  -> {rendered}")

    parts = [
        'Idea:\n"""',
        context["idea"],
        '"""',
        "",
        f"Domain: {analysis.get('domain', 'unknown')}",
        f"Product type: {analysis.get('product_type_guess', 'unknown')}",
        "",
        *_lines("Known", analysis.get("known")),
        "",
        *_lines("Unknown / undecided", analysis.get("unknowns")),
        "",
        "Discovery answers:",
        *(qa_lines or ["(none)"]),
        "",
        "Produce the Product Blueprint.",
    ]
    return "\n".join(parts)


BLUEPRINT_GENERATION = Operation(
    name="blueprint_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=BlueprintDraft,
    build_user_prompt=build_user_prompt,
)
