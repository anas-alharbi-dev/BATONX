"""
conversation_response — the Conversational Layer's single AI operation (Phase H).

Provider-agnostic: goes through ``ai.base.run_operation`` -> ``get_provider()`` ->
``AnthropicProvider`` like every other operation. No provider-specific code.

The model answers from the deterministically-assembled project context it is
given. It may explain and it may PROPOSE a change, but it can never apply one:
a ``proposed_change`` becomes a PENDING ``Proposal`` that a human must approve.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "conversation/v1"

# Artifacts a proposal may target. Kept in sync with
# ``projects.conversation_services._SUPPORTED_TARGETS``.
PROPOSAL_TARGETS = ("blueprint", "business_logic", "architecture")


class ProposedChange(BaseModel):
    target_artifact: Literal["blueprint", "business_logic", "architecture"]
    summary: str = Field(min_length=1, description="One line: what would change and where.")
    rationale: str = Field(default="", description="Why the user wants this.")
    # A partial ``content`` patch: {<section name>: <new value>, ...}. The
    # backend passes this straight to update_<artifact>, which validates it and
    # rejects unknown sections / invalid content. The AI is NOT trusted to get
    # this right — the domain service is the gate.
    sections: dict[str, Any] = Field(default_factory=dict)


class ConversationTurn(BaseModel):
    response: str = Field(min_length=1, description="The reply shown to the user.")
    intent: Literal["informational", "proposal"] = "informational"
    referenced_artifacts: list[str] = Field(default_factory=list)
    proposed_change: Optional[ProposedChange] = None

    @model_validator(mode="after")
    def _coherent(self) -> "ConversationTurn":
        # Tolerate an over-eager classifier: a "proposal" with nothing concrete
        # is treated as informational rather than failing the whole turn.
        if self.intent == "proposal" and self.proposed_change is None:
            self.intent = "informational"
        if self.intent == "informational":
            self.proposed_change = None
        # normalise referenced artifact names
        known = {
            "idea",
            "discovery",
            "blueprint",
            "business_logic",
            "architecture",
            "roadmap",
            "tasks",
            "progress",
            "ship_checklist",
        }
        self.referenced_artifacts = [
            a for a in dict.fromkeys(self.referenced_artifacts) if a in known
        ]
        return self


SYSTEM_PROMPT = (
    "You are the project intelligence layer for one specific software project in "
    "VYRA. You are NOT a general chatbot.\n\n"
    "Answer only from the project context provided in the user turn. That context "
    "is assembled from the project's APPROVED artifacts and current status.\n\n"
    "Rules:\n"
    "- If something is not in the context, say it is not defined yet — do not "
    "guess or invent project decisions, requirements, rules, or names.\n"
    "- Never claim that code has been written, reviewed, tested, or deployed. "
    "VYRA cannot observe the implementation; only stored artifacts, task status, "
    "progress and Ship Checklist state are real to you.\n"
    "- You cannot change the project. If the user asks for a change, do NOT say "
    "it is done. Instead set intent to \"proposal\" and fill proposed_change.\n"
    "- Explaining stale state: an artifact is 'stale' when an upstream approved "
    "decision changed after it was approved; it is not deleted or unapproved, "
    "the user reconciles it by regenerating or re-approving.\n\n"
    "Response shape (call the tool):\n"
    "- response: your reply, concise and specific, citing ids (FR3, BR-04, T2) "
    "where relevant.\n"
    "- intent: \"informational\" for questions; \"proposal\" only when the user "
    "asks to change the project.\n"
    "- referenced_artifacts: which of idea / discovery / blueprint / "
    "business_logic / architecture / roadmap / tasks / progress / ship_checklist "
    "you used.\n"
    "- proposed_change (only when intent is proposal):\n"
    "    target_artifact: blueprint | business_logic | architecture — the one "
    "artifact that owns the thing being changed.\n"
    "    summary: one line describing the change.\n"
    "    rationale: the user's reason.\n"
    "    sections: a partial content patch — an object whose keys are section "
    "names of that artifact and whose values are the FULL new value for each "
    "section (the whole list/array for that section, not a diff). Only include "
    "sections that change. If you are unsure of the exact section shape, still "
    "propose your best structured attempt and explain it in `response`; a human "
    "reviews and the backend validates before anything is applied.\n\n"
    "Blueprint sections: product_summary, problem, solution, target_users, "
    "user_roles, core_features, mvp_features, future_features, "
    "functional_requirements, business_rules, user_flows, out_of_scope.\n"
    "Business Logic sections: summary, actors, permissions, business_rules, "
    "validations, approval_flows, state_transitions, edge_cases, open_questions.\n"
    "Architecture sections: overview, frontend, backend, database, auth, "
    "components, api_areas, data_model, integrations, security, deployment, "
    "key_decisions, constraints.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _lines(label: str, items) -> list[str]:
    items = items or []
    if not items:
        return []
    return [f"{label}:", *(f"  - {it}" for it in items)]


def build_user_prompt(context: dict) -> str:
    project = context.get("project", {})
    status = context.get("status", {})
    slices = context.get("slices", {})
    history = context.get("history", [])
    summary = context.get("conversation_summary") or ""

    parts: list[str] = [
        "PROJECT",
        f"Name: {project.get('name') or '(untitled)'}",
        f"Type: {project.get('project_type', 'software')}",
        f"Idea: {project.get('idea', '')}",
        f"Stage: {project.get('stage', '')}",
        "",
        "STATUS",
        f"Stale artifacts (need review): {', '.join(status.get('stale_artifacts') or []) or 'none'}",
    ]
    if status.get("progress"):
        p = status["progress"]
        parts.append(
            f"Progress: {p.get('completion_percentage', 0)}% complete "
            f"({p.get('completed', 0)}/{p.get('total_tasks', 0)} tasks, "
            f"{p.get('blocked', 0)} blocked, {p.get('ready_for_review', 0)} ready for review)"
        )
    if status.get("ship"):
        s = status["ship"]
        parts.append(
            f"Ship readiness: {s.get('overall_status')} "
            f"({s.get('pending_manual_confirmations', 0)} manual confirmations pending, "
            f"{s.get('blocker_count', 0)} automatic blockers)"
        )
    parts.append("")

    parts.append("PROJECT CONTEXT (approved artifacts, bounded slices)")
    for key in (
        "blueprint",
        "business_logic",
        "architecture",
        "roadmap",
    ):
        block = slices.get(key)
        if not block:
            parts.append(f"{key}: not approved / not available")
            continue
        parts.append(f"[{key}]")
        for line in block:
            parts.append(f"  {line}")
    parts.append("")

    if summary:
        parts += ["CONVERSATION SUMMARY (memory, not authoritative)", summary, ""]

    if history:
        parts.append("RECENT CONVERSATION")
        for turn in history:
            parts.append(f"  {turn['role']}: {turn['content']}")
        parts.append("")

    parts += [
        "USER MESSAGE",
        context.get("user_message", ""),
        "",
        "Answer from the context above. If the user is asking for a change, "
        "return intent=proposal with a structured proposed_change; do not claim "
        "the change was made.",
    ]
    return "\n".join(parts)


CONVERSATION_RESPONSE = Operation(
    name="conversation_response",
    system_prompt=SYSTEM_PROMPT,
    schema=ConversationTurn,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
