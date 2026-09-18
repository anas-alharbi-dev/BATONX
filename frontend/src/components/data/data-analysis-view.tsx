"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type {
  AnalysisComparison,
  AnalysisMethod,
  AnalysisPlan,
  AnalysisResult,
  DashboardBlueprintContent,
  DashboardPanel,
  Insight,
  MetricDefinition,
  Project,
} from "@/lib/api/types";
import { AiUnconfiguredNotice } from "@/components/feedback/ai-unconfigured-notice";
import { EmptyState } from "@/components/feedback/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { inputClass, StringListEditor } from "@/components/ui/editor-primitives";
import { Field } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/format";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

import { DataLineagePanel } from "./data-lineage-panel";

type Tab = "plans" | "results" | "insights" | "dashboard";

const METHODS: AnalysisMethod[] = ["descriptive", "trend", "segmentation", "comparison", "funnel"];

function csv(v: string): string[] {
  return v.split(",").map((s) => s.trim()).filter(Boolean);
}

// =====================================================================
// Analysis Plan editor (shared: create manually + edit)
// =====================================================================

function emptyPlanDraft(): Partial<AnalysisPlan> {
  return {
    business_question: "", method: "descriptive", hypotheses: [],
    required_metrics: [], segments: [], comparisons: [], expected_outputs: [],
  };
}

function ComparisonsEditor({
  value, onChange, needsTimeRange,
}: {
  value: AnalysisComparison[];
  onChange: (v: AnalysisComparison[]) => void;
  needsTimeRange: boolean;
}) {
  const { dict } = useLanguage();
  const set = (i: number, patch: Partial<AnalysisComparison>) =>
    onChange(value.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  return (
    <div className="grid gap-3">
      {value.map((c, i) => (
        <div key={i} className="grid gap-2 rounded-md border border-line bg-bg/40 p-3">
          <div className="flex items-center gap-2">
            <input
              type="text" placeholder="label" className={inputClass}
              value={c.label} onChange={(e) => set(i, { label: e.target.value })}
            />
            <button
              type="button"
              onClick={() => onChange(value.filter((_, idx) => idx !== i))}
              className="shrink-0 text-xs text-fg-subtle hover:text-danger"
            >
              {dict.dataShared.remove}
            </button>
          </div>
          {needsTimeRange ? (
            <div className="grid grid-cols-2 gap-2">
              <input
                type="date" className={inputClass}
                value={c.time_range?.start ?? ""}
                onChange={(e) =>
                  set(i, { time_range: { start: e.target.value, end: c.time_range?.end ?? "" } })
                }
              />
              <input
                type="date" className={inputClass}
                value={c.time_range?.end ?? ""}
                onChange={(e) =>
                  set(i, { time_range: { start: c.time_range?.start ?? "", end: e.target.value } })
                }
              />
            </div>
          ) : (
            <input
              type="text" className={inputClass}
              placeholder="filters as field=value, field=value"
              value={(c.filters || []).map((f) => `${f.field}=${f.value}`).join(", ")}
              onChange={(e) =>
                set(i, {
                  filters: csv(e.target.value).map((pair) => {
                    const [field, value] = pair.split("=").map((s) => s.trim());
                    return { field, operator: "eq" as const, value };
                  }),
                })
              }
            />
          )}
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...value, { label: "", time_range: null, filters: [] }])}
        className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-line-strong px-3 py-2 text-sm text-fg-muted hover:border-accent hover:text-fg"
      >
        + {dict.dataAnalysis.addComparison}
      </button>
    </div>
  );
}

function PlanEditorForm({
  slug, metrics, initial, onSaved, onCancel,
}: {
  slug: string;
  metrics: MetricDefinition[];
  initial?: AnalysisPlan;
  onSaved: (p: AnalysisPlan) => void;
  onCancel: () => void;
}) {
  const { dict } = useLanguage();
  const [draft, setDraft] = useState<Partial<AnalysisPlan>>(initial || emptyPlanDraft());
  const approvedKpis = metrics.filter((m) => m.status === "approved");

  const save = useMutation({
    mutationFn: () =>
      initial
        ? api.updateAnalysisPlan(slug, initial.id, draft)
        : api.createAnalysisPlan(slug, draft),
    onSuccess: onSaved,
  });
  const err = save.error as ApiRequestError | null;
  const needsSegments = draft.method === "segmentation";
  const needsComparisons = draft.method === "trend" || draft.method === "comparison" || draft.method === "funnel";
  const needsTimeRangeComparisons = draft.method === "trend";

  return (
    <div className="grid gap-3 rounded-lg border border-line bg-bg/40 p-4">
      <Field htmlFor="plan-question" label={dict.dataAnalysis.fieldBusinessQuestion}>
        <Textarea
          id="plan-question" value={draft.business_question || ""}
          onChange={(e) => setDraft({ ...draft, business_question: e.target.value })}
        />
      </Field>
      <Field htmlFor="plan-method" label={dict.dataAnalysis.fieldMethod}>
        <select
          id="plan-method" className={`${inputClass} [color-scheme:dark]`}
          value={draft.method || "descriptive"}
          onChange={(e) => setDraft({ ...draft, method: e.target.value as AnalysisMethod })}
          dir="ltr"
        >
          {METHODS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </Field>
      <Field htmlFor="plan-kpis" label={dict.dataAnalysis.fieldRequiredKpis}>
        <div className="flex flex-wrap gap-3">
          {approvedKpis.length === 0 && (
            <p className="text-xs text-fg-subtle">{dict.dataAnalysis.noApprovedKpis}</p>
          )}
          {approvedKpis.map((m) => (
            <label key={m.id} className="inline-flex items-center gap-1.5 text-sm text-fg-muted">
              <input
                type="checkbox"
                checked={(draft.required_metrics || []).includes(m.business_id)}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    required_metrics: e.target.checked
                      ? [...(draft.required_metrics || []), m.business_id]
                      : (draft.required_metrics || []).filter((x) => x !== m.business_id),
                  })
                }
              />
              <span className="font-mono text-xs">{m.business_id}</span> {m.name}
            </label>
          ))}
        </div>
      </Field>
      {needsSegments && (
        <Field htmlFor="plan-segments" label={dict.dataAnalysis.fieldSegments}>
          <input
            id="plan-segments" type="text" className={inputClass}
            value={(draft.segments || []).join(", ")}
            onChange={(e) => setDraft({ ...draft, segments: csv(e.target.value) })}
          />
        </Field>
      )}
      {needsComparisons && (
        <Field
          htmlFor="plan-comparisons"
          label={draft.method === "funnel" ? dict.dataAnalysis.fieldFunnelSteps : dict.dataAnalysis.fieldComparisons}
        >
          <ComparisonsEditor
            value={draft.comparisons || []}
            onChange={(v) => setDraft({ ...draft, comparisons: v })}
            needsTimeRange={needsTimeRangeComparisons}
          />
        </Field>
      )}
      <Field htmlFor="plan-outputs" label={dict.dataAnalysis.fieldExpectedOutputs}>
        <StringListEditor
          value={draft.expected_outputs || []}
          onChange={(v) => setDraft({ ...draft, expected_outputs: v })}
          itemNoun={dict.dataAnalysis.itemNounExpectedOutput}
        />
      </Field>
      <Field htmlFor="plan-hypotheses" label={dict.dataAnalysis.fieldHypotheses}>
        <StringListEditor
          value={draft.hypotheses || []}
          onChange={(v) => setDraft({ ...draft, hypotheses: v })}
          itemNoun={dict.dataAnalysis.itemNounHypothesis}
        />
      </Field>
      {err && (
        <p role="alert" className="text-sm text-danger">{err.message}</p>
      )}
      <div className="flex gap-2">
        <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>
          {initial ? dict.dataAnalysis.saveChanges : dict.dataAnalysis.createPlan}
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel}>{dict.common.cancel}</Button>
      </div>
    </div>
  );
}

// =====================================================================
// Plans tab
// =====================================================================

function PlanCard({
  slug, plan, metrics, onChanged, onViewResults,
}: {
  slug: string;
  plan: AnalysisPlan;
  metrics: MetricDefinition[];
  onChanged: (p: AnalysisPlan) => void;
  onViewResults: (planId: string, resultId: string) => void;
}) {
  const { dict } = useLanguage();
  const [editing, setEditing] = useState(false);
  const approve = useMutation({
    mutationFn: () => api.approveAnalysisPlan(slug, plan.id),
    onSuccess: onChanged,
  });
  const run = useMutation({
    mutationFn: () => api.runAnalysisPlan(slug, plan.id),
    onSuccess: (result: AnalysisResult) => {
      onViewResults(plan.id, result.id);
    },
  });
  const runErr = run.error as ApiRequestError | null;

  return (
    <li className="rounded-lg border border-line bg-surface/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] font-medium text-fg">{plan.business_id}</span>
        <Badge tone={plan.status === "approved" ? "success" : "neutral"}>
          {plan.status === "approved" ? dict.dataShared.approved : dict.dataShared.draft}
        </Badge>
        <Badge tone="accent">{plan.method}</Badge>
        <span className="text-sm text-fg">{plan.business_question}</span>
        <div className="ms-auto flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setEditing((v) => !v)}>
            {editing ? dict.dataShared.close : dict.dataShared.edit}
          </Button>
          {plan.status === "draft" && (
            <Button size="sm" loading={approve.isPending} onClick={() => approve.mutate()}>
              {dict.dataMetrics.approve}
            </Button>
          )}
          {plan.status === "approved" && (
            <Button size="sm" loading={run.isPending} onClick={() => run.mutate()}>
              {dict.dataQueries.execute}
            </Button>
          )}
        </div>
      </div>
      {runErr && <p role="alert" className="mt-2 text-sm text-danger">{runErr.message}</p>}
      {plan.results.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-fg-subtle">
          <span>{dict.dataAnalysis.runHistory}</span>
          {plan.results.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => onViewResults(plan.id, r.id)}
              className="rounded-sm border border-line bg-surface px-1.5 py-0.5 font-mono hover:border-accent hover:text-fg"
            >
              {interpolate(dict.dataAnalysis.findingsCount, {
                n: String(r.findings_count),
                when: new Date(r.created_at).toLocaleString(),
              })}
            </button>
          ))}
        </div>
      )}
      {editing && (
        <div className="mt-4">
          <PlanEditorForm
            slug={slug} metrics={metrics} initial={plan}
            onSaved={(p) => { onChanged(p); setEditing(false); }}
            onCancel={() => setEditing(false)}
          />
        </div>
      )}
    </li>
  );
}

function PlansTab({
  slug, metrics, onViewResults,
}: {
  slug: string;
  metrics: MetricDefinition[];
  onViewResults: (planId: string, resultId: string) => void;
}) {
  const { dict } = useLanguage();
  const qc = useQueryClient();
  const [question, setQuestion] = useState("");
  const [creating, setCreating] = useState(false);

  const list = useQuery({
    queryKey: ["analysis-plans", slug],
    queryFn: () => api.listAnalysisPlans(slug),
    retry: false,
  });
  const generate = useMutation({
    mutationFn: () => api.generateAnalysisPlan(slug, question),
    onSuccess: (p) => {
      qc.setQueryData<AnalysisPlan[]>(["analysis-plans", slug], (prev) => (prev ? [...prev, p] : [p]));
      setQuestion("");
    },
  });
  const genErr = generate.error as ApiRequestError | null;

  function replace(p: AnalysisPlan) {
    qc.setQueryData<AnalysisPlan[]>(["analysis-plans", slug], (prev) =>
      prev ? prev.map((x) => (x.id === p.id ? p : x)) : prev,
    );
  }
  function added(p: AnalysisPlan) {
    qc.setQueryData<AnalysisPlan[]>(["analysis-plans", slug], (prev) => (prev ? [...prev, p] : [p]));
    setCreating(false);
  }

  return (
    <div className="grid gap-6">
      <div className="grid gap-3 rounded-xl border border-line bg-surface/40 p-5">
        <Field htmlFor="an-question" label={dict.dataAnalysis.planQuestionHint}>
          <input
            id="an-question" type="text" className={inputClass}
            placeholder={dict.dataAnalysis.planQuestionPlaceholder}
            value={question} onChange={(e) => setQuestion(e.target.value)}
          />
        </Field>
        {genErr?.code === "missing_api_key" && <AiUnconfiguredNotice />}
        {genErr && genErr.code !== "missing_api_key" && (
          <p role="alert" className="text-sm text-danger">{genErr.message}</p>
        )}
        {genErr?.code === "no_approved_metrics" && (
          <p className="text-sm text-fg-subtle">{dict.dataAnalysis.approveKpiFirst}</p>
        )}
        <div className="flex gap-2">
          <Button size="sm" loading={generate.isPending} onClick={() => generate.mutate()}>
            {dict.dataAnalysis.generatePlanAi}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setCreating((v) => !v)}>
            {creating ? dict.common.cancel : dict.dataAnalysis.createManually}
          </Button>
        </div>
        {creating && (
          <PlanEditorForm
            slug={slug} metrics={metrics} onSaved={added} onCancel={() => setCreating(false)}
          />
        )}
      </div>

      {list.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : list.isError ? (
        <EmptyState title={interpolate(dict.dataShared.couldntLoad, { thing: dict.dataAnalysis.tabPlans })} description={(list.error as ApiRequestError).message} />
      ) : !list.data || list.data.length === 0 ? (
        <p className="text-sm text-fg-subtle">{dict.dataAnalysis.noPlansYet}</p>
      ) : (
        <ul className="grid gap-3">
          {list.data.map((p) => (
            <PlanCard
              key={p.id} slug={slug} plan={p} metrics={metrics}
              onChanged={replace} onViewResults={onViewResults}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

// =====================================================================
// Results + Insights (share a selected AnalysisResult)
// =====================================================================

function FindingCard({ f, dict }: { f: AnalysisResult["findings"][number]; dict: Dictionary }) {
  return (
    <li className="rounded-lg border border-accent/30 bg-accent/5 p-3">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[11px] font-medium text-fg">{f.id}</span>
        <Badge tone="success">{dict.dataAnalysis.computedFact}</Badge>
      </div>
      <p className="mt-1 text-sm font-medium text-fg">{f.statement}</p>
      {Object.keys(f.metric_values).length > 0 && (
        <pre dir="ltr" className="mt-2 overflow-x-auto text-start font-mono text-[11px] text-fg-muted">
          {JSON.stringify(f.metric_values, null, 0)}
        </pre>
      )}
      {f.breakdown.length > 0 && (
        <div className="mt-2 overflow-x-auto rounded-md border border-line">
          <table className="w-full border-collapse text-start text-xs">
            <tbody>
              {f.breakdown.slice(0, 20).map((row, i) => (
                <tr key={i} className="border-t border-line first:border-t-0">
                  {Object.entries(row).map(([k, v]) => (
                    <td key={k} className="px-2 py-1 text-fg-muted">{String(v)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 flex flex-wrap gap-1 text-[11px] text-fg-subtle">
        <span>{dict.dataAnalysis.evidence}</span>
        {[f.evidence.analysis_plan_ref, ...f.evidence.kpi_refs].map((r) => (
          <span key={r} className="rounded-sm border border-line bg-surface px-1 font-mono">{r}</span>
        ))}
      </p>
    </li>
  );
}

function InsightCard({ slug, insight, onChanged, dict }: { slug: string; insight: Insight; onChanged: (i: Insight) => void; dict: Dictionary }) {
  const accept = useMutation({
    mutationFn: () => api.acceptInsight(slug, insight.id),
    onSuccess: onChanged,
  });
  return (
    <li className="rounded-lg border-s-4 border-s-warning border border-line bg-surface/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] font-medium text-fg">{insight.business_id}</span>
        <Badge tone={insight.status === "accepted" ? "success" : "warning"}>
          {insight.status === "accepted" ? dict.dataAnalysis.accepted : dict.dataShared.draft}
        </Badge>
        <Badge tone="neutral">{interpolate(dict.dataAnalysis.confidence, { level: insight.confidence })}</Badge>
        {insight.status === "draft" && (
          <Button size="sm" className="ms-auto" loading={accept.isPending} onClick={() => accept.mutate()}>
            {dict.dataAnalysis.accept}
          </Button>
        )}
      </div>
      <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">{dict.dataAnalysis.factLabel}</p>
      <p className="text-sm text-fg">{insight.fact}</p>
      <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">{dict.dataAnalysis.interpretationLabel}</p>
      <p className="text-sm italic text-fg">{insight.interpretation}</p>
      {insight.recommendation && (
        <>
          <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">{dict.dataAnalysis.recommendationLabel}</p>
          <p className="text-sm italic text-fg-muted">{insight.recommendation}</p>
        </>
      )}
      {insight.caveats.length > 0 && (
        <ul className="mt-2 list-inside list-disc text-xs text-fg-subtle">
          {insight.caveats.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      )}
      <p className="mt-2 flex flex-wrap gap-1 text-[11px] text-fg-subtle">
        <span>{dict.dataAnalysis.basedOn}</span>
        {insight.supporting_finding_ids.map((fid) => (
          <span key={fid} className="rounded-sm border border-line bg-surface px-1 font-mono">{fid}</span>
        ))}
      </p>
    </li>
  );
}

function ResultsAndInsights({
  slug, resultId,
}: {
  slug: string;
  resultId: string;
}) {
  const { dict } = useLanguage();
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["analysis-result", slug, resultId],
    queryFn: () => api.getAnalysisResult(slug, resultId),
  });
  const generate = useMutation({
    mutationFn: () => api.generateInsights(slug, resultId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analysis-result", slug, resultId] }),
  });
  const genErr = generate.error as ApiRequestError | null;

  function replaceInsight(i: Insight) {
    qc.setQueryData<AnalysisResult>(["analysis-result", slug, resultId], (prev) =>
      prev ? { ...prev, insights: prev.insights.map((x) => (x.id === i.id ? i : x)) } : prev,
    );
  }

  if (query.isPending) return <Skeleton className="h-40 w-full" />;
  if (query.isError) {
    return <EmptyState title={interpolate(dict.dataShared.couldntLoad, { thing: dict.dataAnalysis.tabResults })} description={(query.error as ApiRequestError).message} />;
  }
  const result = query.data;

  return (
    <div className="grid gap-6">
      <section className="grid gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
          {interpolate(dict.dataAnalysis.findingsHeading, { planId: result.plan_business_id })}
        </h3>
        <ul className="grid gap-2">
          {result.findings.map((f) => <FindingCard key={f.id} f={f} dict={dict} />)}
        </ul>
        {result.data_caveats.length > 0 && (
          <div className="rounded-md border border-warning/30 bg-warning/5 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-warning">{dict.dataAnalysis.dataCaveats}</p>
            <ul className="mt-1 list-inside list-disc text-xs text-fg-muted">
              {result.data_caveats.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </div>
        )}
      </section>

      <section className="grid gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">{dict.dataAnalysis.insightsHeading}</h3>
          <Button size="sm" variant="outline" loading={generate.isPending} onClick={() => generate.mutate()}>
            {dict.dataAnalysis.generateInsightsAi}
          </Button>
        </div>
        {genErr?.code === "missing_api_key" && <AiUnconfiguredNotice />}
        {genErr && genErr.code !== "missing_api_key" && (
          <p role="alert" className="text-sm text-danger">{genErr.message}</p>
        )}
        {result.insights.length === 0 ? (
          <p className="text-sm text-fg-subtle">{dict.dataAnalysis.noInsightsYet}</p>
        ) : (
          <ul className="grid gap-2">
            {result.insights.map((i) => (
              <InsightCard key={i.id} slug={slug} insight={i} onChanged={replaceInsight} dict={dict} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

// =====================================================================
// Dashboard tab
// =====================================================================

function PanelCard({ p, dict }: { p: DashboardPanel; dict: Dictionary }) {
  return (
    <li className="rounded-lg border border-line bg-surface/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] font-medium text-fg">{p.id}</span>
        <Badge tone="accent">{p.viz_type}</Badge>
        <span className="text-sm text-fg">{p.title}</span>
      </div>
      <p className="mt-1 flex flex-wrap gap-1 text-[11px] text-fg-subtle">
        <span>{dict.dataAnalysis.metricsLabel}</span>
        {p.metric_refs.map((r) => (
          <span key={r} className="rounded-sm border border-line bg-surface px-1 font-mono">{r}</span>
        ))}
        {p.dimension && <span>{interpolate(dict.dataAnalysis.dimensionLabel, { value: p.dimension })}</span>}
        {p.comparison && <span>{interpolate(dict.dataAnalysis.comparisonLabel, { value: p.comparison })}</span>}
      </p>
      {p.notes && <p className="mt-1 text-xs text-fg-muted">{p.notes}</p>}
    </li>
  );
}

function DashboardTab({ slug, metrics }: { slug: string; metrics: MetricDefinition[] }) {
  const { dict } = useLanguage();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Partial<DashboardBlueprintContent> | null>(null);

  const query = useQuery({
    queryKey: ["dashboard", slug],
    queryFn: () => api.getDashboard(slug),
    retry: false,
  });
  const set = (d: typeof query.data) => qc.setQueryData(["dashboard", slug], d);

  const generate = useMutation({
    mutationFn: () => api.generateDashboard(slug),
    onSuccess: set,
  });
  const approve = useMutation({
    mutationFn: () => api.approveDashboard(slug),
    onSuccess: (d) => { set(d); qc.invalidateQueries({ queryKey: ["project", slug] }); },
  });
  const save = useMutation({
    mutationFn: () => api.updateDashboard(slug, draft || {}),
    onSuccess: (d) => { set(d); setEditing(false); },
  });
  const buildPrompt = useMutation({
    mutationFn: () => api.generateDashboardBuildPrompt(slug),
    onSuccess: set,
  });

  const genErr = generate.error as ApiRequestError | null;
  const saveErr = save.error as ApiRequestError | null;
  const promptErr = buildPrompt.error as ApiRequestError | null;
  const approvedKpis = metrics.filter((m) => m.status === "approved");

  if (query.isPending) return <Skeleton className="h-40 w-full" />;
  if (query.isError) {
    return <EmptyState title={interpolate(dict.dataShared.couldntLoad, { thing: dict.dataAnalysis.tabDashboard })} description={(query.error as ApiRequestError).message} />;
  }
  const dash = query.data;

  return (
    <div className="grid gap-6">
      {!dash.content ? (
        <div className="mx-auto grid max-w-md justify-items-center gap-4 py-10 text-center">
          <p className="text-sm text-fg-muted">
            {dict.dataAnalysis.dashboardIntro}
          </p>
          <Button loading={generate.isPending} onClick={() => generate.mutate()}>
            {dict.dataAnalysis.generateDashboardAi}
          </Button>
          {genErr?.code === "missing_api_key" && <AiUnconfiguredNotice />}
          {genErr && genErr.code !== "missing_api_key" && (
            <p role="alert" className="text-sm text-danger">{genErr.message}</p>
          )}
          {genErr?.code === "no_approved_metrics" && (
            <p className="text-sm text-fg-subtle">{dict.dataAnalysis.approveKpiFirst}</p>
          )}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Badge tone={dash.approved ? "success" : "neutral"}>{dash.approved ? dict.dataShared.approved : dict.dataShared.draft}</Badge>
              <span className="text-sm text-fg">{dash.content.audience} — {dash.content.decision_use_case}</span>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => { setEditing((v) => !v); setDraft(dash.content); }}>
                {editing ? dict.dataShared.close : dict.dataShared.edit}
              </Button>
              <Button size="sm" variant="outline" loading={generate.isPending} onClick={() => generate.mutate()}>
                {dict.dataShared.regenerate}
              </Button>
              {!dash.approved && (
                <Button size="sm" loading={approve.isPending} onClick={() => approve.mutate()}>
                  {dict.dataMetrics.approve}
                </Button>
              )}
            </div>
          </div>

          {editing && draft && (
            <div className="grid gap-3 rounded-lg border border-line bg-bg/40 p-4">
              <Field htmlFor="dash-audience" label={dict.dataAnalysis.fieldAudience}>
                <input
                  id="dash-audience" type="text" className={inputClass}
                  value={draft.audience || ""} onChange={(e) => setDraft({ ...draft, audience: e.target.value })}
                />
              </Field>
              <Field htmlFor="dash-decision" label={dict.dataAnalysis.fieldDecisionUseCase}>
                <Textarea
                  id="dash-decision" value={draft.decision_use_case || ""}
                  onChange={(e) => setDraft({ ...draft, decision_use_case: e.target.value })}
                />
              </Field>
              <Field htmlFor="dash-cadence" label={dict.dataAnalysis.fieldRefreshCadence}>
                <input
                  id="dash-cadence" type="text" className={inputClass}
                  value={draft.refresh_cadence || ""} onChange={(e) => setDraft({ ...draft, refresh_cadence: e.target.value })}
                />
              </Field>
              <p className="text-xs text-fg-subtle">
                {interpolate(dict.dataAnalysis.panelsEditNote, {
                  kpis: approvedKpis.map((m) => m.business_id).join(", ") || "none",
                })}
              </p>
              {saveErr && <p role="alert" className="text-sm text-danger">{saveErr.message}</p>}
              <div className="flex gap-2">
                <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>{dict.common.save}</Button>
                <Button size="sm" variant="outline" onClick={() => setEditing(false)}>{dict.common.cancel}</Button>
              </div>
            </div>
          )}

          <section className="grid gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">{dict.dataAnalysis.panelsHeading}</h3>
            <p className="text-xs text-fg-subtle">
              {dict.dataAnalysis.panelsSubtitle}
            </p>
            <ul className="grid gap-2">
              {dash.content.panels.map((p) => <PanelCard key={p.id} p={p} dict={dict} />)}
            </ul>
          </section>

          <section className="grid gap-2">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
                {dict.dataAnalysis.buildPromptHeading}
              </h3>
              <Button
                size="sm" variant="outline" disabled={!dash.approved}
                loading={buildPrompt.isPending} onClick={() => buildPrompt.mutate()}
              >
                {dict.dataAnalysis.generateBuildPromptAi}
              </Button>
            </div>
            {!dash.approved && (
              <p className="text-sm text-fg-subtle">{dict.dataAnalysis.approveBlueprintFirst}</p>
            )}
            {promptErr?.code === "missing_api_key" && <AiUnconfiguredNotice />}
            {promptErr && promptErr.code !== "missing_api_key" && (
              <p role="alert" className="text-sm text-danger">{promptErr.message}</p>
            )}
            {dash.latest_build_prompt && (
              <div className="grid gap-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs text-fg-subtle" dir="ltr">
                    {interpolate(dict.taskWorkspace.generatedAt, { when: formatDateTime(dash.latest_build_prompt.created_at) })}
                    {dash.latest_build_prompt.model ? ` · ${dash.latest_build_prompt.model}` : ""}
                  </span>
                  <CopyButton text={dash.latest_build_prompt.content} />
                </div>
                <pre dir="ltr" className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-bg-subtle p-4 text-start font-mono text-xs leading-relaxed text-fg-muted">
                  {dash.latest_build_prompt.content}
                </pre>
                <p className="text-xs text-fg-subtle">
                  {dict.dataAnalysis.buildPromptFooter}
                </p>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

// =====================================================================
// Root view
// =====================================================================

export function DataAnalysisView({ initialProject }: { initialProject: Project }) {
  const { dict } = useLanguage();
  const slug = initialProject.slug;
  const [tab, setTab] = useState<Tab>("plans");
  const [selectedResultId, setSelectedResultId] = useState<string | null>(null);

  const metrics = useQuery({
    queryKey: ["metrics", slug],
    queryFn: () => api.listMetrics(slug),
  });

  function viewResults(_planId: string, resultId: string) {
    setSelectedResultId(resultId);
    setTab("results");
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: "plans", label: dict.dataAnalysis.tabPlans },
    { id: "results", label: dict.dataAnalysis.tabResults },
    { id: "insights", label: dict.dataAnalysis.tabInsights },
    { id: "dashboard", label: dict.dataAnalysis.tabDashboard },
  ];

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.dataShared.dataProject}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{dict.dataAnalysis.title}</h1>
        <p className="text-sm text-fg-muted">{dict.journeyData.analysis.label}</p>
        <p className="text-sm leading-relaxed text-fg-muted">
          {dict.dataAnalysis.introPart1}
          <span className="font-medium text-fg">{dict.concepts.observedFactPlural}</span>
          {dict.dataAnalysis.introPart2}
          <span className="font-medium text-fg">{dict.concepts.aiInterpretation}</span>
          {dict.dataAnalysis.introPart3}
          <span className="font-medium text-fg">{dict.concepts.recommendation}</span>
          {dict.dataAnalysis.introPart4}
        </p>
      </div>

      <div className="mb-6 flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={
              "border-b-2 px-3 py-2 text-sm font-medium transition-colors " +
              (tab === t.id
                ? "border-accent text-fg"
                : "border-transparent text-fg-subtle hover:text-fg-muted")
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {metrics.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <>
          {tab === "plans" && (
            <PlansTab slug={slug} metrics={metrics.data || []} onViewResults={viewResults} />
          )}
          {tab === "results" &&
            (selectedResultId ? (
              <ResultsAndInsights slug={slug} resultId={selectedResultId} />
            ) : (
              <p className="text-sm text-fg-subtle">
                {dict.dataAnalysis.runPlanHint}
              </p>
            ))}
          {tab === "insights" &&
            (selectedResultId ? (
              <ResultsAndInsights slug={slug} resultId={selectedResultId} />
            ) : (
              <p className="text-sm text-fg-subtle">
                {dict.dataAnalysis.selectRunHint}
              </p>
            ))}
          {tab === "dashboard" && <DashboardTab slug={slug} metrics={metrics.data || []} />}
        </>
      )}

      <div className="mt-8">
        <DataLineagePanel slug={slug} />
      </div>
    </>
  );
}
