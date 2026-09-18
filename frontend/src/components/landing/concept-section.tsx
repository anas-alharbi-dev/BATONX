"use client";

import {
  StackIcon,
  GearIcon,
  RocketIcon,
} from "@radix-ui/react-icons";

import { useLanguage } from "@/lib/i18n";

import { Reveal, Stagger, StaggerItem, HoverCard } from "./motion-primitives";

const ICONS = [StackIcon, GearIcon, RocketIcon];

export function ConceptSection() {
  const { dict } = useLanguage();
  return (
    <section id="product" className="relative mx-auto max-w-6xl scroll-mt-20 px-4 py-20 safe-px lg:py-28">
      <Reveal className="max-w-xl">
        <p className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-accent">
          {dict.landing.conceptEyebrow}
        </p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-fg sm:text-[2.2rem]">
          {dict.landing.conceptHeading}
        </h2>
      </Reveal>

      <Stagger className="mt-12 grid gap-5 sm:grid-cols-3">
        {dict.landing.conceptItems.map((c, i) => {
          const Icon = ICONS[i] ?? StackIcon;
          return (
            <StaggerItem key={c.n}>
              <HoverCard className="group relative h-full overflow-hidden rounded-2xl border border-line bg-surface/60 p-6 transition-colors duration-300 hover:border-accent/30">
                <div
                  aria-hidden
                  className="pointer-events-none absolute -end-8 -top-8 size-28 rounded-full bg-accent/0 blur-2xl transition-colors duration-500 group-hover:bg-accent/[0.16]"
                />
                <div className="relative flex items-center justify-between">
                  <span
                    aria-hidden
                    className="grid size-10 place-items-center rounded-lg border border-line-strong bg-bg text-accent transition-colors duration-300 group-hover:border-accent/40"
                  >
                    <Icon className="size-4" />
                  </span>
                  <span className="font-mono text-xs text-fg-subtle" dir="ltr">
                    {c.n}
                  </span>
                </div>
                <h3 className="relative mt-5 text-[15px] font-semibold text-fg">{c.title}</h3>
                <p className="relative mt-2 text-sm leading-relaxed text-fg-muted">{c.body}</p>
              </HoverCard>
            </StaggerItem>
          );
        })}
      </Stagger>
    </section>
  );
}
