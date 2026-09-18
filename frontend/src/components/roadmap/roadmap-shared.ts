import type { RoadmapContent, RoadmapTask, TaskStatus } from "@/lib/api/types";

export const STATUS_ORDER: TaskStatus[] = [
  "not_started",
  "in_progress",
  "ready_for_review",
  "completed",
];

export const STATUS_LABEL: Record<TaskStatus, string> = {
  not_started: "Not Started",
  in_progress: "In Progress",
  ready_for_review: "Ready for Review",
  completed: "Completed",
};

export const STATUS_TONE: Record<
  TaskStatus,
  "neutral" | "accent" | "success" | "warning"
> = {
  not_started: "neutral",
  in_progress: "accent",
  ready_for_review: "warning",
  completed: "success",
};

/**
 * Allowed next task statuses from a given status — mirrors the backend
 * transition matrix (`projects/roadmap.py::ALLOWED_TRANSITIONS`). The current
 * status is always included (a no-op re-set is accepted).
 */
const TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  not_started: ["in_progress"],
  in_progress: ["ready_for_review", "not_started"],
  ready_for_review: ["completed", "in_progress"],
  completed: ["in_progress"],
};

export function nextStatuses(current: TaskStatus): TaskStatus[] {
  return [current, ...TRANSITIONS[current]];
}

export function allTasks(content: RoadmapContent): RoadmapTask[] {
  return content.phases.flatMap((phase) => phase.tasks);
}

export function taskTitleById(content: RoadmapContent): Record<string, string> {
  return Object.fromEntries(allTasks(content).map((t) => [t.id, t.title]));
}

/** A not_started task whose dependencies aren't all completed. */
export function blockedDeps(
  task: RoadmapTask,
  statusById: Record<string, TaskStatus>,
): string[] {
  return task.dependencies.filter((d) => statusById[d] !== "completed");
}
