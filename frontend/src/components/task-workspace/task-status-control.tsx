"use client";

import type { TaskStatus } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  nextStatuses,
  STATUS_ORDER,
} from "@/components/roadmap/roadmap-shared";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

/** The verb for moving *forward* to this status — matches the exact
 *  examples the product spec calls for (Start Task / Mark Ready for
 *  Review / Complete Review), distinct from the neutral `taskStatus`
 *  vocabulary used everywhere else for "what state is this in." */
function forwardVerb(status: TaskStatus, dict: Dictionary): string | null {
  switch (status) {
    case "in_progress":
      return dict.taskWorkspace.forwardVerbStart;
    case "ready_for_review":
      return dict.taskWorkspace.forwardVerbReview;
    case "completed":
      return dict.taskWorkspace.forwardVerbComplete;
    default:
      return null;
  }
}

interface Props {
  status: TaskStatus;
  blocked: boolean;
  unfinishedDependencies: string[];
  pending: boolean;
  error: string | null;
  onSetStatus: (status: TaskStatus) => void;
}

const ACTIVE: TaskStatus[] = ["in_progress", "ready_for_review", "completed"];

export function TaskStatusControl({
  status,
  blocked,
  unfinishedDependencies,
  pending,
  error,
  onSetStatus,
}: Props) {
  const { dict } = useLanguage();
  const allowed = nextStatuses(status);
  const currentIndex = STATUS_ORDER.indexOf(status);
  const forward = allowed.find((s) => STATUS_ORDER.indexOf(s) > currentIndex) ?? null;
  const forwardBlocked = blocked && !!forward && ACTIVE.includes(forward);

  return (
    <div className="grid gap-3">
      {forward && (
        <Button
          onClick={() => onSetStatus(forward)}
          disabled={pending || forwardBlocked}
          loading={pending}
          className="w-fit"
        >
          {forwardVerb(forward, dict) ?? interpolate(dict.taskWorkspace.markStatus, { status: dict.taskStatus[forward] })}
        </Button>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-fg-subtle">{dict.taskWorkspace.changeStatus}</span>
        <span
          className="inline-flex rounded-md border border-line p-0.5"
          role="group"
          aria-label={dict.taskWorkspace.statusFor}
        >
          {STATUS_ORDER.map((s) => {
            const isCurrent = s === status;
            const depBlocked = blocked && ACTIVE.includes(s);
            const selectable = !isCurrent && allowed.includes(s) && !depBlocked;
            return (
              <button
                key={s}
                type="button"
                aria-pressed={isCurrent}
                disabled={pending || (!isCurrent && !selectable)}
                title={
                  depBlocked
                    ? dict.roadmap.finishDependenciesFirst
                    : undefined
                }
                onClick={() => selectable && onSetStatus(s)}
                className={
                  "rounded-[5px] px-3 py-1.5 text-xs font-medium transition-colors [touch-action:manipulation] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40 " +
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
        {pending && <Spinner className="size-4 text-fg-subtle" />}
      </div>

      <p className="text-xs text-fg-subtle">
        {dict.taskWorkspace.neverChangesStatusHint}
      </p>

      {blocked && unfinishedDependencies.length > 0 && !error && (
        <p className="text-xs text-fg-subtle">
          {interpolate(dict.taskWorkspace.blockedByComplete, { deps: unfinishedDependencies.join(", ") })}
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
