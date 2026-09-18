"use client";

import { ArtifactApprovedNotice } from "@/components/workspace/artifact-approved-notice";
import { useLanguage } from "@/lib/i18n";

export function BlueprintNext({ slug }: { slug: string }) {
  const { dict } = useLanguage();
  return (
    <ArtifactApprovedNotice
      summary={dict.blueprint.nextSummary}
      nextLabel={dict.blueprint.continueToBusinessLogic}
      nextHref={`/projects/${slug}/business-logic`}
    />
  );
}
