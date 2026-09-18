"""
review_prompt_generation — compose ONE self-contained *verification* prompt for a
reviewer or an external coding agent (Claude Code, Codex, Cursor, ...), from the
same deterministically-assembled task context used for the Build Prompt
(``projects.context_selection``), plus the most recent Build Prompt for the task
when one exists.

A Review Prompt is NOT another Build Prompt. It instructs the reader to inspect,
verify, test, compare, and report — not to implement the feature. Output is a
single markdown string; VYRA does not parse or execute it.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES, render_business_logic

# Explicit, stable, operation-level prompt version. Recorded on AIRequestLog.
PROMPT_VERSION = "review_prompt/v1"


class ReviewPrompt(BaseModel):
    prompt_markdown: str = Field(
        min_length=200,
        description="The full review/verification prompt, in markdown, with clear sections.",
    )


SYSTEM_PROMPT = (
    "You are VYRA's review-prompt author. Write ONE verification prompt that a "
    "developer will paste, unchanged, into a reviewer or an AI coding agent to "
    "VERIFY an already-implemented Roadmap task.\n\n"
    "This is a REVIEW prompt, not a build prompt. It must tell the reader to "
    "inspect, run, test, compare against the approved context, and report "
    "findings. It must NOT primarily instruct the reader to implement the "
    "feature. If defects are found, the reader may describe what is wrong, where, "
    "why it violates the approved context, and what should be corrected — but the "
    "primary purpose stays REVIEW.\n\n"
    "Use ONLY the context provided. The approved Blueprint, Business Logic, "
    "Architecture, and Roadmap are authoritative: judge the implementation "
    "against them. Do not invent requirements, rename components or entities, or "
    "add rules that are not in the context.\n\n"
    "Structure the markdown with these sections (omit one only if it would be "
    "empty):\n"
    "1. Review objective — one or two lines: what is being verified and against "
    "what.\n"
    "2. Task being reviewed — id, title, objective, expected output.\n"
    "3. Expected behavior — what a correct implementation does.\n"
    "4. Acceptance criteria — copy each; the reviewer marks pass/fail with "
    "evidence.\n"
    "5. Relevant business rules — the exact permissions, validations, approval "
    "rules, state transitions, and edge cases that must hold (cite ids and the "
    "requirement ids they trace to).\n"
    "6. Relevant architecture constraints — the stack, boundaries, components, "
    "and decisions the implementation must respect.\n"
    "7. What VYRA instructed (if a Build Prompt is given) — 2–4 lines summarising "
    "what the agent was told to build, so the reviewer can compare intent vs. "
    "result.\n"
    "8. Review checklist — concrete checks grouped as: Functional correctness; "
    "Business logic (permissions, validations, approvals, state transitions, "
    "edge cases, no invented rules); Architecture (follows approved design, "
    "respects boundaries, no unnecessary coupling, no unrelated redesign, APIs/"
    "modules used correctly); Regression safety (existing behavior intact, no "
    "unrelated files/behavior changed, dependencies respected); Scope control "
    "(implementation does not exceed the task, unrelated refactors identified, "
    "hidden assumptions surfaced).\n"
    "9. Validation / test expectations — the tests that should exist: happy "
    "paths, validation failures, permission failures, edge cases, regression "
    "cases.\n"
    "10. Scope guardrails — what was explicitly out of scope for this task and "
    "must not have been changed.\n"
    "11. Required review output — instruct the reviewer to produce a structured "
    "result with: Status (PASS | PASS WITH ISSUES | FAIL); Summary; Findings "
    "(severity, issue, evidence, expected behavior, recommended correction); "
    "Acceptance criteria table (criterion, pass/fail, evidence); Business logic "
    "compliance; Architecture compliance; Tests / validation; Out-of-scope "
    "changes; Final recommendation.\n\n"
    "Be specific and concise. No filler, no marketing language, no restating the "
    "whole project. Reference concrete names and ids from the context. Make it "
    "unmistakable that the reader is verifying, not building.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _lines(label: str, items) -> list[str]:
    items = items or []
    if not items:
        return [f"{label}: (none)"]
    return [f"{label}:", *(f"- {item}" for item in items)]


def _build_prompt_lines(bp: dict) -> list[str]:
    """The most recent Build Prompt for the task, as supporting context."""
    if not bp:
        return [
            "PRIOR BUILD PROMPT: (none stored — review from the task context alone)"
        ]
    head = "PRIOR BUILD PROMPT (what VYRA instructed the coding agent to build; "
    head += "for comparison only, not authoritative):"
    meta = (
        f"(generated {bp.get('created_at', '')}"
        + (f", model {bp['model']}" if bp.get("model") else "")
        + ")"
    )
    return [head, meta, "---", bp.get("content", ""), "---"]


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
        *_build_prompt_lines(context.get("build_prompt") or {}),
        "",
        "Write the review prompt now. It must instruct the reader to VERIFY the "
        "implementation against the approved context above — check functional "
        "correctness, every acceptance criterion, business-logic compliance "
        "(permissions, validations, approvals, state transitions, edge cases, no "
        "invented rules), architecture compliance, regression safety, and scope "
        "control — and to return the structured review result. It must NOT tell "
        "the reader to implement the feature.",
    ]
    return "\n".join(parts)


REVIEW_PROMPT_GENERATION = Operation(
    name="review_prompt_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=ReviewPrompt,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
