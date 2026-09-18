"""
roadmap_generation — turn the approved Blueprint + Architecture into a
project-specific, dependency-ordered Development Roadmap.

The model does not assign ids/orders and refers to dependencies by task TITLE;
``projects.roadmap.normalize_roadmap_content`` assigns ids and resolves the
dependency graph.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES, render_business_logic


class TaskDraft(BaseModel):
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1, description="What this task delivers.")
    why: str = Field(min_length=1, description="Why it matters to the product.")
    requirements: list[str] = Field(
        default_factory=list,
        description="Blueprint requirement ids (e.g. FR3) or short phrases this task addresses.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Exact titles of tasks that must be done first. Earlier tasks only.",
    )
    expected_output: str = Field(min_length=1, description="The concrete artifact produced.")
    acceptance_criteria: list[str] = Field(
        min_length=1, description="Checks that prove the task is done."
    )


class PhaseDraft(BaseModel):
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    tasks: list[TaskDraft] = Field(min_length=1)


class RoadmapDraft(BaseModel):
    phases: list[PhaseDraft] = Field(min_length=2, max_length=8)


SYSTEM_PROMPT = (
    "You are VYRA's delivery lead. Given an APPROVED Product Blueprint and an "
    "APPROVED Architecture, produce a Development Roadmap this specific project "
    "can execute with an AI coding agent.\n\n"
    "Rules specific to the Roadmap:\n"
    "- The approved Blueprint and Architecture are authoritative. Do not add "
    "product scope or contradict any approved decision.\n"
    "- Structure it as Phases -> Tasks. Order phases so foundations come before "
    "the core domain, which comes before secondary features and hardening.\n"
    "- Each task must be small enough for one focused agent session yet produce a "
    "verifiable increment. If a task would take many unrelated changes, split it.\n"
    "- Make dependencies explicit and correct: list the exact titles of tasks "
    "that must be finished first. Only depend on EARLIER tasks.\n"
    "- Tie tasks to the Blueprint: cite requirement ids in 'requirements' where "
    "they apply.\n"
    "- acceptance_criteria are concrete, checkable statements - not restatements "
    "of the objective.\n\n"
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
    arch = context.get("architecture") or {}
    reqs = [
        f"{r['id']} [{r['priority']}] {r['text']}"
        for r in bp.get("functional_requirements", [])
    ]
    components = [f"{c['name']}: {c['responsibility']}" for c in arch.get("components", [])]
    entities = [
        f"{e['entity']} ({', '.join(e.get('fields', []))})"
        for e in arch.get("data_model", [])
    ]
    api_areas = [f"{a['name']}: {a['purpose']}" for a in arch.get("api_areas", [])]

    parts = [
        'Idea:\n"""',
        context["idea"],
        '"""',
        "",
        f"MVP features: {', '.join(bp.get('mvp_features', []))}",
        "",
        *_lines("Functional requirements", reqs),
        "",
        *_lines("Business rules", bp.get("business_rules")),
        "",
        f"Architecture style: {arch.get('overview', {}).get('style', '')}",
        f"Frontend: {arch.get('frontend', {}).get('choice', '')}",
        f"Backend: {arch.get('backend', {}).get('choice', '')}",
        f"Database: {arch.get('database', {}).get('choice', '')}",
        f"Auth: {arch.get('auth', {}).get('approach', '')}",
        "",
        *_lines("Components", components),
        "",
        *_lines("API areas", api_areas),
        "",
        *_lines("Data entities", entities),
        "",
        *_lines("Integrations", [i["name"] for i in arch.get("integrations", [])]),
        "",
        *_lines("Constraints", arch.get("constraints")),
        "",
        *render_business_logic(context.get("business_logic") or {}),
        "",
        "Produce the Development Roadmap. Ensure tasks cover the business rules, "
        "validations, approval flows, and state transitions above.",
    ]
    return "\n".join(parts)


ROADMAP_GENERATION = Operation(
    name="roadmap_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=RoadmapDraft,
    build_user_prompt=build_user_prompt,
)
