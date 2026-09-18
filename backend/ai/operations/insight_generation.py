"""
insight_generation — AI interprets deterministic Analysis findings (Phase
I-4). It sees computed facts, never raw data rows. The service layer runs a
strict evidence validator (``projects.data.insights``) before persisting
anything — this operation's job is to make compliance easy, not to be trusted
blindly.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "insight/v1"

_Confidence = Literal["low", "medium", "high"]


class InsightDraft(BaseModel):
    fact: str = Field(
        min_length=1,
        description="MUST be copied VERBATIM from one of the given findings' 'statement' — never reworded, never a different number.",
    )
    interpretation: str = Field(min_length=1)
    recommendation: str = Field(default="")
    confidence: _Confidence = "medium"
    supporting_finding_ids: list[str] = Field(
        default_factory=list, description="Finding ids (e.g. F-01) this insight is based on. MUST be non-empty."
    )
    caveats: list[str] = Field(default_factory=list)


class InsightsDraft(BaseModel):
    insights: list[InsightDraft] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You interpret DETERMINISTIC Analysis findings for a data project. You are "
    "given a list of findings, each with an id (F-01, ...), a deterministic "
    "'statement' sentence, its computed metric_values/breakdown, and evidence "
    "references. These numbers were computed by SQL, not by you — you cannot "
    "change them.\n\n"
    "For each insight you propose:\n"
    "- fact: copy ONE finding's 'statement' EXACTLY, character for character. "
    "Do not reword it, do not round differently, do not combine two findings "
    "into one sentence here.\n"
    "- supporting_finding_ids: the finding id(s) (e.g. ['F-01']) this insight "
    "is based on — MUST include the id of the finding you copied into fact, "
    "and MUST be non-empty.\n"
    "- interpretation: explain what the fact means in plain language. Any "
    "number you state here MUST already appear in the findings you cited — "
    "never introduce a new number.\n"
    "- recommendation: an ADVISORY suggestion for what a human might do next. "
    "This is the ONLY place you may suggest investigating a possible cause — "
    "phrase it as a suggestion ('investigate whether...', 'consider...'), "
    "never as a settled fact.\n"
    "- CRITICAL: never write in 'fact' or 'interpretation' that something "
    "'caused', 'led to', or was 'due to' something else — this analysis method "
    "only supports correlation/association, not causation. That kind of "
    "language belongs only in 'recommendation', phrased as something to "
    "investigate.\n"
    "- confidence: low/medium/high, based on how directly the evidence "
    "supports the interpretation.\n"
    "- caveats: anything a reader must know (sampling, data quality, small "
    "sample size, ...).\n\n"
    "Propose 1-3 insights, each grounded in one or more of the given findings. "
    "Do not propose an insight with no clear supporting finding.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def build_user_prompt(context: dict) -> str:
    findings = context.get("findings") or []
    brief = context.get("data_brief") or {}
    caveats = context.get("data_caveats") or []

    parts = [
        f"DATA BRIEF GOAL: {brief.get('business_goal', '')}",
        "",
        "FINDINGS (computed by SQL — these are the only facts you may cite)",
    ]
    for f in findings:
        parts.append(f"- {f['id']}: {f['statement']}")
        if f.get("metric_values"):
            parts.append(f"    metric_values: {f['metric_values']}")
        if f.get("breakdown"):
            parts.append(f"    breakdown: {f['breakdown'][:10]}")
    if caveats:
        parts += ["", "DATA CAVEATS", *[f"- {c}" for c in caveats]]

    parts += ["", "Propose the insight(s) now."]
    return "\n".join(parts)


INSIGHT_GENERATION = Operation(
    name="insight_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=InsightsDraft,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
