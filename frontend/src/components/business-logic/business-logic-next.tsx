"use client";

import { ArtifactApprovedNotice } from "@/components/workspace/artifact-approved-notice";
import { useLanguage } from "@/lib/i18n";

export function BusinessLogicNext({ slug }: { slug: string }) {
  const { dict } = useLanguage();
  return (
    <ArtifactApprovedNotice
      summary={dict.businessLogic.nextSummary}
      nextLabel={dict.businessLogic.continueToArchitecture}
      nextHref={`/projects/${slug}/architecture`}
    />
  );
}
