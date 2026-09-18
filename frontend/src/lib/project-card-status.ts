import type { DataProgress, Project, ProjectProgress } from "@/lib/api/types";
import {
  buildDataJourney,
  buildSoftwareJourney,
  type DataJourneyStageId,
  type JourneyStageView,
  type SoftwareStageId,
} from "@/lib/journey-model";

export interface ProjectCardStatus {
  /** The stage the project is actually at right now (English fallback —
   *  Phase P-7's card UI re-localizes this via `stageId` + the dictionary,
   *  see `project-card.tsx`; kept here too so any caller that hasn't been
   *  updated still renders correctly). */
  stageLabel: string;
  /** Stable id for the frontier stage, for localized display. */
  stageId: string;
  status: JourneyStageView["status"];
  /** Where "resume" should take the user — the real next-action route, not
   *  a generic project root. */
  href: string;
  completionPercentage: number | null;
  stale: boolean;
}

/**
 * Project cards (Phase P-3) reuse the exact same `buildSoftwareJourney` /
 * `buildDataJourney` the live Journey rail uses — never a second,
 * card-specific computation of stage/status/routing. "Current stage" here is
 * simply the first stage that isn't done yet (or the last one, if every
 * stage is) — the identical frontier `NextAction` already surfaces inside a
 * single project's own workspace.
 */
function frontierOf(stages: JourneyStageView[]): JourneyStageView {
  // "progress" (Data) is a cross-cutting overview promoted into the Journey
  // rail for visibility — never a candidate for "resume here": its own
  // status tracks the whole project's aggregate completion, independent of
  // stage order, so including it here would make almost every not-yet-100%
  // project incorrectly resume at the Progress overview instead of its real
  // next actionable stage.
  const candidates = stages.filter((s) => s.id !== "progress");
  return (
    candidates.find((s) => s.status !== "completed" && s.status !== "skipped") ??
    candidates[candidates.length - 1]
  );
}

export function softwareCardStatus(
  project: Project,
  progress: ProjectProgress | null,
): ProjectCardStatus {
  const stages = buildSoftwareJourney(project, "" as SoftwareStageId, progress);
  const frontier = frontierOf(stages);
  return {
    stageLabel: frontier.label,
    stageId: frontier.id,
    status: frontier.status,
    href: frontier.href,
    completionPercentage: progress?.summary.completion_percentage ?? null,
    stale: Object.values(project.downstream_stale ?? {}).some(Boolean),
  };
}

export function dataCardStatus(
  project: Project,
  progress: DataProgress | null,
): ProjectCardStatus {
  const stages = buildDataJourney(project, "" as DataJourneyStageId, progress);
  const frontier = frontierOf(stages);
  return {
    stageLabel: frontier.label,
    stageId: frontier.id,
    status: frontier.status,
    href: frontier.href,
    completionPercentage: progress?.summary.completion_percentage ?? null,
    stale: (progress?.stale_context.length ?? 0) > 0,
  };
}
