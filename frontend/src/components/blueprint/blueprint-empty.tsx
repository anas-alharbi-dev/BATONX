"use client";

import Link from "next/link";

import { AiUnconfiguredNotice } from "@/components/feedback/ai-unconfigured-notice";
import { EmptyState } from "@/components/feedback/states";
import { Button, buttonClasses } from "@/components/ui/button";
import type { ApiRequestError } from "@/lib/api/client";
import { useLanguage } from "@/lib/i18n";

interface Props {
  variant: "ready" | "needs-discovery";
  slug: string;
  onGenerate: () => void;
  loading: boolean;
  error: ApiRequestError | null;
}

export function BlueprintEmpty({
  variant,
  slug,
  onGenerate,
  loading,
  error,
}: Props) {
  const { dict } = useLanguage();

  if (variant === "needs-discovery") {
    return (
      <EmptyState
        title={dict.blueprint.needsDiscoveryTitle}
        description={dict.blueprint.needsDiscoveryBody}
      >
        <Link
          href={`/projects/${slug}/discovery`}
          className={buttonClasses("solid", "md")}
        >
          {dict.blueprint.goToDiscovery}
        </Link>
      </EmptyState>
    );
  }

  const missingKey = error?.code === "missing_api_key";
  const showRetry = !!error && error.retryable;

  return (
    <div className="mx-auto grid max-w-md justify-items-center gap-4 py-16 text-center">
      <h2 className="text-lg font-semibold text-fg">
        {dict.blueprint.generateTitle}
      </h2>
      <p className="text-sm leading-relaxed text-fg-muted">
        {dict.blueprint.generateBody}
      </p>

      <Button size="lg" onClick={onGenerate} loading={loading}>
        {loading ? dict.common.generatingEllipsis : dict.blueprint.generateCta}
      </Button>

      {error && !missingKey && (
        <p role="alert" className="text-sm text-danger">
          {error.message}
          {showRetry ? ` ${dict.common.tryAgainSentence}` : ""}
        </p>
      )}
      {missingKey && (
        <div className="w-full text-start">
          <AiUnconfiguredNotice />
        </div>
      )}
    </div>
  );
}
