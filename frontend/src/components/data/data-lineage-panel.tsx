"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import { inputClass } from "@/components/ui/editor-primitives";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { interpolate, useLanguage } from "@/lib/i18n";

/**
 * Deterministic lineage lookup (Phase I-3) — trace any node id (a dataset id,
 * DQ-xx / QR-xx / TX-xx / KPI-xx / Q-xx business id, or "data_brief") to what
 * feeds it and what it feeds. Read-only; no graph is stored, just walked.
 */
export function DataLineagePanel({ slug }: { slug: string }) {
  const { dict } = useLanguage();
  const [node, setNode] = useState("");

  const trace = useMutation({
    mutationFn: (n: string) => api.getLineage(slug, n),
  });

  const err = trace.error as ApiRequestError | null;
  const result = trace.data;

  return (
    <section className="rounded-xl border border-line bg-surface/40 p-5">
      <h4 className="text-xs font-semibold uppercase tracking-[0.08em] text-fg-subtle">
        {dict.dataLineage.heading}
        <span className="ms-2 font-normal normal-case text-fg-subtle">
          {dict.dataLineage.subtitle}
        </span>
      </h4>
      <p className="mt-1 text-sm text-fg-muted">
        {dict.dataLineage.hint}{" "}
        <code dir="ltr">KPI-01</code>, <code dir="ltr">Q-01</code>,{" "}
        <code dir="ltr">QR-01</code>, <code dir="ltr">TX-01</code>, or{" "}
        <code dir="ltr">data_brief</code>.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <div className="min-w-48 flex-1">
          <Field htmlFor="lineage-node" label={dict.dataLineage.fieldNode}>
            <input
              id="lineage-node"
              type="text"
              dir="ltr"
              className={inputClass}
              value={node}
              onChange={(e) => setNode(e.target.value)}
              placeholder={dict.dataLineage.placeholder}
            />
          </Field>
        </div>
        <Button
          size="sm"
          variant="outline"
          loading={trace.isPending}
          disabled={!node.trim()}
          onClick={() => trace.mutate(node.trim())}
        >
          {dict.dataLineage.trace}
        </Button>
      </div>
      {err && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {err.message}
        </p>
      )}
      {result && !result.exists && (
        <p className="mt-2 text-sm text-fg-subtle">
          {interpolate(dict.dataLineage.notKnown, { node: result.node })}
        </p>
      )}
      {result && result.exists && (
        <div className="mt-3 grid gap-3 text-sm">
          <div>
            <p className="text-xs font-medium text-fg-subtle">{dict.dataLineage.upstreamHeading}</p>
            {result.upstream.length === 0 ? (
              <p className="text-xs text-fg-subtle">{dict.dataLineage.none}</p>
            ) : (
              <p className="flex flex-wrap gap-1" dir="ltr">
                {result.upstream.map((n) => (
                  <span key={n} className="rounded-sm border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px]">
                    {n}
                  </span>
                ))}
              </p>
            )}
          </div>
          <div>
            <p className="text-xs font-medium text-fg-subtle">{dict.dataLineage.downstreamHeading}</p>
            {result.downstream.length === 0 ? (
              <p className="text-xs text-fg-subtle">{dict.dataLineage.none}</p>
            ) : (
              <p className="flex flex-wrap gap-1" dir="ltr">
                {result.downstream.map((n) => (
                  <span key={n} className="rounded-sm border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px]">
                    {n}
                  </span>
                ))}
              </p>
            )}
          </div>
          {result.edges.length > 0 && (
            <div>
              <p className="text-xs font-medium text-fg-subtle">{dict.dataLineage.edgesHeading}</p>
              <ul dir="ltr" className="mt-1 grid gap-0.5 text-start font-mono text-[11px] text-fg-muted">
                {result.edges.map((e, i) => (
                  <li key={i}>
                    {e.from} —{e.type}→ {e.to}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
