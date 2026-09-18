"""
architecture_generation — turn the approved Blueprint + Project Context into a
pragmatic recommended Architecture.

The stored schema (``projects.architecture.ArchitectureContent``) is reused
directly as the AI output contract - there is no transform between them.
"""
from __future__ import annotations

from ai.base import Operation
from ai.prompts import QUALITY_RULES, render_business_logic
from projects.architecture import ArchitectureContent

SYSTEM_PROMPT = (
    "You are VYRA's software architect. Given an APPROVED Product Blueprint and "
    "project context, recommend an architecture a semi-technical builder could "
    "act on.\n\n"
    "Rules specific to the Architecture:\n"
    "- The approved Blueprint AND the approved Business Logic (if present) are "
    "authoritative. Your components, APIs, data model, and auth model must "
    "support every business rule, permission, validation, and state transition. "
    "Do not contradict them or invent new rules/permissions.\n"
    "- Be pragmatic and proportional to THIS product. Prefer a well-structured "
    "monolith. Do NOT reach for microservices, Kubernetes, event-driven "
    "architecture, message queues, or extra infrastructure unless the approved "
    "requirements genuinely force it - and if they do, say why in key_decisions.\n"
    "- For frontend, backend, database, auth, and deployment, give a concrete "
    "choice and a concise 'why this?' a non-expert can follow.\n"
    "- components are the few real building blocks of the system, each with one "
    "clear responsibility.\n"
    "- api_areas are coarse boundaries (e.g. 'Catalog API'), not endpoint lists.\n"
    "- data_model is conceptual: entities with key fields and their relationships.\n"
    "- integrations only lists genuinely required third parties.\n"
    "- security is concrete, task-relevant practices for this product.\n"
    "- key_decisions captures the choices and constraints a reviewer should know "
    "about, each with a short rationale.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _bullets(label: str, items) -> list[str]:
    items = items or []
    if not items:
        return [f"{label}: (none)"]
    return [f"{label}:", *(f"- {item}" for item in items)]


def build_user_prompt(context: dict) -> str:
    bp = context.get("blueprint") or {}
    roles = [f"{r['name']}: {r['description']}" for r in bp.get("user_roles", [])]
    reqs = [
        f"[{r['priority']}] {r['text']}" for r in bp.get("functional_requirements", [])
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
        f"Product summary: {bp.get('product_summary', '')}",
        f"Problem: {bp.get('problem', '')}",
        f"Solution: {bp.get('solution', '')}",
        "",
        *_bullets("Target users", bp.get("target_users")),
        "",
        *_bullets("User roles", roles),
        "",
        *_bullets("MVP features", bp.get("mvp_features")),
        "",
        *_bullets("Functional requirements", reqs),
        "",
        *_bullets("Business rules", bp.get("business_rules")),
        "",
        *_bullets("Key user flows", flows),
        "",
        *_bullets("Out of scope", bp.get("out_of_scope")),
        "",
        *render_business_logic(context.get("business_logic") or {}),
        "",
        "Recommend the architecture.",
    ]
    return "\n".join(parts)


ARCHITECTURE_GENERATION = Operation(
    name="architecture_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=ArchitectureContent,
    build_user_prompt=build_user_prompt,
)
