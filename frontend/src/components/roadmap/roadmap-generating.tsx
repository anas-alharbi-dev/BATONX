"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useLanguage } from "@/lib/i18n";

export function RoadmapGenerating({ regenerate = false }: { regenerate?: boolean }) {
  const { dict } = useLanguage();
  return (
    <div className="grid gap-6" aria-live="polite">
      <div className="flex items-center gap-3">
        <Spinner className="size-5 text-accent" />
        <div>
          <p className="text-sm font-medium text-fg">
            {regenerate ? dict.roadmap.regeneratingTitle : dict.roadmap.generatingTitle}
          </p>
          <p className="text-sm text-fg-muted">
            {dict.roadmap.generatingBody}
          </p>
        </div>
      </div>

      <div className="grid gap-5">
        {[0, 1].map((p) => (
          <div key={p} className="grid gap-3 rounded-xl border border-line bg-surface/40 p-5">
            <Skeleton className="h-4 w-40" />
            {[0, 1, 2].map((t) => (
              <Skeleton key={t} className="h-16 w-full" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
