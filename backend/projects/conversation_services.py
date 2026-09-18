"""
Conversational Layer domain services (Phase H).

The conversation reads, explains and proposes. It never mutates authoritative
project state directly. A ``proposed_change`` becomes a PENDING ``Proposal``;
only ``approve_proposal`` applies it, and only by calling the same domain
service that already owns the artifact — so validation, normalization and
Phase C stale propagation are inherited, not re-implemented.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone as dj_timezone

from ai.base import run_operation
from ai.operations.conversation_response import CONVERSATION_RESPONSE
from ai.operations.data_conversation_response import DATA_CONVERSATION_RESPONSE
from projects.conversation_context import build_conversation_context
from projects.dependencies import downstream_of
from projects.data.proposal_services import (
    DATA_PROPOSAL_TARGETS,
    apply_data_proposal,
    data_impact_summary,
)
from projects.exceptions import ProjectWorkflowError
from projects.models import Conversation, ConversationMessage, Project, Proposal
from projects.services import (
    update_architecture,
    update_blueprint,
    update_business_logic,
)

# Artifacts a conversation proposal may target. Everything else — task status,
# Progress, Ship Checklist confirmations, GeneratedPrompt history, provider
# settings, secrets, project_type, system config — is intentionally NOT
# proposable from the conversation. Software and Data target names are
# disjoint by construction, so they can share one flat lookup safely.
_SUPPORTED_TARGETS = ("blueprint", "business_logic", "architecture")
_APPLY = {
    "blueprint": update_blueprint,
    "business_logic": update_business_logic,
    "architecture": update_architecture,
}

# How many trailing messages of history are sent to the model.
_HISTORY_LIMIT = 10

_APPROVED_AT = {
    "blueprint": "blueprint_approved_at",
    "business_logic": "business_logic_approved_at",
    "architecture": "architecture_approved_at",
    "roadmap": "roadmap_approved_at",
}

# Phase I-5 project-type dispatch — the existing Software path above is
# untouched; this only adds a second, separate operation + target set.
_RESPONSE_OPERATIONS = {
    "software": CONVERSATION_RESPONSE,
    "data": DATA_CONVERSATION_RESPONSE,
}


def _operation_for(project: Project):
    return _RESPONSE_OPERATIONS.get(project.project_type, CONVERSATION_RESPONSE)


def _targets_for(project: Project) -> tuple[str, ...]:
    return DATA_PROPOSAL_TARGETS if project.project_type == "data" else _SUPPORTED_TARGETS


# --- conversation lifecycle ------------------------------------------------


def create_conversation(project: Project) -> Conversation:
    return Conversation.objects.create(project=project)


def get_conversation(project: Project, conversation_id) -> Conversation:
    try:
        return Conversation.objects.get(id=conversation_id, project=project)
    except (Conversation.DoesNotExist, ValueError, TypeError):
        raise ProjectWorkflowError(
            "conversation_not_found",
            "No such conversation for this project.",
            status=404,
        )


def _recent_history(conversation: Conversation, exclude_id=None) -> list[dict]:
    qs = conversation.messages.all()
    if exclude_id is not None:
        qs = qs.exclude(id=exclude_id)
    rows = list(qs.order_by("-created_at", "-id")[:_HISTORY_LIMIT])
    rows.reverse()  # oldest first
    return [{"role": m.role, "content": m.content} for m in rows]


# --- messaging (AI-first, no project mutation) ---------------------------


def post_message(project: Project, conversation: Conversation, text) -> dict:
    text = (text or "").strip()
    if not text:
        raise ProjectWorkflowError(
            "empty_message", "Type a message to send.", status=400
        )

    # The user's message is persisted immediately so the thread is never lost,
    # even if the AI call then fails. This is conversation memory only — no
    # authoritative project state is touched here.
    user_msg = ConversationMessage.objects.create(
        conversation=conversation,
        role=ConversationMessage.Role.USER,
        content=text,
    )

    ctx = build_conversation_context(project, text)
    operation = _operation_for(project)
    turn = run_operation(
        operation,
        {
            **ctx,
            "history": _recent_history(conversation, exclude_id=user_msg.id),
            "conversation_summary": conversation.summary,
            "user_message": text,
        },
        project=project,
    )

    with transaction.atomic():
        assistant_msg = ConversationMessage.objects.create(
            conversation=conversation,
            role=ConversationMessage.Role.ASSISTANT,
            content=turn.response,
            metadata={
                "intent": turn.intent,
                "referenced_artifacts": turn.referenced_artifacts,
                "prompt_version": operation.prompt_version,
            },
        )

        proposal = None
        change = turn.proposed_change
        if (
            turn.intent == "proposal"
            and change is not None
            and change.target_artifact in _targets_for(project)
        ):
            entity_id = getattr(change, "entity_id", "") or ""
            proposal = Proposal.objects.create(
                conversation=conversation,
                project=project,
                target_artifact=change.target_artifact,
                proposal_type="section_patch",
                proposed_change={
                    "sections": change.sections or {},
                    "summary": change.summary,
                    "entity_id": entity_id,
                },
                rationale=change.rationale or "",
                impact_summary=(
                    data_impact_summary(project, change.target_artifact, entity_id)
                    if project.project_type == "data"
                    else _impact_summary(project, change.target_artifact)
                ),
                status=Proposal.Status.PENDING,
            )
            assistant_msg.metadata["proposal_id"] = str(proposal.id)
            assistant_msg.save(update_fields=["metadata"])

        conversation.save(update_fields=["updated_at"])

    return {
        "message": _serialize_message(assistant_msg),
        "proposal": _serialize_proposal(proposal) if proposal else None,
    }


# --- impact analysis (deterministic) -----------------------------------


def _is_approved(project: Project, artifact: str) -> bool:
    attr = _APPROVED_AT.get(artifact)
    return bool(attr and getattr(project, attr, None))


def _impact_summary(project: Project, target: str) -> dict:
    downstream = downstream_of(target)  # staleable nodes strictly after target
    approved_downstream = [a for a in downstream if _is_approved(project, a)]
    notes = [
        f"Applying this reverts {target.replace('_', ' ')} to a draft; you "
        "re-approve it afterwards.",
    ]
    if approved_downstream:
        notes.append(
            "These approved artifacts will be flagged for review (kept, not "
            "deleted, not unapproved): " + ", ".join(approved_downstream) + "."
        )
    else:
        notes.append("No approved downstream artifacts would be affected yet.")
    notes.append(
        "Task progress and generated Build/Review Prompt history are preserved."
    )
    return {
        "target_artifact": target,
        "downstream_review_candidates": approved_downstream,
        "stale_propagation_possible": bool(approved_downstream),
        "notes": notes,
    }


# --- proposal decisions ------------------------------------------------


def _get_proposal(project: Project, proposal_id) -> Proposal:
    try:
        return Proposal.objects.select_related("project").get(
            id=proposal_id, project=project
        )
    except (Proposal.DoesNotExist, ValueError, TypeError):
        raise ProjectWorkflowError(
            "proposal_not_found",
            "No such proposal for this project.",
            status=404,
        )


def _require_pending(proposal: Proposal) -> None:
    if proposal.status != Proposal.Status.PENDING:
        raise ProjectWorkflowError(
            "proposal_not_pending",
            f"This proposal is already {proposal.status}.",
            status=409,
            details={"status": proposal.status},
        )


def approve_proposal(project: Project, proposal_id) -> dict:
    """
    Apply a PENDING proposal through the artifact's own domain service. Any
    validation / workflow error from that service propagates unchanged and the
    proposal stays PENDING (nothing was mutated).
    """
    proposal = _get_proposal(project, proposal_id)
    _require_pending(proposal)

    if proposal.target_artifact not in _targets_for(project):
        raise ProjectWorkflowError(
            "unsupported_proposal_target",
            f"Proposals cannot modify '{proposal.target_artifact}'.",
            status=422,
            details={"target_artifact": proposal.target_artifact},
        )

    sections = (proposal.proposed_change or {}).get("sections") or {}

    # Outside any Proposal write: if this raises, the proposal is untouched.
    if project.project_type == "data":
        entity_id = (proposal.proposed_change or {}).get("entity_id") or ""
        apply_data_proposal(project, proposal.target_artifact, entity_id, sections)
    else:
        _APPLY[proposal.target_artifact](project, sections)

    now = dj_timezone.now()
    proposal.status = Proposal.Status.APPLIED
    proposal.decided_at = now
    proposal.applied_at = now
    proposal.save(update_fields=["status", "decided_at", "applied_at"])

    # ``project`` is the same instance the domain service just mutated and
    # saved in place (every apply path calls .save() on this exact object, or
    # on a child row plus this object's context_digest) — safe to reuse
    # directly rather than trusting each function's own return type, which
    # differs (Project for data_brief/blueprint/etc., a dict summary for the
    # Data entity-scoped services).
    return {"project": project, "proposal": _serialize_proposal(proposal)}


def reject_proposal(project: Project, proposal_id) -> dict:
    proposal = _get_proposal(project, proposal_id)
    _require_pending(proposal)
    proposal.status = Proposal.Status.REJECTED
    proposal.decided_at = dj_timezone.now()
    proposal.save(update_fields=["status", "decided_at"])
    return {"proposal": _serialize_proposal(proposal)}


# --- serialization ---------------------------------------------------


def _serialize_message(m: ConversationMessage) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "metadata": m.metadata,
        "created_at": m.created_at.isoformat(),
    }


def _serialize_proposal(p: Proposal) -> dict:
    return {
        "id": str(p.id),
        "conversation_id": str(p.conversation_id),
        "target_artifact": p.target_artifact,
        "proposal_type": p.proposal_type,
        "proposed_change": p.proposed_change,
        "rationale": p.rationale,
        "impact_summary": p.impact_summary,
        "status": p.status,
        "created_at": p.created_at.isoformat(),
        "decided_at": p.decided_at.isoformat() if p.decided_at else None,
        "applied_at": p.applied_at.isoformat() if p.applied_at else None,
    }


def serialize_conversation(conversation: Conversation) -> dict:
    return {
        "id": str(conversation.id),
        "project": conversation.project.slug,
        "summary": conversation.summary,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "messages": [
            _serialize_message(m) for m in conversation.messages.all()
        ],
        "proposals": [
            _serialize_proposal(p)
            for p in conversation.proposals.all().order_by("created_at")
        ],
    }
