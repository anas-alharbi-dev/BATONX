import Link from "next/link";
import { ArrowRightIcon, CheckIcon } from "@radix-ui/react-icons";

/**
 * Compact "this is approved, here's what's next" strip (Phase P-4) —
 * replaces the old pattern of two stacked cards (a big "Approved" banner
 * plus a second card restating the next stage's purpose and a full-size
 * button) that duplicated what the global Next Action banner and the
 * Journey rail already show. One line, one link, no competing CTA.
 */
export function ArtifactApprovedNotice({
  summary,
  nextLabel,
  nextHref,
}: {
  /** One sentence: what this approval means for downstream work. */
  summary: string;
  nextLabel: string;
  nextHref: string;
}) {
  return (
    <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface/60 px-4 py-3">
      <p className="flex min-w-0 items-center gap-2 text-sm text-fg-muted">
        <CheckIcon className="size-4 shrink-0 text-completed" aria-hidden />
        <span>{summary}</span>
      </p>
      <Link
        href={nextHref}
        className="group inline-flex shrink-0 items-center gap-1 rounded-sm text-sm font-medium text-accent hover:text-accent-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        {nextLabel}
        <ArrowRightIcon
          className="size-3.5 transition-transform group-hover:translate-x-0.5"
          aria-hidden
        />
      </Link>
    </div>
  );
}
