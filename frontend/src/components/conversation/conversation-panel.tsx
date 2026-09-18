"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PaperPlaneIcon } from "@radix-ui/react-icons";

import { api, ApiRequestError } from "@/lib/api/client";
import type {
  Conversation,
  ConversationMessage,
  Project,
  Proposal,
} from "@/lib/api/types";
import { AiUnconfiguredNotice } from "@/components/feedback/ai-unconfigured-notice";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { currentStageLabel } from "@/components/shell/project-journey";
import { useLanguage, type Dictionary } from "@/lib/i18n";

import { ProposalCard } from "./proposal-card";

const STORAGE_PREFIX = "batonx:conversation:";

function storedId(slug: string): string | null {
  try {
    return window.localStorage.getItem(STORAGE_PREFIX + slug);
  } catch {
    return null;
  }
}
function storeId(slug: string, id: string) {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + slug, id);
  } catch {
    /* ignore */
  }
}

async function loadConversation(slug: string): Promise<Conversation> {
  const existing = storedId(slug);
  if (existing) {
    try {
      return await api.getConversation(slug, existing);
    } catch (err) {
      if ((err as ApiRequestError).code !== "conversation_not_found") throw err;
    }
  }
  const created = await api.createConversation(slug);
  storeId(slug, created.id);
  return created;
}

/** Reuses the exact structured flag every other Workspace surface (Project
 *  cards, the Journey rail) already reads — never a second staleness
 *  computation. */
function isProjectStale(project: Project): boolean {
  return Object.values(project.downstream_stale ?? {}).some(Boolean);
}

const APPROVAL_FIELDS: (keyof Project)[] = [
  "blueprint_approved_at",
  "business_logic_approved_at",
  "architecture_approved_at",
  "roadmap_approved_at",
  "data_brief_approved_at",
  "data_quality_approved_at",
  "transformation_plan_approved_at",
  "dashboard_blueprint_approved_at",
];

function approvedArtifactCount(project: Project): number {
  return APPROVAL_FIELDS.filter((f) => Boolean(project[f])).length;
}

/** Compact, safe starter prompts (Phase P-6) — static per project type, plus
 *  one state-derived prompt surfaced only when the already-computed `stale`
 *  flag is true. Never a second business-rules engine: everything here maps
 *  to a real, already-supported conversation capability. Sourced from the
 *  dictionary (Phase P-7) so Arabic gets its own natural phrasing, not a
 *  runtime translation of the English strings. */
function starterPrompts(projectType: "software" | "data", stale: boolean, dict: Dictionary): string[] {
  const base = projectType === "data" ? dict.intelligence.startersData : dict.intelligence.startersSoftware;
  return stale ? [dict.intelligence.startersStale, ...base] : base;
}

function MessageBubble({ message }: { message: ConversationMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div className="max-w-[85%]">
        {!isUser && (
          <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.08em] text-fg-subtle">
            BATONX
          </p>
        )}
        <div
          className={
            "whitespace-pre-wrap rounded-lg px-3 py-2 text-sm leading-relaxed " +
            (isUser
              ? "bg-accent/15 text-fg"
              : "border border-line bg-surface/60 text-fg-muted")
          }
        >
          {message.content}
        </div>
      </div>
    </div>
  );
}

export function ConversationPanel({ project }: { project: Project }) {
  const slug = project.slug;
  const projectType = project.project_type;
  const pathname = usePathname();
  const { dict } = useLanguage();
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const [pendingProposalId, setPendingProposalId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const query = useQuery({
    queryKey: ["conversation", slug],
    queryFn: () => loadConversation(slug),
    retry: false,
    staleTime: Infinity,
  });

  const conversation = query.data;

  const setConversation = (updater: (c: Conversation) => Conversation) => {
    qc.setQueryData<Conversation>(["conversation", slug], (c) =>
      c ? updater(c) : c,
    );
  };

  const send = useMutation({
    mutationFn: (content: string) => {
      if (!conversation) throw new Error("no conversation");
      return api.sendConversationMessage(slug, conversation.id, content);
    },
    onSuccess: (result) => {
      setConversation((c) => ({
        ...c,
        messages: [...c.messages, result.message],
        proposals: result.proposal
          ? [...c.proposals, result.proposal]
          : c.proposals,
      }));
    },
  });

  const decide = useMutation({
    mutationFn: ({
      proposalId,
      action,
    }: {
      proposalId: string;
      action: "approve" | "reject";
    }) =>
      action === "approve"
        ? api.approveProposal(slug, proposalId)
        : api.rejectProposal(slug, proposalId),
    onMutate: ({ proposalId }) => setPendingProposalId(proposalId),
    onSuccess: (result) => {
      setConversation((c) => ({
        ...c,
        proposals: c.proposals.map((p) =>
          p.id === result.proposal.id ? result.proposal : p,
        ),
      }));
      if (result.proposal.status === "applied") {
        // Every page that reads authoritative project state gets refreshed
        // from the real APIs — Journey, Next Action, and artifact status all
        // derive from these same query keys, so they update naturally.
        // Never simulated client-side. Covers every real proposal target
        // (Software: Blueprint/Business Logic/Architecture live on the
        // Project itself; Data: project-level artifacts plus the
        // entity-level lists a Metric/Query/Analysis Plan proposal can
        // change) — an unaffected page simply refetches unchanged data.
        for (const key of [
          "project",
          "progress",
          "ship-checklist",
          "data-progress",
          "data-readiness",
          "data-quality",
          "transformation",
          "metrics",
          "queries",
          "dashboard",
        ]) {
          qc.invalidateQueries({ queryKey: [key, slug] });
        }
      }
    },
    onSettled: () => setPendingProposalId(null),
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [conversation?.messages.length, send.isPending]);

  const sendError = send.error as ApiRequestError | null;
  const decideError = decide.error as ApiRequestError | null;
  const missingKey = sendError?.code === "missing_api_key";

  function submit(value?: string) {
    const text = (value ?? draft).trim();
    if (!text || send.isPending || !conversation) return;
    // optimistic user bubble
    setConversation((c) => ({
      ...c,
      messages: [
        ...c.messages,
        {
          id: -Date.now(),
          role: "user",
          content: text,
          metadata: {},
          created_at: new Date().toISOString(),
        },
      ],
    }));
    setDraft("");
    send.mutate(text);
  }

  const proposalById = (id?: string): Proposal | undefined =>
    id ? conversation?.proposals.find((p) => p.id === id) : undefined;

  const stale = isProjectStale(project);
  const stageLabel = pathname ? currentStageLabel(pathname, project, dict) : null;
  const approvedCount = approvedArtifactCount(project);

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-line px-4 py-3">
        <p className="text-sm font-semibold text-fg">{dict.intelligence.title}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-fg-subtle">
          {dict.intelligence.description}
        </p>
        {/* Context/awareness indicator — reassurance, not a debug dump: no
            token counts, no raw context digest. */}
        <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-fg-subtle">
          <span className="rounded-full bg-surface px-1.5 py-px">
            {dict.intelligence.awareOf}{" "}
            {stageLabel ? `${stageLabel} ${dict.intelligence.stage}` : dict.intelligence.thisProject}
          </span>
          <span>
            · {approvedCount}{" "}
            {approvedCount === 1 ? dict.intelligence.approvedArtifact : dict.intelligence.approvedArtifacts}
          </span>
          {stale && <span className="text-warning">· {dict.intelligence.staleDownstream}</span>}
        </p>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-4"
      >
        {query.isPending && (
          <div className="space-y-3">
            <Skeleton className="h-16 w-3/4" />
            <Skeleton className="ms-auto h-10 w-1/2" />
          </div>
        )}

        {query.isError && (
          <p role="alert" className="text-sm text-danger">
            {(query.error as ApiRequestError).message}
          </p>
        )}

        {conversation && conversation.messages.length === 0 && (
          <div className="grid gap-2.5 rounded-lg border border-line bg-surface/40 p-4 text-sm text-fg-muted">
            <p className="font-medium text-fg">{dict.intelligence.askTitle}</p>
            <p className="text-xs leading-relaxed text-fg-subtle">{dict.intelligence.askBody}</p>
            <div className="flex flex-wrap gap-1.5">
              {starterPrompts(projectType, stale, dict).map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => submit(prompt)}
                  className="rounded-full border border-line-strong bg-bg px-2.5 py-1 text-xs text-fg-muted transition-colors hover:border-accent/50 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {conversation?.messages.map((message) => {
          const proposal =
            message.role === "assistant"
              ? proposalById(message.metadata.proposal_id)
              : undefined;
          return (
            <div key={message.id} className="space-y-1">
              <MessageBubble message={message} />
              {proposal && (
                <ProposalCard
                  proposal={proposal}
                  pending={pendingProposalId === proposal.id}
                  error={
                    pendingProposalId === null &&
                    decideError &&
                    decide.variables?.proposalId === proposal.id
                      ? decideError
                      : null
                  }
                  onApprove={() =>
                    decide.mutate({ proposalId: proposal.id, action: "approve" })
                  }
                  onReject={() =>
                    decide.mutate({ proposalId: proposal.id, action: "reject" })
                  }
                />
              )}
            </div>
          );
        })}

        {send.isPending && (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-2 text-xs text-fg-subtle"
          >
            <Spinner className="size-3.5" />
            {dict.intelligence.thinking}
          </div>
        )}

        {missingKey && <AiUnconfiguredNotice />}
        {sendError && !missingKey && (
          <p role="alert" className="text-sm text-danger">
            {sendError.message}
          </p>
        )}
      </div>

      <form
        className="border-t border-line p-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label htmlFor="assistant-input" className="sr-only">
          {dict.intelligence.composerLabel}
        </label>
        <div className="flex items-end gap-2 rounded-lg border border-line bg-bg-subtle p-1.5 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/25">
          <textarea
            id="assistant-input"
            rows={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={dict.intelligence.composerPlaceholder}
            className="max-h-32 min-h-[2.25rem] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-fg placeholder:text-fg-subtle focus-visible:outline-none"
            disabled={!conversation || send.isPending}
          />
          <Button
            type="submit"
            size="sm"
            aria-label={dict.intelligence.send}
            disabled={!draft.trim() || send.isPending || !conversation}
          >
            {/* A directional "send" glyph — mirror it under RTL so it still
                points toward the composer's leading edge. */}
            <PaperPlaneIcon className="size-4 rtl:-scale-x-100" aria-hidden />
          </Button>
        </div>
      </form>
    </div>
  );
}
