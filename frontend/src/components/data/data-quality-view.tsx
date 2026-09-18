"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircledIcon, CrossCircledIcon } from "@radix-ui/react-icons";

import { api, ApiRequestError } from "@/lib/api/client";
import type {
  DataQualityView as DQView,
  Project,
  QualityRule,
} from "@/lib/api/types";
import { AiUnconfiguredNotice } from "@/components/feedback/ai-unconfigured-notice";
import { EmptyState } from "@/components/feedback/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArtifactApprovedNotice } from "@/components/workspace/artifact-approved-notice";
import { interpolate, useLanguage } from "@/lib/i18n";

const SEV_TONE = {
  info: "neutral",
  warn: "warning",
  critical: "danger",
} as const;

function paramSummary(rule: QualityRule): string {
  const p = rule.params || {};
  if (rule.assertion === "in_set" && Array.isArray(p.values))
    return `in {${(p.values as string[]).join(", ")}}`;
  if (rule.assertion === "range")
    return `between ${p.min ?? "−∞"} and ${p.max ?? "∞"}`;
  if (rule.assertion === "regex") return `matches /${p.pattern}/`;
  if (rule.assertion === "row_count_gt") return `row count > ${p.threshold}`;
  return "";
}

export function DataQualityView({ initialProject }: { initialProject: Project }) {
  const { dict } = useLanguage();
  const slug = initialProject.slug;
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ["data-quality", slug],
    queryFn: () => api.getDataQuality(slug),
    retry: false,
  });

  const set = (dq: DQView) => qc.setQueryData(["data-quality", slug], dq);

  const observe = useMutation({
    mutationFn: () => api.observeDataQuality(slug),
    onSuccess: set,
  });
  const propose = useMutation({
    mutationFn: () => api.proposeQualityRules(slug),
    onSuccess: set,
  });
  const update = useMutation({
    mutationFn: (rules: QualityRule[]) =>
      api.updateDataQuality(slug, { rules }),
    onSuccess: set,
  });
  const approve = useMutation({
    mutationFn: () => api.approveDataQuality(slug),
    onSuccess: (dq) => {
      set(dq);
      qc.invalidateQueries({ queryKey: ["project", slug] });
    },
  });
  const check = useMutation({
    mutationFn: () => api.runQualityChecks(slug),
    onSuccess: set,
  });

  const dq = query.data;
  const err = (m: typeof observe | typeof propose | typeof check) =>
    m.error as ApiRequestError | null;
  const proposeErr = err(propose);

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.dataShared.dataProject}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {dict.dataQuality.title}
        </h1>
        <p className="text-sm text-fg-muted">{dict.journeyData.data_quality.label}</p>
        <p className="text-sm leading-relaxed text-fg-muted">
          <span className="font-medium text-fg">{dict.dataQuality.legendObservations}</span>
          {dict.dataQuality.legendObservationsBody}
          <span className="font-medium text-fg">{dict.dataQuality.legendRules}</span>
          {dict.dataQuality.legendRulesBody}
          <span className="font-medium text-fg">{dict.dataQuality.legendCheckResults}</span>
          {dict.dataQuality.legendCheckResultsBody}
        </p>
      </div>

      {query.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : query.isError ? (
        <EmptyState
          title={interpolate(dict.dataShared.couldntLoad, { thing: dict.dataQuality.title })}
          description={(query.error as ApiRequestError).message}
        />
      ) : !dq ? null : (
        <div className="grid gap-8">
          {/* SUMMARY — concise, before any detail; unresolved_critical is the
              same authoritative count Data Progress/Readiness use. */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-lg border border-line bg-surface/40 px-4 py-3 text-sm">
            <span className={dq.unresolved_critical > 0 ? "font-medium text-danger" : "text-fg-muted"}>
              {interpolate(dict.dataQuality.criticalUnresolved, { n: String(dq.unresolved_critical) })}
            </span>
            <span className="text-fg-muted">
              {interpolate(dict.dataQuality.rulesApproved, {
                approved: String(dq.content.rules.filter((r) => r.status === "approved").length),
                total: String(dq.content.rules.length),
              })}
            </span>
            {dq.latest_check_run && (
              <span className="text-fg-muted">
                {interpolate(dict.dataQuality.lastCheck, {
                  passed: String(dq.latest_check_run.summary.passed),
                  failed: String(dq.latest_check_run.summary.failed),
                })}
              </span>
            )}
          </div>

          {/* OBSERVED */}
          <section className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
                {dict.dataQuality.observedHeading}
                <span className="ms-2 font-normal normal-case text-fg-subtle">
                  {dict.dataQuality.observedSubtitle}
                </span>
              </h2>
              <Button
                size="sm"
                variant="outline"
                loading={observe.isPending}
                onClick={() => observe.mutate()}
              >
                {dq.content.observations.length
                  ? dict.dataQuality.rederive
                  : dict.dataQuality.deriveObservations}
              </Button>
            </div>
            {err(observe) && (
              <p role="alert" className="text-sm text-danger">
                {err(observe)!.message}
              </p>
            )}
            {dq.content.observations.length === 0 ? (
              <p className="text-sm text-fg-subtle">
                {dict.dataQuality.noObservations}
              </p>
            ) : (
              <ul className="grid gap-2">
                {dq.content.observations.map((o) => (
                  <li
                    key={o.id}
                    className="rounded-lg border border-line bg-surface/40 p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[11px] text-fg-subtle">
                        {o.id}
                      </span>
                      <Badge tone={SEV_TONE[o.severity]}>{o.severity}</Badge>
                      <span className="text-[11px] text-fg-subtle">
                        {o.dimension}
                        {o.column ? ` · ${o.column}` : ""}
                      </span>
                      {o.heuristic && (
                        <span className="text-[11px] text-fg-subtle">
                          {dict.dataQuality.heuristicNote}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-fg-muted">{o.statement}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* PROPOSED / APPROVED RULES */}
          <section className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
                {dict.dataQuality.rulesHeading}
                <span className="ms-2 font-normal normal-case text-fg-subtle">
                  {dq.approved ? dict.dataQuality.rulesApprovedTag : dict.dataQuality.rulesProposedTag}
                </span>
              </h2>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  loading={propose.isPending}
                  disabled={dq.content.observations.length === 0}
                  onClick={() => propose.mutate()}
                >
                  {dq.content.rules.length ? dict.dataQuality.reproposeRules : dict.dataQuality.proposeRules}
                </Button>
                {!dq.approved && dq.content.rules.length > 0 && (
                  <Button
                    size="sm"
                    loading={approve.isPending}
                    onClick={() => approve.mutate()}
                  >
                    {dict.dataQuality.approveRules}
                  </Button>
                )}
              </div>
            </div>
            {proposeErr?.code === "missing_api_key" && <AiUnconfiguredNotice />}
            {proposeErr && proposeErr.code !== "missing_api_key" && (
              <p role="alert" className="text-sm text-danger">
                {proposeErr.message}
              </p>
            )}
            {err(approve) && (
              <p role="alert" className="text-sm text-danger">
                {err(approve)!.message}
              </p>
            )}

            {dq.content.rules.length === 0 ? (
              <p className="text-sm text-fg-subtle">
                {dict.dataQuality.noRules}
              </p>
            ) : (
              <ul className="grid gap-2">
                {dq.content.rules.map((r) => (
                  <li
                    key={r.id}
                    className="rounded-lg border border-line bg-surface/40 p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[11px] font-medium text-fg">
                        {r.id}
                      </span>
                      <Badge tone={r.status === "approved" ? "success" : "neutral"}>
                        {r.status === "approved" ? dict.dataShared.approved : dict.dataShared.draft}
                      </Badge>
                      <span className="font-mono text-xs text-fg-muted" dir="ltr">
                        {r.assertion}({r.column || "table"}) {paramSummary(r)}
                      </span>
                      {r.accepted_risk && (
                        <Badge tone="warning">{dict.dataQuality.acceptedRisk}</Badge>
                      )}
                      {!dq.approved && (
                        <button
                          type="button"
                          onClick={() =>
                            update.mutate(
                              dq.content.rules.filter((x) => x.id !== r.id),
                            )
                          }
                          className="ms-auto text-[11px] text-fg-subtle underline-offset-2 hover:text-danger hover:underline"
                        >
                          {dict.dataShared.remove}
                        </button>
                      )}
                    </div>
                    {r.rationale && (
                      <p className="mt-1 text-xs text-fg-muted">{r.rationale}</p>
                    )}
                    {r.related_observations.length > 0 && (
                      <p className="mt-1 flex flex-wrap gap-1 text-[11px] text-fg-subtle">
                        <span>{dict.dataQuality.tracesTo}</span>
                        {r.related_observations.map((d) => (
                          <span
                            key={d}
                            className="rounded-sm border border-line bg-surface px-1 font-mono"
                          >
                            {d}
                          </span>
                        ))}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* CHECK RESULTS */}
          <section className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
                {dict.dataQuality.checkResultsHeading}
                <span className="ms-2 font-normal normal-case text-fg-subtle">
                  {dict.dataQuality.checkResultsSubtitle}
                </span>
              </h2>
              <Button
                size="sm"
                variant="outline"
                disabled={!dq.approved}
                loading={check.isPending}
                onClick={() => check.mutate()}
              >
                {dict.dataQuality.runChecks}
              </Button>
            </div>
            {!dq.approved && (
              <p className="text-sm text-fg-subtle">
                {dict.dataQuality.approveToRunChecks}
              </p>
            )}
            {err(check) && (
              <p role="alert" className="text-sm text-danger">
                {err(check)!.message}
              </p>
            )}
            {dq.latest_check_run && (
              <div className="grid gap-2 rounded-xl border border-line bg-surface/40 p-4">
                <p className="text-xs text-fg-muted">
                  {interpolate(dict.dataQuality.checkSummary, {
                    passed: String(dq.latest_check_run.summary.passed),
                    failed: String(dq.latest_check_run.summary.failed),
                    critical: String(dq.latest_check_run.summary.critical_failed),
                  })}
                </p>
                <ul className="grid gap-1.5">
                  {dq.latest_check_run.results.map((res) => (
                    <li
                      key={res.rule_id}
                      className="flex flex-wrap items-center gap-2 text-sm"
                    >
                      {res.passed ? (
                        <CheckCircledIcon
                          className="size-4 text-accent"
                          aria-hidden
                        />
                      ) : (
                        <CrossCircledIcon
                          className="size-4 text-danger"
                          aria-hidden
                        />
                      )}
                      <span className="font-mono text-xs text-fg-subtle">
                        {res.rule_id}
                      </span>
                      <span className="text-fg-muted" dir="ltr">
                        {res.assertion}({res.column || "table"})
                      </span>
                      {!res.passed && res.failing_row_count != null && (
                        <span className="text-xs text-danger">
                          {interpolate(dict.dataQuality.violatingRows, { n: String(res.failing_row_count) })}
                        </span>
                      )}
                      {res.error && (
                        <span className="text-xs text-danger">{res.error}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {dq.approved && (
            <ArtifactApprovedNotice
              summary={dict.dataQuality.nextSummary}
              nextLabel={dict.dataQuality.nextLabel}
              nextHref={`/projects/${slug}/data-build`}
            />
          )}
        </div>
      )}
    </>
  );
}
