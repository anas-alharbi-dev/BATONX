"""
business_logic_generation — derive explicit behavioral rules from the approved
Blueprint + upstream context.

Two-schema pattern (like blueprint_generation): the model returns
``BusinessLogicDraft`` (no ids); ``projects.business_logic`` assigns stable
``BR-01`` / ``VAL-01`` / ``EC-01`` ids and canonicalises requirement references.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

# Stable, operation-level prompt version. Bump manually if this prompt or the
# BusinessLogicDraft schema changes materially. Recorded on AIRequestLog.
PROMPT_VERSION = "business_logic/v1"


class ActorDraft(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class PermissionDraft(BaseModel):
    actor: str = Field(min_length=1)
    can: list[str] = Field(min_length=1)
    conditions: list[str] = Field(default_factory=list)


class BusinessRuleDraft(BaseModel):
    statement: str = Field(min_length=1, description="The rule, one sentence.")
    actor: str = Field(default="", description="Actor the rule applies to, if any.")
    conditions: list[str] = Field(default_factory=list, description="Triggers / guards.")
    outcome: str = Field(default="", description="What happens when the rule fires.")
    exceptions: list[str] = Field(default_factory=list)
    validations: list[str] = Field(default_factory=list)
    related_requirements: list[str] = Field(
        default_factory=list, description="Functional requirement ids this rule comes from."
    )
    derived: bool = Field(
        default=False,
        description="True if logically required by requirements but not explicitly stated.",
    )


class ValidationDraft(BaseModel):
    rule: str = Field(min_length=1)
    applies_to: str = Field(default="")
    related_requirements: list[str] = Field(default_factory=list)


class ApprovalFlowDraft(BaseModel):
    name: str = Field(min_length=1)
    approver: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    conditions: list[str] = Field(default_factory=list)
    related_requirements: list[str] = Field(default_factory=list)


class StateTransitionDraft(BaseModel):
    entity: str = Field(min_length=1)
    from_state: str = Field(min_length=1)
    to_state: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    actor: str = Field(default="")
    guards: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    related_requirements: list[str] = Field(default_factory=list)


class EdgeCaseDraft(BaseModel):
    scenario: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    related_requirements: list[str] = Field(default_factory=list)


class BusinessLogicDraft(BaseModel):
    summary: str = Field(min_length=1)
    actors: list[ActorDraft] = Field(min_length=1)
    permissions: list[PermissionDraft] = Field(default_factory=list)
    business_rules: list[BusinessRuleDraft] = Field(min_length=1)
    validations: list[ValidationDraft] = Field(default_factory=list)
    approval_flows: list[ApprovalFlowDraft] = Field(default_factory=list)
    state_transitions: list[StateTransitionDraft] = Field(default_factory=list)
    edge_cases: list[EdgeCaseDraft] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You are VYRA's business analyst. Given an APPROVED Product Blueprint and the "
    "discovery answers, make the product's REQUIRED BEHAVIOR explicit so an AI "
    "coding agent cannot invent permissions or rules later.\n\n"
    "Rules specific to Business Logic:\n"
    "- Derive behavior from the approved requirements. You may add rules that are "
    "logically REQUIRED by those requirements - mark them `derived: true`. Do NOT "
    "invent unrelated product functionality or new scope.\n"
    "- Every business rule: who (actor), under what conditions, what outcome, "
    "what exceptions. Cite the functional requirement id(s) it comes from in "
    "`related_requirements` whenever one applies.\n"
    "- validations are business-level ('a booking cannot overlap another'), not "
    "framework validation.\n"
    "- Only include state_transitions for entities that genuinely have a "
    "lifecycle. Capture from/to/trigger/actor/guards/effects.\n"
    "- approval_flows: multi-step human approvals the product requires.\n"
    "- edge_cases: meaningful failure / boundary behavior that must be handled.\n"
    "- If a consequential rule cannot be safely derived, DO NOT guess a policy - "
    "add it to `open_questions` for a human to decide.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _lines(label: str, items) -> list[str]:
    items = items or []
    if not items:
        return [f"{label}: (none)"]
    return [f"{label}:", *(f"- {item}" for item in items)]


def build_user_prompt(context: dict) -> str:
    bp = context.get("blueprint") or {}
    discovery = context.get("discovery") or {}
    questions = discovery.get("questions") or []
    answers = discovery.get("answers") or {}

    qa = []
    for q in questions:
        raw = answers.get(q["id"])
        rendered = ", ".join(raw) if isinstance(raw, list) else (raw or "(no answer)")
        qa.append(f"- {q['question']} -> {rendered}")

    roles = [f"{r['name']}: {r['description']}" for r in bp.get("user_roles", [])]
    reqs = [
        f"{r['id']} [{r['priority']}] {r['text']}"
        for r in bp.get("functional_requirements", [])
    ]
    flows = [
        f"{f['name']}: " + " -> ".join(f.get("steps", []))
        for f in bp.get("user_flows", [])
    ]

    parts = [
        'Idea:\n"""',
        context["idea"],
        '"""',
        "",
        f"Problem: {bp.get('problem', '')}",
        f"Solution: {bp.get('solution', '')}",
        "",
        *_lines("User roles", roles),
        "",
        *_lines("Functional requirements", reqs),
        "",
        *_lines("Business rules (from Blueprint)", bp.get("business_rules")),
        "",
        *_lines("Key user flows", flows),
        "",
        *_lines("Discovery answers", qa),
        "",
        "Produce the Business Logic.",
    ]
    return "\n".join(parts)


BUSINESS_LOGIC_GENERATION = Operation(
    name="business_logic_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=BusinessLogicDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
