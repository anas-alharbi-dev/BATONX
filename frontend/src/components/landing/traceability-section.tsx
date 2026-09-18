"use client";

import {
  CheckCircledIcon,
  LayersIcon,
  FileTextIcon,
  Link2Icon,
  Pencil2Icon,
  BarChartIcon,
} from "@radix-ui/react-icons";

import { useLanguage } from "@/lib/i18n";

import { Reveal, Stagger, StaggerItem, HoverCard } from "./motion-primitives";

const ICONS = [CheckCircledIcon, LayersIcon, FileTextIcon, Link2Icon, Pencil2Icon, BarChartIcon];

export function TraceabilitySection() {
  const { dict } = useLanguage();
  const items = dict.landing.traceabilityItems;

  return (
    <section className="relative mx-auto max-w-6xl px-4 py-20 safe-px lg:py-24">
      <Reveal className="max-w-xl">
        <p className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-accent">
          {dict.landing.traceabilityEyebrow}
        </p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-fg sm:text-[2.1rem]">
          {dict.landing.traceabilityHeading}
        </h2>
        <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-fg-muted">
          {dict.landing.traceabilityBody}
        </p>
      </Reveal>

      <Stagger className="mt-10 grid gap-3 sm:grid-cols-3">
        {items.map((item, i) => {
          const Icon = ICONS[i] ?? FileTextIcon;
          return (
            <StaggerItem key={item}>
              <HoverCard className="flex h-full items-center gap-3 rounded-xl border border-line bg-surface/60 px-4 py-3.5 transition-colors duration-300 hover:border-accent/30">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg border border-line-strong bg-bg text-accent">
                  <Icon className="size-3.5" />
                </span>
                <span className="text-[13.5px] font-medium text-fg">{item}</span>
              </HoverCard>
            </StaggerItem>
          );
        })}
      </Stagger>
    </section>
  );
}
