"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/auth/auth-provider";
import { BrandLogo } from "@/components/brand/brand-logo";
import { LanguageSwitcher } from "@/components/i18n/language-switcher";
import { buttonClasses } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";

import { ApiStatus } from "./api-status";

/**
 * Marketing-site header (landing, future public pages). Hidden inside the
 * authenticated Workspace, which renders its own `AppTopBar` — the two never
 * stack. `usePathname` makes this a client component; it was already
 * effectively static markup, so the cost is negligible.
 */
export function SiteHeader() {
  const pathname = usePathname();
  const { status } = useAuth();
  const { dict } = useLanguage();
  if (pathname?.startsWith("/projects") || pathname === "/login" || pathname === "/signup") {
    return null;
  }
  const isLanding = pathname === "/";

  const NAV = [
    { href: "#product", label: dict.nav.product },
    { href: "#software", label: dict.nav.software },
    { href: "#data", label: dict.nav.data },
    { href: "#how-it-works", label: dict.nav.howItWorks },
  ] as const;

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/80 backdrop-blur-md shadow-[inset_0_-1px_0_0_rgb(255_255_255_/_0.03)]">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 safe-px">
        <Link
          href="/"
          aria-label={dict.nav.homeAria}
          className="shrink-0 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <BrandLogo />
        </Link>

        {isLanding && (
          <nav className="hidden items-center gap-6 md:flex" aria-label="Product sections">
            {NAV.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="text-sm text-fg-muted transition-colors hover:text-fg"
              >
                {item.label}
              </a>
            ))}
          </nav>
        )}

        <div className="flex shrink-0 items-center gap-3">
          <ApiStatus />
          <LanguageSwitcher />
          {status === "authenticated" ? (
            <Link href="/projects" className={buttonClasses("outline", "sm")}>
              {dict.common.projects}
            </Link>
          ) : (
            <>
              <Link href="/login" className="text-sm font-medium text-fg-muted hover:text-fg">
                {dict.nav.login}
              </Link>
              <Link href="/signup?next=/projects/new" className={buttonClasses("solid", "sm")}>
                {dict.nav.startNow}
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
