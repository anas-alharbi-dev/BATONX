"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type { Dataset, DatasetDetail, Project } from "@/lib/api/types";
import { EmptyState } from "@/components/feedback/states";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { ArtifactApprovedNotice } from "@/components/workspace/artifact-approved-notice";
import { formatDateTime } from "@/lib/format";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

import { ProfilingTable } from "./profiling-table";
import { SourceInterpretationPanel } from "./source-interpretation-panel";

const STATUS_TONE: Record<Dataset["status"], "neutral" | "accent" | "success" | "danger"> = {
  uploaded: "neutral",
  profiling: "accent",
  profiled: "success",
  failed: "danger",
};

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function DatasetCard({
  slug,
  dataset,
  onChanged,
  dict,
}: {
  slug: string;
  dataset: Dataset;
  onChanged: (ds: Dataset) => void;
  dict: Dictionary;
}) {
  const [detail, setDetail] = useState<DatasetDetail | null>(null);

  const profile = useMutation({
    mutationFn: () => api.profileDataset(slug, dataset.id),
    onSuccess: (d) => {
      setDetail(d);
      onChanged(d.dataset);
    },
  });
  const loadDetail = useQuery({
    queryKey: ["dataset", slug, dataset.id],
    queryFn: () => api.getDataset(slug, dataset.id),
    enabled: dataset.status === "profiled" && detail === null,
  });

  const run = detail?.profiling_run ?? loadDetail.data?.profiling_run ?? null;
  const profErr = profile.error as ApiRequestError | null;

  return (
    <div className="grid gap-4 rounded-xl border border-line bg-surface/40 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-fg-subtle uppercase" dir="ltr">
          {dataset.source_type}
        </span>
        <h3 className="text-sm font-medium text-fg">{dataset.name}</h3>
        <Badge tone={STATUS_TONE[dataset.status]}>
          {dataset.status === "uploaded"
            ? dict.dataSources.statusUploaded
            : dataset.status === "profiling"
              ? dict.dataSources.statusProfiling
              : dataset.status === "profiled"
                ? dict.dataSources.statusProfiled
                : dict.dataSources.statusFailed}
        </Badge>
        {dataset.sampled && <Badge tone="warning">{dict.dataSources.sampled}</Badge>}
        {(dataset.profiling_stale || dataset.interpretation_stale) && (
          <Badge tone="warning">{dict.dataSources.stale}</Badge>
        )}
        <span className="ms-auto text-xs text-fg-subtle">
          {bytes(dataset.size_bytes)} &middot;{" "}
          {interpolate(dict.dataSources.uploadedAt, { when: formatDateTime(dataset.uploaded_at) })}
        </span>
      </div>

      {dataset.status === "failed" && dataset.error && (
        <p role="alert" className="text-sm text-danger">
          {dataset.error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={dataset.status === "profiled" ? "outline" : "solid"}
          loading={profile.isPending}
          onClick={() => profile.mutate()}
        >
          {dataset.status === "profiled" ? dict.dataSources.rerunProfiling : dict.dataSources.runProfiling}
        </Button>
        {dataset.row_count != null && (
          <span className="text-xs text-fg-subtle">
            {interpolate(dict.dataSources.rowsColumns, {
              rows: dataset.row_count.toLocaleString(),
              cols: String(dataset.column_count),
            })}
          </span>
        )}
      </div>

      {profErr && (
        <p role="alert" className="text-sm text-danger">
          {profErr.message}
        </p>
      )}

      {run ? (
        <details className="group rounded-lg border border-line bg-bg/40" open>
          <summary className="cursor-pointer px-4 py-2.5 text-sm font-medium text-fg marker:content-none">
            {dict.dataSources.profilingResults}
          </summary>
          <div className="border-t border-line p-4">
            <ProfilingTable run={run} />
          </div>
        </details>
      ) : loadDetail.isFetching ? (
        <Skeleton className="h-24 w-full" />
      ) : null}

      {dataset.status === "profiled" && (
        <div className="rounded-lg border border-line bg-bg/40 p-4">
          <p className="mb-2 text-sm font-medium text-fg">{dict.dataSources.sourceInterpretation}</p>
          <SourceInterpretationPanel
            slug={slug}
            dataset={dataset}
            onChanged={onChanged}
          />
        </div>
      )}
    </div>
  );
}

export function DataSourcesView({ initialProject }: { initialProject: Project }) {
  const { dict } = useLanguage();
  const slug = initialProject.slug;
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const list = useQuery({
    queryKey: ["datasets", slug],
    queryFn: () => api.listDatasets(slug),
  });

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDataset(slug, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets", slug] });
      if (fileRef.current) fileRef.current.value = "";
    },
  });

  const uploadErr = upload.error as ApiRequestError | null;

  function replace(ds: Dataset) {
    qc.setQueryData<{ datasets: Dataset[] }>(["datasets", slug], (prev) =>
      prev
        ? { datasets: prev.datasets.map((d) => (d.id === ds.id ? ds : d)) }
        : prev,
    );
  }

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.dataShared.dataProject}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {dict.dataSources.title}
        </h1>
        <p className="text-sm text-fg-muted">{dict.journeyData.sources.label}</p>
        <p className="text-sm leading-relaxed text-fg-muted">
          {dict.dataSources.uploadHint}
        </p>
      </div>

      <div className="mb-8 grid gap-3 rounded-xl border border-line bg-surface/40 p-5">
        <label htmlFor="dataset-file" className="text-sm font-medium text-fg">
          {dict.dataSources.addSourceLabel}
        </label>
        <input
          id="dataset-file"
          ref={fileRef}
          type="file"
          accept=".csv,.json,text/csv,application/json"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload.mutate(f);
          }}
          className="text-sm text-fg-muted file:me-3 file:cursor-pointer file:rounded-md file:border file:border-line-strong file:bg-surface file:px-3 file:py-1.5 file:text-sm file:text-fg hover:file:bg-surface-hover"
        />
        {upload.isPending && (
          <p className="flex items-center gap-2 text-sm text-fg-muted">
            <Spinner className="size-4" /> {dict.dataSources.uploading}
          </p>
        )}
        {uploadErr && (
          <p role="alert" className="text-sm text-danger">
            {uploadErr.message}
          </p>
        )}
      </div>

      {list.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : list.data && list.data.datasets.length > 0 ? (
        <>
          <div className="grid gap-5">
            {list.data.datasets.map((d) => (
              <DatasetCard
                key={d.id}
                slug={slug}
                dataset={d}
                onChanged={replace}
                dict={dict}
              />
            ))}
          </div>
          {list.data.datasets.some((d) => d.status === "profiled") && (
            <ArtifactApprovedNotice
              summary={dict.dataSources.nextSummary}
              nextLabel={dict.dataSources.nextLabel}
              nextHref={`/projects/${slug}/data-quality`}
            />
          )}
        </>
      ) : (
        <EmptyState
          title={dict.dataSources.emptyTitle}
          description={dict.dataSources.emptyBody}
        >
          <Link
            href={`/projects/${slug}/data-overview`}
            className={buttonClasses("outline", "md")}
          >
            {dict.dataSources.backToBrief}
          </Link>
        </EmptyState>
      )}
    </>
  );
}
