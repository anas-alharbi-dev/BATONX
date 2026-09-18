"""
Deterministic context-selection layer for Task Workspace / Build Prompt.

``assemble_task_context`` builds - with NO AI and NO randomness - the slice of
APPROVED project context relevant to one Roadmap task. It reads only:
  - project.original_idea
  - context_digest["idea_analysis"]  (model analysis of the idea; no secrets)
  - approved Blueprint content
  - approved Architecture content
  - approved Roadmap content
It never touches env vars, API keys, or the full context_digest.

Relevance rule: the architecture "spine" (style, tech choices, key decisions,
constraints) is always included because any implementation task needs it. The
large lists (components, API areas, data entities, integrations, roles, rules,
security) are filtered by keyword match against the task text; if nothing
matches, a small list is included whole, otherwise it is dropped (the spine
still carries the essentials).
"""
from __future__ import annotations

import re

from projects.roadmap import find_task

_MAX_FALLBACK_LIST = 6
_MAX_MUST_REQUIREMENTS = 8
_MAX_ROLES_FALLBACK = 4
_MAX_RULES = 6
_MAX_SECURITY = 4


def _task_text(task: dict) -> str:
    parts = [
        task.get("title", ""),
        task.get("objective", ""),
        task.get("why", ""),
        task.get("expected_output", ""),
        *task.get("acceptance_criteria", []),
        *task.get("requirements", []),
    ]
    return " ".join(str(p) for p in parts).lower()


def _mentions(name: str, text: str) -> bool:
    token = (name or "").strip().lower()
    if not token:
        return False
    if token in text:
        return True
    words = [w for w in re.split(r"[^a-z0-9]+", token) if len(w) >= 4]
    return any(w in text for w in words)


def _filter_named(items: list[dict], key: str, text: str) -> list[dict]:
    hits = [item for item in items if _mentions(item.get(key, ""), text)]
    if hits:
        return hits
    if len(items) <= _MAX_FALLBACK_LIST:
        return list(items)
    return []


def _select_business_logic(project, req_ids: set[str], text: str) -> dict:
    """
    Task-relevant slice of approved Business Logic: rules / validations / edge
    cases traced to one of the task's requirement ids first, then keyword
    matches, capped. State transitions and permissions whose actor/entity is
    mentioned in the task text. Empty dict if Business Logic is not approved.
    """
    content = (project.business_logic or {}).get("content")
    if not (project.business_logic_approved_at and content):
        return {}

    def by_req_then_keyword(rows: list[dict], text_key: str) -> list[dict]:
        traced = [
            r for r in rows if req_ids & set(r.get("related_requirements", []))
        ]
        if traced:
            return traced[:_MAX_FALLBACK_LIST]
        keyword = [r for r in rows if _mentions(r.get(text_key, ""), text)]
        return keyword[:_MAX_FALLBACK_LIST]

    rules = by_req_then_keyword(content.get("business_rules", []), "statement")
    validations = by_req_then_keyword(content.get("validations", []), "rule")
    edge_cases = by_req_then_keyword(content.get("edge_cases", []), "scenario")

    transitions = [
        t
        for t in content.get("state_transitions", [])
        if _mentions(t.get("entity", ""), text) or _mentions(t.get("trigger", ""), text)
    ][:_MAX_FALLBACK_LIST]

    rule_actors = {r.get("actor", "") for r in rules if r.get("actor")}
    permissions = [
        p
        for p in content.get("permissions", [])
        if p.get("actor") in rule_actors or _mentions(p.get("actor", ""), text)
    ][:_MAX_FALLBACK_LIST]

    slice_ = {
        "summary": content.get("summary", ""),
        "business_rules": [
            {
                "id": r["id"],
                "statement": r["statement"],
                "actor": r.get("actor", ""),
                "conditions": r.get("conditions", []),
                "outcome": r.get("outcome", ""),
                "exceptions": r.get("exceptions", []),
                "related_requirements": r.get("related_requirements", []),
            }
            for r in rules
        ],
        "validations": [
            {"id": v["id"], "rule": v["rule"], "applies_to": v.get("applies_to", "")}
            for v in validations
        ],
        "state_transitions": [
            {
                "entity": t["entity"],
                "from": t["from_state"],
                "to": t["to_state"],
                "trigger": t["trigger"],
                "actor": t.get("actor", ""),
                "guards": t.get("guards", []),
            }
            for t in transitions
        ],
        "permissions": [
            {"actor": p["actor"], "can": p["can"], "conditions": p.get("conditions", [])}
            for p in permissions
        ],
        "edge_cases": [
            {"id": e["id"], "scenario": e["scenario"], "expected_behavior": e["expected_behavior"]}
            for e in edge_cases
        ],
    }
    return slice_


def assemble_task_context(project, task_id: str) -> dict | None:
    roadmap = (project.roadmap or {}).get("content") or {}
    blueprint = (project.blueprint or {}).get("content") or {}
    architecture = (project.architecture or {}).get("content") or {}
    analysis = (project.context_digest or {}).get("idea_analysis") or {}

    task = find_task(roadmap, task_id)
    if task is None:
        return None

    phase = next(
        (p for p in roadmap.get("phases", []) if p["id"] == task["phase_id"]), {}
    )
    text = _task_text(task)

    tasks_by_id = {
        t["id"]: t for p in roadmap.get("phases", []) for t in p["tasks"]
    }
    dependencies = [
        {
            "id": dep_id,
            "title": tasks_by_id.get(dep_id, {}).get("title", dep_id),
            "status": tasks_by_id.get(dep_id, {}).get("status", "unknown"),
            "expected_output": tasks_by_id.get(dep_id, {}).get("expected_output", ""),
        }
        for dep_id in task.get("dependencies", [])
    ]

    # requirements: resolve FR ids referenced by the task; keep free-form notes.
    fr_by_id = {r["id"]: r for r in blueprint.get("functional_requirements", [])}
    requirements: list[dict] = []
    requirement_notes: list[str] = []
    for ref in task.get("requirements", []):
        ref = str(ref).strip()
        if ref in fr_by_id:
            fr = fr_by_id[ref]
            requirements.append(
                {"id": fr["id"], "text": fr["text"], "priority": fr["priority"]}
            )
        elif ref:
            requirement_notes.append(ref)
    if not requirements:
        musts = [
            r
            for r in blueprint.get("functional_requirements", [])
            if r.get("priority") == "must"
        ]
        requirements = [
            {"id": r["id"], "text": r["text"], "priority": r["priority"]}
            for r in musts[:_MAX_MUST_REQUIREMENTS]
        ]

    roles = _filter_named(blueprint.get("user_roles", []), "name", text)
    if not roles and len(blueprint.get("user_roles", [])) <= _MAX_ROLES_FALLBACK:
        roles = list(blueprint.get("user_roles", []))

    rules = [r for r in blueprint.get("business_rules", []) if _mentions(r, text)]
    if not rules:
        rules = blueprint.get("business_rules", [])[:_MAX_RULES]

    overview = architecture.get("overview", {})
    security = [
        s for s in architecture.get("security", []) if _mentions(s, text)
    ][:_MAX_SECURITY]
    if not security:
        security = architecture.get("security", [])[:_MAX_SECURITY]

    # Business rules traced to the task's requirement ids (deterministic first),
    # then keyword. Empty {} when Business Logic isn't approved (grandfathered).
    task_req_ids = {r["id"] for r in requirements}
    business_logic = _select_business_logic(project, task_req_ids, text)

    return {
        "product": {
            "idea": project.original_idea,
            "domain": analysis.get("domain", ""),
            "problem": blueprint.get("problem", ""),
            "solution": blueprint.get("solution", ""),
        },
        "task": {
            "id": task["id"],
            "order": task["order"],
            "phase_id": task["phase_id"],
            "phase_title": phase.get("title", ""),
            "title": task["title"],
            "objective": task["objective"],
            "why": task["why"],
            "expected_output": task["expected_output"],
            "acceptance_criteria": task["acceptance_criteria"],
            "status": task["status"],
        },
        "dependencies": dependencies,
        "requirements": requirements,
        "requirement_notes": requirement_notes,
        "user_roles": [
            {"name": r["name"], "description": r["description"]} for r in roles
        ],
        "business_rules": rules,
        "business_logic": business_logic,
        "architecture": {
            "style": overview.get("style", ""),
            "summary": overview.get("summary", ""),
            "frontend": architecture.get("frontend", {}).get("choice", ""),
            "backend": architecture.get("backend", {}).get("choice", ""),
            "database": architecture.get("database", {}).get("choice", ""),
            "auth": architecture.get("auth", {}).get("approach", ""),
            "components": [
                {"name": c["name"], "responsibility": c["responsibility"]}
                for c in _filter_named(architecture.get("components", []), "name", text)
            ],
            "api_areas": [
                {"name": a["name"], "purpose": a["purpose"]}
                for a in _filter_named(architecture.get("api_areas", []), "name", text)
            ],
            "data_model": [
                {
                    "entity": e["entity"],
                    "fields": e["fields"],
                    "relationships": e["relationships"],
                }
                for e in _filter_named(
                    architecture.get("data_model", []), "entity", text
                )
            ],
            "integrations": [
                {"name": i["name"], "purpose": i["purpose"]}
                for i in architecture.get("integrations", [])
                if _mentions(i.get("name", ""), text)
            ],
            "security": security,
            "key_decisions": [
                {"decision": d["decision"], "rationale": d["rationale"]}
                for d in architecture.get("key_decisions", [])
            ],
            "constraints": architecture.get("constraints", []),
        },
    }
