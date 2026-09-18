"use client";

import { useState } from "react";
import Link from "next/link";
import {
  CheckCircledIcon,
  CircleIcon,
  CrossCircledIcon,
  ExclamationTriangleIcon,
} from "@radix-ui/react-icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type {
  AutomaticCheck,
  ManualCheck,
  ShipCheckStatus,
  ShipReadiness,
} from "@/lib/api/types";
import { EmptyState, ErrorState } from "@/components/feedback/states";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { formatDateTime } from "@/lib/format";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

function readinessMeta(
  status: ShipReadiness,
  dict: Dictionary,
): { label: string; tone: "danger" | "warning" | "success" } {
  switch (status) {
    case "NOT_READY":
      return { label: dict.ship.readinessNotReady, tone: "danger" };
    case "READY_WITH_MANUAL_CHECKS":
      return { label: dict.ship.readinessManualPending, tone: "warning" };
    case "READY_TO_SHIP":
      return { label: dict.ship.readinessReady, tone: "success" };
  }
}

function checkMeta(
  status: ShipCheckStatus,
  dict: Dictionary,
): { label: string; tone: "success" | "danger" | "warning"; Icon: typeof CheckCircledIcon } {
  switch (status) {
    case "pass":
      return { label: dict.ship.checkPass, tone: "success", Icon: CheckCircledIcon };
    case "fail":
      return { label: dict.ship.checkFail, tone: "danger", Icon: CrossCircledIcon };
    case "warning":
      return { label: dict.ship.checkWarning, tone: "warning", Icon: ExclamationTriangleIcon };
  }
}

function groupByCategory<T extends { category: string }>(items: T[]) {
  const out: Record<string, T[]> = {};
  for (const item of items) (out[item.category] ??= []).push(item);
  return Object.entries(out);
}

function AutomaticRow({ check, dict }: { check: AutomaticCheck; dict: Dictionary }) {
  const meta = checkMeta(check.status, dict);
  return (
    <div className="grid gap-1 border-t border-line py-3 first:border-t-0 first:pt-0">
      <div className="flex items-start gap-2">
        <meta.Icon
          className={
            "mt-0.5 size-4 shrink-0 " +
            (meta.tone === "success"
              ? "text-accent"
              : meta.tone === "danger"
                ? "text-danger"
                : "text-warning")
          }
          aria-hidden
        />
        <div className="grid flex-1 gap-0.5">
          <p className="text-sm font-medium text-fg">
            {check.title}
            {!check.required && (
              <span className="ms-2 text-[11px] font-normal text-fg-subtle">
                {dict.ship.advisory}
              </span>
            )}
          </p>
          <p className="text-xs leading-relaxed text-fg-muted">{check.evidence}</p>
          {check.status !== "pass" && check.action && (
            <p className="text-xs leading-relaxed text-fg-subtle">
              → {check.action}
            </p>
          )}
        </div>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>
    </div>
  );
}

function ManualRow({
  check,
  pending,
  onToggle,
  dict,
}: {
  check: ManualCheck;
  pending: boolean;
  onToggle: (confirmed: boolean) => void;
  dict: Dictionary;
}) {
  return (
    <div className="grid gap-2 border-t border-line py-3 first:border-t-0 first:pt-0">
      <div className="flex items-start gap-2">
        {check.confirmed ? (
          <CheckCircledIcon className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
        ) : (
          <CircleIcon className="mt-0.5 size-4 shrink-0 text-fg-subtle" aria-hidden />
        )}
        <div className="grid flex-1 gap-0.5">
          <p className="text-sm font-medium text-fg">{check.title}</p>
          <p className="text-xs leading-relaxed text-fg-muted">
            {check.why_manual}
          </p>
          {check.confirmed && check.confirmed_at && (
            <p className="text-[11px] text-fg-subtle">
              {interpolate(dict.ship.confirmedAt, { when: formatDateTime(check.confirmed_at) })}
              {check.note ? ` — ${check.note}` : ""}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {pending && <Spinner className="size-4 text-fg-subtle" />}
          {check.confirmed ? (
            <Button
              variant="ghost"
              size="sm"
              disabled={pending}
              onClick={() => onToggle(false)}
            >
              {dict.ship.undo}
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              disabled={pending}
              onClick={() => onToggle(true)}
            >
              {dict.ship.confirm}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function ShipChecklistView({ slug }: { slug: string }) {
  const { dict } = useLanguage();
  const qc = useQueryClient();
  const [pendingItem, setPendingItem] = useState<string | null>(null);

  const projectQuery = useQuery({
    queryKey: ["project", slug],
    queryFn: () => api.getProject(slug),
    retry: false,
  });
  const checklistQuery = useQuery({
    queryKey: ["ship-checklist", slug],
    queryFn: () => api.getShipChecklist(slug),
    retry: false,
  });

  const confirm = useMutation({
    mutationFn: (vars: { itemId: string; confirmed: boolean }) =>
      api.confirmShipItem(slug, vars.itemId, vars.confirmed),
    onMutate: (vars) => setPendingItem(vars.itemId),
    onSuccess: (data) => {
      qc.setQueryData(["ship-checklist", slug], data);
      qc.invalidateQueries({ queryKey: ["project", slug] });
    },
    onSettled: () => setPendingItem(null),
  });

  if (projectQuery.isPending || checklistQuery.isPending) {
    return (
      <>
        <div className="grid gap-4">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-9 w-52" />
          <Skeleton className="h-28 w-full" />
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

  if (checklistQuery.isError) {
    const error = checklistQuery.error as ApiRequestError;
    return (
      <ErrorState
        title={dict.ship.couldntLoad}
        description={error.message}
        retryable={error.retryable}
        retrying={checklistQuery.isRefetching}
        onRetry={() => checklistQuery.refetch()}
      />
    );
  }

  const project = projectQuery.data;
  const checklist = checklistQuery.data;
  const readiness = readinessMeta(checklist.overall_status, dict);
  const confirmError = confirm.error as ApiRequestError | null;

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.ship.stepLabel}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {dict.ship.title}
        </h1>
        <p className="text-sm text-fg-muted">
          {dict.journeySoftware.ship.purpose}
        </p>
        <p className="rounded-md border border-line bg-surface/60 px-3.5 py-2.5 text-sm leading-relaxed text-fg-muted">
          {project.original_idea}
        </p>
      </div>

      <div className="grid gap-3 rounded-xl border border-line bg-surface/40 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={readiness.tone}>{readiness.label}</Badge>
          <span className="text-sm text-fg-muted">
            {interpolate(dict.ship.percentTasksComplete, { percent: String(checklist.progress.completion_percentage) })}
          </span>
        </div>
        <p className="text-sm leading-relaxed text-fg-muted">
          {checklist.readiness_summary}
        </p>
      </div>

      {checklist.stale_context.length > 0 && (
        <div className="mt-4 grid gap-1 rounded-lg border border-warning/25 bg-warning/10 p-4">
          <Badge tone="warning">{dict.ship.contextReviewRequired}</Badge>
          <p className="text-xs text-warning/90">
            {interpolate(dict.ship.staleFlagged, { items: checklist.stale_context.join(", ") })}
          </p>
        </div>
      )}

      {checklist.blockers.length > 0 && (
        <section className="mt-6 grid gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-danger">
            {interpolate(dict.ship.blockersHeading, { n: String(checklist.blockers.length) })}
          </h2>
          <ul className="grid gap-1.5">
            {checklist.blockers.map((b) => (
              <li
                key={b.id}
                className="rounded-md border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger"
              >
                <span className="font-mono text-xs">{b.id}</span> {b.title}
                <span className="block text-xs text-danger/80">{b.evidence}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-8 grid gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
          {dict.ship.automaticChecksHeading}
          <span className="ms-2 font-normal normal-case text-fg-subtle">
            {dict.ship.automaticChecksSubtitle}
          </span>
        </h2>
        {groupByCategory(checklist.automatic_checks).map(([category, checks]) => (
          <div
            key={category}
            className="rounded-xl border border-line bg-surface/40 p-4"
          >
            <p className="mb-1 text-xs uppercase tracking-[0.06em] text-fg-subtle">
              {category}
            </p>
            {checks.map((c) => (
              <AutomaticRow key={c.id} check={c} dict={dict} />
            ))}
          </div>
        ))}
      </section>

      <section className="mt-8 grid gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
          {dict.ship.manualChecksHeading}
          <span className="ms-2 font-normal normal-case text-fg-subtle">
            {dict.ship.manualChecksSubtitle}
          </span>
        </h2>
        {confirmError && (
          <p role="alert" className="text-sm text-danger">
            {confirmError.message}
          </p>
        )}
        {groupByCategory(checklist.manual_checks).map(([category, checks]) => (
          <div
            key={category}
            className="rounded-xl border border-line bg-surface/40 p-4"
          >
            <p className="mb-1 text-xs uppercase tracking-[0.06em] text-fg-subtle">
              {category}
            </p>
            {checks.map((c) => (
              <ManualRow
                key={c.id}
                check={c}
                dict={dict}
                pending={pendingItem === c.id}
                onToggle={(confirmed) =>
                  confirm.mutate({ itemId: c.id, confirmed })
                }
              />
            ))}
          </div>
        ))}
      </section>

      <div className="mt-8 rounded-xl border border-line bg-surface/60 p-5 text-sm leading-relaxed text-fg-muted">
        {checklist.overall_status === "READY_TO_SHIP" ? (
          <>
            {dict.ship.readyToShipPrefix}
            <span className="text-fg">{dict.ship.readyToShipEmphasis}</span>
            {dict.ship.readyToShipSuffix}
          </>
        ) : checklist.overall_status === "READY_WITH_MANUAL_CHECKS" ? (
          interpolate(dict.ship.manualPendingBody, {
            n: String(checklist.pending_manual_confirmations),
            plural: checklist.pending_manual_confirmations === 1 ? "" : "s",
          })
        ) : (
          dict.ship.blockersBody
        )}
      </div>
    </>
  );
}
