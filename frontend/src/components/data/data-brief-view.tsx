"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type { DataBriefContent, Project } from "@/lib/api/types";
import { AiUnconfiguredNotice } from "@/components/feedback/ai-unconfigured-notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { StringListEditor } from "@/components/ui/editor-primitives";
import { Skeleton } from "@/components/ui/skeleton";
import { ArtifactApprovedNotice } from "@/components/workspace/artifact-approved-notice";
import { formatDateTime } from "@/lib/format";
import { useLanguage, type Dictionary } from "@/lib/i18n";

function prose(dict: Dictionary): { key: keyof DataBriefContent; label: string }[] {
  return [
    { key: "business_goal", label: dict.dataBrief.fieldBusinessGoal },
    { key: "decision_context", label: dict.dataBrief.fieldDecisionContext },
  ];
}
function lists(dict: Dictionary): { key: keyof DataBriefContent; label: string; noun: string }[] {
  return [
    { key: "audience", label: dict.dataBrief.fieldAudience, noun: dict.dataBrief.itemNounAudience },
    { key: "success_criteria", label: dict.dataBrief.fieldSuccessCriteria, noun: dict.dataBrief.itemNounCriterion },
    { key: "constraints", label: dict.dataBrief.fieldConstraints, noun: dict.dataBrief.itemNounConstraint },
    { key: "candidate_sources", label: dict.dataBrief.fieldCandidateSources, noun: dict.dataBrief.itemNounSource },
    { key: "out_of_scope", label: dict.dataBrief.fieldOutOfScope, noun: dict.dataBrief.itemNounOutOfScopeItem },
  ];
}

function emptyContent(dataGoal: string): DataBriefContent {
  return {
    business_goal: "",
    decision_context: "",
    audience: [],
    success_criteria: [],
    constraints: [],
    candidate_sources: [],
    out_of_scope: [],
    data_goal: dataGoal,
  };
}

export function DataBriefView({ initialProject }: { initialProject: Project }) {
  const { dict } = useLanguage();
  const [project, setProject] = useState(initialProject);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DataBriefContent | null>(null);
  const [confirmRegen, setConfirmRegen] = useState(false);

  const slug = project.slug;
  const content = project.data_brief?.content;
  const approved = !!project.data_brief_approved_at;

  const generate = useMutation({
    mutationFn: () => api.generateDataBrief(slug),
    onSuccess: (p) => {
      setProject(p);
      setEditing(false);
      setConfirmRegen(false);
    },
  });
  const save = useMutation({
    mutationFn: (value: DataBriefContent) => api.updateDataBrief(slug, value),
    onSuccess: (p) => {
      setProject(p);
      setEditing(false);
    },
  });
  const approve = useMutation({
    mutationFn: () => api.approveDataBrief(slug),
    onSuccess: (p) => setProject(p),
  });

  const genErr = generate.error as ApiRequestError | null;
  const saveErr = save.error as ApiRequestError | null;
  const approveErr = approve.error as ApiRequestError | null;

  function startEdit() {
    setDraft(structuredClone(content ?? emptyContent(project.data_goal || "")));
    setEditing(true);
    save.reset();
  }

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.dataBrief.goalPrefix} &middot; {project.data_goal || "analytics"}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {dict.dataBrief.title}
        </h1>
        <p className="text-sm text-fg-muted">{dict.journeyData.data_brief.label}</p>
        <p className="rounded-md border border-line bg-surface/60 px-3.5 py-2.5 text-sm leading-relaxed text-fg-muted">
          {project.original_idea}
        </p>
      </div>

      {!content ? (
        generate.isPending ? (
          <div className="grid gap-4">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : (
          <div className="mx-auto grid max-w-md justify-items-center gap-4 py-14 text-center">
            <h2 className="text-lg font-semibold text-fg">{dict.dataBrief.generateTitle}</h2>
            <p className="text-sm leading-relaxed text-fg-muted">
              {dict.dataBrief.generateBody}
            </p>
            <Button
              size="lg"
              loading={generate.isPending}
              onClick={() => generate.mutate()}
            >
              {dict.dataBrief.generateCta}
            </Button>
            {genErr && genErr.code === "missing_api_key" && (
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
        )
      ) : (
        <>
          <div className="sticky top-14 z-30 -mx-4 mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-line bg-bg/90 px-4 py-3 backdrop-blur-md">
            <div className="flex items-center gap-2 text-sm">
              {approved ? (
                <>
                  <Badge tone="success">{dict.dataShared.approved}</Badge>
                  <span className="text-fg-subtle">
                    {formatDateTime(project.data_brief_approved_at)}
                  </span>
                </>
              ) : (
                <Badge tone="neutral">{dict.dataShared.draft}</Badge>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirmRegen(true)}
              >
                {dict.dataShared.regenerate}
              </Button>
              {!editing && (
                <Button variant="outline" size="sm" onClick={startEdit}>
                  {dict.dataBrief.editCta}
                </Button>
              )}
              {!approved && !editing && (
                <Button
                  size="sm"
                  loading={approve.isPending}
                  onClick={() => approve.mutate()}
                >
                  {dict.dataBrief.approveCta}
                </Button>
              )}
            </div>
          </div>

          {approveErr && (
            <p role="alert" className="mb-4 text-sm text-danger">
              {approveErr.message}
            </p>
          )}

          {editing && draft ? (
            <div className="grid gap-5 rounded-xl border border-line bg-surface/40 p-5 sm:p-7">
              {prose(dict).map(({ key, label }) => (
                <label key={key} className="grid gap-1.5 text-sm">
                  <span className="font-medium text-fg">{label}</span>
                  <textarea
                    rows={2}
                    value={draft[key] as string}
                    onChange={(e) =>
                      setDraft({ ...draft, [key]: e.target.value })
                    }
                    className="w-full resize-y rounded-md border border-line bg-bg-subtle px-3 py-2 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  />
                </label>
              ))}
              {lists(dict).map(({ key, label, noun }) => (
                <div key={key} className="grid gap-1.5">
                  <span className="text-sm font-medium text-fg">{label}</span>
                  <StringListEditor
                    value={draft[key] as string[]}
                    onChange={(v) => setDraft({ ...draft, [key]: v })}
                    itemNoun={noun}
                  />
                </div>
              ))}
              {saveErr && (
                <p role="alert" className="text-sm text-danger">
                  {saveErr.message}
                </p>
              )}
              <div className="flex gap-3">
                <Button
                  size="sm"
                  loading={save.isPending}
                  onClick={() => save.mutate(draft)}
                >
                  {dict.dataBrief.saveCta}
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
            <div className="grid gap-6 rounded-xl border border-line bg-surface/40 p-5 sm:p-7">
              {prose(dict).map(({ key, label }) => (
                <section key={key} className="grid gap-1">
                  <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
                    {label}
                  </h2>
                  <p className="text-sm leading-relaxed text-fg-muted">
                    {(content[key] as string) || "—"}
                  </p>
                </section>
              ))}
              {lists(dict).map(({ key, label }) => {
                const items = content[key] as string[];
                return (
                  <section key={key} className="grid gap-1">
                    <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
                      {label}
                    </h2>
                    {items.length ? (
                      <ul className="grid list-disc gap-1 ps-5 text-sm leading-relaxed text-fg-muted">
                        {items.map((it, i) => (
                          <li key={i}>{it}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-fg-subtle">—</p>
                    )}
                  </section>
                );
              })}
            </div>
          )}

          {approved && (
            <ArtifactApprovedNotice
              summary={dict.dataBrief.nextSummary}
              nextLabel={dict.dataBrief.nextLabel}
              nextHref={`/projects/${slug}/data-sources`}
            />
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmRegen}
        title={dict.dataBrief.regenerateTitle}
        description={approved ? dict.dataBrief.regenerateApprovedDesc : dict.dataBrief.regenerateDraftDesc}
        confirmLabel={dict.dataShared.regenerate}
        tone="danger"
        busy={generate.isPending}
        onConfirm={() => generate.mutate()}
        onCancel={() => setConfirmRegen(false)}
      />
    </>
  );
}
