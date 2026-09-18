"""
Downstream stale-state policy — the single place that decides which artifacts a
change invalidates, and how a stale flag is set or cleared.

Meaning of "stale": *previously approved, but an upstream approved decision has
since changed, so it may no longer be consistent.* A stale artifact keeps its
content, its ``*_approved_at`` timestamp, and all ``GeneratedPrompt`` history —
only a per-artifact boolean in ``Project.downstream_stale`` is set. Human
regeneration / approval clears it.

The authoritative chain is one explicit tuple. The next phase inserts
``"business_logic"`` between ``"blueprint"`` and ``"architecture"`` here and
nowhere else; a future Conversational Layer calls ``mark_downstream_stale`` after
a human-approved proposal is applied.

Helpers mutate ``project.downstream_stale`` in memory and return whether it
changed; the caller adds ``"downstream_stale"`` to ``save(update_fields=...)``.
"""
from __future__ import annotations

# Ordered authoritative-artifact chain.
ARTIFACT_CHAIN: tuple[str, ...] = (
    "discovery",
    "blueprint",
    "business_logic",
    "architecture",
    "roadmap",
)

# Chain nodes that can carry a stale flag: they have an approval gate AND
# something upstream that can change after they are approved.
STALEABLE: tuple[str, ...] = ("business_logic", "architecture", "roadmap")

# Which approval timestamp proves an artifact is currently approved.
_APPROVED_AT_ATTR: dict[str, str] = {
    "blueprint": "blueprint_approved_at",
    "business_logic": "business_logic_approved_at",
    "architecture": "architecture_approved_at",
    "roadmap": "roadmap_approved_at",
}


def downstream_of(artifact: str) -> list[str]:
    """Staleable artifacts strictly downstream of ``artifact`` in the chain."""
    if artifact not in ARTIFACT_CHAIN:
        return []
    after = ARTIFACT_CHAIN[ARTIFACT_CHAIN.index(artifact) + 1 :]
    return [node for node in after if node in STALEABLE]


def _is_approved(project, artifact: str) -> bool:
    attr = _APPROVED_AT_ATTR.get(artifact)
    return bool(attr and getattr(project, attr, None))


def mark_downstream_stale(project, changed_artifact: str) -> bool:
    """
    Set ``stale = True`` for every currently-approved artifact downstream of
    ``changed_artifact``. Never marks an artifact that was never approved (no
    noise). Returns True if ``project.downstream_stale`` was modified.
    """
    stale = dict(project.downstream_stale or {})
    changed = False
    for target in downstream_of(changed_artifact):
        if _is_approved(project, target) and stale.get(target) is not True:
            stale[target] = True
            changed = True
    if changed:
        project.downstream_stale = stale
    return changed


def clear_stale(project, artifact: str) -> bool:
    """
    Clear the stale flag for exactly ``artifact`` (human reconciled it by
    regenerating / re-approving). Never touches any other flag. Returns True if
    ``project.downstream_stale`` was modified.
    """
    stale = dict(project.downstream_stale or {})
    if artifact in stale:
        stale.pop(artifact)
        project.downstream_stale = stale
        return True
    return False


def is_stale(project, artifact: str) -> bool:
    return bool((project.downstream_stale or {}).get(artifact))


def stale_artifacts(project) -> list[str]:
    return [name for name, flag in (project.downstream_stale or {}).items() if flag]


def chain_for(project) -> tuple[str, ...]:
    """
    Dispatch by ``project.project_type`` (Phase I-5). Purely additive — every
    function above this line is untouched and keeps its exact Software-only
    behavior; this is the one new seam a caller uses to work generically
    across both workflows. The Data chain lives in ``projects.data.stale``
    (its multi-instance artifacts need more than a project-level flag, so it
    is not a drop-in extension of ``ARTIFACT_CHAIN``).
    """
    if getattr(project, "project_type", "software") == "data":
        from projects.data.stale import DATA_ARTIFACT_CHAIN

        return DATA_ARTIFACT_CHAIN
    return ARTIFACT_CHAIN
