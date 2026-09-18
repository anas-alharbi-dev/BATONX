"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useLanguage } from "@/lib/i18n";

export function BlueprintGenerating({ regenerate = false }: { regenerate?: boolean }) {
  const { dict } = useLanguage();
  return (
    <div className="grid gap-6" aria-live="polite">
      <div className="flex items-center gap-3">
        <Spinner className="size-5 text-accent" />
        <div>
          <p className="text-sm font-medium text-fg">
            {regenerate ? dict.blueprint.regeneratingTitle : dict.blueprint.generatingTitle}
          </p>
          <p className="text-sm text-fg-muted">
            {dict.blueprint.generatingBody}
          </p>
        </div>
      </div>

      <div className="grid gap-4 rounded-xl border border-line bg-surface/40 p-5 sm:p-7">
        {[
          "w-40",
          "w-full",
          "w-4/5",
          "w-32",
          "w-full",
          "w-3/4",
          "w-36",
          "w-2/3",
        ].map((w, i) => (
          <Skeleton key={i} className={`h-4 ${w}`} />
        ))}
      </div>
    </div>
  );
}
