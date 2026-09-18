"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRightIcon } from "@radix-ui/react-icons";

import { api, ApiRequestError } from "@/lib/api/client";
import type { DataProgressStage, DataStageStatus, Project } from "@/lib/api/types";
import { EmptyState } from "@/components/feedback/states";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

function statusMeta(
  status: DataStageStatus,
  dict: Dictionary,
): { label: string; tone: "neutral" | "accent" | "success" | "danger" | "warning" } {
  switch (status) {
    case "not_started":
      return { label: dict.dataProgress.statusNotStarted, tone: "neutral" };
    case "in_progress":
      return { label: dict.dataProgress.statusInProgress, tone: "accent" };
    case "needs_review":
      return { label: dict.dataProgress.statusNeedsReview, tone: "warning" };
    case "complete":
      return { label: dict.dataProgress.statusComplete, tone: "success" };
    case "blocked":
      return { label: dict.dataProgress.statusBlocked, tone: "danger" };
    case "skipped":
      return { label: dict.dataProgress.statusSkipped, tone: "neutral" };
  }
}

function Meter({ percent, dict }: { percent: number; dict: Dictionary }) {
  return (
    <div className="grid gap-2">
      <div className="flex items-baseline gap-2">
        <span className="text-4xl font-semibold tracking-tight text-fg">{percent}%</span>
        <span className="text-sm text-fg-muted">{dict.progress.complete}</span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-surface"
        role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}
      >
        <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

const STAGE_HREF: Record<DataProgressStage["id"], string> = {
  data_brief: "data-overview",
  sources: "data-sources",
  data_quality: "data-quality",
  transformation_plan: "data-build",
  metrics: "data-metrics",
  queries: "data-queries",
  analysis: "data-analysis",
  dashboard: "data-analysis",
  delivery_readiness: "data-readiness",
};

function StageRow({ slug, stage, dict }: { slug: string; stage: DataProgressStage; dict: Dictionary }) {
  const meta = statusMeta(stage.status, dict);
  const href = `/projects/${slug}/${STAGE_HREF[stage.id]}`;
  return (
    <Link
      href={href}
      className="grid gap-1.5 border-t border-line py-3 first:border-t-0 first:pt-0 transition-colors hover:bg-surface/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-md px-2 -mx-2"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-fg">{stage.name}</span>
        <Badge tone={meta.tone}>{meta.label}</Badge>
        <ArrowRightIcon className="ms-auto size-3.5 shrink-0 text-fg-subtle rtl:-scale-x-100" aria-hidden />
      </div>
      {stage.blockers.length > 0 && (
        <ul className="grid gap-0.5 text-xs leading-relaxed text-fg-muted">
          {stage.blockers.slice(0, 5).map((b, i) => (
            <li key={i}>&middot; {b}</li>
          ))}
        </ul>
      )}
    </Link>
  );
}

export function DataProgressView({ initialProject }: { initialProject: Project }) {
  const { dict } = useLanguage();
  const slug = initialProject.slug;
  const query = useQuery({
    queryKey: ["data-progress", slug],
    queryFn: () => api.getDataProgress(slug),
    retry: false,
  });

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.dataShared.dataProject}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{dict.dataProgress.title}</h1>
        <p className="text-sm text-fg-muted">{dict.journeyData.progress.label}</p>
        <p className="text-sm leading-relaxed text-fg-muted">
          {interpolate(dict.dataProgress.intro, { goal: initialProject.data_goal || "analytics" })}
        </p>
      </div>

      {query.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : query.isError ? (
        <EmptyState
          title={interpolate(dict.dataShared.couldntLoad, { thing: dict.dataProgress.title })}
          description={(query.error as ApiRequestError).message}
        />
      ) : (
        <div className="grid gap-8">
          <Meter percent={query.data.summary.completion_percentage} dict={dict} />

          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              { key: "stages_complete", label: dict.dataProgress.countComplete },
              { key: "stages_in_review", label: dict.dataProgress.countNeedsReview },
              { key: "stages_blocked", label: dict.dataProgress.countBlocked },
              { key: "stages_skipped", label: dict.dataProgress.countSkipped },
            ].map(({ key, label }) => (
              <div key={key} className="rounded-lg border border-line bg-surface/40 p-3 text-center">
                <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">{label}</dt>
                <dd className="mt-1 text-xl font-semibold text-fg">
                  {query.data.summary[key as keyof typeof query.data.summary]}
                </dd>
              </div>
            ))}
          </dl>

          {(query.data.summary.open_critical_quality > 0 ||
            query.data.summary.pending_proposals > 0 ||
            query.data.stale_context.length > 0) && (
            <div className="grid gap-2 rounded-lg border border-warning/25 bg-warning/10 p-4 text-sm">
              {query.data.summary.open_critical_quality > 0 && (
                <p className="text-warning">
                  {interpolate(dict.dataProgress.criticalQualityIssues, { n: String(query.data.summary.open_critical_quality) })}
                </p>
              )}
              {query.data.summary.pending_proposals > 0 && (
                <p className="text-warning">
                  {interpolate(dict.dataProgress.pendingProposals, { n: String(query.data.summary.pending_proposals) })}
                </p>
              )}
              {query.data.stale_context.length > 0 && (
                <p className="text-warning">
                  {interpolate(dict.dataProgress.staleNeedsReview, { items: query.data.stale_context.join(", ") })}
                </p>
              )}
            </div>
          )}

          {query.data.next_action && (
            <Link
              href={`/projects/${slug}/${query.data.next_action.href}`}
              className="flex items-center gap-3 rounded-xl border border-accent/40 bg-accent/[0.06] p-4 ring-1 ring-accent/20 transition-colors hover:bg-accent/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <div className="grid flex-1 gap-0.5">
                <span className="text-xs uppercase tracking-[0.06em] text-fg-subtle">{dict.dataProgress.nextAction}</span>
                <span className="text-sm font-medium text-fg">{query.data.next_action.label}</span>
              </div>
              <ArrowRightIcon className="size-4 text-accent rtl:-scale-x-100" aria-hidden />
            </Link>
          )}

          {query.data.deferred_future_stages.length > 0 && (
            <p className="text-xs text-fg-subtle">
              {interpolate(dict.dataProgress.deferredStages, { stages: query.data.deferred_future_stages.join(" and ") })}
            </p>
          )}

          <section className="grid gap-1">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
              {dict.dataProgress.stagesHeading}
            </h2>
            <div className="rounded-xl border border-line bg-surface/40 px-4">
              {query.data.stages.map((s) => (
                <StageRow key={s.id} slug={slug} stage={s} dict={dict} />
              ))}
            </div>
          </section>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface/60 px-4 py-3">
            <p className="text-sm text-fg-muted">
              {dict.dataProgress.footerNote}
            </p>
            <Link
              href={`/projects/${slug}/data-readiness`}
              className="group inline-flex shrink-0 items-center gap-1 rounded-sm text-sm font-medium text-accent hover:text-accent-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {dict.dataProgress.openDeliveryReadiness}
              <ArrowRightIcon
                className="size-3.5 transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5"
                aria-hidden
              />
            </Link>
          </div>
        </div>
      )}
    </>
  );
}
