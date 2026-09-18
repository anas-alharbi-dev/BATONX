"use client";

import { CheckCircledIcon } from "@radix-ui/react-icons";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ImpactNotice } from "@/components/workspace/impact-notice";
import { formatDateTime } from "@/lib/format";
import { interpolate, useLanguage } from "@/lib/i18n";

interface Props {
  approved: boolean;
  approvedAt: string | null;
  updatedAt?: string;
  amending: boolean;
  approving: boolean;
  approveError?: string | null;
  onApprove: () => void;
  onRegenerate: () => void;
  onToggleAmend: () => void;
}

export function BlueprintStatusBar({
  approved,
  approvedAt,
  updatedAt,
  amending,
  approving,
  approveError,
  onApprove,
  onRegenerate,
  onToggleAmend,
}: Props) {
  const { dict } = useLanguage();
  return (
    <div className="sticky top-14 z-30 -mx-4 mb-6 border-b border-line bg-bg/90 px-4 py-3 backdrop-blur-md">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-sm">
          {approved ? (
            <>
              <Badge tone="success">
                <CheckCircledIcon className="size-3.5" aria-hidden />
                {dict.softwareShared.approvedBadge}
              </Badge>
              <span className="text-fg-subtle">{formatDateTime(approvedAt)}</span>
            </>
          ) : (
            <>
              <Badge tone="neutral">{dict.softwareShared.draftBadge}</Badge>
              {updatedAt && (
                <span className="text-fg-subtle">
                  {interpolate(dict.common.updatedAt, { when: formatDateTime(updatedAt) }).toLowerCase()}
                </span>
              )}
            </>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={onRegenerate}>
            {dict.softwareShared.regenerate}
          </Button>
          {approved ? (
            <Button variant="outline" size="sm" onClick={onToggleAmend}>
              {amending ? dict.softwareShared.doneEditing : dict.blueprint.editArtifact}
            </Button>
          ) : (
            <Button size="sm" loading={approving} onClick={onApprove}>
              {dict.blueprint.approveArtifact}
            </Button>
          )}
        </div>
      </div>

      {approved && amending && <ImpactNotice artifact="blueprint" />}

      {approveError && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {approveError}
        </p>
      )}
    </div>
  );
}
