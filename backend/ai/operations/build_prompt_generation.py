"""
build_prompt_generation — compose ONE self-contained implementation prompt for an
external coding agent (Claude Code, Codex, Cursor, Replit, ...), from the
deterministically-assembled task context (``projects.context_selection``).

Output is a single markdown string. It is for a human to copy into their agent;
VYRA does not parse or execute it.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES, render_business_logic


class BuildPrompt(BaseModel):
    prompt_markdown: str = Field(
        min_length=200,
        description="The full implementation prompt, in markdown, with clear sections.",
    )


SYSTEM_PROMPT = (
    "You are VYRA's build-prompt author. Write ONE implementation prompt that a "
    "developer will paste, unchanged, into an external AI coding agent to "
    "implement a single Roadmap task.\n\n"
    "Use ONLY the context provided. The approved Blueprint, Architecture, and "
    "Roadmap are authoritative - do not invent requirements, rename components or "
    "entities, or contradict any approved decision.\n\n"
    "Structure the markdown with these sections (omit one only if it would be "
    "empty):\n"
    "1. Role - one line telling the agent what it is doing.\n"
    "2. Objective - the task's goal in one or two sentences.\n"
    "3. Project context - 2-4 lines only: the product and the parts of the "
    "architecture this task touches. No project-wide dump.\n"
    "4. Architecture constraints - the stack and rules the implementation must "
    "follow (framework, database, auth approach, relevant components/entities).\n"
    "5. The task - what to build, concretely.\n"
    "6. Requirements - the specific requirements this task satisfies (cite ids).\n"
    "7. Prerequisites already done - the completed dependencies and what they "
    "produced, so the agent can build on them.\n"
    "8. Expected output - the concrete artifact(s) to produce.\n"
    "9. Acceptance criteria - copy them; the agent must satisfy each.\n"
    "10. Implementation constraints - keep it minimal, match existing patterns, "
    "no new dependencies unless required, etc.\n"
    "11. How to verify - concrete checks / tests the agent should run.\n"
    "12. Out of scope / do not change - explicit boundaries so the agent does "
    "not touch unrelated code or expand scope.\n\n"
    "Be specific and concise. No filler, no marketing language, no restating the "
    "whole project. Reference concrete names from the context.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _lines(label: str, items) -> list[str]:
    items = items or []
    if not items:
        return [f"{label}: (none)"]
    return [f"{label}:", *(f"- {item}" for item in items)]


def build_user_prompt(context: dict) -> str:
    product = context.get("product", {})
    task = context.get("task", {})
    arch = context.get("architecture", {})

    deps = [
        f"{d['id']} {d['title']} [{d['status']}] -> {d['expected_output']}"
        for d in context.get("dependencies", [])
    ]
    reqs = [
        f"{r['id']} [{r['priority']}] {r['text']}"
        for r in context.get("requirements", [])
    ]
    roles = [f"{r['name']}: {r['description']}" for r in context.get("user_roles", [])]
    components = [
        f"{c['name']}: {c['responsibility']}" for c in arch.get("components", [])
    ]
    api_areas = [f"{a['name']}: {a['purpose']}" for a in arch.get("api_areas", [])]
    entities = [
        f"{e['entity']} (fields: {', '.join(e.get('fields', []))}; "
        f"relationships: {', '.join(e.get('relationships', []))})"
        for e in arch.get("data_model", [])
    ]
    integrations = [
        f"{i['name']}: {i['purpose']}" for i in arch.get("integrations", [])
    ]
    decisions = [
        f"{d['decision']} - {d['rationale']}" for d in arch.get("key_decisions", [])
    ]

    parts = [
        f"PRODUCT: {product.get('idea', '')}",
        f"Domain: {product.get('domain', '')}",
        f"Problem: {product.get('problem', '')}",
        f"Solution: {product.get('solution', '')}",
        "",
        f"TASK {task.get('id', '')} (phase: {task.get('phase_title', '')}, "
        f"status: {task.get('status', '')})",
        f"Title: {task.get('title', '')}",
        f"Objective: {task.get('objective', '')}",
        f"Why it matters: {task.get('why', '')}",
        f"Expected output: {task.get('expected_output', '')}",
        "",
        *_lines("Acceptance criteria", task.get("acceptance_criteria")),
        "",
        *_lines("Requirements", reqs),
        *_lines("Requirement notes", context.get("requirement_notes")),
        "",
        *_lines("Completed prerequisites", deps),
        "",
        "ARCHITECTURE",
        f"Style: {arch.get('style', '')}",
        f"Frontend: {arch.get('frontend', '')}",
        f"Backend: {arch.get('backend', '')}",
        f"Database: {arch.get('database', '')}",
        f"Auth: {arch.get('auth', '')}",
        "",
        *_lines("Relevant components", components),
        *_lines("Relevant API areas", api_areas),
        *_lines("Relevant data entities", entities),
        *_lines("Relevant integrations", integrations),
        *_lines("Relevant security constraints", arch.get("security")),
        *_lines("Key decisions", decisions),
        *_lines("Constraints", arch.get("constraints")),
        *_lines("User roles", roles),
        *_lines("Business rules (from Blueprint)", context.get("business_rules")),
        "",
        *render_business_logic(context.get("business_logic") or {}),
        "",
        "Write the implementation prompt now. If Business Logic rules are listed, "
        "the prompt MUST instruct the agent to implement those exact rules, "
        "permissions, validations, and state transitions - the agent must not "
        "invent its own.",
    ]
    return "\n".join(parts)


BUILD_PROMPT_GENERATION = Operation(
    name="build_prompt_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=BuildPrompt,
    build_user_prompt=build_user_prompt,
)
