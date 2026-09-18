"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type { Dataset, SourceInterpretationContent } from "@/lib/api/types";
import { AiUnconfiguredNotice } from "@/components/feedback/ai-unconfigured-notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StringListEditor } from "@/components/ui/editor-primitives";
import { useLanguage } from "@/lib/i18n";

export function SourceInterpretationPanel({
  slug,
  dataset,
  onChanged,
}: {
  slug: string;
  dataset: Dataset;
  onChanged: (ds: Dataset) => void;
}) {
  const { dict } = useLanguage();
  const content = dataset.interpretation?.content;
  const approved = !!dataset.interpretation_approved_at;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<SourceInterpretationContent | null>(null);

  const generate = useMutation({
    mutationFn: () => api.generateSourceInterpretation(slug, dataset.id),
    onSuccess: (ds) => {
      onChanged(ds);
      setEditing(false);
    },
  });
  const save = useMutation({
    mutationFn: (value: SourceInterpretationContent) =>
      api.updateSourceInterpretation(slug, dataset.id, value),
    onSuccess: (ds) => {
      onChanged(ds);
      setEditing(false);
    },
  });
  const approve = useMutation({
    mutationFn: () => api.approveSourceInterpretation(slug, dataset.id),
    onSuccess: onChanged,
  });

  const genErr = generate.error as ApiRequestError | null;
  const saveErr = save.error as ApiRequestError | null;

  if (dataset.status !== "profiled") {
    return (
      <p className="text-sm text-fg-subtle">
        {dict.sourceInterpretation.needsProfileHint}
      </p>
    );
  }

  if (!content) {
    return (
      <div className="grid gap-2">
        <p className="text-sm leading-relaxed text-fg-muted">
          {dict.sourceInterpretation.generateBody}
        </p>
        <div>
          <Button
            size="sm"
            loading={generate.isPending}
            onClick={() => generate.mutate()}
          >
            {dict.sourceInterpretation.generateCta}
          </Button>
        </div>
        {genErr?.code === "missing_api_key" && <AiUnconfiguredNotice />}
        {genErr && genErr.code !== "missing_api_key" && (
          <p role="alert" className="text-sm text-danger">
            {genErr.message}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      <p className="text-xs text-fg-subtle">
        {dict.sourceInterpretation.aiProposedHint}
      </p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge tone={approved ? "success" : "neutral"}>
          {approved ? dict.sourceInterpretation.approvedBadge : dict.sourceInterpretation.draftBadge}
        </Badge>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => generate.mutate()}
            loading={generate.isPending}
          >
            {dict.dataShared.regenerate}
          </Button>
          {!editing && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setDraft(structuredClone(content));
                setEditing(true);
              }}
            >
              {dict.dataShared.edit}
            </Button>
          )}
          {!approved && !editing && (
            <Button
              size="sm"
              loading={approve.isPending}
              onClick={() => approve.mutate()}
            >
              {dict.sourceInterpretation.approveCta}
            </Button>
          )}
        </div>
      </div>

      {editing && draft ? (
        <div className="grid gap-4 rounded-lg border border-line bg-bg/40 p-4">
          <label className="grid gap-1 text-sm">
            <span className="font-medium text-fg">{dict.sourceInterpretation.fieldBusinessEntity}</span>
            <input
              value={draft.business_entity}
              onChange={(e) =>
                setDraft({ ...draft, business_entity: e.target.value })
              }
              className="rounded-md border border-line bg-bg-subtle px-3 py-2 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
          </label>
          <label className="grid gap-1 text-sm">
            <span className="font-medium text-fg">{dict.sourceInterpretation.fieldGrain}</span>
            <input
              value={draft.grain}
              onChange={(e) => setDraft({ ...draft, grain: e.target.value })}
              className="rounded-md border border-line bg-bg-subtle px-3 py-2 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
          </label>
          <div className="grid gap-1">
            <span className="text-sm font-medium text-fg">{dict.sourceInterpretation.fieldKeyColumns}</span>
            <StringListEditor
              value={draft.key_columns}
              onChange={(v) => setDraft({ ...draft, key_columns: v })}
              itemNoun={dict.sourceInterpretation.itemNounColumn}
            />
          </div>
          <div className="grid gap-1">
            <span className="text-sm font-medium text-fg">{dict.sourceInterpretation.fieldCaveats}</span>
            <StringListEditor
              value={draft.caveats}
              onChange={(v) => setDraft({ ...draft, caveats: v })}
              itemNoun={dict.sourceInterpretation.itemNounCaveat}
            />
          </div>
          {saveErr && (
            <p role="alert" className="text-sm text-danger">
              {saveErr.message}
            </p>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              loading={save.isPending}
              onClick={() => save.mutate(draft)}
            >
              {dict.common.save}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={save.isPending}
              onClick={() => setEditing(false)}
            >
              {dict.common.cancel}
            </Button>
          </div>
        </div>
      ) : (
        <dl className="grid gap-2 rounded-lg border border-line bg-bg/40 p-4 text-sm">
          <div>
            <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
              {dict.sourceInterpretation.fieldBusinessEntity}
            </dt>
            <dd className="text-fg-muted">{content.business_entity}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
              {dict.sourceInterpretation.fieldGrain}
            </dt>
            <dd className="text-fg-muted">{content.grain}</dd>
          </div>
          {content.key_columns.length > 0 && (
            <div>
              <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
                {dict.sourceInterpretation.fieldKeyColumns}
              </dt>
              <dd className="font-mono text-xs text-fg-muted" dir="ltr">
                {content.key_columns.join(", ")}
              </dd>
            </div>
          )}
          {content.column_meanings.length > 0 && (
            <div>
              <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
                {dict.sourceInterpretation.columnMeanings}
              </dt>
              <dd>
                <ul className="grid gap-0.5 text-fg-muted">
                  {content.column_meanings.map((cm) => (
                    <li key={cm.column}>
                      <span className="font-mono text-xs text-fg-subtle" dir="ltr">
                        {cm.column}
                      </span>{" "}
                      — {cm.meaning}
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          )}
          {content.caveats.length > 0 && (
            <div>
              <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
                {dict.sourceInterpretation.fieldCaveats}
              </dt>
              <dd>
                <ul className="grid list-disc gap-0.5 ps-5 text-fg-muted">
                  {content.caveats.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </dd>
            </div>
          )}
          {content.sensitivity_flags.length > 0 && (
            <div>
              <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
                {dict.sourceInterpretation.sensitivity}
              </dt>
              <dd className="flex flex-wrap gap-1.5">
                {content.sensitivity_flags.map((f) => (
                  <Badge key={f.column} tone="warning">
                    {f.column}: {f.kind}
                  </Badge>
                ))}
              </dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}
