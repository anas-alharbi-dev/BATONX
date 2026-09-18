"use client";

import { useState } from "react";
import { ChevronRightIcon } from "@radix-ui/react-icons";

import { ConversationPanel } from "@/components/conversation/conversation-panel";
import type { Project } from "@/lib/api/types";
import { useLanguage } from "@/lib/i18n";

/**
 * Right column — BATONX Intelligence, permanent on desktop. Wraps the
 * existing `ConversationPanel` verbatim (all message/proposal/loading/error
 * states, all backend calls unchanged) in a persistent, collapsible column
 * instead of the floating overlay `ConversationLauncher` used it in before —
 * that overlay mechanism is kept as-is and reused as the tablet/mobile
 * fallback (see `project-workspace-shell.tsx`), so no behavior is lost, only
 * repositioned.
 */
export function IntelligencePanel({ project }: { project: Project }) {
  const { dict } = useLanguage();
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <div className="flex h-full flex-col items-center border-s border-line bg-bg py-3">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          aria-label={dict.intelligence.title}
          title={dict.intelligence.title}
          className="grid size-8 place-items-center rounded-md text-fg-subtle transition-colors hover:bg-surface hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {/* This column docks at the trailing edge (right in LTR, left in
              RTL) — the chevron always points back toward where the panel
              will expand, i.e. toward the page center. */}
          <ChevronRightIcon className="size-4 rotate-180 rtl:rotate-0" aria-hidden />
        </button>
        <span
          className="mt-3 font-mono text-[10px] uppercase tracking-[0.14em] text-fg-subtle"
          style={{ writingMode: "vertical-rl" }}
        >
          {dict.intelligence.launcher}
        </span>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col border-s border-line bg-bg">
      {/* A dedicated strip for the collapse control, kept separate from
          ConversationPanel's own header so the two never overlap regardless
          of how many lines its description wraps to at 320-380px width. */}
      <div className="flex shrink-0 justify-end px-2 pt-2">
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          aria-label={dict.intelligence.title}
          title={dict.intelligence.title}
          className="grid size-6 place-items-center rounded-md text-fg-subtle transition-colors hover:bg-surface hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <ChevronRightIcon className="size-3.5 rtl:rotate-180" aria-hidden />
        </button>
      </div>
      <div className="min-h-0 flex-1">
        <ConversationPanel project={project} />
      </div>
    </div>
  );
}
