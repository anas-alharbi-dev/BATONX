"""
Stored Development Roadmap schema + normalization + derived progress / next-task.

Stored as a JSON document (like Blueprint / Architecture) so the whole
review -> edit -> regenerate -> approve machinery is reused. Task status is
mutable progress state layered on the approved structure; a status change does
NOT revert approval, a structural edit does.

``normalize_roadmap_content`` is the single place that:
  - assigns stable ids (``P1``.., ``T1``..) and 1..N ``order`` by position
  - resolves each task's ``dependencies`` (given by title or id) to task ids
  - drops self / forward dependencies so the graph is always a DAG
  - trims blanks and coerces ``status``
It is idempotent.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class TaskStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    READY_FOR_REVIEW = "ready_for_review"
    COMPLETED = "completed"


VALID_STATUSES = {s.value for s in TaskStatus}

# Explicit, minimal task-status transition matrix (Phase F). ``blocked`` is NOT a
# stored status - it is derived from unmet dependencies (see ``projects.progress``).
# Forward path: not_started -> in_progress -> ready_for_review -> completed.
# Backward / reopen edges are deliberate and enumerated; anything not listed here
# is rejected with ``invalid_transition``. Re-setting a task to its current status
# is a no-op (allowed).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "not_started": {"in_progress"},
    "in_progress": {"ready_for_review", "not_started"},
    "ready_for_review": {"completed", "in_progress"},
    "completed": {"in_progress"},
}

# Target statuses that require every dependency to be completed first.
ACTIVE_STATUSES = {"in_progress", "ready_for_review", "completed"}


def can_transition(current: str, target: str) -> bool:
    return target == current or target in ALLOWED_TRANSITIONS.get(current, set())


class Task(BaseModel):
    id: str = Field(pattern=r"^T\d+$")
    order: int = Field(ge=1)
    phase_id: str = Field(pattern=r"^P\d+$")
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    why: str = Field(min_length=1)
    requirements: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    expected_output: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    status: TaskStatus = TaskStatus.NOT_STARTED


class Phase(BaseModel):
    id: str = Field(pattern=r"^P\d+$")
    order: int = Field(ge=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    tasks: list[Task] = Field(min_length=1)


class RoadmapContent(BaseModel):
    phases: list[Phase] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_graph(self) -> "RoadmapContent":
        tasks = [t for p in self.phases for t in p.tasks]
        ids = [t.id for t in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate task ids")
        if len(self.phases) != len({p.id for p in self.phases}):
            raise ValueError("duplicate phase ids")

        order_by_id = {t.id: t.order for t in tasks}
        for task in tasks:
            for dep in task.dependencies:
                if dep not in order_by_id:
                    raise ValueError(f"{task.id} depends on unknown task {dep}")
                if order_by_id[dep] >= task.order:
                    raise ValueError(f"{task.id} depends on non-earlier task {dep}")
        return self


def _clean(items) -> list[str]:
    return [str(x).strip() for x in (items or []) if str(x).strip()]


def normalize_roadmap_content(content: dict) -> dict:
    phases_in = content.get("phases") or []

    # pass 1 — flatten and index every task by position, submitted id, and title
    flat: list[dict] = []
    by_sid: dict[str, int] = {}
    by_title: dict[str, int] = {}
    pos = 0
    for phase_index, phase in enumerate(phases_in):
        for task in phase.get("tasks") or []:
            sid = str(task.get("id") or "").strip()
            title_key = str(task.get("title") or "").strip().lower()
            if sid:
                by_sid.setdefault(sid, pos)
            if title_key:
                by_title.setdefault(title_key, pos)
            flat.append({"phase_index": phase_index, "task": task, "pos": pos})
            pos += 1

    def resolve(ref: str):
        r = str(ref or "").strip()
        if r in by_sid:
            return by_sid[r]
        return by_title.get(r.lower())

    pos_to_id = {entry["pos"]: f"T{entry['pos'] + 1}" for entry in flat}

    # pass 2 — emit normalized structure
    out_phases: list[dict] = []
    for phase_index, phase in enumerate(phases_in):
        pid = f"P{phase_index + 1}"
        out_tasks: list[dict] = []
        for entry in (e for e in flat if e["phase_index"] == phase_index):
            task = entry["task"]
            tp = entry["pos"]
            dep_positions = set()
            for ref in task.get("dependencies") or []:
                rp = resolve(ref)
                if rp is not None and rp < tp:
                    dep_positions.add(rp)
            status = task.get("status")
            out_tasks.append(
                {
                    "id": f"T{tp + 1}",
                    "order": tp + 1,
                    "phase_id": pid,
                    "title": str(task.get("title") or "").strip(),
                    "objective": str(task.get("objective") or "").strip(),
                    "why": str(task.get("why") or "").strip(),
                    "requirements": _clean(task.get("requirements")),
                    "dependencies": sorted(
                        (pos_to_id[p] for p in dep_positions),
                        key=lambda x: int(x[1:]),
                    ),
                    "expected_output": str(task.get("expected_output") or "").strip(),
                    "acceptance_criteria": _clean(task.get("acceptance_criteria")),
                    "status": status if status in VALID_STATUSES else "not_started",
                }
            )
        out_phases.append(
            {
                "id": pid,
                "order": phase_index + 1,
                "title": str(phase.get("title") or "").strip(),
                "objective": str(phase.get("objective") or "").strip(),
                "tasks": out_tasks,
            }
        )

    return {"phases": out_phases}


# --- derived state -------------------------------------------------------


def flat_tasks(content: dict) -> list[dict]:
    return [t for p in content.get("phases", []) for t in p.get("tasks", [])]


def compute_progress(content: dict) -> dict:
    tasks = flat_tasks(content)
    total = len(tasks)
    completed = sum(1 for t in tasks if t["status"] == "completed")
    in_progress = sum(1 for t in tasks if t["status"] == "in_progress")
    ready_for_review = sum(1 for t in tasks if t["status"] == "ready_for_review")
    phases = []
    for phase in content.get("phases", []):
        phase_tasks = phase.get("tasks", [])
        phase_done = sum(1 for t in phase_tasks if t["status"] == "completed")
        phases.append(
            {
                "phase_id": phase["id"],
                "total": len(phase_tasks),
                "completed": phase_done,
                "done": len(phase_tasks) > 0 and phase_done == len(phase_tasks),
            }
        )
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "ready_for_review": ready_for_review,
        "not_started": total - completed - in_progress - ready_for_review,
        "percent": round(completed / total * 100) if total else 0,
        "phases": phases,
    }


def next_recommended_task(content: dict) -> dict:
    """
    Current task = the (first, by order) in_progress task.
    Next recommended = the first not_started task whose every dependency is
    completed. Not from position alone - a blocked earlier task is skipped.
    """
    tasks = sorted(flat_tasks(content), key=lambda t: t["order"])
    status_by_id = {t["id"]: t["status"] for t in tasks}

    current = next((t["id"] for t in tasks if t["status"] == "in_progress"), None)
    nxt = None
    for task in tasks:
        if task["status"] != "not_started":
            continue
        if all(status_by_id.get(d) == "completed" for d in task["dependencies"]):
            nxt = task["id"]
            break

    return {"current_task_id": current, "next_recommended_task_id": nxt}


def find_task(content: dict, task_id: str) -> dict | None:
    for task in flat_tasks(content):
        if task["id"] == task_id:
            return task
    return None
