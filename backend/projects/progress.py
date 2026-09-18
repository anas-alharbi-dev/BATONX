"""
Deterministic Progress Tracking (Phase F).

Progress is derived state: every number here comes from Roadmap task status +
the (already deterministic) dependency graph. No AI, no randomness, no stored
counters. The Conversational Layer may later *explain* this output; it must never
compute or override it.

``blocked`` is derived, not a stored status: a task is blocked when it is
``not_started`` and at least one required dependency is not ``completed``. The
five reported buckets (not_started / in_progress / ready_for_review / completed /
blocked) partition the task set exactly.
"""
from __future__ import annotations

from projects.dependencies import is_stale
from projects.roadmap import flat_tasks

# Upstream authoritative artifacts whose staleness the Progress view must surface
# (Phase C). Ordered as in the artifact chain.
_STALE_CONTEXT = ("business_logic", "architecture", "roadmap")


def _unfinished_deps(task: dict, status_by_id: dict[str, str]) -> list[str]:
    return [
        dep
        for dep in task.get("dependencies", [])
        if status_by_id.get(dep) != "completed"
    ]


def is_blocked(task: dict, status_by_id: dict[str, str]) -> bool:
    return task["status"] == "not_started" and bool(
        _unfinished_deps(task, status_by_id)
    )


def _bucket_counts(tasks: list[dict], status_by_id: dict[str, str]) -> dict:
    counts = {
        "not_started": 0,
        "in_progress": 0,
        "ready_for_review": 0,
        "completed": 0,
        "blocked": 0,
    }
    for task in tasks:
        if is_blocked(task, status_by_id):
            counts["blocked"] += 1
        else:
            counts[task["status"]] += 1
    total = len(tasks)
    return {
        "total_tasks": total,
        **counts,
        "completion_percentage": (
            round(counts["completed"] / total * 100) if total else 0
        ),
    }


def _brief(task: dict) -> dict:
    return {
        "id": task["id"],
        "title": task["title"],
        "phase_id": task["phase_id"],
        "status": task["status"],
    }


def compute_project_progress(project) -> dict:
    """The authoritative operational view of implementation status."""
    content = (project.roadmap or {}).get("content") or {"phases": []}
    tasks = flat_tasks(content)
    status_by_id = {t["id"]: t["status"] for t in tasks}
    phase_title = {p["id"]: p["title"] for p in content.get("phases", [])}

    phases = [
        {
            "phase_id": phase["id"],
            "title": phase["title"],
            "order": phase["order"],
            **_bucket_counts(phase.get("tasks", []), status_by_id),
        }
        for phase in content.get("phases", [])
    ]

    blocked_tasks = [
        {**_brief(t), "unfinished_dependencies": _unfinished_deps(t, status_by_id)}
        for t in tasks
        if is_blocked(t, status_by_id)
    ]
    ready_for_review_tasks = [
        _brief(t) for t in tasks if t["status"] == "ready_for_review"
    ]
    completed_tasks = [_brief(t) for t in tasks if t["status"] == "completed"]

    # Next actionable task, deterministic:
    #   1. the in-progress task (lowest order) - it is already being worked on
    #   2. else the first not_started task (by order) whose deps are all completed
    #   3. else the first ready_for_review task - it needs a human to review it
    ordered = sorted(tasks, key=lambda t: t["order"])
    nxt = next((t for t in ordered if t["status"] == "in_progress"), None)
    if nxt is None:
        nxt = next(
            (
                t
                for t in ordered
                if t["status"] == "not_started"
                and all(
                    status_by_id.get(d) == "completed"
                    for d in t.get("dependencies", [])
                )
            ),
            None,
        )
    if nxt is None:
        nxt = next((t for t in ordered if t["status"] == "ready_for_review"), None)

    next_task = None
    if nxt is not None:
        next_task = {
            **_brief(nxt),
            "phase_title": phase_title.get(nxt["phase_id"], ""),
        }

    return {
        "summary": _bucket_counts(tasks, status_by_id),
        "phases": phases,
        "next_task": next_task,
        "blocked_tasks": blocked_tasks,
        "ready_for_review_tasks": ready_for_review_tasks,
        "completed_tasks": completed_tasks,
        "stale_context": [a for a in _STALE_CONTEXT if is_stale(project, a)],
        "roadmap_stale": is_stale(project, "roadmap"),
    }
