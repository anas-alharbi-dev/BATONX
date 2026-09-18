"use client";

import { ChevronDownIcon } from "@radix-ui/react-icons";

import { BrandMark } from "@/components/brand/brand-logo";
import { useLanguage } from "@/lib/i18n";

import { Reveal, Stagger, StaggerItem, HoverCard } from "./motion-primitives";

// Kept in Latin script even in Arabic mode — these are external product
// names, not translatable copy (Phase P-7 explicit guidance).
const AGENTS = ["Claude Code", "Codex", "Cursor"] as const;

/**
 * Positions BATONX above the execution layer visually, not just in prose —
 * a small BATONX chip sits over a row of real agent-name cards, connected
 * by a short downward line, so the "orchestration above execution" claim is
 * something the eye confirms in a second, not a sentence the reader has to
 * take on faith. No logos, no fake integration marks — plain, honest names.
 */
export function AgentPositioningSection() {
  const { dict } = useLanguage();
  return (
    <section className="relative mx-auto max-w-6xl px-4 py-16 safe-px">
      <div className="grid items-center gap-10 lg:grid-cols-[1fr_auto]">
        <Reveal className="max-w-lg">
          <p className="text-[15px] font-medium text-fg">{dict.landing.agentPositioningHeading}</p>
          <p className="mt-2 text-sm leading-relaxed text-fg-muted">
            {dict.landing.agentPositioningBody}
          </p>
        </Reveal>

        <Reveal className="flex flex-col items-center">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent-soft px-3 py-1.5">
            <BrandMark size={14} />
            <span translate="no" className="text-xs font-bold text-fg">
              BATON<span className="text-accent">X</span>
            </span>
          </span>
          <ChevronDownIcon className="my-1 size-4 text-fg-subtle motion-safe:animate-float" aria-hidden />
          <Stagger className="flex flex-wrap justify-center gap-2">
            {AGENTS.map((agent) => (
              <StaggerItem key={agent}>
                <HoverCard className="rounded-lg border border-line bg-surface/70 px-3 py-1.5 transition-colors duration-300 hover:border-line-strong">
                  <span className="text-xs font-medium text-fg-muted" dir="ltr" translate="no">
                    {agent}
                  </span>
                </HoverCard>
              </StaggerItem>
            ))}
          </Stagger>
        </Reveal>
      </div>
    </section>
  );
}
