"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRightIcon, UpdateIcon } from "@radix-ui/react-icons";

import { StatusBadge } from "@/components/shell/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { dataCardStatus, softwareCardStatus } from "@/lib/project-card-status";
import { displayProjectName } from "@/lib/project-name";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";
import { localizedStageLabel } from "@/lib/i18n/stage-labels";
import type { Project } from "@/lib/api/types";

function relativeTime(iso: string, dict: Dictionary): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 1) return dict.common.justNow;
  if (minutes < 60) return interpolate(dict.common.minutesAgo, { n: String(minutes) });
  const hours = Math.round(minutes / 60);
  if (hours < 24) return interpolate(dict.common.hoursAgo, { n: String(hours) });
  const days = Math.round(hours / 24);
  if (days < 30) return interpolate(dict.common.daysAgo, { n: String(days) });
  return new Date(iso).toLocaleDateString();
}

/**
 * One Project — Software or Data, same card shape, same status vocabulary
 * (see `project-card-status.ts`, which reuses the identical Journey
 * computation the live Workspace uses — never a second, drifting notion of
 * "what stage is this project at").
 */
export function ProjectCard({ project }: { project: Project }) {
  const { dict } = useLanguage();
  const isData = project.project_type === "data";
  const typeLabel: Record<string, string> = { software: dict.nav.software, data: dict.nav.data };

  const softwareProgress = useQuery({
    queryKey: ["progress", project.slug],
    queryFn: () => api.getProgress(project.slug),
    enabled: !isData && !!project.roadmap_approved_at,
    retry: false,
  });
  const dataProgress = useQuery({
    queryKey: ["data-progress", project.slug],
    queryFn: () => api.getDataProgress(project.slug),
    enabled: isData,
    retry: false,
  });

  const loading = isData ? dataProgress.isPending : softwareProgress.isPending && !!project.roadmap_approved_at;

  const info = isData
    ? dataCardStatus(project, dataProgress.data ?? null)
    : softwareCardStatus(project, softwareProgress.data ?? null);
  const stageLabel = localizedStageLabel(info.stageId, isData, dict) ?? info.stageLabel;

  return (
    <Link
      href={info.href}
      className="group flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 transition-colors hover:border-line-strong hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-fg" title={displayProjectName(project)}>
            {displayProjectName(project)}
          </p>
          <p className="mt-0.5 flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.06em] text-fg-subtle" dir="ltr">
            {typeLabel[project.project_type] ?? project.project_type}
            <span aria-hidden>·</span>
            {project.slug}
          </p>
        </div>
        <ArrowRightIcon
          aria-hidden
          className="mt-0.5 size-4 shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5 group-hover:text-fg-muted"
        />
      </div>

      {loading ? (
        <div className="grid gap-1.5">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-3 w-40" />
        </div>
      ) : (
        <div className="grid gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-medium text-fg">{stageLabel}</span>
            <StatusBadge status={info.status} />
            {info.stale && (
              <span className="inline-flex items-center gap-1 rounded-full bg-warning-soft px-1.5 py-px text-[10px] font-medium text-stale">
                <UpdateIcon className="size-2.5" aria-hidden />
                {dict.common.stale}
              </span>
            )}
          </div>

          {info.completionPercentage !== null && (
            <div className="flex items-center gap-2">
              <div className="h-1 flex-1 overflow-hidden rounded-full bg-line">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${info.completionPercentage}%` }}
                />
              </div>
              <span className="font-mono text-[10.5px] tabular text-fg-subtle" dir="ltr">
                {info.completionPercentage}%
              </span>
            </div>
          )}
        </div>
      )}

      <p className="text-[11px] text-fg-subtle">
        {interpolate(dict.common.updatedAt, { when: relativeTime(project.updated_at, dict) })}
      </p>
    </Link>
  );
}
