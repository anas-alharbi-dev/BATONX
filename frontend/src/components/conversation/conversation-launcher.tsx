"use client";

import { useEffect, useState } from "react";
import { Cross2Icon } from "@radix-ui/react-icons";

import { BrandMark } from "@/components/brand/brand-logo";
import type { Project } from "@/lib/api/types";
import { useLanguage } from "@/lib/i18n";

import { ConversationPanel } from "./conversation-panel";

/**
 * Tablet/mobile entry point to BATONX Intelligence — a floating launcher
 * opening a full drawer. On desktop the Workspace shell renders
 * `IntelligencePanel` as a permanent column instead and this never mounts;
 * below that breakpoint this is the entire Intelligence experience, so every
 * state `ConversationPanel` supports (empty/history/loading/proposal/error)
 * is reachable here exactly as it is in the desktop column.
 */
export function ConversationLauncher({ project }: { project: Project }) {
  const { dict } = useLanguage();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-5 end-5 z-40 inline-flex items-center gap-2 rounded-full border border-line-strong bg-surface px-4 py-2.5 text-sm font-medium text-fg shadow-[0_8px_30px_-12px_rgb(0_0_0_/_0.7)] transition-colors hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <BrandMark size={16} />
          {dict.intelligence.launcher}
        </button>
      )}

      {open && (
        <div className="fixed inset-0 z-50 flex">
          <button
            type="button"
            aria-label={dict.intelligence.closeAria}
            onClick={() => setOpen(false)}
            className="flex-1 bg-black/50 backdrop-blur-[1px]"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label={dict.intelligence.title}
            className="animate-rise-in flex h-full w-full max-w-md flex-col border-s border-line bg-bg shadow-2xl"
          >
            {/* A dedicated strip for Close, kept separate from
                ConversationPanel's own header (title + awareness indicator)
                so the two never overlap regardless of content length. */}
            <div className="flex shrink-0 justify-end px-2 pt-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label={dict.intelligence.closeAria}
                className="rounded-md p-1.5 text-fg-muted transition-colors hover:bg-surface hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                <Cross2Icon className="size-4" aria-hidden />
              </button>
            </div>
            <div className="min-h-0 flex-1">
              <ConversationPanel project={project} />
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
