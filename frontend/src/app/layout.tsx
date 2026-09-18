import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { SiteHeader } from "@/components/site/site-header";
import { themeInitScript } from "@/components/theme/theme-provider";
import { languageInitScript } from "@/lib/i18n";
import { BRAND } from "@/lib/brand";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: {
    default: `${BRAND.name} — ${BRAND.tagline}`,
    template: `%s — ${BRAND.name}`,
  },
  description: BRAND.description,
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f8f7" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0b" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // `lang`, `dir`, and `data-resolved-theme` are never rendered here —
    // all three are owned exclusively by the blocking `themeInitScript` /
    // `languageInitScript` below (and by their providers afterward for live
    // switches/toggles), which must run before hydration to avoid a
    // flash of the wrong theme/direction. That's a real, unavoidable,
    // intentional difference between the server-rendered <html> and the
    // live DOM by the time React hydrates — confirmed from the browser's
    // own hydration diff, scoped to exactly these three root-element
    // attributes — so `suppressHydrationWarning` here silences a false
    // positive rather than masking an actual content bug.
    <html suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <head>
        {/* Stamps data-resolved-theme on <html> before first paint, from the
            stored preference or the OS setting — see theme-provider.tsx.
            Prevents a flash of the wrong theme on load/reload. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        {/* Stamps lang/dir on <html> before first paint (P-7) — see
            language-provider.tsx. Runs after the theme script; independent
            of it (different attributes, same "no flash" technique). */}
        <script dangerouslySetInnerHTML={{ __html: languageInitScript }} />
      </head>
      <body className="min-h-[100dvh]">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-50 focus:rounded-md focus:border focus:border-line-strong focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:text-fg focus:outline-none focus:ring-2 focus:ring-accent"
        >
          Skip to content
        </a>
        <Providers>
          <SiteHeader />
          <div id="main-content" tabIndex={-1} className="outline-none">
            {children}
          </div>
        </Providers>
      </body>
    </html>
  );
}
