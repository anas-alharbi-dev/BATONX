"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRightIcon } from "@radix-ui/react-icons";

import { useAuth } from "@/components/auth/auth-provider";
import { buttonClasses } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";

import { useMotionSafe } from "./motion-primitives";
import { OrchestrationScene } from "./orchestration-scene";

const EASE = [0.16, 1, 0.3, 1] as const;

/**
 * Public Landing hero (Landing redesign, building on Phase P-3). Still never
 * creates a project directly — Start Now routes to the authenticated Create
 * Project flow (via signup when signed out). The copy side plays a short,
 * one-shot reveal sequence on load; the visual side is `OrchestrationScene`,
 * a card-based retelling of the same "Idea → BATONX → Execution → Delivery"
 * story the old hero told as plain text.
 */
export function Hero() {
  const { status } = useAuth();
  const { dict } = useLanguage();
  const safe = useMotionSafe();
  const authenticated = status === "authenticated";

  const rise = (delay: number) =>
    safe
      ? {
          initial: { opacity: 0, y: 18 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.6, ease: EASE, delay },
        }
      : {};

  return (
    <section className="relative overflow-hidden">
      {/* Faint technical backdrop: a large soft grid plus one restrained
          accent glow, both fixed to the hero only — never flooding the
          whole page, never competing with the cards. */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div
          className="absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage:
              "linear-gradient(to right, currentColor 1px, transparent 1px), linear-gradient(to bottom, currentColor 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage: "radial-gradient(ellipse 70% 60% at 50% 0%, black 40%, transparent 100%)",
          }}
        />
        <div className="absolute start-1/2 top-[-160px] size-[560px] -translate-x-1/2 rounded-full bg-accent/[0.08] blur-[140px]" />
      </div>

      <div className="mx-auto grid max-w-6xl gap-14 px-4 py-16 safe-px lg:grid-cols-12 lg:gap-10 lg:py-28">
        <div className="lg:col-span-7">
          <motion.span
            {...rise(0)}
            className="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs text-fg-muted backdrop-blur-sm"
          >
            <span aria-hidden className="size-1.5 rounded-full bg-accent motion-safe:animate-glow-breathe" />
            {dict.landing.heroBadge}
          </motion.span>

          <motion.h1
            {...rise(0.08)}
            className="mt-5 text-4xl font-semibold leading-[1.05] tracking-tight text-fg sm:text-5xl lg:text-[3.4rem]"
          >
            {dict.landing.heroLine1}
            <br />
            {dict.landing.heroLine2}
            <br />
            <span className="bg-gradient-to-r from-accent to-accent-strong bg-clip-text text-transparent">
              {dict.landing.heroLine3}
            </span>
          </motion.h1>

          <motion.p
            {...rise(0.16)}
            className="mt-6 max-w-xl text-base leading-relaxed text-fg-muted"
          >
            {dict.landing.heroBodyFull}
          </motion.p>

          <motion.div {...rise(0.24)} className="mt-9 flex flex-wrap items-center gap-3">
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
          </motion.div>

          <motion.p {...rise(0.3)} className="mt-8 font-mono text-[11px] uppercase tracking-[0.14em] text-fg-subtle">
            {dict.landing.heroFinePrint}
          </motion.p>
        </div>

        <div className="lg:col-span-5">
          <OrchestrationScene />
        </div>
      </div>
    </section>
  );
}
