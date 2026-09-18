"use client";

import { CheckIcon } from "@radix-ui/react-icons";

import type {
  RoadmapContent,
  RoadmapMeta,
  TaskStatus,
} from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";

import { allTasks, taskTitleById } from "./roadmap-shared";
import { TaskCard } from "./task-card";

interface Props {
  slug: string;
  content: RoadmapContent;
  meta: RoadmapMeta | null;
  approved: boolean;
  pendingTaskId: string | null;
  taskErrors: Record<string, string>;
  onSetStatus: (taskId: string, status: TaskStatus) => void;
}

export function RoadmapPhases({
  slug,
  content,
  meta,
  approved,
  pendingTaskId,
  taskErrors,
  onSetStatus,
}: Props) {
  const titleById = taskTitleById(content);
  const statusById = Object.fromEntries(
    allTasks(content).map((t) => [t.id, t.status]),
  ) as Record<string, TaskStatus>;
  const phaseProgress = Object.fromEntries(
    (meta?.progress.phases ?? []).map((p) => [p.phase_id, p]),
  );

  return (
    <div className="grid gap-6">
      {content.phases.map((phase) => {
        const pp = phaseProgress[phase.id];
        return (
          <section key={phase.id} className="grid gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-fg-subtle">{phase.id}</span>
              <h2 className="text-base font-semibold text-fg">{phase.title}</h2>
              {approved && pp && (
                <Badge tone={pp.done ? "success" : "neutral"} className="tabular">
                  {pp.done && <CheckIcon className="size-3" aria-hidden />}
                  {pp.completed}/{pp.total}
                </Badge>
              )}
            </div>
            <p className="text-sm leading-relaxed text-fg-muted">
              {phase.objective}
            </p>
            <div className="grid gap-3">
              {phase.tasks.map((task) => (
                <TaskCard
                  key={task.id}
                  slug={slug}
                  task={task}
                  titleById={titleById}
                  statusById={statusById}
                  isNext={meta?.next_recommended_task_id === task.id}
                  approved={approved}
                  onSetStatus={(status) => onSetStatus(task.id, status)}
                  statusPending={pendingTaskId === task.id}
                  statusError={taskErrors[task.id] ?? null}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
