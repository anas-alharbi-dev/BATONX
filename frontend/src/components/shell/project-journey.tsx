"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import type { Project, ProjectProgress } from "@/lib/api/types";
import {
  buildDataJourney,
  buildSoftwareJourney,
  type DataJourneyStageId,
  type SoftwareStageId,
} from "@/lib/journey-model";
import { useLanguage, type Dictionary } from "@/lib/i18n";
import { localizeStages, localizedStageLabel } from "@/lib/i18n/stage-labels";

import { JourneyStage } from "./journey-stage";

export const SOFTWARE_SEGMENT_TO_STAGE: Record<string, SoftwareStageId> = {
  discovery: "discovery",
  blueprint: "blueprint",
  "business-logic": "business_logic",
  architecture: "architecture",
  roadmap: "roadmap",
  progress: "progress",
  ship: "ship",
};

/**
 * "roadmap" is one route segment shared by three Journey stages (Roadmap
 * itself, Tasks/Build, and Review — see journey-model.ts). Disambiguate
 * using the same structured Progress data the Journey statuses are built
 * from: the bare `/roadmap` page is the Roadmap stage; a specific
 * `/roadmap/tasks/:taskId` is Review iff that exact task id is in
 * `progress.ready_for_review_tasks`, else Tasks/Build. No text matching.
 */
function currentSoftwareStage(
  pathname: string,
  slug: string,
  progress: ProjectProgress | null | undefined,
): SoftwareStageId {
  const rest = pathname.startsWith(`/projects/${slug}/`) ? pathname.slice(`/projects/${slug}/`.length) : "";
  const parts = rest.split("/");
  const segment = parts[0] ?? "";
  if (segment !== "roadmap") return SOFTWARE_SEGMENT_TO_STAGE[segment] ?? "discovery";
  const taskId = parts[1] === "tasks" ? parts[2] : undefined;
  if (!taskId) return "roadmap";
  if (progress?.ready_for_review_tasks.some((t) => t.id === taskId)) return "review";
  return "tasks_build";
}

export const DATA_SEGMENT_TO_STAGE: Partial<Record<string, DataJourneyStageId>> = {
  "data-overview": "data_brief",
  "data-sources": "sources",
  "data-quality": "data_quality",
  "data-build": "transformation_plan",
  "data-metrics": "metrics",
  "data-queries": "queries",
  "data-analysis": "analysis",
  "data-progress": "progress",
  "data-readiness": "delivery_readiness",
};

/** The segment immediately after /projects/<slug>/ — works for nested
 *  routes too (e.g. roadmap/tasks/T3 still resolves to "roadmap"). */
export function currentSegment(pathname: string, slug: string): string {
  const prefix = `/projects/${slug}/`;
  if (!pathname.startsWith(prefix)) return "";
  return pathname.slice(prefix.length).split("/")[0] ?? "";
}

/**
 * A coarse, display-only "which stage is the user looking at" label (Phase
 * P-6) — used by BATONX Intelligence's context indicator, not by the Journey
 * rail itself (which stays precise via `buildSoftwareJourney`/
 * `buildDataJourney`). Deliberately doesn't disambiguate Tasks/Build vs.
 * Review the way the Journey does (that needs live Progress data just for a
 * cosmetic label) — "Roadmap" is an honest enough answer either way.
 */
export function currentStageLabel(pathname: string, project: Project, dict: Dictionary): string | null {
  const segment = currentSegment(pathname, project.slug);
  const isData = project.project_type === "data";
  const id = isData ? DATA_SEGMENT_TO_STAGE[segment] : SOFTWARE_SEGMENT_TO_STAGE[segment];
  return id ? localizedStageLabel(id, isData, dict) : null;
}

/**
 * Left column — the Project Journey. Project-type-aware: reads
 * `project.project_type` and renders the matching stage list, built by
 * `journey-model.ts` from real backend state (Progress for Software, once
 * the Roadmap is approved; Data Progress unconditionally for Data — it has
 * no approval gate). No AI, purely derived state.
 */
export function ProjectJourney({ project, pathname }: { project: Project; pathname: string }) {
  const { dict } = useLanguage();
  const segment = currentSegment(pathname, project.slug);
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

  const rawStages = isData
    ? buildDataJourney(
        project,
        DATA_SEGMENT_TO_STAGE[segment] ?? ("" as DataJourneyStageId),
        dataProgress.data ?? null,
      )
    : buildSoftwareJourney(
        project,
        currentSoftwareStage(pathname, project.slug, softwareProgress.data),
        softwareProgress.data ?? null,
      );
  const stages = localizeStages(rawStages, dict, isData);

  return (
    <nav aria-label="Project journey" className="flex h-full flex-col">
      <div className="border-b border-line px-4 py-3.5">
        <p className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-fg-subtle">
          {dict.language.label === "Language" ? "Journey" : dict.language.label /* placeholder guard */}
        </p>
      </div>
      <ol className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {stages.map((stage, i) => (
          <JourneyStage key={stage.id} stage={stage} index={i} isLast={i === stages.length - 1} statusLabel={dict.status[stage.status]} />
        ))}
      </ol>
    </nav>
  );
}
