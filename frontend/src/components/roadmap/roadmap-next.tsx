"use client";

import { ArtifactApprovedNotice } from "@/components/workspace/artifact-approved-notice";
import { interpolate, useLanguage } from "@/lib/i18n";

export function RoadmapNext({
  slug,
  nextTaskId,
}: {
  slug: string;
  nextTaskId: string | null;
}) {
  const { dict } = useLanguage();
  return (
    <ArtifactApprovedNotice
      summary={dict.roadmap.nextSummary}
      nextLabel={nextTaskId ? interpolate(dict.roadmap.openTask, { id: nextTaskId }) : dict.roadmap.viewProgress}
      nextHref={
        nextTaskId
          ? `/projects/${slug}/roadmap/tasks/${nextTaskId}`
          : `/projects/${slug}/progress`
      }
    />
  );
}
