"use client";

import Link from "next/link";
import { CheckCircledIcon } from "@radix-ui/react-icons";

import type { RoadmapMeta } from "@/lib/api/types";
import { StaleNotice } from "@/components/feedback/stale-notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { interpolate, useLanguage } from "@/lib/i18n";

interface Props {
  slug: string;
  approved: boolean;
  approvedAt: string | null;
  updatedAt?: string;
  editing: boolean;
  approving: boolean;
  approveError?: string | null;
  stale?: boolean;
  meta: RoadmapMeta | null;
  nextTaskTitle?: string;
  onApprove: () => void;
  onRegenerate: () => void;
  onToggleEdit: () => void;
}

export function RoadmapStatusBar({
  slug,
  approved,
  approvedAt,
  updatedAt,
  editing,
  approving,
  approveError,
  stale = false,
  meta,
  nextTaskTitle,
  onApprove,
  onRegenerate,
  onToggleEdit,
}: Props) {
  const { dict } = useLanguage();
  const progress = meta?.progress;

  return (
    <div className="sticky top-14 z-30 -mx-4 mb-6 border-b border-line bg-bg/90 px-4 py-3 backdrop-blur-md">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-sm">
          {approved ? (
            <>
              <Badge tone="success">
                <CheckCircledIcon className="size-3.5" aria-hidden />
                {dict.softwareShared.approvedBadge}
              </Badge>
              <span className="text-fg-subtle">{formatDateTime(approvedAt)}</span>
            </>
          ) : (
            <>
              <Badge tone="neutral">{dict.softwareShared.draftBadge}</Badge>
              {updatedAt && (
                <span className="text-fg-subtle">
                  {interpolate(dict.common.updatedAt, { when: formatDateTime(updatedAt) }).toLowerCase()}
                </span>
              )}
              {approved === false && editing && (
                <span className="text-fg-subtle">{dict.softwareShared.editingSuffix}</span>
              )}
            </>
          )}
          {approved && editing && (
            <span className="text-warning">
              {dict.softwareShared.savingMovesToDraft}
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={onToggleEdit}>
            {editing ? dict.softwareShared.doneEditing : dict.roadmap.editArtifact}
          </Button>
          <Button variant="outline" size="sm" onClick={onRegenerate}>
            {dict.softwareShared.regenerate}
          </Button>
          {!approved && (
            <Button
              size="sm"
              loading={approving}
              disabled={editing}
              onClick={onApprove}
            >
              {dict.roadmap.approveArtifact}
            </Button>
          )}
        </div>
      </div>

      {stale && (
        <div className="mt-2">
          <StaleNotice artifact={dict.roadmap.staleArtifactName} />
        </div>
      )}

      {approved && progress && (
        <div className="mt-3 grid gap-1.5">
          <div className="flex items-center justify-between text-xs text-fg-muted">
            <span className="tabular">
              {interpolate(dict.roadmap.tasksOf, {
                completed: String(progress.completed),
                total: String(progress.total),
                percent: String(progress.percent),
              })}
            </span>
            {nextTaskTitle && meta?.next_recommended_task_id && (
              <span>
                {dict.roadmap.nextUp}{" "}
                <Link
                  href={`/projects/${slug}/roadmap/tasks/${meta.next_recommended_task_id}`}
                  className="text-fg underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  {nextTaskTitle}
                </Link>
              </span>
            )}
          </div>
          <div
            className="h-1.5 overflow-hidden rounded-full bg-surface-hover"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={progress.total}
            aria-valuenow={progress.completed}
          >
            <div
              className="h-full rounded-full bg-accent transition-[width] duration-300 ease-out"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
        </div>
      )}

      {approveError && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {approveError}
        </p>
      )}
    </div>
  );
}
