"use client";

import Link from "next/link";
import { ArrowLeftIcon, ArrowRightIcon } from "@radix-ui/react-icons";
import { useQuery } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type {
  PhaseProgress,
  ProgressSummary,
  ProgressTaskBrief,
} from "@/lib/api/types";
import { EmptyState, ErrorState } from "@/components/feedback/states";
import { Badge } from "@/components/ui/badge";
import { buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

function countFields(dict: Dictionary): { key: keyof ProgressSummary; label: string }[] {
  return [
    { key: "not_started", label: dict.progress.countNotStarted },
    { key: "in_progress", label: dict.progress.countInProgress },
    { key: "ready_for_review", label: dict.progress.countReadyForReview },
    { key: "completed", label: dict.progress.countCompleted },
    { key: "blocked", label: dict.progress.countBlocked },
  ];
}

function Meter({ percent, dict }: { percent: number; dict: Dictionary }) {
  return (
    <div className="grid gap-2">
      <div className="flex items-baseline gap-2">
        <span className="text-4xl font-semibold tracking-tight text-fg">
          {percent}%
        </span>
        <span className="text-sm text-fg-muted">{dict.progress.complete}</span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-surface"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

function CountGrid({ summary, dict }: { summary: ProgressSummary; dict: Dictionary }) {
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      {countFields(dict).map(({ key, label }) => (
        <div
          key={key}
          className="rounded-lg border border-line bg-surface/40 p-3 text-center"
        >
          <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
            {label}
          </dt>
          <dd className="mt-1 text-xl font-semibold text-fg">
            {summary[key] as number}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function PhaseRow({ phase, dict }: { phase: PhaseProgress; dict: Dictionary }) {
  return (
    <div className="grid gap-2 border-t border-line py-4 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-fg">
          <span className="font-mono text-xs text-fg-subtle">{phase.phase_id}</span>{" "}
          {phase.title}
        </p>
        <span className="text-xs text-fg-muted">
          {interpolate(dict.progress.tasksComplete, {
            completed: String(phase.completed),
            total: String(phase.total_tasks),
            percent: String(phase.completion_percentage),
          })}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${phase.completion_percentage}%` }}
        />
      </div>
      <div className="flex flex-wrap gap-1.5 text-[11px] text-fg-subtle">
        {phase.in_progress > 0 && <span>{interpolate(dict.progress.inProgressCount, { n: String(phase.in_progress) })}</span>}
        {phase.ready_for_review > 0 && (
          <span>&middot; {interpolate(dict.progress.readyForReviewCount, { n: String(phase.ready_for_review) })}</span>
        )}
        {phase.blocked > 0 && <span>&middot; {interpolate(dict.progress.blockedCount, { n: String(phase.blocked) })}</span>}
        {phase.not_started > 0 && <span>&middot; {interpolate(dict.progress.notStartedCount, { n: String(phase.not_started) })}</span>}
      </div>
    </div>
  );
}

function TaskLinkList({
  slug,
  tasks,
  emptyLabel,
  renderMeta,
}: {
  slug: string;
  tasks: ProgressTaskBrief[];
  emptyLabel: string;
  renderMeta?: (task: ProgressTaskBrief) => React.ReactNode;
}) {
  if (tasks.length === 0) {
    return <p className="text-sm text-fg-subtle">{emptyLabel}</p>;
  }
  return (
    <ul className="grid gap-1.5">
      {tasks.map((t) => (
        <li key={t.id}>
          <Link
            href={`/projects/${slug}/roadmap/tasks/${t.id}`}
            className="flex items-center gap-2 rounded-md border border-line bg-surface/40 px-3 py-2 text-sm text-fg-muted transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <span className="font-mono text-xs text-fg-subtle">{t.id}</span>
            <span className="flex-1 truncate">{t.title}</span>
            {renderMeta?.(t)}
            <ArrowRightIcon className="size-3.5 shrink-0 rtl:-scale-x-100" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-3">
      <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
        {title}
        {typeof count === "number" && (
          <span className="ms-2 text-fg-muted">{count}</span>
        )}
      </h2>
      {children}
    </section>
  );
}

export function ProgressView({ slug }: { slug: string }) {
  const { dict } = useLanguage();
  const projectQuery = useQuery({
    queryKey: ["project", slug],
    queryFn: () => api.getProject(slug),
    retry: false,
  });
  const progressQuery = useQuery({
    queryKey: ["progress", slug],
    queryFn: () => api.getProgress(slug),
    retry: false,
  });

  if (projectQuery.isPending || progressQuery.isPending) {
    return (
      <>
        <div className="grid gap-4">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-9 w-40" />
          <Skeleton className="h-24 w-full" />
        </div>
      </>
    );
  }

  if (projectQuery.isError) {
    const error = projectQuery.error as ApiRequestError;
    if (error.code === "project_not_found") {
      return (
        <EmptyState
          title={dict.common.projectNotFoundTitle}
          description={dict.common.projectNotFoundBody}
        >
          <Link href="/projects/new" className={buttonClasses("solid", "md")}>
            {dict.softwareShared.projectNotFoundLinkLabel}
          </Link>
        </EmptyState>
      );
    }
    return (
      <ErrorState
        title={dict.softwareShared.couldntLoadProject}
        description={error.message}
        retryable={error.retryable}
        retrying={projectQuery.isRefetching}
        onRetry={() => projectQuery.refetch()}
      />
    );
  }

  const project = projectQuery.data;
  const backToRoadmap = (
    <Link
      href={`/projects/${slug}/roadmap`}
      className="mb-6 inline-flex items-center gap-1.5 text-sm text-fg-muted underline-offset-4 hover:text-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <ArrowLeftIcon className="size-3.5 rtl:-scale-x-100" aria-hidden />
      {dict.journeySoftware.roadmap.label}
    </Link>
  );

  if (progressQuery.isError) {
    const error = progressQuery.error as ApiRequestError;
    if (error.code === "roadmap_not_approved") {
      return (
        <>
          {backToRoadmap}
          <EmptyState
            title={dict.progress.needsRoadmapTitle}
            description={dict.progress.needsRoadmapBody}
          >
            <Link
              href={`/projects/${slug}/roadmap`}
              className={buttonClasses("solid", "md")}
            >
              {dict.progress.goToRoadmap}
            </Link>
          </EmptyState>
        </>
      );
    }
    return (
      <ErrorState
        title={dict.progress.couldntLoad}
        description={error.message}
        retryable={error.retryable}
        retrying={progressQuery.isRefetching}
        onRetry={() => progressQuery.refetch()}
      />
    );
  }

  const progress = progressQuery.data;
  const { summary } = progress;

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.journeySoftware.progress.label}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {dict.progress.title}
        </h1>
        <p className="text-sm text-fg-muted">
          {dict.journeySoftware.progress.purpose}
        </p>
        <p className="rounded-md border border-line bg-surface/60 px-3.5 py-2.5 text-sm leading-relaxed text-fg-muted">
          {project.original_idea}
        </p>
      </div>

      {progress.stale_context.length > 0 && (
        <div className="mb-6 grid gap-1 rounded-lg border border-warning/25 bg-warning/10 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="warning">{dict.progress.contextReviewRequired}</Badge>
            <span className="text-xs text-warning/90">
              {progress.roadmap_stale
                ? dict.progress.roadmapStaleMsg
                : dict.progress.upstreamChangedMsg}
            </span>
          </div>
          <p className="text-xs text-warning/90">
            {interpolate(dict.progress.reconcile, { items: progress.stale_context.join(", ") })}
          </p>
        </div>
      )}

      <div className="grid gap-8">
        <Meter percent={summary.completion_percentage} dict={dict} />
        <CountGrid summary={summary} dict={dict} />

        <Section title={dict.progress.nextTaskHeading}>
          {progress.next_task ? (
            <Link
              href={`/projects/${slug}/roadmap/tasks/${progress.next_task.id}`}
              className="flex items-center gap-3 rounded-xl border border-accent/40 bg-accent/[0.06] p-4 ring-1 ring-accent/20 transition-colors hover:bg-accent/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <div className="grid flex-1 gap-0.5">
                <span className="text-sm font-medium text-fg">
                  <span className="font-mono text-xs text-fg-subtle">
                    {progress.next_task.id}
                  </span>{" "}
                  {progress.next_task.title}
                </span>
                <span className="text-xs text-fg-muted">
                  {progress.next_task.phase_title} &middot;{" "}
                  {dict.taskStatus[progress.next_task.status]}
                </span>
              </div>
              <ArrowRightIcon className="size-4 text-accent rtl:-scale-x-100" aria-hidden />
            </Link>
          ) : (
            <p className="text-sm text-fg-subtle">
              {dict.progress.nextTaskEmpty}
            </p>
          )}
        </Section>

        <Section title={dict.progress.phasesHeading}>
          <div className="rounded-xl border border-line bg-surface/40 p-5">
            {progress.phases.map((phase) => (
              <PhaseRow key={phase.phase_id} phase={phase} dict={dict} />
            ))}
          </div>
        </Section>

        <Section title={dict.progress.blockedHeading} count={progress.blocked_tasks.length}>
          <TaskLinkList
            slug={slug}
            tasks={progress.blocked_tasks}
            emptyLabel={dict.progress.noBlockedTasks}
            renderMeta={(t) => {
              const deps =
                progress.blocked_tasks.find((b) => b.id === t.id)
                  ?.unfinished_dependencies ?? [];
              return deps.length > 0 ? (
                <span className="shrink-0 text-[11px] text-fg-subtle">
                  {interpolate(dict.progress.waitingOn, { deps: deps.join(", ") })}
                </span>
              ) : null;
            }}
          />
        </Section>

        <Section
          title={dict.progress.readyForReviewHeading}
          count={progress.ready_for_review_tasks.length}
        >
          <TaskLinkList
            slug={slug}
            tasks={progress.ready_for_review_tasks}
            emptyLabel={dict.progress.noReadyForReview}
          />
        </Section>

        {progress.completed_tasks.length > 0 && (
          <details className="grid gap-3">
            <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle marker:content-none">
              {dict.progress.completedHeading}
              <span className="ms-2 text-fg-muted">{progress.completed_tasks.length}</span>
            </summary>
            <TaskLinkList
              slug={slug}
              tasks={progress.completed_tasks}
              emptyLabel={dict.progress.noCompletedYet}
            />
          </details>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface/60 px-4 py-3">
          <p className="text-sm text-fg-muted">
            {summary.completion_percentage === 100 && summary.blocked === 0
              ? dict.progress.allComplete
              : dict.progress.seeGapsBeforeShip}
          </p>
          <Link
            href={`/projects/${slug}/ship`}
            className="group inline-flex shrink-0 items-center gap-1 rounded-sm text-sm font-medium text-accent hover:text-accent-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {dict.progress.openDeliveryReadiness}
            <ArrowRightIcon
              className="size-3.5 transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5"
              aria-hidden
            />
          </Link>
        </div>
      </div>
    </>
  );
}
