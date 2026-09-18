"use client";

import {
  ChatBubbleIcon,
  EyeOpenIcon,
  CheckIcon,
  ArrowRightIcon,
  ArchiveIcon,
} from "@radix-ui/react-icons";

import { useLanguage } from "@/lib/i18n";

import { Reveal, Stagger, StaggerItem, HoverCard } from "./motion-primitives";

const ICONS = [ChatBubbleIcon, EyeOpenIcon, CheckIcon, ArchiveIcon];

/**
 * Human-in-the-loop section (Landing redesign). Retells the same P-1
 * governance rule the old bullet list did — "AI proposes. Human decides.
 * System remembers." — as a literal left-to-right decision sequence, since
 * that flow *is* the product's most load-bearing guarantee and deserves to
 * be seen, not just stated.
 */
export function HumanControlSection() {
  const { dict } = useLanguage();
  const steps = dict.landing.humanControlSteps;

  return (
    <section id="how-it-works" className="relative mx-auto max-w-6xl scroll-mt-20 px-4 py-20 safe-px lg:py-24">
      <Reveal className="mx-auto max-w-2xl text-center">
        <p className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-accent">
          {dict.landing.humanControlEyebrow}
        </p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-fg sm:text-[2.1rem]">
          {dict.landing.humanControlHeading}
        </h2>
        <p className="mx-auto mt-3 max-w-lg text-[15px] leading-relaxed text-fg-muted">
          {dict.landing.humanControlBody}
        </p>
      </Reveal>

      <Stagger className="mt-12 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
        {steps.map((step, i) => {
          const Icon = ICONS[i] ?? ChatBubbleIcon;
          const isDecision = i === 1;
          return (
            <div key={step.label} className="flex items-center gap-3 sm:flex-1">
              <StaggerItem className="flex-1">
                <HoverCard
                  className={
                    "flex h-full flex-col gap-3 rounded-2xl border p-5 transition-colors duration-300 " +
                    (isDecision
                      ? "border-accent/35 bg-accent-soft"
                      : "border-line bg-surface/60 hover:border-line-strong")
                  }
                >
                  <span
                    aria-hidden
                    className={
                      "grid size-9 place-items-center rounded-lg border " +
                      (isDecision
                        ? "border-accent/40 bg-bg text-accent-strong"
                        : "border-line-strong bg-bg text-fg-muted")
                    }
                  >
                    <Icon className="size-4" />
                  </span>
                  <div>
                    <p className="text-[13.5px] font-semibold text-fg">{step.label}</p>
                    <p className="mt-1 text-xs leading-relaxed text-fg-subtle">{step.body}</p>
                  </div>
                </HoverCard>
              </StaggerItem>
              {i < steps.length - 1 && (
                <span aria-hidden className="shrink-0 rotate-90 text-fg-subtle/50 sm:rotate-0">
                  <ArrowRightIcon className="size-4 rtl:-scale-x-100" />
                </span>
              )}
            </div>
          );
        })}
      </Stagger>
    </section>
  );
}
