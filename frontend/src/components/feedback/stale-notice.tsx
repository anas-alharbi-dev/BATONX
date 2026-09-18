"use client";

import { Badge } from "@/components/ui/badge";
import { interpolate, useLanguage } from "@/lib/i18n";

/**
 * Non-destructive downstream-stale indicator. Shown when an approved artifact may
 * no longer be consistent with an updated upstream source. The artifact keeps
 * its content and approval — the user reconciles by regenerating or re-approving.
 */
export function StaleNotice({ artifact }: { artifact: string }) {
  const { dict } = useLanguage();
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Badge tone="warning">{dict.softwareShared.reviewRequired}</Badge>
      <span className="text-xs text-warning/90">
        {interpolate(dict.softwareShared.staleReconcile, { artifact })}
      </span>
    </span>
  );
}
