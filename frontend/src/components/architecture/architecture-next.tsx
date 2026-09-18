"use client";

import { ArtifactApprovedNotice } from "@/components/workspace/artifact-approved-notice";
import { useLanguage } from "@/lib/i18n";

export function ArchitectureNext({ slug }: { slug: string }) {
  const { dict } = useLanguage();
  return (
    <ArtifactApprovedNotice
      summary={dict.architecture.nextSummary}
      nextLabel={dict.architecture.continueToRoadmap}
      nextHref={`/projects/${slug}/roadmap`}
    />
  );
}
