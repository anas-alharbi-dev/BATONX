"use client";

import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";

interface StateProps {
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  icon?: ReactNode;
}

function Shell({ title, description, children, icon }: StateProps) {
  return (
    <div className="mx-auto grid max-w-md justify-items-center gap-3 py-16 text-center">
      {icon ? <div className="text-fg-subtle">{icon}</div> : null}
      <h2 className="text-lg font-semibold text-fg">{title}</h2>
      {description ? (
        <p className="text-sm leading-relaxed text-fg-muted">{description}</p>
      ) : null}
      {children ? <div className="mt-2 flex gap-3">{children}</div> : null}
    </div>
  );
}

/** Empty / not-found state. Explains how to move forward. */
export function EmptyState(props: StateProps) {
  return <Shell {...props} />;
}

interface ErrorStateProps {
  title?: string;
  description?: ReactNode;
  onRetry?: () => void;
  retrying?: boolean;
  retryable?: boolean;
}

/** Error state with an optional Retry. Never a dead end. Title/button text
 *  is localized centrally here (Phase P-7) so every caller across the app
 *  gets it for free unless it passes its own `title`. */
export function ErrorState({
  title,
  description,
  onRetry,
  retrying = false,
  retryable = true,
}: ErrorStateProps) {
  const { dict } = useLanguage();
  return (
    <Shell title={title ?? dict.common.somethingWentWrong} description={description}>
      {onRetry && retryable ? (
        <Button variant="outline" onClick={onRetry} loading={retrying}>
          {dict.common.retry}
        </Button>
      ) : null}
    </Shell>
  );
}
