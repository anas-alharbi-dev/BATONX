"""
Data Conversation context provider (Phase I-5) — the ``data`` counterpart to
``projects.conversation_context._software_context``. Wired into
``_CONTEXT_PROVIDERS["data"]`` there; the existing Conversation infrastructure
(models, message-turn flow, Proposal lifecycle) is untouched.

Reuses ``build_data_digest`` (already bounded, already approved-state-only,
already excludes raw rows) as the authoritative slice, plus a small status
block (stale / progress / readiness) mirroring the Software provider's
``_status_block``. No AI, no raw dataset rows, no full query result tables,
no secrets — see the module docstring on ``data_context.py`` for the caps
already enforced there.
"""
from __future__ import annotations

from projects.data.data_context import build_data_digest
from projects.data.progress import compute_data_progress
from projects.data.readiness import compute_data_readiness


def _status_block(project) -> dict:
    progress = compute_data_progress(project)
    readiness = compute_data_readiness(project)
    return {
        "progress": progress["summary"],
        "next_action": progress["next_action"],
        "stale": progress["stale_context"],
        "readiness": {
            "overall_status": readiness["overall_status"],
            "pending_manual_confirmations": readiness["pending_manual_confirmations"],
            "blocker_count": len(readiness["blockers"]),
        },
    }


def build_data_conversation_context(project, message: str) -> dict:
    return {
        "project": {
            "name": project.name,
            "idea": project.original_idea,
            "project_type": project.project_type,
            "data_goal": project.data_goal,
            "stage": project.stage,
        },
        "status": _status_block(project),
        "data": build_data_digest(project),
    }
