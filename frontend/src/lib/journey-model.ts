import type {
  DataProgress,
  DataStageId,
  Project,
  ProjectProgress,
} from "@/lib/api/types";

/**
 * Unified Journey status vocabulary (Phase P-1) — the same seven states for
 * both Software and Data, so the two workflows read as one product. Not a
 * cosmetic relabeling: "stale" and "blocked" are now visually distinct from
 * "needs review", which the previous five-state model (done/current/
 * available/locked/skipped) collapsed together.
 */
export type WorkflowStatus =
  | "completed"
  | "in_progress"
  | "needs_review"
  | "stale"
  | "blocked"
  | "upcoming"
  | "skipped";

export interface JourneyStageView {
  id: string;
  label: string;
  /** One line: what this stage is for. Shown on the rail as a tooltip/expansion. */
  purpose: string;
  status: WorkflowStatus;
  /** This is the page currently open — independent of `status` (a stage can
   *  be current AND, say, needs_review at the same time). */
  current: boolean;
  /** Reachable at all — an inert/"upcoming" stage the user can't yet open. */
  reachable: boolean;
  href: string;
}

export type SoftwareStageId =
  | "discovery"
  | "blueprint"
  | "business_logic"
  | "architecture"
  | "roadmap"
  | "tasks_build"
  | "review"
  | "progress"
  | "ship";

/**
 * "Tasks / Build" and "Review" are real, distinct phases of the same Roadmap
 * lifecycle, not new backend stages — they're derived from the existing Task
 * status machine (``not_started -> in_progress -> ready_for_review ->
 * completed``, see backend ``projects/roadmap.py``) and the existing
 * ``ProjectProgress`` buckets, and both route into the existing Task
 * Workspace (``/roadmap/tasks/:taskId``, hosting the real Build Prompt and
 * Review Prompt for that task) — no new page, no invented backend concept.
 */
export const SOFTWARE_STAGES: { id: SoftwareStageId; label: string; segment: string; purpose: string }[] = [
  { id: "discovery", label: "Discovery", segment: "discovery", purpose: "Answer a few questions that shape everything after." },
  { id: "blueprint", label: "Blueprint", segment: "blueprint", purpose: "The product definition — scope, roles, requirements." },
  { id: "business_logic", label: "Business Logic", segment: "business-logic", purpose: "Explicit rules, permissions, and state transitions." },
  { id: "architecture", label: "Architecture", segment: "architecture", purpose: "The technical design an agent will build against." },
  { id: "roadmap", label: "Roadmap", segment: "roadmap", purpose: "Tasks, dependencies, and the plan you approve." },
  { id: "tasks_build", label: "Tasks / Build", segment: "roadmap", purpose: "Executing tasks — each with a generated Build Prompt." },
  { id: "review", label: "Review", segment: "roadmap", purpose: "Tasks awaiting your review, each with a Review Prompt." },
  { id: "progress", label: "Progress", segment: "progress", purpose: "What's done, in review, or blocked, right now." },
  { id: "ship", label: "Delivery Readiness", segment: "ship", purpose: "Automatic checks plus your own manual confirmations." },
];

function businessLogicSkipped(project: Project): boolean {
  return !project.business_logic?.content && !!project.architecture?.content;
}

function isStaleSoftware(project: Project, id: SoftwareStageId): boolean {
  switch (id) {
    case "business_logic":
      return !!project.downstream_stale?.business_logic;
    case "architecture":
      return !!project.downstream_stale?.architecture;
    case "roadmap":
      return !!project.downstream_stale?.roadmap;
    default:
      return false;
  }
}

export function buildSoftwareJourney(
  project: Project,
  currentId: SoftwareStageId,
  progress: ProjectProgress | null,
): JourneyStageView[] {
  const roadmapDone = !!project.roadmap_approved_at;

  function statusFor(id: SoftwareStageId): { status: WorkflowStatus; reachable: boolean } {
    if (id === "business_logic" && businessLogicSkipped(project)) {
      return { status: "skipped", reachable: false };
    }
    if (isStaleSoftware(project, id)) return { status: "stale", reachable: true };

    switch (id) {
      case "discovery":
        return project.discovery?.answered_at
          ? { status: "completed", reachable: true }
          : project.discovery?.questions?.length
            ? { status: "in_progress", reachable: true }
            : { status: "upcoming", reachable: true };
      case "blueprint":
        if (project.blueprint_approved_at) return { status: "completed", reachable: true };
        if (!project.discovery?.answered_at) return { status: "upcoming", reachable: false };
        return project.blueprint?.content
          ? { status: "needs_review", reachable: true }
          : { status: "upcoming", reachable: true };
      case "business_logic": {
        const reachable = !!project.blueprint_approved_at;
        if (project.business_logic_approved_at) return { status: "completed", reachable };
        if (!reachable) return { status: "upcoming", reachable };
        return project.business_logic?.content
          ? { status: "needs_review", reachable }
          : { status: "upcoming", reachable };
      }
      case "architecture": {
        const reachable =
          !!project.blueprint_approved_at &&
          (!!project.business_logic_approved_at || businessLogicSkipped(project));
        if (project.architecture_approved_at) return { status: "completed", reachable };
        if (!reachable) return { status: "upcoming", reachable };
        return project.architecture?.content
          ? { status: "needs_review", reachable }
          : { status: "upcoming", reachable };
      }
      case "roadmap": {
        // Plan approval only — once approved, this stage's own job is done;
        // task-level blocking is a Tasks/Build concern, not a Roadmap one.
        const reachable = !!project.architecture_approved_at;
        if (!reachable) return { status: "upcoming", reachable };
        if (roadmapDone) return { status: "completed", reachable };
        return project.roadmap?.content
          ? { status: "needs_review", reachable }
          : { status: "upcoming", reachable };
      }
      case "tasks_build": {
        // Execution: is anything actively being built, still to start, stuck
        // on unmet dependencies, or has every task at least reached review?
        // All from the real ``ProjectProgress`` bucket counts — no guessing.
        if (!roadmapDone) return { status: "upcoming", reachable: false };
        if (!progress) return { status: "in_progress", reachable: true };
        const { not_started, in_progress: buildingCount, blocked } = progress.summary;
        if (buildingCount > 0) return { status: "in_progress", reachable: true };
        // "blocked" tasks are a separate bucket from "not_started" (a
        // not-yet-started task with an unmet dependency is counted as
        // blocked, not not_started — see backend `_bucket_counts`), so both
        // must be zero before anything can call building "done".
        if (not_started === 0 && blocked === 0) return { status: "completed", reachable: true };
        // A freely-startable task (not_started, deps already met) means
        // there IS something actionable right now — this must be checked
        // before "blocked", or a project with one startable task and many
        // legitimately-blocked-behind-it tasks would wrongly read as
        // "Blocked" instead of "in progress" (confirmed against live data:
        // `next_task` picks exactly this not_started task as actionable).
        if (not_started > 0) return { status: "in_progress", reachable: true };
        if (blocked > 0) return { status: "blocked", reachable: true };
        return { status: "in_progress", reachable: true };
      }
      case "review": {
        // Needs a human right now iff a real task sits in ``ready_for_review``
        // — read directly from ``progress.ready_for_review_tasks``.
        if (!roadmapDone) return { status: "upcoming", reachable: false };
        if (!progress) return { status: "in_progress", reachable: true };
        if (progress.ready_for_review_tasks.length > 0) return { status: "needs_review", reachable: true };
        if (progress.summary.completion_percentage === 100) return { status: "completed", reachable: true };
        return { status: "in_progress", reachable: true };
      }
      case "progress": {
        // Same priority order as "tasks_build" and for the same reason: a
        // blocked task elsewhere must not read as "the project is blocked"
        // while something else is actively being built or freely startable.
        if (!roadmapDone) return { status: "upcoming", reachable: false };
        if (!progress) return { status: "in_progress", reachable: true };
        const { not_started, in_progress: buildingCount, blocked, completion_percentage } = progress.summary;
        if (completion_percentage === 100) return { status: "completed", reachable: true };
        if (buildingCount > 0 || not_started > 0) return { status: "in_progress", reachable: true };
        if (blocked > 0) return { status: "blocked", reachable: true };
        return { status: "in_progress", reachable: true };
      }
      case "ship":
        if (!roadmapDone) return { status: "upcoming", reachable: false };
        return project.stage === "ship"
          ? { status: "completed", reachable: true }
          : { status: "in_progress", reachable: true };
    }
  }

  // Tasks/Build and Review both route into the real Task Workspace for a
  // specific task when one is known (the task actually being built, or the
  // task actually awaiting review) — falling back to the Roadmap's own task
  // list when no single task is the obvious target yet. No new route.
  // `next_task` falls back to a ready_for_review task as its own last
  // resort (see backend `compute_project_progress`) when nothing is
  // actually buildable — that case belongs to Review, not Build, so it's
  // excluded here rather than pointing both stages at the same task.
  const buildHref =
    progress?.next_task && progress.next_task.status !== "ready_for_review"
      ? `/projects/${project.slug}/roadmap/tasks/${progress.next_task.id}`
      : `/projects/${project.slug}/roadmap`;
  const reviewHref = progress?.ready_for_review_tasks.length
    ? `/projects/${project.slug}/roadmap/tasks/${progress.ready_for_review_tasks[0].id}`
    : `/projects/${project.slug}/roadmap`;

  return SOFTWARE_STAGES.map((stage) => {
    const { status, reachable } = statusFor(stage.id);
    const href =
      stage.id === "tasks_build"
        ? buildHref
        : stage.id === "review"
          ? reviewHref
          : `/projects/${project.slug}/${stage.segment}`;
    return {
      id: stage.id,
      label: stage.label,
      purpose: stage.purpose,
      status,
      current: stage.id === currentId,
      reachable,
      href,
    };
  });
}

/**
 * The user-facing Data Journey (Phase P-3 correction) is nine stages:
 * Brief -> Sources -> Quality -> Transformation -> Metrics -> Queries ->
 * Analysis -> Progress -> Delivery. This is deliberately NOT the same list
 * as the backend's own `DataStageId` (which has "dashboard", not
 * "progress") — Dashboard is a real, unremoved artifact/capability, still
 * reachable at the exact same `data-analysis` route as Analysis (its own
 * status is folded into the Analysis node's, see `mergedAnalysisStatus`
 * below), and Progress is promoted from a cross-cutting overview into a
 * first-class Journey stage pointing at the existing `/data-progress` page
 * — no new backend stage, no new route, no Core change.
 */
export type DataJourneyStageId = Exclude<DataStageId, "dashboard"> | "progress";

export const DATA_STAGE_META: Record<DataJourneyStageId, { label: string; segment: string; purpose: string }> = {
  data_brief: { label: "Brief", segment: "data-overview", purpose: "The business goal and decision this project serves." },
  sources: { label: "Sources", segment: "data-sources", purpose: "Upload, profile, and interpret your datasets." },
  data_quality: { label: "Quality", segment: "data-quality", purpose: "Observed issues and the rules you approve for them." },
  transformation_plan: { label: "Transformation", segment: "data-build", purpose: "The cleaning steps compiled to deterministic SQL." },
  metrics: { label: "Metrics", segment: "data-metrics", purpose: "KPI definitions, validated against real data." },
  queries: { label: "Queries", segment: "data-queries", purpose: "Business questions, reviewed SQL, bounded results." },
  analysis: { label: "Analysis", segment: "data-analysis", purpose: "Deterministic findings and the Dashboard Blueprint handed off for implementation." },
  progress: { label: "Progress", segment: "data-progress", purpose: "Where the project stands — complete, blocked, and what's next." },
  delivery_readiness: { label: "Delivery", segment: "data-readiness", purpose: "Automatic checks plus your own manual confirmations." },
};

const DATA_STATUS_MAP: Record<string, WorkflowStatus> = {
  not_started: "upcoming",
  in_progress: "in_progress",
  needs_review: "needs_review",
  complete: "completed",
  blocked: "blocked",
  skipped: "skipped",
};

/**
 * Structured stale detection — reads ``DataProgress.stale_context`` (the
 * same authoritative, ID-based list ``compute_data_progress`` returns; see
 * backend ``projects/data/progress.py`` / ``projects/data/stale.py``), never
 * blocker prose. ``stale_context`` mixes four kinds of entries by
 * construction: the three Project-level artifact names Data reuses from
 * ``Project.downstream_stale`` ("data_quality" / "transformation_plan" /
 * "dashboard_blueprint"), ``"dataset:<id>"`` for a stale source
 * interpretation, and bare per-row business ids for stale Metrics / Queries /
 * Analysis Plans. Those business ids carry a deterministic, schema-enforced
 * prefix (``KPI-`` / ``Q-`` / ``AN-`` — see ``projects/models.py``), so
 * matching on it is a structural check against a guaranteed id format, not
 * text-parsing free-form prose.
 */
function isDataStageStale(stageId: DataStageId, staleContext: string[]): boolean {
  switch (stageId) {
    case "sources":
      return staleContext.some((id) => id.startsWith("dataset:"));
    case "data_quality":
      return staleContext.includes("data_quality");
    case "transformation_plan":
      return staleContext.includes("transformation_plan");
    case "metrics":
      return staleContext.some((id) => id.startsWith("KPI-"));
    case "queries":
      return staleContext.some((id) => id.startsWith("Q-"));
    case "analysis":
      return staleContext.some((id) => id.startsWith("AN-"));
    case "dashboard":
      return staleContext.includes("dashboard_blueprint");
    default:
      // data_brief and delivery_readiness are never independently staleable.
      return false;
  }
}

function refineDataStatus(
  status: WorkflowStatus,
  stageId: DataStageId,
  staleContext: string[],
): WorkflowStatus {
  if (status === "needs_review" && isDataStageStale(stageId, staleContext)) {
    return "stale";
  }
  return status;
}

/**
 * Analysis and Dashboard are two independently-tracked backend stages that
 * share one user-facing Journey node (and one route, `data-analysis`) — so
 * the node can't read "done" while either half still has outstanding work.
 * Purely a frontend presentation merge of two already-computed statuses;
 * no new backend logic. `b` (Dashboard) being "skipped" (a data_goal that
 * never requires it) means the merge is a no-op — just `a`.
 */
function combineWorkflowStatus(a: WorkflowStatus, b: WorkflowStatus): WorkflowStatus {
  if (b === "skipped") return a;
  if (a === "blocked" || b === "blocked") return "blocked";
  if (a === "stale" || b === "stale") return "stale";
  if (a === "completed" && b === "completed") return "completed";
  if (a === "in_progress" || b === "in_progress") return "in_progress";
  if (a === "upcoming" && b === "upcoming") return "upcoming";
  return "needs_review";
}

export function buildDataJourney(
  project: Project,
  currentId: DataJourneyStageId,
  progress: DataProgress | null,
): JourneyStageView[] {
  const ids = Object.keys(DATA_STAGE_META) as DataJourneyStageId[];

  if (!progress) {
    // Honest neutral state before the first fetch resolves — never guessed.
    return ids.map((id) => {
      const meta = DATA_STAGE_META[id];
      return {
        id,
        label: meta.label,
        purpose: meta.purpose,
        status: "upcoming" as WorkflowStatus,
        current: id === currentId,
        reachable: true,
        href: `/projects/${project.slug}/${meta.segment}`,
      };
    });
  }

  // Every real backend stage's own status, refined for staleness — includes
  // "dashboard", which has no Journey node of its own (see DATA_STAGE_META).
  const byBackendId: Partial<Record<DataStageId, WorkflowStatus>> = {};
  for (const s of progress.stages) {
    byBackendId[s.id] = refineDataStatus(DATA_STATUS_MAP[s.status] ?? "upcoming", s.id, progress.stale_context);
  }

  return ids.map((id) => {
    const meta = DATA_STAGE_META[id];
    let status: WorkflowStatus;
    if (id === "progress") {
      // Cross-cutting overview, not a sequential gate — its own status
      // reflects the whole project's aggregate state (same priority order
      // as Software's own "Progress" node), not a single backend stage.
      const { stages_blocked, completion_percentage } = progress.summary;
      status = stages_blocked > 0 ? "blocked" : completion_percentage === 100 ? "completed" : "in_progress";
    } else if (id === "analysis") {
      status = combineWorkflowStatus(
        byBackendId.analysis ?? "upcoming",
        byBackendId.dashboard ?? "upcoming",
      );
    } else {
      status = byBackendId[id as DataStageId] ?? "upcoming";
    }
    return {
      id,
      label: meta.label,
      purpose: meta.purpose,
      status,
      current: id === currentId,
      // Progress is always reachable — it's a permanent overview, never
      // gated behind an earlier stage the way the others are.
      reachable: id === "progress" ? true : status !== "skipped",
      href: `/projects/${project.slug}/${meta.segment}`,
    };
  });
}
