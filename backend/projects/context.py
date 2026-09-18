"""
Project Context digest.

``context_digest`` is a small, derived summary of a project's *approved*
artifacts. It is rebuilt on every approval and is what downstream AI operations
use as base context, so the whole project is never shipped to the model.

Phase 2: idea analysis + (once approved) a compact Blueprint summary.
"""
from __future__ import annotations

from projects.data.data_context import build_data_digest
from projects.roadmap import compute_progress, next_recommended_task

_MAX_RULES = 8
_MAX_REQUIREMENTS = 20
_MAX_BL_RULES = 30


def build_context_digest(project) -> dict:
    # Data projects have a different authoritative-memory shape (Phase I).
    if getattr(project, "project_type", "software") == "data":
        return build_data_digest(project)

    digest: dict = {}

    analysis = (project.context_digest or {}).get("idea_analysis")
    if analysis:
        digest["idea_analysis"] = analysis

    content = (project.blueprint or {}).get("content")
    if project.blueprint_approved_at and content:
        digest["blueprint"] = {
            "product_summary": content["product_summary"],
            "problem": content["problem"],
            "solution": content["solution"],
            "target_users": content["target_users"],
            "user_roles": [role["name"] for role in content["user_roles"]],
            "mvp_features": content["mvp_features"],
            "business_rules": content["business_rules"][:_MAX_RULES],
            "functional_requirements": [
                {"id": r["id"], "text": r["text"], "priority": r["priority"]}
                for r in content["functional_requirements"][:_MAX_REQUIREMENTS]
            ],
            "approved_at": project.blueprint_approved_at.isoformat(),
        }

    bl = (project.business_logic or {}).get("content")
    if project.business_logic_approved_at and bl:
        digest["business_logic"] = {
            "summary": bl["summary"],
            "actors": [a["name"] for a in bl["actors"]],
            "permissions": [
                {"actor": p["actor"], "can": p["can"][:4]}
                for p in bl["permissions"][:_MAX_RULES]
            ],
            "business_rules": [
                {
                    "id": r["id"],
                    "statement": r["statement"],
                    "related_requirements": r["related_requirements"],
                }
                for r in bl["business_rules"][:_MAX_BL_RULES]
            ],
            "validations": [
                {
                    "id": v["id"],
                    "rule": v["rule"],
                    "related_requirements": v["related_requirements"],
                }
                for v in bl["validations"][:_MAX_RULES]
            ],
            "state_transitions": [
                {
                    "entity": t["entity"],
                    "from": t["from_state"],
                    "to": t["to_state"],
                    "trigger": t["trigger"],
                }
                for t in bl["state_transitions"][:_MAX_RULES]
            ],
            "edge_cases": [
                {
                    "id": e["id"],
                    "scenario": e["scenario"],
                    "related_requirements": e["related_requirements"],
                }
                for e in bl["edge_cases"][:_MAX_RULES]
            ],
            "open_questions": bl["open_questions"][:_MAX_RULES],
            "approved_at": project.business_logic_approved_at.isoformat(),
        }

    arch = (project.architecture or {}).get("content")
    if project.architecture_approved_at and arch:
        digest["architecture"] = {
            "style": arch["overview"]["style"],
            "frontend": arch["frontend"]["choice"],
            "backend": arch["backend"]["choice"],
            "database": arch["database"]["choice"],
            "auth": arch["auth"]["approach"],
            "components": [c["name"] for c in arch["components"]],
            "api_areas": [a["name"] for a in arch["api_areas"]],
            "data_model": [
                {"entity": e["entity"], "relationships": e["relationships"]}
                for e in arch["data_model"]
            ],
            "integrations": [i["name"] for i in arch["integrations"]],
            "key_decisions": [d["decision"] for d in arch["key_decisions"]][:_MAX_RULES],
            "constraints": arch["constraints"][:_MAX_RULES],
            "approved_at": project.architecture_approved_at.isoformat(),
        }

    roadmap = (project.roadmap or {}).get("content")
    if project.roadmap_approved_at and roadmap:
        derived = next_recommended_task(roadmap)
        digest["roadmap"] = {
            "approved_at": project.roadmap_approved_at.isoformat(),
            "phases": [
                {
                    "id": p["id"],
                    "order": p["order"],
                    "title": p["title"],
                    "task_ids": [t["id"] for t in p["tasks"]],
                }
                for p in roadmap["phases"]
            ],
            "tasks": [
                {
                    "id": t["id"],
                    "order": t["order"],
                    "phase_id": t["phase_id"],
                    "title": t["title"],
                    "dependencies": t["dependencies"],
                    "status": t["status"],
                }
                for p in roadmap["phases"]
                for t in p["tasks"]
            ],
            "progress": compute_progress(roadmap),
            "current_task_id": derived["current_task_id"],
            "next_recommended_task_id": derived["next_recommended_task_id"],
        }

    return digest
