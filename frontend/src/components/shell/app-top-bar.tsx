"use client";

import Link from "next/link";
import { ChevronLeftIcon } from "@radix-ui/react-icons";

import { BrandLogo } from "@/components/brand/brand-logo";
import { LanguageSwitcher } from "@/components/i18n/language-switcher";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { useLanguage } from "@/lib/i18n";
import { displayProjectName } from "@/lib/project-name";
import { AccountMenu } from "./account-menu";
import type { Project } from "@/lib/api/types";

/**
 * The permanent top bar for the authenticated Workspace. Distinct from
 * `SiteHeader` (the marketing-site header) — the two never render together,
 * see `site-header.tsx`.
 *
 * The right side shows the real authenticated identity (Phase P-2) via
 * `AccountMenu` — this component only renders inside `/projects/*`, which
 * is now entirely auth-gated (see `app/projects/layout.tsx`), so a `user`
 * is always present here in practice.
 */
export function AppTopBar({ project }: { project?: Project }) {
  const { dict } = useLanguage();
  const typeLabel: Record<Project["project_type"], string> = {
    software: dict.projectType.software,
    data: dict.projectType.data,
  };

  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-line bg-bg px-4 safe-px">
      <Link
        href="/"
        aria-label={dict.nav.homeAria}
        className="shrink-0 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <BrandLogo />
      </Link>

      {project && (
        <>
          <span aria-hidden className="h-5 w-px shrink-0 bg-line" />
          <Link
            href="/projects"
            className="flex shrink-0 items-center gap-1 rounded-sm text-sm text-fg-subtle transition-colors hover:text-fg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {/* A "back" chevron is directional — it must point toward the
                start of reading order in both directions, so it flips under
                RTL rather than staying pinned to the left. */}
            <ChevronLeftIcon className="size-3.5 rtl:-scale-x-100" aria-hidden />
            <span className="hidden sm:inline">{dict.common.projects}</span>
          </Link>
          <span aria-hidden className="h-5 w-px shrink-0 bg-line" />
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-medium text-fg" title={displayProjectName(project)}>
              {displayProjectName(project)}
            </span>
            <span className="hidden shrink-0 rounded-full border border-line bg-surface px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.04em] text-fg-subtle sm:inline">
              {typeLabel[project.project_type]}
            </span>
          </div>
        </>
      )}

      <div className="ms-auto flex shrink-0 items-center gap-3">
        <LanguageSwitcher />
        <ThemeToggle />
        <AccountMenu />
      </div>
    </header>
  );
}
