"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type { MetricDefinition, MetricEditableFields, Project } from "@/lib/api/types";
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

function structuredSummary(s: MetricDefinition["structured"]): string {
  const filters = s.default_filters.length
    ? ` where ${s.default_filters.map((f) => `${f.field} ${f.operator} ${JSON.stringify(f.value)}`).join(" and ")}`
    : "";
  if (s.aggregation === "ratio") {
    return `${s.numerator?.field ?? "?"} / ${s.denominator?.field ?? "?"}${filters}`;
  }
  if (s.aggregation === "count") {
    return `count(${s.measure?.field ?? "*"})${filters}`;
  }
  return `${s.aggregation}(${s.measure?.field ?? "?"})${filters}`;
}

type EditableSimpleFields = Pick<
  MetricEditableFields,
  "name" | "business_meaning" | "formula_text" | "owner" | "time_grain" | "related_goal_ref" | "caveats" | "validation_checks"
>;

function MetricCard({
  slug,
  metric,
  onChanged,
  dict,
}: {
  slug: string;
  metric: MetricDefinition;
  onChanged: (m: MetricDefinition) => void;
  dict: Dictionary;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<EditableSimpleFields>({
    name: metric.name,
    business_meaning: metric.business_meaning,
    formula_text: metric.formula_text,
    owner: metric.owner,
    time_grain: metric.time_grain,
    related_goal_ref: metric.related_goal_ref,
    caveats: metric.caveats,
    validation_checks: metric.validation_checks,
  });

  const approve = useMutation({
    mutationFn: () => api.approveMetric(slug, metric.id),
    onSuccess: onChanged,
  });
  const validate = useMutation({
    mutationFn: () => api.validateMetric(slug, metric.id),
    onSuccess: onChanged,
  });
  const update = useMutation({
    mutationFn: (patch: Partial<MetricEditableFields>) =>
      api.updateMetric(slug, metric.id, patch),
    onSuccess: (m) => {
      onChanged(m);
      setEditing(false);
    },
  });

  const updateErr = update.error as ApiRequestError | null;
  const validateErr = validate.error as ApiRequestError | null;
  const lv = metric.latest_validation;

  return (
    <li className="rounded-lg border border-line bg-surface/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] font-medium text-fg">
          {metric.business_id}
        </span>
        <Badge tone={metric.status === "approved" ? "success" : "neutral"}>
          {metric.status === "approved" ? dict.dataShared.approved : dict.dataShared.draft}
        </Badge>
        {metric.status === "approved" && !lv?.passed && (
          <span className="text-[11px] text-fg-subtle">
            {lv ? dict.dataMetrics.lastValidationFailed : dict.dataMetrics.notYetValidated}
          </span>
        )}
        <h3 className="text-sm font-medium text-fg">{metric.name}</h3>
        <div className="ms-auto flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setEditing((v) => !v)}>
            {editing ? dict.common.cancel : dict.dataShared.edit}
          </Button>
          <Button
            size="sm"
            variant="outline"
            loading={validate.isPending}
            onClick={() => validate.mutate()}
          >
            {dict.dataMetrics.validate}
          </Button>
          {metric.status !== "approved" && (
            <Button size="sm" loading={approve.isPending} onClick={() => approve.mutate()}>
              {dict.dataMetrics.approve}
            </Button>
          )}
        </div>
      </div>

      <p className="mt-2 font-mono text-xs text-accent" dir="ltr">{structuredSummary(metric.structured)}</p>
      {metric.formula_text && (
        <p className="mt-1 text-sm text-fg-muted">{metric.formula_text}</p>
      )}
      {metric.business_meaning && (
        <p className="mt-1 text-xs text-fg-subtle">{metric.business_meaning}</p>
      )}
      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-fg-subtle">
        {metric.time_grain && (
          <span className="rounded-sm border border-line bg-surface px-1">
            {interpolate(dict.dataMetrics.grainTag, { grain: metric.time_grain })}
          </span>
        )}
        {metric.allowed_dimensions.map((d) => (
          <span key={d} className="rounded-sm border border-line bg-surface px-1">
            {d}
          </span>
        ))}
      </div>
      {metric.caveats.length > 0 && (
        <ul className="mt-2 list-inside list-disc text-xs text-fg-subtle">
          {metric.caveats.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      )}

      {validateErr && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {validateErr.message}
        </p>
      )}
      {lv && (
        <div className="mt-3 rounded-lg border border-line bg-bg/40 p-3 text-sm">
          <p className={lv.passed ? "text-accent" : "text-danger"}>
            {lv.passed ? dict.dataMetrics.validated : dict.dataMetrics.validationFailed}
            {lv.passed && "value" in lv.result && (
              <span className="ms-2 font-mono text-fg-muted" dir="ltr">
                {lv.result.null_result ? "∅" : String(lv.result.value)}{" "}
                {interpolate(dict.dataMetrics.acrossRows, { n: String(lv.result.row_count) })}
              </span>
            )}
          </p>
          {lv.error && <p className="mt-1 text-xs text-danger">{lv.error}</p>}
        </div>
      )}

      {editing && (
        <div className="mt-4 grid gap-3 border-t border-line pt-4">
          <Field htmlFor={`m-name-${metric.id}`} label={dict.dataMetrics.fieldName}>
            <input
              id={`m-name-${metric.id}`}
              type="text"
              className={inputClass}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </Field>
          <Field htmlFor={`m-formula-${metric.id}`} label={dict.dataMetrics.fieldFormula}>
            <Textarea
              id={`m-formula-${metric.id}`}
              value={draft.formula_text}
              onChange={(e) => setDraft({ ...draft, formula_text: e.target.value })}
            />
          </Field>
          <Field htmlFor={`m-meaning-${metric.id}`} label={dict.dataMetrics.fieldBusinessMeaning}>
            <Textarea
              id={`m-meaning-${metric.id}`}
              value={draft.business_meaning}
              onChange={(e) => setDraft({ ...draft, business_meaning: e.target.value })}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field htmlFor={`m-owner-${metric.id}`} label={dict.dataMetrics.fieldOwner}>
              <input
                id={`m-owner-${metric.id}`}
                type="text"
                className={inputClass}
                value={draft.owner}
                onChange={(e) => setDraft({ ...draft, owner: e.target.value })}
              />
            </Field>
            <Field htmlFor={`m-grain-${metric.id}`} label={dict.dataMetrics.fieldTimeGrain}>
              <input
                id={`m-grain-${metric.id}`}
                type="text"
                className={inputClass}
                value={draft.time_grain}
                onChange={(e) => setDraft({ ...draft, time_grain: e.target.value })}
              />
            </Field>
          </div>
          <Field htmlFor={`m-caveats-${metric.id}`} label={dict.dataMetrics.fieldCaveats}>
            <StringListEditor
              value={draft.caveats}
              onChange={(v) => setDraft({ ...draft, caveats: v })}
              itemNoun={dict.dataMetrics.itemNounCaveat}
            />
          </Field>
          {updateErr && (
            <p role="alert" className="text-sm text-danger">
              {updateErr.message}
            </p>
          )}
          <p className="text-xs text-fg-subtle">
            {dict.dataMetrics.formulaEditNote}
          </p>
          <div className="flex gap-2">
            <Button size="sm" loading={update.isPending} onClick={() => update.mutate(draft)}>
              {dict.common.save}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
              {dict.common.cancel}
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

export function DataMetricsView({ initialProject }: { initialProject: Project }) {
  const { dict } = useLanguage();
  const slug = initialProject.slug;
  const qc = useQueryClient();

  const list = useQuery({
    queryKey: ["metrics", slug],
    queryFn: () => api.listMetrics(slug),
    retry: false,
  });

  const generate = useMutation({
    mutationFn: () => api.generateMetrics(slug),
    onSuccess: (metrics) => qc.setQueryData(["metrics", slug], metrics),
  });

  function replace(m: MetricDefinition) {
    qc.setQueryData<MetricDefinition[]>(["metrics", slug], (prev) =>
      prev ? prev.map((x) => (x.id === m.id ? m : x)) : prev,
    );
    if (m.status === "approved") qc.invalidateQueries({ queryKey: ["project", slug] });
  }

  const genErr = generate.error as ApiRequestError | null;

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.dataShared.dataProject}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {dict.dataMetrics.title}
        </h1>
        <p className="text-sm text-fg-muted">{dict.journeyData.metrics.label}</p>
        <p className="text-sm leading-relaxed text-fg-muted">
          {dict.dataMetrics.intro}
        </p>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <Button loading={generate.isPending} onClick={() => generate.mutate()}>
          {list.data && list.data.length > 0 ? dict.dataMetrics.generateMore : dict.dataMetrics.generateFirst}
        </Button>
      </div>
      {genErr?.code === "missing_api_key" && <AiUnconfiguredNotice />}
      {genErr && genErr.code !== "missing_api_key" && (
        <p role="alert" className="mb-4 text-sm text-danger">
          {genErr.message}
        </p>
      )}
      {genErr?.code === "no_profiled_datasets" && (
        <p className="mb-4 text-sm text-fg-subtle">
          {dict.dataMetrics.profileFirstHint}
        </p>
      )}

      {list.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : list.isError ? (
        <EmptyState
          title={interpolate(dict.dataShared.couldntLoad, { thing: dict.dataMetrics.title })}
          description={(list.error as ApiRequestError).message}
        />
      ) : !list.data || list.data.length === 0 ? (
        <p className="text-sm text-fg-subtle">
          {dict.dataMetrics.noneYet}
        </p>
      ) : (
        <ul className="grid gap-3">
          {list.data.map((m) => (
            <MetricCard key={m.id} slug={slug} metric={m} onChanged={replace} dict={dict} />
          ))}
        </ul>
      )}

      {list.data &&
        list.data.length > 0 &&
        list.data.every((m) => m.status === "approved" && m.latest_validation?.passed) && (
          <ArtifactApprovedNotice
            summary={dict.dataMetrics.nextSummary}
            nextLabel={dict.dataMetrics.nextLabel}
            nextHref={`/projects/${slug}/data-queries`}
          />
        )}
    </>
  );
}
