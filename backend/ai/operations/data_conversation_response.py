"""
data_conversation_response — the Data project's Conversational Layer AI
operation (Phase I-5). The ``software`` counterpart, ``conversation_response``,
is untouched; this is a separate operation with its own schema tailored to
Data semantics, wired in by ``projects.conversation_context``'s
``_data_context`` provider and ``projects.conversation_services``'s
project-type dispatch.

Enforces the platform's core distinction for Data: an answer must clearly
separate COMPUTED FACT (from Findings/validations/query results — numbers
that came out of DuckDB) from HUMAN DECISION (an approved definition/plan)
from AI INTERPRETATION (an Insight's reading of a fact). The model never
fabricates a number, and never returns raw dataset rows — only what is
already in the bounded Data digest it is given.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from ai.base import Operation
from ai.prompts import QUALITY_RULES

PROMPT_VERSION = "data_conversation/v1"

# Kept in sync with projects.data.proposal_services.DATA_PROPOSAL_TARGETS.
DATA_PROPOSAL_TARGETS = (
    "data_brief",
    "source_interpretation",
    "data_quality",
    "transformation_plan",
    "metric",
    "query_plan",
    "analysis_plan",
    "dashboard_blueprint",
)

_ENTITY_SCOPED_TARGETS = {"source_interpretation", "metric", "query_plan", "analysis_plan"}


class DataProposedChange(BaseModel):
    target_artifact: Literal[
        "data_brief", "source_interpretation", "data_quality", "transformation_plan",
        "metric", "query_plan", "analysis_plan", "dashboard_blueprint",
    ]
    # Required when target_artifact is entity-scoped (source_interpretation
    # needs a dataset id; metric/query_plan/analysis_plan need a business id
    # like KPI-01 / Q-02 / AN-03). Empty for the 4 project-level targets.
    entity_id: str = Field(default="", description="Exact dataset id or business id (KPI-xx/Q-xx/AN-xx) this change targets, if the target is entity-scoped.")
    summary: str = Field(min_length=1, description="One line: what would change and where.")
    rationale: str = Field(default="", description="Why the user wants this.")
    sections: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _entity_id_required_where_applicable(self) -> "DataProposedChange":
        if self.target_artifact in _ENTITY_SCOPED_TARGETS and not self.entity_id.strip():
            raise ValueError(f"{self.target_artifact} requires entity_id")
        return self


class DataConversationTurn(BaseModel):
    response: str = Field(min_length=1, description="The reply shown to the user.")
    intent: Literal["informational", "proposal"] = "informational"
    referenced_artifacts: list[str] = Field(default_factory=list)
    proposed_change: Optional[DataProposedChange] = None

    @model_validator(mode="after")
    def _coherent(self) -> "DataConversationTurn":
        if self.intent == "proposal" and self.proposed_change is None:
            self.intent = "informational"
        if self.intent == "informational":
            self.proposed_change = None
        known = {
            "data_brief", "sources", "data_quality", "transformation_plan",
            "metrics", "queries", "analyses", "insights", "dashboard",
            "lineage", "progress", "readiness", "stale",
        }
        self.referenced_artifacts = [
            a for a in dict.fromkeys(self.referenced_artifacts) if a in known
        ]
        return self


SYSTEM_PROMPT = (
    "You are the project intelligence layer for one specific Data & Analytics "
    "project in VYRA. You are NOT a general chatbot and you are NOT a SQL "
    "console.\n\n"
    "Answer only from the project context provided in the user turn — a "
    "bounded digest of this project's APPROVED/authoritative Data state "
    "(Data Brief, dataset schemas, Quality Rules, Transformation summary, "
    "KPIs, reviewed Queries, Analysis Results/Findings, accepted Insights, "
    "Dashboard Blueprint, lineage, stale flags, progress, readiness).\n\n"
    "CRITICAL — keep three categories visibly distinct in every answer:\n"
    "- COMPUTED FACT: a number or breakdown that came from real execution "
    "(a Finding's statement/metric_values, a metric validation result, a "
    "query result). Only ever state a fact number that is literally present "
    "in the context you were given.\n"
    "- HUMAN DECISION: an approved definition (a KPI's formula, a Query "
    "Plan, an approved Transformation step, an approved Dashboard panel) — "
    "a choice a human made, not something VYRA computed.\n"
    "- AI INTERPRETATION: an Insight's interpretation/recommendation — "
    "always advisory, always traceable to specific finding ids, never "
    "presented as more certain than the human who reviewed it treated it.\n\n"
    "Rules:\n"
    "- If something is not in the context, say it is not defined yet — do "
    "not guess a KPI formula, a column name, a finding, or any other "
    "project fact.\n"
    "- NEVER return raw dataset rows or a full query result table, even if "
    "asked directly ('show me rows'). Explain that raw data is not part of "
    "the conversation context and point the user to the appropriate Data "
    "workspace view instead.\n"
    "- Never fabricate a number. Every number you state must already appear "
    "in the given context.\n"
    "- You cannot change the project. If the user asks for a change, do NOT "
    "say it is done. Set intent to \"proposal\" and fill proposed_change.\n"
    "- Explaining stale state: an artifact/entity is 'stale' when an "
    "upstream approved decision changed after it was approved/run; content "
    "and history are kept, not deleted — the user reconciles it via its own "
    "workflow (re-approve, re-review, or re-run, depending on the artifact).\n"
    "- Lineage / impact questions ('what breaks if I change TX-04?', 'where "
    "does KPI-03 come from?'): answer only from the lineage_index / stale "
    "state given; if you don't have enough to trace it, say so rather than "
    "guessing.\n\n"
    "Response shape (call the tool):\n"
    "- response: your reply, concise and specific, citing business ids "
    "(KPI-03, Q-02, AN-01, F-01, INS-02, VIZ-04) where relevant.\n"
    "- intent: \"informational\" for questions; \"proposal\" only when the "
    "user asks to change the project.\n"
    "- referenced_artifacts: which context categories you used.\n"
    "- proposed_change (only when intent is proposal):\n"
    "    target_artifact: one of data_brief | source_interpretation | "
    "data_quality | transformation_plan | metric | query_plan | "
    "analysis_plan | dashboard_blueprint — the artifact that OWNS the thing "
    "being changed. You may NEVER target anything else (not a computed "
    "result, not a validation/execution run, not a manual readiness "
    "confirmation).\n"
    "    entity_id: for source_interpretation give the dataset id; for "
    "metric/query_plan/analysis_plan give the exact business id (KPI-xx / "
    "Q-xx / AN-xx) from the context. Leave blank for the 4 project-level "
    "targets (data_brief, data_quality, transformation_plan, "
    "dashboard_blueprint).\n"
    "    summary: one line describing the change.\n"
    "    rationale: the user's reason.\n"
    "    sections: a partial content patch for that artifact's own editable "
    "fields — the backend validates it before anything is applied.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def _lines(label: str, items) -> list[str]:
    items = items or []
    if not items:
        return [f"{label}: (none)"]
    return [f"{label}:", *(f"  - {it}" for it in items)]


def build_user_prompt(context: dict) -> str:
    project = context.get("project", {})
    status = context.get("status", {})
    data = context.get("data", {})
    history = context.get("history", [])
    summary = context.get("conversation_summary") or ""

    parts: list[str] = [
        "PROJECT",
        f"Name: {project.get('name') or '(untitled)'}",
        f"Type: {project.get('project_type', 'data')}",
        f"Data goal: {project.get('data_goal', '')}",
        f"Idea: {project.get('idea', '')}",
        "",
        "STATUS",
    ]
    prog = status.get("progress") or {}
    if prog:
        parts.append(
            f"Progress: {prog.get('completion_percentage', 0)}% complete "
            f"({prog.get('stages_complete', 0)}/{prog.get('stages_total', 0)} stages, "
            f"{prog.get('stages_blocked', 0)} blocked, {prog.get('stages_in_review', 0)} in review)"
        )
    ready = status.get("readiness") or {}
    if ready:
        parts.append(
            f"Delivery readiness: {ready.get('overall_status')} "
            f"({ready.get('pending_manual_confirmations', 0)} manual confirmations pending, "
            f"{ready.get('blocker_count', 0)} automatic blockers)"
        )
    stale = status.get("stale") or []
    parts.append(f"Stale (need review): {', '.join(stale) if stale else 'none'}")
    nxt = status.get("next_action")
    if nxt:
        parts.append(f"Suggested next action: {nxt.get('label')} ({nxt.get('stage')})")
    parts.append("")

    parts.append("DATA CONTEXT (bounded, approved-state-only — no raw rows)")
    for key in (
        "data_brief", "data_sources", "schemas", "data_quality", "transformation_plan",
        "metrics", "queries", "analyses", "accepted_insights", "dashboard",
        "lineage_index", "stale", "approved_at",
    ):
        if key in data:
            parts.append(f"[{key}]")
            parts.append(f"  {data[key]}")
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
        "Answer from the context above only. If asked for raw rows, decline "
        "and point to the appropriate Data workspace view instead of "
        "inventing or including any. If the user is asking for a change, "
        "return intent=proposal with a structured proposed_change; do not "
        "claim the change was made.",
    ]
    return "\n".join(parts)


DATA_CONVERSATION_RESPONSE = Operation(
    name="data_conversation_response",
    system_prompt=SYSTEM_PROMPT,
    schema=DataConversationTurn,
    build_user_prompt=build_user_prompt,
    prompt_version=PROMPT_VERSION,
)
