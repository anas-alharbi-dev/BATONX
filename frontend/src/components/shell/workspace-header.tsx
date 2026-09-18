import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";

/**
 * The standard header every stage workspace opens with: eyebrow (which
 * project/stage), title, one-line description, an authoritative status
 * badge (approved / draft / stale — whatever the stage means by it), and
 * action slots. Individual stage views (BlueprintView, DataQualityView, …)
 * keep their own body content; this only standardizes the header they sit
 * under so the rhythm is identical everywhere in the Workspace.
 */
export function WorkspaceHeader({
  eyebrow,
  title,
  description,
  status,
  primaryAction,
  secondaryActions,
  meta,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  status?: { label: string; tone: "neutral" | "accent" | "success" | "warning" | "danger" };
  primaryAction?: ReactNode;
  secondaryActions?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <div className="mb-8 grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {eyebrow}
        </span>
        {status && <Badge tone={status.tone}>{status.label}</Badge>}
      </div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{title}</h1>
        {(primaryAction || secondaryActions) && (
          <div className="flex flex-wrap items-center gap-2">
            {secondaryActions}
            {primaryAction}
          </div>
        )}
      </div>
      {description && (
        <p className="max-w-2xl text-sm leading-relaxed text-fg-muted">{description}</p>
      )}
      {meta && <div className="flex flex-wrap items-center gap-2 text-xs text-fg-subtle">{meta}</div>}
    </div>
  );
}
