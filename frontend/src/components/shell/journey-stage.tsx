import Link from "next/link";

import type { JourneyStageView } from "@/lib/journey-model";

import { statusBadgeClass, STATUS_META } from "./status-badge";

/**
 * Status → icon + label + shape + color. Never color alone (P-1
 * accessibility requirement) — a colorblind user or a grayscale screenshot
 * can still tell "stale" from "needs review" from "blocked" by icon and
 * label shape, not hue. ``STATUS_META``/``statusBadgeClass`` live in
 * `status-badge.tsx` (P-3) so Project cards show status identically.
 */

export function JourneyStage({
  stage,
  index,
  isLast,
  statusLabel,
}: {
  stage: JourneyStageView;
  index: number;
  isLast: boolean;
  /** Localized status text (Phase P-7) — falls back to the English
   *  `STATUS_META` label so any caller that hasn't been updated yet still
   *  renders correctly. */
  statusLabel?: string;
}) {
  const meta = STATUS_META[stage.status];
  const label = statusLabel ?? meta.label;
  const inert = !stage.reachable || stage.status === "skipped";

  const marker = (
    <span
      aria-hidden
      className={
        "relative grid size-5 shrink-0 place-items-center rounded-full border font-mono text-[10px] " +
        meta.ring +
        " " +
        (stage.status === "upcoming" || stage.status === "skipped" ? "bg-bg" : "")
      }
    >
      {meta.Icon ? (
        <meta.Icon
          className={
            "size-2.5 " +
            (stage.status === "completed" ? "text-fg-inverse" : "text-fg-inverse")
          }
        />
      ) : stage.status === "in_progress" ? (
        <span className="size-2 rounded-full bg-active" />
      ) : stage.status === "skipped" ? (
        <span className="text-fg-subtle">–</span>
      ) : (
        <span className={stage.status === "upcoming" ? "text-fg-subtle" : "text-fg-inverse"}>{index + 1}</span>
      )}
      {(stage.status === "completed" || stage.status === "needs_review" || stage.status === "stale" || stage.status === "blocked") && (
        <span className={"absolute inset-0 rounded-full -z-10 " + meta.dot} />
      )}
    </span>
  );

  const body = (
    <span className="flex flex-1 flex-col gap-0.5 py-0.5 text-start">
      <span className="flex items-center gap-1.5">
        <span className={"text-[13px] font-medium " + meta.text}>{stage.label}</span>
      </span>
      <span className="text-[11px] leading-snug text-fg-subtle">{stage.purpose}</span>
      <span className={statusBadgeClass(stage.status)}>{label}</span>
    </span>
  );

  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {!isLast && (
        <span
          aria-hidden
          className={
            "absolute start-[9px] top-5 h-[calc(100%-4px)] w-px " +
            (stage.status === "completed" ? "bg-accent/50" : "bg-line-strong")
          }
        />
      )}
      {inert ? (
        <div aria-current={stage.current ? "step" : undefined} className="flex flex-1 gap-3 opacity-70">
          {marker}
          {body}
        </div>
      ) : (
        <Link
          href={stage.href}
          aria-current={stage.current ? "step" : undefined}
          className={
            "flex flex-1 gap-3 rounded-md -mx-1.5 px-1.5 transition-colors hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent " +
            (stage.current ? "bg-surface-raised motion-safe:animate-rise-in" : "")
          }
        >
          {marker}
          {body}
        </Link>
      )}
    </li>
  );
}
