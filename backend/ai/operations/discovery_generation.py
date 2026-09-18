"""
discovery_generation — turn a raw idea (+ its analysis) into 3-6 dynamic,
high-value discovery questions.

Follows the same shape as every VYRA AI operation: an ``Operation`` (instruction
template) + a Pydantic output schema. The schema is intentionally strict so the
UI and database can rely on it; malformed model output triggers the one repair
retry in ``run_operation``.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from ai.base import Operation
from ai.prompts import QUALITY_RULES


class QuestionType(str, Enum):
    TEXT = "text"
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"


class DiscoveryQuestionSpec(BaseModel):
    question: str = Field(min_length=5, description="The question shown to the user.")
    type: QuestionType = Field(description="How the user answers.")
    options: list[str] = Field(
        default_factory=list,
        description="2-6 concise choices. Required for select types; omit for 'text'.",
    )
    why_it_matters: str = Field(
        min_length=5,
        description="One short sentence: what this decision changes downstream.",
    )

    @model_validator(mode="after")
    def _check_options(self) -> "DiscoveryQuestionSpec":
        if self.type in (QuestionType.SINGLE_SELECT, QuestionType.MULTI_SELECT):
            if not (2 <= len(self.options) <= 6):
                raise ValueError(
                    f"{self.type.value} questions need between 2 and 6 options"
                )
        else:
            self.options = []
        return self


class DiscoveryQuestions(BaseModel):
    questions: list[DiscoveryQuestionSpec] = Field(min_length=3, max_length=6)


SYSTEM_PROMPT = (
    "You are VYRA's discovery analyst. VYRA turns a software idea into a "
    "structured engineering workflow. Your job is to ask the few questions whose "
    "answers most change what gets built.\n\n"
    "You are given the raw idea and a short analysis of what is already known and "
    "what is unknown. Produce 3 to 6 questions that close the highest-impact "
    "unknowns. Make them specific to THIS idea - never a generic questionnaire.\n\n"
    "Use answer types deliberately:\n"
    "- single_select when the decision is one choice from a small set\n"
    "- multi_select when several may apply\n"
    "- text when the answer is genuinely open\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _bullets(items: list[str], empty: str) -> list[str]:
    return [f"- {item}" for item in items] if items else [f"- {empty}"]


def build_user_prompt(context: dict) -> str:
    analysis = context.get("analysis") or {}
    known = analysis.get("known") or []
    unknowns = analysis.get("unknowns") or []
    lines = [
        'Idea:\n"""',
        context["idea"],
        '"""',
        "",
        f"Domain: {analysis.get('domain', 'unknown')}",
        f"Product type: {analysis.get('product_type_guess', 'unknown')}",
        "",
        "Known:",
        *_bullets(known, "(none stated)"),
        "",
        "Unknown / undecided:",
        *_bullets(unknowns, "(none identified)"),
        "",
        "Generate the discovery questions.",
    ]
    return "\n".join(lines)


DISCOVERY_GENERATION = Operation(
    name="discovery_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=DiscoveryQuestions,
    build_user_prompt=build_user_prompt,
)
