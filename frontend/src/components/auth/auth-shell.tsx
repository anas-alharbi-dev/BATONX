import Link from "next/link";

import { BrandLogo } from "@/components/brand/brand-logo";

/**
 * Shared split-screen frame for /login and /signup. Left: the form itself.
 * Right (desktop only): a quiet, on-brand visual — not new marketing copy,
 * just the product's own Journey language previewed at rest (see
 * `AuthJourneyPreview`). Below `lg` the right panel simply isn't rendered;
 * the form fills the screen.
 */
export function AuthShell({
  title,
  subtitle,
  children,
  visual,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  visual: React.ReactNode;
}) {
  return (
    <div className="grid min-h-[100dvh] lg:grid-cols-2">
      <div className="flex flex-col px-6 py-8 safe-px sm:px-10 lg:px-16">
        <Link href="/" aria-label="BATONX home" className="w-fit rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
          <BrandLogo />
        </Link>

        <div className="flex flex-1 items-center py-10">
          <div className="w-full max-w-sm">
            <h1 className="text-2xl font-semibold tracking-tight text-fg">{title}</h1>
            <p className="mt-1.5 text-sm text-fg-muted">{subtitle}</p>
            <div className="mt-8">{children}</div>
          </div>
        </div>
      </div>

      <div className="hidden border-s border-line bg-bg-subtle lg:flex lg:items-center lg:justify-center">
        {visual}
      </div>
    </div>
  );
}
