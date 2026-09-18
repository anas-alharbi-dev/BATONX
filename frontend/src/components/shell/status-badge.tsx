"use client";

import {
  CheckIcon,
  ExclamationTriangleIcon,
  LockClosedIcon,
  UpdateIcon,
} from "@radix-ui/react-icons";

import type { WorkflowStatus } from "@/lib/journey-model";
import { useLanguage } from "@/lib/i18n";

/**
 * The single source of truth for how a `WorkflowStatus` reads visually —
 * shared by the Journey rail (`journey-stage.tsx`) and Project cards
 * (`project-card.tsx`) so status never has two different appearances in the
 * product. Icon + label + color together (never color alone).
 */
export const STATUS_META: Record<
  WorkflowStatus,
  { label: string; Icon: typeof CheckIcon | null; dot: string; ring: string; text: string }
> = {
  completed: { label: "Completed", Icon: CheckIcon, dot: "bg-completed", ring: "border-completed/50", text: "text-fg-muted" },
  in_progress: { label: "In progress", Icon: null, dot: "bg-active", ring: "border-active/60 ring-2 ring-active/20", text: "text-fg" },
  needs_review: { label: "Needs review", Icon: ExclamationTriangleIcon, dot: "bg-needs-review", ring: "border-needs-review/50", text: "text-fg" },
  stale: { label: "Stale — may be inconsistent", Icon: UpdateIcon, dot: "bg-stale", ring: "border-stale/50", text: "text-fg" },
  blocked: { label: "Blocked", Icon: LockClosedIcon, dot: "bg-blocked", ring: "border-blocked/50", text: "text-fg" },
  upcoming: { label: "Upcoming", Icon: null, dot: "bg-transparent", ring: "border-line-strong", text: "text-fg-subtle" },
  skipped: { label: "Skipped — not required", Icon: null, dot: "bg-transparent", ring: "border-line", text: "text-fg-subtle" },
};

export function statusBadgeClass(status: WorkflowStatus): string {
  return (
    "mt-0.5 inline-flex w-fit items-center gap-1 rounded-full px-1.5 py-px text-[10px] font-medium " +
    (status === "upcoming"
      ? "text-fg-subtle"
      : status === "skipped"
        ? "text-fg-subtle line-through decoration-line-strong"
        : status === "completed"
          ? "bg-success-soft text-success"
          : status === "in_progress"
            ? "bg-info-soft text-active"
            : status === "blocked"
              ? "bg-danger-soft text-blocked"
              : "bg-warning-soft text-needs-review")
  );
}

export function StatusBadge({ status }: { status: WorkflowStatus }) {
  const { dict } = useLanguage();
  return <span className={statusBadgeClass(status)}>{dict.status[status]}</span>;
}
