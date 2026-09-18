"use client";

import Link from "next/link";
import { ArrowRightIcon } from "@radix-ui/react-icons";

import { useAuth } from "@/components/auth/auth-provider";
import { buttonClasses } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";

import { Reveal } from "./motion-primitives";

/**
 * The closing section — a full anchored panel, not a footer-weight
 * afterthought. Same restraint as the rest of the redesign: one soft glow,
 * one accent, no new visual language introduced this late in the page.
 */
export function FinalCtaSection() {
  const { status } = useAuth();
  const { dict } = useLanguage();
  const authenticated = status === "authenticated";

  return (
    <section className="relative mx-auto max-w-6xl px-4 py-20 safe-px lg:py-28">
      <Reveal className="relative overflow-hidden rounded-[32px] border border-line bg-gradient-to-b from-surface-raised to-surface px-6 py-16 text-center sm:px-12 sm:py-20">
        <div
          aria-hidden
          className="pointer-events-none absolute start-1/2 top-0 size-[420px] -translate-x-1/2 -translate-y-1/3 rounded-full bg-accent/[0.14] blur-[120px] motion-safe:animate-glow-breathe"
        />

        <p className="relative font-mono text-[10.5px] uppercase tracking-[0.16em] text-accent">
          {dict.landing.finalCtaEyebrow}
        </p>
        <h2 className="relative mx-auto mt-4 max-w-2xl text-3xl font-semibold tracking-tight text-fg sm:text-4xl lg:text-[2.6rem]">
          {dict.landing.finalCtaLine1}
          <br />
          {dict.landing.finalCtaLine2}
        </h2>
        <p className="relative mx-auto mt-4 max-w-md text-[15px] leading-relaxed text-fg-muted">
          {dict.landing.finalCtaBody}
        </p>

        <div className="relative mt-9 flex flex-wrap items-center justify-center gap-3">
          {authenticated ? (
            <Link href="/projects" className={buttonClasses("solid", "lg", "group")}>
              {dict.landing.goToProjects}
              <ArrowRightIcon className="size-4 transition-transform rtl:-scale-x-100 group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5" aria-hidden />
            </Link>
          ) : (
            <>
              <Link href="/signup?next=/projects/new" className={buttonClasses("solid", "lg", "group")}>
                {dict.nav.startNow}
                <ArrowRightIcon className="size-4 transition-transform rtl:-scale-x-100 group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5" aria-hidden />
              </Link>
              <Link href="/login" className={buttonClasses("outline", "lg")}>
                {dict.nav.login}
              </Link>
            </>
          )}
        </div>
      </Reveal>
    </section>
  );
}
