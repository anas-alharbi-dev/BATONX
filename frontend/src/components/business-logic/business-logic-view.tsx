"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type { BusinessLogicContent, Project } from "@/lib/api/types";
import { fieldMessage } from "@/components/review/review-helpers";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { interpolate, useLanguage } from "@/lib/i18n";

import { BusinessLogicEmpty } from "./business-logic-empty";
import { BusinessLogicGenerating } from "./business-logic-generating";
import { BusinessLogicNext } from "./business-logic-next";
import { BusinessLogicSections } from "./business-logic-sections";
import type { SectionKey } from "./business-logic-shared";
import { BusinessLogicStatusBar } from "./business-logic-status-bar";

export function BusinessLogicView({ initialProject }: { initialProject: Project }) {
  const { dict } = useLanguage();
  const [project, setProject] = useState(initialProject);
  const [editingKey, setEditingKey] = useState<SectionKey | null>(null);
  const [amending, setAmending] = useState(false);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);

  const slug = project.slug;
  const content = project.business_logic?.content;
  const approved = !!project.business_logic_approved_at;
  const blueprintApproved = !!project.blueprint_approved_at;

  const generate = useMutation({
    mutationFn: () => api.generateBusinessLogic(slug),
    onSuccess: (updated) => {
      setProject(updated);
      setEditingKey(null);
      setAmending(false);
      setConfirmRegenerate(false);
    },
  });

  const patch = useMutation({
    mutationFn: ({ key, value }: { key: SectionKey; value: unknown }) =>
      api.updateBusinessLogic(slug, { [key]: value } as Partial<BusinessLogicContent>),
    onSuccess: (updated) => {
      setProject(updated);
      setEditingKey(null);
    },
  });

  const approve = useMutation({
    mutationFn: () => api.approveBusinessLogic(slug),
    onSuccess: (updated) => {
      setProject(updated);
      setAmending(false);
    },
  });

  const generateError = generate.error as ApiRequestError | null;
  const patchError = patch.error as ApiRequestError | null;
  const approveError = approve.error as ApiRequestError | null;

  const editError =
    patchError && editingKey
      ? patchError.code === "invalid_business_logic"
        ? fieldMessage(patchError)
        : patchError.message
      : null;

  const bannerError =
    patchError && patchError.code !== "invalid_business_logic"
      ? patchError.message
      : null;

  function startEdit(key: SectionKey) {
    patch.reset();
    setEditingKey(key);
  }
  function cancelEdit() {
    patch.reset();
    setEditingKey(null);
  }

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.softwareShared.stepPrefix} 3 &middot; {dict.journeySoftware.business_logic.label}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {dict.businessLogic.title}
        </h1>
        <p className="text-sm text-fg-muted">
          {dict.journeySoftware.business_logic.purpose}
        </p>
        <p className="rounded-md border border-line bg-surface/60 px-3.5 py-2.5 text-sm leading-relaxed text-fg-muted">
          {project.original_idea}
        </p>
      </div>

      {!content ? (
        generate.isPending ? (
          <BusinessLogicGenerating />
        ) : (
          <BusinessLogicEmpty
            variant={blueprintApproved ? "ready" : "needs-blueprint"}
            slug={slug}
            onGenerate={() => generate.mutate()}
            loading={generate.isPending}
            error={generateError}
          />
        )
      ) : generate.isPending ? (
        <BusinessLogicGenerating regenerate />
      ) : (
        <>
          <BusinessLogicStatusBar
            approved={approved}
            approvedAt={project.business_logic_approved_at}
            updatedAt={project.business_logic?.updated_at}
            amending={amending}
            approving={approve.isPending}
            approveError={approveError?.message ?? null}
            stale={!!project.downstream_stale?.business_logic}
            onApprove={() => approve.mutate()}
            onRegenerate={() => setConfirmRegenerate(true)}
            onToggleAmend={() => setAmending((value) => !value)}
          />

          {generateError && (
            <p role="alert" className="mb-4 text-sm text-danger">
              {interpolate(dict.softwareShared.couldntRegenerate, { msg: generateError.message })}
            </p>
          )}
          {bannerError && (
            <p
              role="alert"
              className="mb-4 rounded-md border border-danger/25 bg-danger/10 px-4 py-3 text-sm text-danger"
            >
              {bannerError}
            </p>
          )}

          <BusinessLogicSections
            content={content}
            editable={!approved || amending}
            editingKey={editingKey}
            saving={patch.isPending}
            editError={editError}
            onStartEdit={startEdit}
            onCancel={cancelEdit}
            onSave={(key, value) => patch.mutate({ key, value })}
          />

          {approved && <BusinessLogicNext slug={slug} />}
        </>
      )}

      <ConfirmDialog
        open={confirmRegenerate}
        title={dict.businessLogic.regenerateTitle}
        description={approved ? dict.businessLogic.regenerateApprovedDesc : dict.businessLogic.regenerateDraftDesc}
        confirmLabel={dict.softwareShared.regenerate}
        tone="danger"
        busy={generate.isPending}
        onConfirm={() => generate.mutate()}
        onCancel={() => setConfirmRegenerate(false)}
      />
    </>
  );
}
