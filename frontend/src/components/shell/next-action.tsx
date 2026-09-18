"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRightIcon } from "@radix-ui/react-icons";

import { api } from "@/lib/api/client";
import type { Project } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { useLanguage } from "@/lib/i18n";

const SOFTWARE_SEGMENT: Record<string, string> = {
  discovery: "discovery",
  blueprint: "blueprint",
  business_logic: "business-logic",
  architecture: "architecture",
  roadmap: "roadmap",
  progress: "progress",
  ship: "ship",
};

/**
 * Persistent Next Action — deterministic only, never AI. Software reads
 * `next_task` from the existing (roadmap-approval-gated) Progress endpoint;
 * before the Roadmap is approved, or if the call fails, it falls back to the
 * next unmet approval gate computed client-side from the same fields the
 * Journey itself uses — never a guess, always a real stored fact. Data reads
 * `next_action` from the ungated Data Progress endpoint directly.
 */
export function NextAction({ project }: { project: Project }) {
  const { dict } = useLanguage();
  const isData = project.project_type === "data";

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

  let label: string | null = null;
  let href: string | null = null;

  if (isData) {
    const next = dataProgress.data?.next_action;
    if (next) {
      label = next.label;
      href = `/projects/${project.slug}/${next.href}`;
    }
  } else if (project.roadmap_approved_at && softwareProgress.data?.next_task) {
    const task = softwareProgress.data.next_task;
    label = `${task.id} · ${task.title}`;
    href = `/projects/${project.slug}/roadmap/tasks/${task.id}`;
  } else {
    // Deterministic client-side fallback: the first unmet approval gate, in
    // the same fixed order the Journey renders. No network call needed.
    const na = dict.nextAction;
    if (!project.discovery?.answered_at) {
      label = na.answerDiscovery;
      href = SOFTWARE_SEGMENT.discovery;
    } else if (!project.blueprint_approved_at) {
      label = project.blueprint?.content ? na.approveBlueprint : na.generateBlueprint;
      href = SOFTWARE_SEGMENT.blueprint;
    } else if (
      !project.business_logic_approved_at &&
      !(!project.business_logic?.content && !!project.architecture?.content)
    ) {
      label = project.business_logic?.content ? na.approveBusinessLogic : na.generateBusinessLogic;
      href = SOFTWARE_SEGMENT.business_logic;
    } else if (!project.architecture_approved_at) {
      label = project.architecture?.content ? na.approveArchitecture : na.generateArchitecture;
      href = SOFTWARE_SEGMENT.architecture;
    } else if (!project.roadmap_approved_at) {
      label = project.roadmap?.content ? na.approveRoadmap : na.generateRoadmap;
      href = SOFTWARE_SEGMENT.roadmap;
    } else {
      label = na.reviewDelivery;
      href = SOFTWARE_SEGMENT.ship;
    }
    if (href) href = `/projects/${project.slug}/${href}`;
  }

  // Only the *real* progress-endpoint path can be pending on first mount (the
  // client-side gate fallback is synchronous) — while it's in flight, show a
  // neutral loading state rather than momentarily claiming "nothing
  // actionable," which would be a false statement for the instant it's shown.
  const isLoading = isData
    ? dataProgress.isPending
    : !!project.roadmap_approved_at && softwareProgress.isPending;

  return (
    <div className="border-b border-line bg-surface/60 px-5 py-3">
      {isLoading ? (
        <div className="flex items-center gap-3 py-1">
          <Skeleton className="h-4 w-10 rounded-full" />
          <Skeleton className="h-3.5 w-48" />
        </div>
      ) : label && href ? (
        <Link
          href={href}
          className="group flex items-center gap-3 rounded-sm py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <span className="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-accent">
            {dict.nextAction.label}
          </span>
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-fg group-hover:text-accent-strong">
            {label}
          </span>
          <ArrowRightIcon
            className="size-3.5 shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5 group-hover:text-accent"
            aria-hidden
          />
        </Link>
      ) : (
        <div className="flex items-center gap-3 py-1">
          <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-fg-subtle">
            {dict.nextAction.label}
          </span>
          <span className="text-sm text-fg-muted">{dict.nextAction.empty}</span>
        </div>
      )}
    </div>
  );
}
