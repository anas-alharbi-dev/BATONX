"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiRequestError } from "@/lib/api/client";
import type { Project, TransformationView as TView } from "@/lib/api/types";
import { AiUnconfiguredNotice } from "@/components/feedback/ai-unconfigured-notice";
import { EmptyState } from "@/components/feedback/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ArtifactApprovedNotice } from "@/components/workspace/artifact-approved-notice";
import { interpolate, useLanguage } from "@/lib/i18n";

export function DataTransformationView({
  initialProject,
}: {
  initialProject: Project;
}) {
  const { dict } = useLanguage();
  const slug = initialProject.slug;
  const qc = useQueryClient();
  const [confirmRegen, setConfirmRegen] = useState(false);

  const query = useQuery({
    queryKey: ["transformation", slug],
    queryFn: () => api.getTransformation(slug),
    retry: false,
  });
  const set = (t: TView) => qc.setQueryData(["transformation", slug], t);

  const generate = useMutation({
    mutationFn: () => api.generateTransformation(slug),
    onSuccess: (t) => {
      set(t);
      setConfirmRegen(false);
    },
  });
  const approve = useMutation({
    mutationFn: () => api.approveTransformation(slug),
    onSuccess: (t) => {
      set(t);
      qc.invalidateQueries({ queryKey: ["project", slug] });
    },
  });
  const preview = useMutation({
    mutationFn: () => api.previewTransformation(slug),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["transformation", slug] }),
  });

  const t = query.data;
  const genErr = generate.error as ApiRequestError | null;
  const previewErr = preview.error as ApiRequestError | null;
  const approveErr = approve.error as ApiRequestError | null;
  const latestPreview =
    (preview.data?.preview ?? t?.latest_preview?.preview) || null;

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.dataShared.dataProject}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {dict.dataTransformation.title}
        </h1>
        <p className="text-sm text-fg-muted">{dict.journeyData.transformation_plan.label}</p>
        <p className="text-sm leading-relaxed text-fg-muted">
          {dict.dataTransformation.intro}
        </p>
      </div>

      {query.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : query.isError ? (
        <EmptyState
          title={interpolate(dict.dataShared.couldntLoad, { thing: dict.dataTransformation.title })}
          description={(query.error as ApiRequestError).message}
        />
      ) : !t || !t.content ? (
        <div className="mx-auto grid max-w-md justify-items-center gap-4 py-14 text-center">
          <h2 className="text-lg font-semibold text-fg">
            {dict.dataTransformation.generateTitle}
          </h2>
          <p className="text-sm leading-relaxed text-fg-muted">
            {dict.dataTransformation.generateBody}
          </p>
          <Button
            size="lg"
            loading={generate.isPending}
            onClick={() => generate.mutate()}
          >
            {dict.dataTransformation.generateCta}
          </Button>
          {genErr?.code === "missing_api_key" && (
            <div className="w-full text-start">
              <AiUnconfiguredNotice />
            </div>
          )}
          {genErr && genErr.code !== "missing_api_key" && (
            <p role="alert" className="text-sm text-danger">
              {genErr.message}
            </p>
          )}
        </div>
      ) : (
        <div className="grid gap-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Badge tone={t.approved ? "success" : "neutral"}>
              {t.approved ? dict.dataShared.approved : dict.dataShared.draft}
            </Badge>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirmRegen(true)}
              >
                {dict.dataShared.regenerate}
              </Button>
              <Button
                size="sm"
                variant="outline"
                loading={preview.isPending}
                onClick={() => preview.mutate()}
              >
                {dict.dataTransformation.runPreview}
              </Button>
              {!t.approved && (
                <Button
                  size="sm"
                  loading={approve.isPending}
                  onClick={() => approve.mutate()}
                >
                  {dict.dataTransformation.approvePlan}
                </Button>
              )}
            </div>
          </div>
          {approveErr && (
            <p role="alert" className="text-sm text-danger">
              {approveErr.message}
            </p>
          )}

          <section className="grid gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
              {dict.dataTransformation.stepsHeading}
            </h2>
            <ol className="grid gap-2">
              {t.content.steps.map((s) => (
                <li
                  key={s.id}
                  className="rounded-lg border border-line bg-surface/40 p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[11px] font-medium text-fg">
                      {s.id}
                    </span>
                    <span className="font-mono text-xs text-accent" dir="ltr">{s.op}</span>
                    <span className="text-xs text-fg-subtle" dir="ltr">
                      → {s.output_name}
                    </span>
                    {s.related_quality_rules.map((qr) => (
                      <span
                        key={qr}
                        className="rounded-sm border border-line bg-surface px-1 font-mono text-[11px] text-fg-subtle"
                      >
                        {qr}
                      </span>
                    ))}
                  </div>
                  <p className="mt-1 font-mono text-[11px] text-fg-muted" dir="ltr">
                    {JSON.stringify(s.params)}
                  </p>
                  {s.rationale && (
                    <p className="mt-1 text-xs text-fg-muted">{s.rationale}</p>
                  )}
                </li>
              ))}
            </ol>
          </section>

          {t.rendered_sql && (
            <section className="grid gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
                {dict.dataTransformation.sqlHeading}
                <span className="ms-2 font-normal normal-case text-fg-subtle">
                  {dict.dataTransformation.sqlSubtitle}
                </span>
              </h2>
              <pre dir="ltr" className="max-h-72 overflow-auto rounded-lg border border-line bg-bg-subtle p-4 text-start font-mono text-xs leading-relaxed text-fg-muted">
                {t.rendered_sql}
              </pre>
            </section>
          )}

          <section className="grid gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
              {dict.dataTransformation.previewHeading}
              <span className="ms-2 font-normal normal-case text-fg-subtle">
                {dict.dataTransformation.previewSubtitle}
              </span>
            </h2>
            {previewErr && (
              <p role="alert" className="text-sm text-danger">
                {previewErr.message}
              </p>
            )}
            {latestPreview ? (
              <div className="grid gap-1">
                <p className="text-xs text-fg-muted">
                  {interpolate(dict.dataTransformation.rowCount, { n: String(latestPreview.row_count) })}
                  {latestPreview.truncated ? dict.dataTransformation.capped : ""}
                  {interpolate(dict.dataTransformation.columnsCount, { n: String(latestPreview.columns.length) })}
                </p>
                <div className="overflow-x-auto rounded-lg border border-line">
                  <table className="w-full border-collapse text-start text-xs">
                    <thead className="bg-surface/60 text-fg-subtle">
                      <tr>
                        {latestPreview.columns.map((c) => (
                          <th key={c} className="px-3 py-2 font-mono font-medium" dir="ltr">
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {latestPreview.rows.slice(0, 50).map((row, i) => (
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
            ) : (
              <p className="text-sm text-fg-subtle">
                {dict.dataTransformation.runPreviewHint}
              </p>
            )}
          </section>

          {t.approved && (
            <ArtifactApprovedNotice
              summary={dict.dataTransformation.nextSummary}
              nextLabel={dict.dataTransformation.nextLabel}
              nextHref={`/projects/${slug}/data-metrics`}
            />
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmRegen}
        title={dict.dataTransformation.regenerateTitle}
        description={
          t?.approved
            ? dict.dataTransformation.regenerateApprovedDesc
            : dict.dataTransformation.regenerateDraftDesc
        }
        confirmLabel={dict.dataShared.regenerate}
        tone="danger"
        busy={generate.isPending}
        onConfirm={() => generate.mutate()}
        onCancel={() => setConfirmRegen(false)}
      />
    </>
  );
}
