"use client";

import Link from "next/link";
import { ArrowRightIcon, CheckCircledIcon, CircleIcon } from "@radix-ui/react-icons";

import type { RoadmapTask, TaskStatus } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { interpolate, useLanguage } from "@/lib/i18n";

import {
  blockedDeps,
  nextStatuses,
  STATUS_ORDER,
  STATUS_TONE,
} from "./roadmap-shared";

interface Props {
  slug: string;
  task: RoadmapTask;
  titleById: Record<string, string>;
  statusById: Record<string, TaskStatus>;
  isNext: boolean;
  approved: boolean;
  onSetStatus: (status: TaskStatus) => void;
  statusPending: boolean;
  statusError: string | null;
}

export function TaskCard({
  slug,
  task,
  titleById,
  statusById,
  isNext,
  approved,
  onSetStatus,
  statusPending,
  statusError,
}: Props) {
  const { dict } = useLanguage();
  const blocked =
    approved && task.status === "not_started"
      ? blockedDeps(task, statusById)
      : [];
  const allowed = nextStatuses(task.status);
  const depsUnmet = blockedDeps(task, statusById).length > 0;

  return (
    <div
      id={`task-${task.id}`}
      className={
        "scroll-mt-28 rounded-lg border bg-bg p-4 " +
        (isNext ? "border-accent/50 ring-1 ring-accent/30" : "border-line")
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-fg-subtle">{task.id}</span>
        <h3 className="text-sm font-medium text-fg">{task.title}</h3>
        <Badge tone={STATUS_TONE[task.status]}>{dict.taskStatus[task.status]}</Badge>
        {blocked.length > 0 && <Badge tone="warning">{dict.roadmap.blockedBadge}</Badge>}
        {approved && (
          <Link
            href={`/projects/${slug}/roadmap/tasks/${task.id}`}
            className="ms-auto inline-flex items-center gap-1 text-xs text-fg-muted underline-offset-4 hover:text-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {dict.roadmap.open}
            <ArrowRightIcon className="size-3 rtl:-scale-x-100" aria-hidden />
          </Link>
        )}
        {isNext && <Badge tone="accent">{dict.roadmap.nextBadge}</Badge>}
      </div>

      <p className="mt-2 text-sm leading-relaxed text-fg-muted">{task.objective}</p>
      <p className="mt-1 text-sm leading-relaxed text-fg-subtle">
        <span className="text-fg-muted">{dict.softwareShared.fieldWhy}: </span>
        {task.why}
      </p>

      {task.requirements.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {task.requirements.map((r) => (
            <span
              key={r}
              className="rounded-sm border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-fg-muted"
            >
              {r}
            </span>
          ))}
        </div>
      )}

      {task.dependencies.length > 0 && (
        <div className="mt-3">
          <p className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
            {dict.roadmap.dependsOn}
          </p>
          <ul className="mt-1 grid gap-1 text-sm text-fg-muted">
            {task.dependencies.map((d) => {
              const done = statusById[d] === "completed";
              return (
                <li key={d} className="flex items-center gap-2">
                  {done ? (
                    <CheckCircledIcon className="size-3.5 text-accent" aria-hidden />
                  ) : (
                    <CircleIcon className="size-3.5 text-fg-subtle" aria-hidden />
                  )}
                  <span className="font-mono text-xs">{d}</span>
                  {titleById[d] ?? "—"}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="mt-3 grid gap-1">
        <p className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
          {dict.roadmap.expectedOutput}
        </p>
        <p className="text-sm leading-relaxed text-fg-muted">
          {task.expected_output}
        </p>
      </div>

      <div className="mt-3 grid gap-1">
        <p className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
          {dict.roadmap.acceptanceCriteria}
        </p>
        <ul className="grid list-disc gap-1 ps-5 text-sm leading-relaxed text-fg-muted">
          {task.acceptance_criteria.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      </div>

      {approved && (
        <div className="mt-4 grid gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="inline-flex rounded-md border border-line p-0.5"
              role="group"
              aria-label={interpolate(dict.roadmap.statusForTask, { title: task.title })}
            >
              {STATUS_ORDER.map((s) => {
                const isCurrent = task.status === s;
                const depBlocked =
                  depsUnmet &&
                  (s === "in_progress" ||
                    s === "ready_for_review" ||
                    s === "completed");
                const selectable =
                  !isCurrent && allowed.includes(s) && !depBlocked;
                return (
                  <button
                    key={s}
                    type="button"
                    aria-pressed={isCurrent}
                    disabled={statusPending || (!isCurrent && !selectable)}
                    title={
                      depBlocked ? dict.roadmap.finishDependenciesFirst : undefined
                    }
                    onClick={() => selectable && onSetStatus(s)}
                    className={
                      "rounded-[5px] px-2.5 py-1 text-xs font-medium transition-colors [touch-action:manipulation] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40 " +
                      (isCurrent
                        ? "bg-accent text-accent-fg"
                        : "text-fg-muted hover:text-fg")
                    }
                  >
                    {dict.taskStatus[s]}
                  </button>
                );
              })}
            </span>
            {statusPending && <Spinner className="size-4 text-fg-subtle" />}
          </div>

          {blocked.length > 0 && !statusError && (
            <p className="text-xs text-fg-subtle">
              {interpolate(dict.roadmap.blockedBy, {
                deps: blocked.map((d) => `${d} ${titleById[d] ?? ""}`.trim()).join(", "),
              })}
            </p>
          )}
          {statusError && (
            <p role="alert" className="text-xs text-danger">
              {statusError}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
