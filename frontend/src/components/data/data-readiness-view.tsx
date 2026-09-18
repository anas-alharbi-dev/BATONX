"use client";

import { useState } from "react";
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
  DataReadinessStatus,
  ManualCheck,
  Project,
} from "@/lib/api/types";
import { EmptyState } from "@/components/feedback/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { formatDateTime } from "@/lib/format";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

function readinessMeta(
  status: DataReadinessStatus,
  dict: Dictionary,
): { label: string; tone: "danger" | "warning" | "success" } {
  switch (status) {
    case "NOT_READY":
      return { label: dict.dataReadiness.readinessNotReady, tone: "danger" };
    case "READY_WITH_MANUAL_CHECKS":
      return { label: dict.dataReadiness.readinessManualPending, tone: "warning" };
    case "READY_TO_DELIVER":
      return { label: dict.dataReadiness.readinessReady, tone: "success" };
  }
}

function checkMeta(
  status: AutomaticCheck["status"],
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
            (meta.tone === "success" ? "text-accent" : meta.tone === "danger" ? "text-danger" : "text-warning")
          }
          aria-hidden
        />
        <div className="grid flex-1 gap-0.5">
          <p className="text-sm font-medium text-fg">
            {check.title}
            {!check.required && (
              <span className="ms-2 text-[11px] font-normal text-fg-subtle">{dict.ship.advisory}</span>
            )}
          </p>
          <p className="text-xs leading-relaxed text-fg-muted">{check.evidence}</p>
          {check.status !== "pass" && check.action && (
            <p className="text-xs leading-relaxed text-fg-subtle">→ {check.action}</p>
          )}
        </div>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>
    </div>
  );
}

function ManualRow({
  check, pending, onToggle, dict,
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
          <p className="text-xs leading-relaxed text-fg-muted">{check.why_manual}</p>
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
            <Button variant="ghost" size="sm" disabled={pending} onClick={() => onToggle(false)}>
              {dict.ship.undo}
            </Button>
          ) : (
            <Button variant="outline" size="sm" disabled={pending} onClick={() => onToggle(true)}>
              {dict.ship.confirm}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function DataReadinessView({ initialProject }: { initialProject: Project }) {
  const { dict } = useLanguage();
  const slug = initialProject.slug;
  const qc = useQueryClient();
  const [pendingItem, setPendingItem] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["data-readiness", slug],
    queryFn: () => api.getDataReadiness(slug),
    retry: false,
  });

  const confirm = useMutation({
    mutationFn: (vars: { itemId: string; confirmed: boolean }) =>
      api.confirmDataReadinessItem(slug, vars.itemId, vars.confirmed),
    onMutate: (vars) => setPendingItem(vars.itemId),
    onSuccess: (data) => qc.setQueryData(["data-readiness", slug], data),
    onSettled: () => setPendingItem(null),
  });
  const confirmError = confirm.error as ApiRequestError | null;

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.dataShared.dataProject}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{dict.dataReadiness.title}</h1>
        <p className="text-sm text-fg-muted">{dict.journeyData.delivery_readiness.label}</p>
        <p className="text-sm leading-relaxed text-fg-muted">
          <span className="font-medium text-fg">{dict.dataReadiness.legendAutomatic}</span>
          {dict.dataReadiness.legendAutomaticBody}
          <span className="font-medium text-fg">{dict.dataReadiness.legendManual}</span>
          {dict.dataReadiness.legendManualBody}
        </p>
      </div>

      {query.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : query.isError ? (
        <EmptyState
          title={interpolate(dict.dataShared.couldntLoad, { thing: dict.dataReadiness.title })}
          description={(query.error as ApiRequestError).message}
        />
      ) : (
        <>
          <div className="grid gap-3 rounded-xl border border-line bg-surface/40 p-5">
            <div className="flex flex-wrap items-center gap-3">
              <Badge tone={readinessMeta(query.data.overall_status, dict).tone}>
                {readinessMeta(query.data.overall_status, dict).label}
              </Badge>
            </div>
            <p className="text-sm leading-relaxed text-fg-muted">
              {query.data.readiness_summary}
            </p>
          </div>

          {query.data.blockers.length > 0 && (
            <section className="mt-6 grid gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-danger">
                {interpolate(dict.dataReadiness.blockersHeading, { n: String(query.data.blockers.length) })}
              </h2>
              <ul className="grid gap-1.5">
                {query.data.blockers.map((b) => (
                  <li key={b.id} className="rounded-md border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">
                    <span className="font-mono text-xs">{b.id}</span> {b.title}
                    <span className="block text-xs text-danger/80">{b.evidence}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="mt-8 grid gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
              {dict.dataReadiness.automaticChecksHeading}
              <span className="ms-2 font-normal normal-case text-fg-subtle">
                {dict.dataReadiness.automaticChecksSubtitle}
              </span>
            </h2>
            {groupByCategory(query.data.automatic_checks).map(([category, checks]) => (
              <div key={category} className="rounded-xl border border-line bg-surface/40 p-4">
                <p className="mb-1 text-xs uppercase tracking-[0.06em] text-fg-subtle">{category}</p>
                {checks.map((c) => <AutomaticRow key={c.id} check={c} dict={dict} />)}
              </div>
            ))}
          </section>

          <section className="mt-8 grid gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
              {dict.dataReadiness.manualChecksHeading}
              <span className="ms-2 font-normal normal-case text-fg-subtle">
                {interpolate(dict.dataReadiness.manualChecksSubtitle, {
                  confirmed: String(query.data.manual_checks.filter((c) => c.confirmed).length),
                  total: String(query.data.manual_checks.length),
                })}
              </span>
            </h2>
            {confirmError && (
              <p role="alert" className="text-sm text-danger">{confirmError.message}</p>
            )}
            {groupByCategory(query.data.manual_checks).map(([category, checks]) => (
              <div key={category} className="rounded-xl border border-line bg-surface/40 p-4">
                <p className="mb-1 text-xs uppercase tracking-[0.06em] text-fg-subtle">{category}</p>
                {checks.map((c) => (
                  <ManualRow
                    key={c.id} check={c} pending={pendingItem === c.id} dict={dict}
                    onToggle={(confirmed) => confirm.mutate({ itemId: c.id, confirmed })}
                  />
                ))}
              </div>
            ))}
          </section>

          <div className="mt-8 rounded-xl border border-line bg-surface/60 p-5 text-sm leading-relaxed text-fg-muted">
            {query.data.overall_status === "READY_TO_DELIVER" ? (
              <>
                {dict.dataReadiness.readyPrefix}
                <span className="text-fg">{dict.dataReadiness.readyEmphasis}</span>
                {dict.dataReadiness.readySuffix}
              </>
            ) : query.data.overall_status === "READY_WITH_MANUAL_CHECKS" ? (
              interpolate(dict.dataReadiness.manualPendingBody, {
                n: String(query.data.pending_manual_confirmations),
                plural: query.data.pending_manual_confirmations === 1 ? "" : "s",
              })
            ) : (
              dict.dataReadiness.blockersBody
            )}
          </div>
        </>
      )}
    </>
  );
}
