"use client";

import { motion } from "framer-motion";
import { CheckIcon, Link2Icon } from "@radix-ui/react-icons";

import { BrandMark } from "@/components/brand/brand-logo";
import { useLanguage } from "@/lib/i18n";
import { SOFTWARE_STAGES } from "@/lib/journey-model";

import { useMotionSafe } from "./motion-primitives";

const EASE = [0.16, 1, 0.3, 1] as const;

/** The stage chips shown inside the BATONX card — the real Software Journey
 *  order (`SOFTWARE_STAGES`, the same source of truth the authenticated
 *  Workspace's Journey rail renders from), trimmed to the seven that read
 *  well as a compact flow. Never a separate, marketing-only list. */
const SCENE_STAGE_IDS = [
  "discovery",
  "blueprint",
  "business_logic",
  "architecture",
  "roadmap",
  "tasks_build",
  "progress",
] as const;

const AGENTS = ["Claude Code", "Codex", "Cursor"] as const;

/**
 * The Landing hero's centerpiece (Landing redesign). Replaces the old plain
 * "Idea → BATONX → AI agent → Deliverable" list with a layered card
 * composition that reads the same story at a glance — Idea in, BATONX
 * orchestrating a real stage flow with two small "aware of" badges peeking
 * off its corners, an execution layer of real external agents, Delivery
 * Ready out — while staying provably true to the product: every stage name
 * comes from `SOFTWARE_STAGES`, the agent names are the same three named
 * everywhere else in the product (Phase P-1 positioning), and nothing here
 * claims BATONX executes anything itself.
 *
 * Built as a vertical card stack (not a full free-floating canvas) so it
 * stays legible and never overflows from 375px phones up through desktop —
 * the "layered/orbiting" feel comes from small corner badges anchored to
 * their own card, not from percentage-positioned elements scattered across
 * the whole scene.
 */
export function OrchestrationScene() {
  const { dict } = useLanguage();
  const safe = useMotionSafe();

  const stages = SCENE_STAGE_IDS.map((id) => dict.journeySoftware[id].label);

  return (
    <div className="relative">
      {/* Restrained ambient glow — one soft blob, never flooding the card
          stack itself. Decorative only; excluded from the a11y tree. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-x-10 -inset-y-16 -z-10"
      >
        <div className="absolute end-0 top-0 size-64 rounded-full bg-accent/[0.14] blur-3xl motion-safe:animate-glow-breathe" />
        <div className="absolute bottom-0 start-0 size-48 rounded-full bg-accent/[0.08] blur-3xl" />
      </div>

      {/* The connecting baton line running behind the card stack. */}
      <svg
        aria-hidden
        className="absolute start-[27px] top-10 bottom-10 -z-10 w-px sm:start-[31px]"
        width="2"
        height="100%"
        preserveAspectRatio="none"
      >
        <line
          x1="1"
          y1="0"
          x2="1"
          y2="100%"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeDasharray="5 6"
          className="text-line-strong"
        />
      </svg>

      <ol className="grid gap-5">
        {/* 1 — Idea */}
        <motion.li
          initial={safe ? { opacity: 0, y: 16 } : false}
          whileInView="show"
          viewport={{ once: true, margin: "-40px" }}
          variants={{ show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: EASE } } }}
          className="relative ps-[52px] sm:ps-[60px]"
        >
          <StageMarker index={1} />
          <div className="rounded-xl border border-line bg-surface/70 px-4 py-3 shadow-[0_1px_0_0_rgba(255,255,255,0.02)_inset] backdrop-blur-sm">
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-subtle">
              {dict.landing.sceneIdeaLabel}
            </p>
            <p className="mt-1 text-[13.5px] italic leading-relaxed text-fg-muted">
              {dict.landing.sceneIdeaQuote}
            </p>
          </div>
        </motion.li>

        {/* 2 — BATONX orchestration card (the anchor: larger, glassy, glowing) */}
        <motion.li
          initial={safe ? { opacity: 0, y: 16 } : false}
          whileInView="show"
          viewport={{ once: true, margin: "-40px" }}
          variants={{ show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE, delay: 0.1 } } }}
          className="relative ps-[52px] sm:ps-[60px]"
        >
          <StageMarker index={2} isBrand />
          <div className="relative">
            {/* Corner context badges — the "aware of" surface, anchored to
                this card only so nothing can overflow at any width. */}
            <div
              aria-hidden
              className="motion-safe:animate-float-delayed absolute -end-2.5 -top-3 z-10 hidden items-center gap-1.5 rounded-full border border-line-strong bg-surface-raised px-2.5 py-1 shadow-lg sm:flex"
            >
              <span className="size-1.5 rounded-full bg-accent" />
              <span className="font-mono text-[10px] text-fg-muted">
                {dict.landing.sceneApprovedBadge}
              </span>
            </div>
            <div
              aria-hidden
              className="motion-safe:animate-float-slow absolute -bottom-3 -start-2.5 z-10 hidden items-center gap-1.5 rounded-full border border-line-strong bg-surface-raised px-2.5 py-1 shadow-lg sm:flex"
            >
              <Link2Icon className="size-3 text-fg-subtle" aria-hidden />
              <span className="font-mono text-[10px] text-fg-muted">
                {dict.landing.sceneContextBadge}
              </span>
            </div>

            <div className="rounded-2xl border border-accent/25 bg-gradient-to-b from-surface-raised to-surface p-5 shadow-[0_0_0_1px_rgba(52,211,153,0.06),0_20px_50px_-20px_rgba(0,0,0,0.5)]">
              <div className="flex items-center gap-2">
                <BrandMark size={18} />
                <span translate="no" className="text-[13px] font-bold tracking-[-0.01em] text-fg">
                  BATON<span className="text-accent">X</span>
                </span>
                <span className="ms-auto font-mono text-[9.5px] uppercase tracking-[0.12em] text-fg-subtle">
                  {dict.landing.sceneOrchestrating}
                </span>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-x-1.5 gap-y-2">
                {stages.map((stage, i) => {
                  const isCurrent = i === 4;
                  return (
                    <span key={stage} className="flex items-center gap-1.5">
                      <span
                        className={
                          "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11.5px] font-medium transition-colors " +
                          (isCurrent
                            ? "border-accent/40 bg-accent-soft text-accent-strong"
                            : "border-line bg-bg/60 text-fg-muted")
                        }
                      >
                        {isCurrent && (
                          <span className="relative flex size-1.5">
                            <span className="motion-safe:animate-pulse-ring absolute inline-flex size-full rounded-full bg-accent" />
                            <span className="relative inline-flex size-1.5 rounded-full bg-accent" />
                          </span>
                        )}
                        {stage}
                      </span>
                      {i < stages.length - 1 && (
                        <span aria-hidden className="text-fg-subtle/60">
                          &rarr;
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
        </motion.li>

        {/* 3 — Execution layer */}
        <motion.li
          initial={safe ? { opacity: 0, y: 16 } : false}
          whileInView="show"
          viewport={{ once: true, margin: "-40px" }}
          variants={{ show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: EASE, delay: 0.18 } } }}
          className="relative ps-[52px] sm:ps-[60px]"
        >
          <StageMarker index={3} />
          <div className="rounded-xl border border-line bg-surface/70 px-4 py-3 backdrop-blur-sm">
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-subtle">
              {dict.landing.sceneExecutionLabel}
            </p>
            <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1.5">
              {AGENTS.map((agent, i) => (
                <span key={agent} className="flex items-center gap-3">
                  {i > 0 && <span aria-hidden className="size-1 rounded-full bg-line-strong" />}
                  <span className="text-[13px] font-medium text-fg-muted" dir="ltr" translate="no">
                    {agent}
                  </span>
                </span>
              ))}
            </div>
          </div>
        </motion.li>

        {/* 4 — Outcome */}
        <motion.li
          initial={safe ? { opacity: 0, y: 16 } : false}
          whileInView="show"
          viewport={{ once: true, margin: "-40px" }}
          variants={{ show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: EASE, delay: 0.26 } } }}
          className="relative ps-[52px] sm:ps-[60px]"
        >
          <StageMarker index={4} isDone />
          <div className="rounded-xl border border-accent/30 bg-accent-soft px-4 py-3">
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent-strong">
              {dict.landing.sceneOutcomeLabel}
            </p>
            <p className="mt-1 text-[13.5px] font-medium text-fg">
              {dict.landing.sceneOutcomeBody}
            </p>
          </div>
        </motion.li>
      </ol>
    </div>
  );
}

function StageMarker({
  index,
  isBrand,
  isDone,
}: {
  index: number;
  isBrand?: boolean;
  isDone?: boolean;
}) {
  return (
    <span
      aria-hidden
      className={
        "absolute start-0 top-0 z-10 grid size-9 shrink-0 place-items-center rounded-full border bg-bg sm:size-10 " +
        (isBrand
          ? "border-accent/40"
          : isDone
            ? "border-accent/40 bg-accent-soft"
            : "border-line-strong")
      }
    >
      {isBrand ? (
        <BrandMark size={16} />
      ) : isDone ? (
        <CheckIcon className="size-4 text-accent-strong" />
      ) : (
        <span className="font-mono text-[11px] text-fg-subtle">{index}</span>
      )}
    </span>
  );
}
