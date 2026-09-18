"""
Deterministic conversation-context selection (Phase H).

No AI, no embeddings, no RAG. Given a project and the user's message, this
assembles a small, bounded set of slices from the project's APPROVED artifacts
plus current status. Every approved artifact is always represented compactly;
an artifact the message clearly refers to is expanded to a larger (still capped)
slice.

Domain-aware by design: ``build_conversation_context`` dispatches on
``project.project_type``. Today only the ``software`` provider exists; a ``data``
provider slots in later without touching callers.
"""
from __future__ import annotations

import re

from projects.dependencies import stale_artifacts
from projects.progress import compute_project_progress
from projects.ship_checklist import compute_ship_checklist

# compact vs expanded caps
_C = {"rules": 8, "reqs": 12, "tasks": 12, "list": 6}
_X = {"rules": 40, "reqs": 40, "tasks": 60, "list": 20}

_FOCUS_KEYWORDS = {
    "blueprint": ("requirement", "blueprint", "scope", "mvp", "feature", "fr-", "fr "),
    "business_logic": (
        "business logic",
        "business rule",
        "br-",
        "permission",
        "actor",
        "role",
        "validation",
        "approval",
        "state transition",
        "edge case",
        "who can",
    ),
    "architecture": (
        "architecture",
        "stack",
        "database",
        "postgres",
        "frontend",
        "backend",
        "auth",
        "component",
        "api",
        "integration",
        "deployment",
        "decision",
    ),
    "roadmap": ("roadmap", "task", "phase", "blocked", "next", "progress", "dependency"),
}


def _detect_focus(message: str) -> set[str]:
    low = (message or "").lower()
    focus = {
        key
        for key, words in _FOCUS_KEYWORDS.items()
        if any(w in low for w in words)
    }
    # explicit id mentions
    if re.search(r"\bbr[-\s]?\d", low):
        focus.add("business_logic")
    if re.search(r"\bfr[-\s]?\d", low):
        focus.add("blueprint")
    if re.search(r"\bt\d", low):
        focus.add("roadmap")
    return focus


def _blueprint_slice(project, expanded: bool) -> list[str] | None:
    content = (project.blueprint or {}).get("content")
    if not (project.blueprint_approved_at and content):
        return None
    cap = _X if expanded else _C
    lines = [
        f"product_summary: {content.get('product_summary', '')}",
        f"problem: {content.get('problem', '')}",
        f"solution: {content.get('solution', '')}",
        f"user_roles: {', '.join(r['name'] for r in content.get('user_roles', []))}",
        f"mvp_features: {', '.join(content.get('mvp_features', [])[: cap['list']])}",
        f"out_of_scope: {', '.join(content.get('out_of_scope', [])[: cap['list']])}",
    ]
    lines.append("functional_requirements:")
    for r in content.get("functional_requirements", [])[: cap["reqs"]]:
        lines.append(f"  {r['id']} [{r['priority']}] {r['text']}")
    br = content.get("business_rules", [])[: cap["rules"]]
    if br:
        lines.append("business_rules (blueprint-level): " + " | ".join(br))
    return lines


def _business_logic_slice(project, expanded: bool) -> list[str] | None:
    content = (project.business_logic or {}).get("content")
    if not (project.business_logic_approved_at and content):
        return None
    cap = _X if expanded else _C
    lines = [f"summary: {content.get('summary', '')}"]
    lines.append(
        "actors: "
        + ", ".join(a["name"] for a in content.get("actors", []))
    )
    perms = content.get("permissions", [])[: cap["list"]]
    if perms:
        lines.append("permissions:")
        for p in perms:
            lines.append(f"  {p['actor']}: {', '.join(p.get('can', []))}")
    lines.append("business_rules:")
    for r in content.get("business_rules", [])[: cap["rules"]]:
        refs = ", ".join(r.get("related_requirements", []))
        extra = f" (actor: {r['actor']})" if r.get("actor") else ""
        lines.append(
            f"  {r['id']}: {r['statement']}{extra}"
            + (f" [traces to {refs}]" if refs else "")
        )
    vals = content.get("validations", [])[: cap["list"]]
    if vals:
        lines.append(
            "validations: "
            + " | ".join(f"{v['id']}: {v['rule']}" for v in vals)
        )
    trans = content.get("state_transitions", [])[: cap["list"]]
    if trans:
        lines.append("state_transitions:")
        for t in trans:
            lines.append(
                f"  {t['entity']}: {t['from_state']} -> {t['to_state']} on '{t['trigger']}'"
            )
    oq = content.get("open_questions", [])[: cap["list"]]
    if oq:
        lines.append("open_questions: " + " | ".join(oq))
    return lines


def _architecture_slice(project, expanded: bool) -> list[str] | None:
    content = (project.architecture or {}).get("content")
    if not (project.architecture_approved_at and content):
        return None
    cap = _X if expanded else _C
    overview = content.get("overview", {})
    lines = [
        f"style: {overview.get('style', '')}",
        f"summary: {overview.get('summary', '')}",
        f"frontend: {content.get('frontend', {}).get('choice', '')}",
        f"backend: {content.get('backend', {}).get('choice', '')}",
        f"database: {content.get('database', {}).get('choice', '')}",
        f"auth: {content.get('auth', {}).get('approach', '')}",
    ]
    comps = content.get("components", [])[: cap["list"]]
    if comps:
        lines.append(
            "components: "
            + " | ".join(f"{c['name']} ({c['responsibility']})" for c in comps)
        )
    apis = content.get("api_areas", [])[: cap["list"]]
    if apis:
        lines.append(
            "api_areas: " + " | ".join(f"{a['name']}: {a['purpose']}" for a in apis)
        )
    decisions = content.get("key_decisions", [])[: cap["rules"]]
    if decisions:
        lines.append("key_decisions:")
        for d in decisions:
            lines.append(f"  {d['decision']} — {d['rationale']}")
    if content.get("constraints"):
        lines.append("constraints: " + " | ".join(content["constraints"][: cap["list"]]))
    return lines


def _roadmap_slice(project, expanded: bool) -> list[str] | None:
    content = (project.roadmap or {}).get("content")
    if not (project.roadmap_approved_at and content):
        return None
    cap = _X if expanded else _C
    lines: list[str] = []
    shown = 0
    for phase in content.get("phases", []):
        lines.append(f"{phase['id']} {phase['title']}: {phase.get('objective', '')}")
        for t in phase.get("tasks", []):
            if shown >= cap["tasks"]:
                lines.append("  … (more tasks omitted)")
                break
            deps = ", ".join(t.get("dependencies", []))
            reqs = ", ".join(t.get("requirements", []))
            lines.append(
                f"  {t['id']} [{t['status']}] {t['title']}"
                + (f" (deps: {deps})" if deps else "")
                + (f" (reqs: {reqs})" if reqs else "")
            )
            shown += 1
    return lines


def _status_block(project) -> dict:
    block: dict = {"stale_artifacts": stale_artifacts(project)}
    if project.roadmap_approved_at:
        prog = compute_project_progress(project)["summary"]
        block["progress"] = {
            "completion_percentage": prog["completion_percentage"],
            "completed": prog["completed"],
            "total_tasks": prog["total_tasks"],
            "blocked": prog["blocked"],
            "ready_for_review": prog["ready_for_review"],
        }
        ship = compute_ship_checklist(project)
        block["ship"] = {
            "overall_status": ship["overall_status"],
            "pending_manual_confirmations": ship["pending_manual_confirmations"],
            "blocker_count": len(ship["blockers"]),
        }
    return block


def _software_context(project, message: str) -> dict:
    focus = _detect_focus(message)
    builders = {
        "blueprint": _blueprint_slice,
        "business_logic": _business_logic_slice,
        "architecture": _architecture_slice,
        "roadmap": _roadmap_slice,
    }
    slices = {
        key: fn(project, expanded=(key in focus))
        for key, fn in builders.items()
    }
    return {
        "project": {
            "name": project.name,
            "idea": project.original_idea,
            "project_type": project.project_type,
            "stage": project.stage,
        },
        "status": _status_block(project),
        "slices": {k: v for k, v in slices.items() if v},
        "focus": sorted(focus),
    }


def _data_context(project, message: str) -> dict:
    from projects.data.data_conversation_context import build_data_conversation_context

    return build_data_conversation_context(project, message)


_CONTEXT_PROVIDERS = {
    "software": _software_context,
    "data": _data_context,  # Phase I-5.
}


def build_conversation_context(project, message: str) -> dict:
    provider = _CONTEXT_PROVIDERS.get(project.project_type, _software_context)
    return provider(project, message or "")
