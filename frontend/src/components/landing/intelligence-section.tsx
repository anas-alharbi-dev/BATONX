"use client";

import {
  LayersIcon,
  CheckCircledIcon,
  UpdateIcon,
  BarChartIcon,
  RocketIcon,
} from "@radix-ui/react-icons";

import { BrandMark } from "@/components/brand/brand-logo";
import { useLanguage } from "@/lib/i18n";

import { Reveal, Stagger, StaggerItem, HoverCard } from "./motion-primitives";

const ICONS = [LayersIcon, CheckCircledIcon, UpdateIcon, BarChartIcon, RocketIcon];

/**
 * BATONX Intelligence section (Landing redesign) — presented as a connected
 * project-awareness surface feeding a central orchestration node, never as
 * a generic chatbot mockup. The five awareness items are the same real,
 * structured signals the authenticated Intelligence panel actually reads
 * (Phase P-6): current stage, approved artifacts, stale dependencies,
 * progress, delivery readiness.
 */
export function IntelligenceSection() {
  const { dict } = useLanguage();
  const items = dict.landing.intelligenceAwareness;

  return (
    <section className="relative mx-auto max-w-6xl px-4 py-20 safe-px lg:py-24">
      <div className="relative overflow-hidden rounded-[28px] border border-line bg-surface/50 p-6 sm:p-10 lg:p-12">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_60%_50%_at_50%_0%,rgba(52,211,153,0.10),transparent_70%)]"
        />

        <Reveal className="mx-auto max-w-lg text-center">
          <div className="mx-auto flex size-14 items-center justify-center rounded-2xl border border-accent/25 bg-accent-soft shadow-[0_0_0_1px_rgba(52,211,153,0.05)]">
            <BrandMark size={26} />
          </div>
          <h2 className="mt-5 text-2xl font-semibold tracking-tight text-fg sm:text-[1.9rem]">
            {dict.landing.intelligenceHeading}
          </h2>
          <p className="mt-2 text-[15px] leading-relaxed text-fg-muted">
            {dict.landing.intelligenceBody}
          </p>
        </Reveal>

        <Stagger className="mx-auto mt-10 grid max-w-3xl gap-3 sm:grid-cols-5">
          {items.map((item, i) => {
            const Icon = ICONS[i] ?? LayersIcon;
            return (
              <StaggerItem key={item}>
                <div className="motion-safe:animate-float" style={{ animationDelay: `${i * 0.6}s` }}>
                  <HoverCard className="flex h-full flex-col items-center gap-2.5 rounded-xl border border-line bg-bg/70 px-3 py-4 text-center backdrop-blur-sm transition-colors duration-300 hover:border-accent/30">
                    <span className="grid size-8 place-items-center rounded-lg border border-line-strong bg-surface text-accent">
                      <Icon className="size-3.5" />
                    </span>
                    <span className="text-[12px] font-medium leading-snug text-fg-muted">{item}</span>
                  </HoverCard>
                </div>
              </StaggerItem>
            );
          })}
        </Stagger>
      </div>
    </section>
  );
}
