"""
Deterministic Ship Checklist (Phase G) — the last stage of the Software Project
MVP workflow.

Ship readiness is derived, not asserted. Every automatic check reads real stored
project state (approvals, Phase C stale flags, Phase F progress). VYRA never
fabricates test results, deployment status, or review outcomes: things it cannot
observe are surfaced as *manual confirmations* the human must tick, or as
honest *warnings*.

No AI. ``compute_ship_checklist`` and ``apply_manual_confirmation`` require no
provider and no ANTHROPIC_API_KEY.

Storage: only the manual confirmations persist, in ``Project.ship_checklist``
(``{item_id: {confirmed, confirmed_at, note}}``). Automatic checks are always
recomputed from authoritative state — never stored.
"""
from __future__ import annotations

from django.utils import timezone as dj_timezone

from projects.progress import compute_project_progress

# --- overall readiness states ------------------------------------------

NOT_READY = "NOT_READY"
READY_WITH_MANUAL_CHECKS = "READY_WITH_MANUAL_CHECKS"
READY_TO_SHIP = "READY_TO_SHIP"

# --- required manual confirmations (concise MVP set) ------------------
# (item_id, category, title, why VYRA cannot verify this itself)
MANUAL_ITEMS: tuple[tuple[str, str, str, str], ...] = (
    (
        "review_completed",
        "Review Readiness",
        "Code review completed and findings resolved",
        "VYRA generates Review Prompts but does not ingest Review Results — "
        "confirm the review outcome externally.",
    ),
    (
        "tests_verified",
        "Testing / Quality",
        "Automated / relevant tests verified",
        "VYRA does not run the project's test suite.",
    ),
    (
        "critical_flows_verified",
        "Testing / Quality",
        "Critical user flows tested end to end",
        "VYRA cannot exercise the running application.",
    ),
    (
        "permissions_verified",
        "Testing / Quality",
        "Permissions / access behavior validated",
        "VYRA defines the rules but cannot verify the implementation at runtime.",
    ),
    (
        "production_config_reviewed",
        "Release / Operations",
        "Production environment configuration reviewed",
        "VYRA has no access to the deployment environment.",
    ),
    (
        "secrets_reviewed",
        "Release / Operations",
        "Secrets / environment configuration reviewed",
        "VYRA does not manage project secrets.",
    ),
    (
        "migrations_reviewed",
        "Release / Operations",
        "Database migrations reviewed",
        "VYRA cannot inspect the project's migration history.",
    ),
    (
        "backup_rollback_reviewed",
        "Release / Operations",
        "Backup / rollback approach reviewed",
        "Operational safety is a human decision.",
    ),
    (
        "deployment_readiness_confirmed",
        "Release / Operations",
        "Deployment completed or ready",
        "VYRA does not perform the deployment.",
    ),
)

MANUAL_ITEM_IDS: frozenset[str] = frozenset(item[0] for item in MANUAL_ITEMS)
MAX_NOTE_LEN = 500


def _business_logic_applicable(project) -> bool:
    """
    Mirror of ``services._business_logic_gate_applies``: a project that already
    had Architecture content before Phase D is not retroactively required to have
    approved Business Logic.
    """
    return not bool((project.architecture or {}).get("content"))


def _automatic_checks(project, progress: dict) -> list[dict]:
    summary = progress["summary"]
    stale = set(progress["stale_context"])
    total = summary["total_tasks"]

    def check(cid, category, title, ok, *, required=True, warn_if=False,
              evidence="", action=""):
        if ok:
            status = "pass"
        elif warn_if:
            status = "warning"
        else:
            status = "fail"
        return {
            "id": cid,
            "category": category,
            "title": title,
            "kind": "automatic",
            "status": status,
            "required": required,
            "evidence": evidence,
            "action": action,
        }

    bl_applicable = _business_logic_applicable(project)
    bl_content = (project.business_logic or {}).get("content") or {}
    open_qs = bl_content.get("open_questions") or []

    checks = [
        check(
            "SC-01", "Product Definition", "Product Blueprint approved",
            bool(project.blueprint_approved_at),
            evidence=(
                f"Approved {project.blueprint_approved_at.isoformat()}"
                if project.blueprint_approved_at
                else "The Blueprint has not been approved."
            ),
            action="Approve the Blueprint.",
        ),
    ]

    if not bl_applicable:
        checks.append(
            check(
                "SC-02", "Product Definition",
                "Business Logic approved where applicable", True,
                evidence="Not applicable — this project predates the Business "
                "Logic stage and keeps its original workflow.",
            )
        )
    else:
        checks.append(
            check(
                "SC-02", "Product Definition",
                "Business Logic approved", bool(project.business_logic_approved_at),
                evidence=(
                    f"Approved {project.business_logic_approved_at.isoformat()}"
                    if project.business_logic_approved_at
                    else "Business Logic has not been approved."
                ),
                action="Approve the Business Logic.",
            )
        )

    checks.append(
        check(
            "SC-03", "Product Definition",
            "No unresolved open questions in approved Business Logic",
            not (project.business_logic_approved_at and open_qs),
            required=False, warn_if=bool(open_qs),
            evidence=(
                f"{len(open_qs)} open question(s) recorded: "
                + "; ".join(open_qs[:5])
                if open_qs
                else "No open questions recorded."
            ),
            action="Resolve the open questions or accept them explicitly.",
        )
    )

    checks.append(
        check(
            "SC-04", "Technical Design", "Architecture approved",
            bool(project.architecture_approved_at),
            evidence=(
                f"Approved {project.architecture_approved_at.isoformat()}"
                if project.architecture_approved_at
                else "The Architecture has not been approved."
            ),
            action="Approve the Architecture.",
        )
    )

    checks.append(
        check(
            "SC-05", "Implementation", "Development Roadmap approved",
            bool(project.roadmap_approved_at),
            evidence=(
                f"Approved {project.roadmap_approved_at.isoformat()}"
                if project.roadmap_approved_at
                else "The Roadmap has not been approved."
            ),
            action="Approve the Roadmap.",
        )
    )
    checks.append(
        check(
            "SC-06", "Implementation", "All roadmap tasks completed (100%)",
            total > 0 and summary["completed"] == total,
            evidence=(
                f"{summary['completed']}/{total} tasks completed "
                f"({summary['completion_percentage']}%)."
                if total
                else "The Roadmap has no tasks."
            ),
            action="Complete every roadmap task.",
        )
    )
    checks.append(
        check(
            "SC-07", "Implementation", "No blocked tasks",
            summary["blocked"] == 0,
            evidence=(
                f"{summary['blocked']} task(s) blocked by unfinished "
                "dependencies."
                if summary["blocked"]
                else "No blocked tasks."
            ),
            action="Resolve the dependencies blocking these tasks.",
        )
    )
    checks.append(
        check(
            "SC-08", "Implementation", "No tasks awaiting review",
            summary["ready_for_review"] == 0,
            evidence=(
                f"{summary['ready_for_review']} task(s) still marked "
                "ready-for-review."
                if summary["ready_for_review"]
                else "No tasks awaiting review."
            ),
            action="Review these tasks and mark them completed.",
        )
    )

    checks.append(
        check(
            "SC-09", "Context Consistency", "Business Logic is not stale",
            "business_logic" not in stale,
            evidence=(
                "Business Logic is flagged stale — an upstream approved "
                "decision changed."
                if "business_logic" in stale
                else "Not stale."
            ),
            action="Regenerate or re-approve the Business Logic.",
        )
    )
    checks.append(
        check(
            "SC-10", "Context Consistency", "Architecture is not stale",
            "architecture" not in stale,
            evidence=(
                "Architecture is flagged stale — an upstream approved decision "
                "changed."
                if "architecture" in stale
                else "Not stale."
            ),
            action="Regenerate or re-approve the Architecture.",
        )
    )
    checks.append(
        check(
            "SC-11", "Context Consistency", "Roadmap is not stale",
            not progress["roadmap_stale"],
            evidence=(
                "Roadmap is flagged stale — progress is based on a Roadmap that "
                "needs review."
                if progress["roadmap_stale"]
                else "Not stale."
            ),
            action="Regenerate or re-approve the Roadmap.",
        )
    )

    checks.append(
        check(
            "SC-12", "Review Readiness",
            "Review verification is confirmed externally", False,
            required=False, warn_if=True,
            evidence="VYRA generates Review Prompts but does not ingest Review "
            "Results, so it cannot automatically confirm the code review "
            "passed.",
            action="Confirm the review outcome using the manual checklist item.",
        )
    )

    return checks


def _manual_checks(project) -> list[dict]:
    stored = project.ship_checklist or {}
    out = []
    for item_id, category, title, why in MANUAL_ITEMS:
        entry = stored.get(item_id) or {}
        out.append(
            {
                "id": item_id,
                "category": category,
                "title": title,
                "kind": "manual",
                "required": True,
                "confirmed": bool(entry.get("confirmed")),
                "confirmed_at": entry.get("confirmed_at"),
                "note": entry.get("note", ""),
                "why_manual": why,
            }
        )
    return out


def _overall(auto: list[dict], manual: list[dict]) -> str:
    required_auto_fail = any(
        c["required"] and c["status"] == "fail" for c in auto
    )
    if required_auto_fail:
        return NOT_READY
    all_manuals_confirmed = all(
        c["confirmed"] for c in manual if c["required"]
    )
    return READY_TO_SHIP if all_manuals_confirmed else READY_WITH_MANUAL_CHECKS


def _summary_sentence(overall: str, blockers: list[dict], pending_manual: int) -> str:
    if overall == NOT_READY:
        n = len(blockers)
        return (
            f"{n} required readiness check{'s' if n != 1 else ''} "
            f"{'are' if n != 1 else 'is'} failing. Resolve "
            f"{'them' if n != 1 else 'it'} before shipping."
        )
    if overall == READY_WITH_MANUAL_CHECKS:
        return (
            f"Every automatic check passes. {pending_manual} manual "
            f"confirmation{'s' if pending_manual != 1 else ''} "
            f"remain{'s' if pending_manual == 1 else ''} before this project is "
            "ready to ship."
        )
    return (
        "Every automatic check passes and all manual confirmations are "
        "complete. This project is ready to ship. VYRA does not perform the "
        "deployment itself."
    )


def compute_ship_checklist(project) -> dict:
    """The full derived Ship Checklist. Pure function of stored project state."""
    progress = compute_project_progress(project)
    auto = _automatic_checks(project, progress)
    manual = _manual_checks(project)
    overall = _overall(auto, manual)

    blockers = [
        {"id": c["id"], "title": c["title"], "evidence": c["evidence"]}
        for c in auto
        if c["required"] and c["status"] == "fail"
    ]
    warnings = [
        {"id": c["id"], "title": c["title"], "evidence": c["evidence"]}
        for c in auto
        if c["status"] == "warning"
    ]
    pending_manual = sum(1 for c in manual if c["required"] and not c["confirmed"])

    summary = progress["summary"]
    return {
        "overall_status": overall,
        "readiness_summary": _summary_sentence(overall, blockers, pending_manual),
        "stage": project.stage,
        "progress": {
            "completion_percentage": summary["completion_percentage"],
            "total_tasks": summary["total_tasks"],
            "completed": summary["completed"],
            "blocked": summary["blocked"],
            "ready_for_review": summary["ready_for_review"],
        },
        "automatic_checks": auto,
        "manual_checks": manual,
        "blockers": blockers,
        "warnings": warnings,
        "stale_context": progress["stale_context"],
        "roadmap_stale": progress["roadmap_stale"],
        "pending_manual_confirmations": pending_manual,
    }


def apply_manual_confirmation(
    project, item_id: str, confirmed, note=None
) -> tuple[dict, bool]:
    """
    Persist ONE manual confirmation. Returns (updated ship_checklist dict,
    stage_changed). Raises ValueError for an unknown ``item_id``.

    Only manual items are writable — automatic checks are never stored, so they
    cannot be influenced from the client.
    """
    if item_id not in MANUAL_ITEM_IDS:
        raise ValueError(item_id)

    confirmed = bool(confirmed)
    note = (str(note).strip()[:MAX_NOTE_LEN]) if note else ""

    stored = dict(project.ship_checklist or {})
    stored[item_id] = {
        "confirmed": confirmed,
        "confirmed_at": dj_timezone.now().isoformat() if confirmed else None,
        "note": note,
    }
    project.ship_checklist = stored
    return stored, confirmed
