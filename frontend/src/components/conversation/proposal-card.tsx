"use client";

import { CheckIcon, Cross2Icon } from "@radix-ui/react-icons";

import type { ApiRequestError } from "@/lib/api/client";
import type { Proposal } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { interpolate, useLanguage } from "@/lib/i18n";

export function ProposalCard({
  proposal,
  pending,
  error,
  onApprove,
  onReject,
}: {
  proposal: Proposal;
  pending: boolean;
  error: ApiRequestError | null;
  onApprove: () => void;
  onReject: () => void;
}) {
  const { dict } = useLanguage();
  const { impact_summary: impact } = proposal;
  const target = dict.proposal.targets[proposal.target_artifact as keyof typeof dict.proposal.targets] ?? proposal.target_artifact;
  const entityId = proposal.proposed_change.entity_id;
  const isPending = proposal.status === "pending";

  return (
    <div className="mt-2 rounded-lg border border-warning/30 bg-warning/[0.06] p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="warning">{dict.proposal.badge}</Badge>
        <span className="text-xs text-fg-muted">
          {target}
          {entityId && (
            // A business/entity id (e.g. KPI-01) is a technical identifier —
            // keep it LTR even inside an Arabic sentence.
            <span dir="ltr" className="ms-1 font-mono text-[11px] text-fg-subtle">
              ({entityId})
            </span>
          )}
          {proposal.status !== "pending" && (
            <>
              {" · "}
              <span
                className={
                  proposal.status === "applied"
                    ? "text-accent"
                    : "text-fg-subtle"
                }
              >
                {proposal.status === "applied"
                  ? dict.proposal.applied
                  : proposal.status === "rejected"
                    ? dict.proposal.rejected
                    : dict.proposal.decided}
              </span>
            </>
          )}
        </span>
      </div>

      <p className="mt-2 text-sm font-medium text-fg">
        {proposal.proposed_change.summary || dict.proposal.defaultSummary}
      </p>
      {proposal.rationale && (
        <p className="mt-1 text-xs leading-relaxed text-fg-muted">
          <span className="text-fg-subtle">{dict.proposal.why} </span>
          {proposal.rationale}
        </p>
      )}

      <div className="mt-2.5 grid gap-1">
        <p className="text-[11px] uppercase tracking-[0.06em] text-fg-subtle">
          {dict.proposal.impact}
        </p>
        <ul className="grid gap-1 text-xs leading-relaxed text-fg-muted">
          {impact.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
        {impact.downstream_review_candidates.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {impact.downstream_review_candidates.map((a) => (
              <span
                key={a}
                dir="ltr"
                className="rounded-sm border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-fg-muted"
              >
                {a}
              </span>
            ))}
          </div>
        )}
      </div>

      {isPending ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" loading={pending} onClick={onApprove}>
            <CheckIcon className="size-3.5" aria-hidden />
            {dict.proposal.approveAndApply}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={pending}
            onClick={onReject}
          >
            <Cross2Icon className="size-3.5" aria-hidden />
            {dict.proposal.reject}
          </Button>
        </div>
      ) : (
        <p className="mt-2 text-[11px] text-fg-subtle">
          {proposal.status === "applied" && proposal.applied_at
            ? `${interpolate(dict.proposal.appliedAt, { when: formatDateTime(proposal.applied_at) })} ${
                impact.downstream_review_candidates.length
                  ? impact.downstream_review_candidates.join(", ") + " " + dict.proposal.needReview
                  : dict.proposal.noDownstream
              }`
            : proposal.decided_at
              ? interpolate(dict.proposal.rejectedAt, { when: formatDateTime(proposal.decided_at) })
              : null}
        </p>
      )}

      {error && (
        <p role="alert" className="mt-2 text-xs text-danger">
          {error.message}
        </p>
      )}
    </div>
  );
}
