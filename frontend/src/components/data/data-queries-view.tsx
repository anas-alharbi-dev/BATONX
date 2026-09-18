"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type { DataQuery, Project, QueryPlan, QueryStatus } from "@/lib/api/types";
import { AiUnconfiguredNotice } from "@/components/feedback/ai-unconfigured-notice";
import { EmptyState } from "@/components/feedback/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { inputClass, StringListEditor } from "@/components/ui/editor-primitives";
import { Field } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ArtifactApprovedNotice } from "@/components/workspace/artifact-approved-notice";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

import { DataLineagePanel } from "./data-lineage-panel";

const STATUS_TONE: Record<QueryStatus, "neutral" | "accent" | "success" | "warning"> = {
  draft_plan: "neutral",
  plan_approved: "accent",
  sql_generated: "warning",
  reviewed: "warning",
  executed: "success",
};

function statusLabel(status: QueryStatus, dict: Dictionary): string {
  switch (status) {
    case "draft_plan":
      return dict.dataQueries.statusDraftPlan;
    case "plan_approved":
      return dict.dataQueries.statusPlanApproved;
    case "sql_generated":
      return dict.dataQueries.statusSqlGenerated;
    case "reviewed":
      return dict.dataQueries.statusReviewed;
    case "executed":
      return dict.dataQueries.statusExecuted;
  }
}

const EMPTY_PLAN: QueryPlan = {
  objective: "",
  required_kpi_refs: [],
  required_fields: [],
  base_table_ref: "",
  grain: "",
  dimensions: [],
  filters: [],
  joins: [],
  sort: [],
  expected_result_shape: "",
  assumptions: [],
};

function csv(v: string): string[] {
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function QueryCard({
  slug,
  q,
  datasets,
  approvedMetricIds,
  onChanged,
  dict,
}: {
  slug: string;
  q: DataQuery;
  datasets: { id: string; name: string }[];
  approvedMetricIds: string[];
  onChanged: (q: DataQuery) => void;
  dict: Dictionary;
}) {
  const [open, setOpen] = useState(false);
  const initialPlan: QueryPlan =
    "objective" in q.plan ? (q.plan as QueryPlan) : EMPTY_PLAN;
  const [plan, setPlan] = useState<QueryPlan>(initialPlan);

  const savePlan = useMutation({
    mutationFn: (p: QueryPlan) => api.updateQueryPlan(slug, q.id, p),
    onSuccess: (updated) => {
      onChanged(updated);
      setPlan("objective" in updated.plan ? (updated.plan as QueryPlan) : EMPTY_PLAN);
    },
  });
  const approvePlan = useMutation({
    mutationFn: () => api.approveQueryPlan(slug, q.id),
    onSuccess: onChanged,
  });
  const genSql = useMutation({
    mutationFn: () => api.generateQuerySql(slug, q.id),
    onSuccess: onChanged,
  });
  const review = useMutation({
    mutationFn: () => api.reviewQuerySql(slug, q.id),
    onSuccess: onChanged,
  });
  const markReviewed = useMutation({
    mutationFn: () => api.markQueryReviewed(slug, q.id),
    onSuccess: onChanged,
  });
  const execute = useMutation({
    mutationFn: () => api.executeQuery(slug, q.id),
    onSuccess: onChanged,
  });

  const err = (m: { error: unknown }) => m.error as ApiRequestError | null;
  const genErr = err(genSql);
  const run = q.latest_run;

  return (
    <li className="rounded-lg border border-line bg-surface/40 p-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full flex-wrap items-center gap-2 text-start"
      >
        <span className="font-mono text-[11px] font-medium text-fg">{q.business_id}</span>
        <Badge tone={STATUS_TONE[q.status]}>{statusLabel(q.status, dict)}</Badge>
        <span className="text-sm text-fg">{q.question}</span>
        <span className="ms-auto text-xs text-fg-subtle">{open ? dict.dataShared.hide : dict.dataShared.show}</span>
      </button>

      {open && (
        <div className="mt-4 grid gap-6 border-t border-line pt-4">
          {/* PLAN */}
          <section className="grid gap-3">
            <h4 className="text-xs font-semibold uppercase tracking-[0.08em] text-fg-subtle">
              {dict.dataQueries.planHeading}
              <span className="ms-2 font-normal normal-case text-fg-subtle">
                {dict.dataQueries.planSubtitle}
              </span>
            </h4>
            <Field htmlFor={`q-obj-${q.id}`} label={dict.dataQueries.fieldObjective}>
              <Textarea
                id={`q-obj-${q.id}`}
                value={plan.objective}
                onChange={(e) => setPlan({ ...plan, objective: e.target.value })}
              />
            </Field>
            <Field htmlFor={`q-base-${q.id}`} label={dict.dataQueries.fieldBaseDataset}>
              <select
                id={`q-base-${q.id}`}
                value={plan.base_table_ref}
                onChange={(e) => setPlan({ ...plan, base_table_ref: e.target.value })}
                className={`${inputClass} [color-scheme:dark]`}
              >
                <option value="">{dict.dataQueries.selectDataset}</option>
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field htmlFor={`q-fields-${q.id}`} label={dict.dataQueries.fieldRequiredFields}>
                <input
                  id={`q-fields-${q.id}`}
                  type="text"
                  className={inputClass}
                  value={plan.required_fields.join(", ")}
                  onChange={(e) => setPlan({ ...plan, required_fields: csv(e.target.value) })}
                />
              </Field>
              <Field htmlFor={`q-dims-${q.id}`} label={dict.dataQueries.fieldDimensions}>
                <input
                  id={`q-dims-${q.id}`}
                  type="text"
                  className={inputClass}
                  value={plan.dimensions.join(", ")}
                  onChange={(e) => setPlan({ ...plan, dimensions: csv(e.target.value) })}
                />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field htmlFor={`q-grain-${q.id}`} label={dict.dataQueries.fieldGrain}>
                <input
                  id={`q-grain-${q.id}`}
                  type="text"
                  className={inputClass}
                  value={plan.grain}
                  onChange={(e) => setPlan({ ...plan, grain: e.target.value })}
                />
              </Field>
              <Field htmlFor={`q-sort-${q.id}`} label={dict.dataQueries.fieldSort}>
                <input
                  id={`q-sort-${q.id}`}
                  type="text"
                  className={inputClass}
                  value={plan.sort.join(", ")}
                  onChange={(e) => setPlan({ ...plan, sort: csv(e.target.value) })}
                />
              </Field>
            </div>
            <Field htmlFor={`q-shape-${q.id}`} label={dict.dataQueries.fieldExpectedShape}>
              <Textarea
                id={`q-shape-${q.id}`}
                value={plan.expected_result_shape}
                onChange={(e) => setPlan({ ...plan, expected_result_shape: e.target.value })}
              />
            </Field>
            <Field htmlFor={`q-assumptions-${q.id}`} label={dict.dataQueries.fieldAssumptions}>
              <StringListEditor
                value={plan.assumptions}
                onChange={(v) => setPlan({ ...plan, assumptions: v })}
                itemNoun={dict.dataQueries.itemNounAssumption}
              />
            </Field>
            {approvedMetricIds.length > 0 && (
              <Field htmlFor={`q-kpis-${q.id}`} label={dict.dataQueries.fieldRequiredKpis}>
                <div className="flex flex-wrap gap-3">
                  {approvedMetricIds.map((kid) => (
                    <label key={kid} className="inline-flex items-center gap-1.5 text-sm text-fg-muted">
                      <input
                        type="checkbox"
                        checked={plan.required_kpi_refs.includes(kid)}
                        onChange={(e) =>
                          setPlan({
                            ...plan,
                            required_kpi_refs: e.target.checked
                              ? [...plan.required_kpi_refs, kid]
                              : plan.required_kpi_refs.filter((x) => x !== kid),
                          })
                        }
                      />
                      <span className="font-mono text-xs">{kid}</span>
                    </label>
                  ))}
                </div>
              </Field>
            )}
            {err(savePlan) && (
              <p role="alert" className="text-sm text-danger">
                {err(savePlan)!.message}
              </p>
            )}
            <div className="flex gap-2">
              <Button size="sm" loading={savePlan.isPending} onClick={() => savePlan.mutate(plan)}>
                {dict.dataQueries.savePlan}
              </Button>
              {q.status === "draft_plan" && (
                <Button
                  size="sm"
                  variant="outline"
                  loading={approvePlan.isPending}
                  onClick={() => approvePlan.mutate()}
                >
                  {dict.dataQueries.approvePlanCta}
                </Button>
              )}
            </div>
            {err(approvePlan) && (
              <p role="alert" className="text-sm text-danger">
                {err(approvePlan)!.message}
              </p>
            )}
          </section>

          {/* SQL */}
          {q.status !== "draft_plan" && (
            <section className="grid gap-3">
              <h4 className="text-xs font-semibold uppercase tracking-[0.08em] text-fg-subtle">
                {dict.dataQueries.sqlHeading}
                <span className="ms-2 font-normal normal-case text-fg-subtle">
                  {dict.dataQueries.sqlSubtitle}
                </span>
              </h4>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" loading={genSql.isPending} onClick={() => genSql.mutate()}>
                  {q.sql ? dict.dataQueries.regenerateSql : dict.dataQueries.generateSql}
                </Button>
                {q.sql && (
                  <Button size="sm" variant="outline" loading={review.isPending} onClick={() => review.mutate()}>
                    {dict.dataQueries.requestAiReview}
                  </Button>
                )}
                {q.status === "sql_generated" && (
                  <Button size="sm" loading={markReviewed.isPending} onClick={() => markReviewed.mutate()}>
                    {dict.dataQueries.markReviewed}
                  </Button>
                )}
              </div>
              {genErr?.code === "missing_api_key" && <AiUnconfiguredNotice />}
              {genErr && genErr.code !== "missing_api_key" && (
                <p role="alert" className="text-sm text-danger">
                  {genErr.message}
                </p>
              )}
              {q.sql && (
                <pre dir="ltr" className="max-h-60 overflow-auto rounded-lg border border-line bg-bg-subtle p-4 text-start font-mono text-xs leading-relaxed text-fg-muted">
                  {q.sql}
                </pre>
              )}
              {q.review.ai && (
                <div className="grid gap-1 rounded-lg border border-line bg-bg/40 p-3 text-sm">
                  <p>
                    <Badge tone={q.review.ai.recommendation === "looks_good" ? "success" : "warning"}>
                      {q.review.ai.recommendation === "looks_good" ? dict.dataQueries.aiLooksGood : dict.dataQueries.aiNeedsChanges}
                    </Badge>
                  </p>
                  <p className="text-xs text-fg-muted">{q.review.ai.alignment_notes}</p>
                  {q.review.ai.risks.length > 0 && (
                    <ul className="list-inside list-disc text-xs text-danger">
                      {q.review.ai.risks.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  )}
                  <p className="text-xs text-fg-subtle">
                    {dict.dataQueries.aiAdvisoryOnly}
                  </p>
                </div>
              )}
              <p className="text-xs text-fg-subtle">
                {q.review.human_reviewed ? dict.dataQueries.markedReviewed : dict.dataQueries.notMarkedReviewed}
              </p>
            </section>
          )}

          {/* EXECUTE */}
          {(q.status === "reviewed" || q.status === "executed") && (
            <section className="grid gap-3">
              <h4 className="text-xs font-semibold uppercase tracking-[0.08em] text-fg-subtle">
                {dict.dataQueries.executeHeading}
                <span className="ms-2 font-normal normal-case text-fg-subtle">
                  {dict.dataQueries.executeSubtitle}
                </span>
              </h4>
              <div>
                <Button size="sm" loading={execute.isPending} onClick={() => execute.mutate()}>
                  {q.status === "executed" ? dict.dataQueries.rerun : dict.dataQueries.execute}
                </Button>
              </div>
              {err(execute) && (
                <p role="alert" className="text-sm text-danger">
                  {err(execute)!.message}
                </p>
              )}
              {run && (
                <div className="grid gap-1">
                  <p className="text-xs text-fg-muted">
                    {interpolate(dict.dataTransformation.rowCount, { n: String(run.row_count) })}
                    {run.truncated ? dict.dataTransformation.capped : ""}
                  </p>
                  <div className="overflow-x-auto rounded-lg border border-line">
                    <table className="w-full border-collapse text-start text-xs">
                      <thead className="bg-surface/60 text-fg-subtle">
                        <tr>
                          {run.columns.map((c) => (
                            <th key={c} className="px-3 py-2 font-mono font-medium" dir="ltr">
                              {c}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {run.rows.slice(0, 50).map((row, i) => (
                          <tr key={i} className="border-t border-line">
                            {row.map((cell, j) => (
                              <td key={j} className="px-3 py-1.5 text-fg-muted" dir="ltr">
                                {cell === null ? "∅" : String(cell)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </section>
          )}
        </div>
      )}
    </li>
  );
}

export function DataQueriesView({ initialProject }: { initialProject: Project }) {
  const { dict } = useLanguage();
  const slug = initialProject.slug;
  const qc = useQueryClient();
  const [question, setQuestion] = useState("");

  const list = useQuery({
    queryKey: ["queries", slug],
    queryFn: () => api.listQueries(slug),
    retry: false,
  });
  const datasets = useQuery({
    queryKey: ["datasets", slug],
    queryFn: () => api.listDatasets(slug),
  });
  const metrics = useQuery({
    queryKey: ["metrics", slug],
    queryFn: () => api.listMetrics(slug),
  });

  const create = useMutation({
    mutationFn: () => api.createQuery(slug, question),
    onSuccess: (q) => {
      qc.setQueryData<DataQuery[]>(["queries", slug], (prev) => (prev ? [...prev, q] : [q]));
      setQuestion("");
    },
  });

  function replace(q: DataQuery) {
    qc.setQueryData<DataQuery[]>(["queries", slug], (prev) =>
      prev ? prev.map((x) => (x.id === q.id ? q : x)) : prev,
    );
    if (q.status === "reviewed" || q.status === "executed") {
      qc.invalidateQueries({ queryKey: ["project", slug] });
    }
  }

  const profiledDatasets = (datasets.data?.datasets ?? [])
    .filter((d) => d.status === "profiled")
    .map((d) => ({ id: d.id, name: d.name }));
  const approvedMetricIds = (metrics.data ?? [])
    .filter((m) => m.status === "approved")
    .map((m) => m.business_id);
  const createErr = create.error as ApiRequestError | null;

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.dataShared.dataProject}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{dict.dataQueries.title}</h1>
        <p className="text-sm text-fg-muted">{dict.journeyData.queries.label}</p>
        <p className="text-sm leading-relaxed text-fg-muted">
          {dict.dataQueries.intro}
        </p>
      </div>

      <div className="mb-8 grid gap-3 rounded-xl border border-line bg-surface/40 p-5">
        <Field htmlFor="new-question" label={dict.dataQueries.newQuestionLabel}>
          <input
            id="new-question"
            type="text"
            className={inputClass}
            placeholder={dict.dataQueries.newQuestionPlaceholder}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </Field>
        {createErr && (
          <p role="alert" className="text-sm text-danger">
            {createErr.message}
          </p>
        )}
        <div>
          <Button
            size="sm"
            loading={create.isPending}
            disabled={!question.trim()}
            onClick={() => create.mutate()}
          >
            {dict.dataQueries.addQuestion}
          </Button>
        </div>
      </div>

      {list.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : list.isError ? (
        <EmptyState
          title={interpolate(dict.dataShared.couldntLoad, { thing: dict.dataQueries.title })}
          description={(list.error as ApiRequestError).message}
        />
      ) : !list.data || list.data.length === 0 ? (
        <p className="text-sm text-fg-subtle">
          {dict.dataQueries.noneYet}
        </p>
      ) : (
        <ul className="grid gap-3">
          {list.data.map((q) => (
            <QueryCard
              key={q.id}
              slug={slug}
              q={q}
              datasets={profiledDatasets}
              approvedMetricIds={approvedMetricIds}
              onChanged={replace}
              dict={dict}
            />
          ))}
        </ul>
      )}

      {list.data && list.data.length > 0 && list.data.every((q) => q.status === "executed") && (
        <ArtifactApprovedNotice
          summary={dict.dataQueries.nextSummary}
          nextLabel={dict.dataQueries.nextLabel}
          nextHref={`/projects/${slug}/data-analysis`}
        />
      )}

      <div className="mt-8">
        <DataLineagePanel slug={slug} />
      </div>
    </>
  );
}
