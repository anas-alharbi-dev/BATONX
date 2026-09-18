"use client";

import { ArrowRightIcon } from "@radix-ui/react-icons";

import { Reveal, Stagger, StaggerItem, HoverCard } from "./motion-primitives";

/**
 * One shared component for both the Software and Data workflow sections
 * (Phase P-3, restyled in the Landing redesign) — same visual system,
 * different real stage list, so the two workflows read as one product
 * rather than two different designs. Stage names come from `SOFTWARE_STAGES`
 * / `DATA_STAGE_META` (via `page.tsx`) — the exact same source of truth the
 * live Journey rail uses — never a separate, marketing-only list.
 */
export function WorkflowSection({
  id,
  eyebrow,
  title,
  description,
  stages,
  note,
  reverse = false,
}: {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  stages: string[];
  note?: { title: string; items: { label: string; body: string }[] };
  reverse?: boolean;
}) {
  return (
    <section
      id={id}
      className={
        "relative mx-auto max-w-6xl scroll-mt-20 px-4 py-20 safe-px lg:py-24 " +
        (reverse ? "bg-bg-subtle/40" : "")
      }
    >
      <Reveal className="max-w-2xl">
        <p className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-accent">{eyebrow}</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-fg sm:text-[2.1rem]">{title}</h2>
        <p className="mt-3 text-[15px] leading-relaxed text-fg-muted">{description}</p>
      </Reveal>

      {/* The track — a single connected line of stage cards. On phones it
          scrolls horizontally inside its own container (never the page
          body); from sm up it wraps into a legible multi-row flow. */}
      <Stagger className="relative mt-10">
        <div className="-mx-4 overflow-x-auto px-4 pb-2 sm:mx-0 sm:overflow-visible sm:px-0">
          <ol className="flex items-stretch gap-3 sm:flex-wrap">
            {stages.map((stage, i) => (
              <li key={stage} className="flex shrink-0 items-stretch gap-3 sm:shrink">
                <StaggerItem>
                  <HoverCard className="flex h-full min-w-[9.5rem] items-center gap-2.5 rounded-xl border border-line bg-surface/70 px-4 py-3.5 transition-colors duration-300 hover:border-accent/35 hover:bg-surface">
                    <span className="grid size-6 shrink-0 place-items-center rounded-full border border-line-strong bg-bg font-mono text-[10.5px] text-fg-subtle">
                      {i + 1}
                    </span>
                    <span className="text-[13.5px] font-medium text-fg">{stage}</span>
                  </HoverCard>
                </StaggerItem>
                {i < stages.length - 1 && (
                  <span aria-hidden className="hidden shrink-0 self-center text-fg-subtle/50 sm:inline">
                    <ArrowRightIcon className="size-4 rtl:-scale-x-100" />
                  </span>
                )}
              </li>
            ))}
          </ol>
        </div>
      </Stagger>

      {note && (
        <Stagger className="mt-8 grid gap-4 sm:grid-cols-3">
          <Reveal className="sm:col-span-3">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-fg-subtle">
              {note.title}
            </p>
          </Reveal>
          {note.items.map((item) => (
            <StaggerItem key={item.label}>
              <div className="h-full rounded-xl border border-line bg-bg/60 p-4">
                <p className="text-[13px] font-semibold text-fg">{item.label}</p>
                <p className="mt-1.5 text-[12.5px] leading-relaxed text-fg-subtle">{item.body}</p>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </section>
  );
}
