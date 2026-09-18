"use client";

import { useState } from "react";
import Link from "next/link";
import { MagnifyingGlassIcon, RocketIcon } from "@radix-ui/react-icons";

import type { ApiRequestError } from "@/lib/api/client";
import type { DependencyState, GeneratedPromptDTO } from "@/lib/api/types";
import { AiUnconfiguredNotice } from "@/components/feedback/ai-unconfigured-notice";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Spinner } from "@/components/ui/spinner";
import { formatDateTime } from "@/lib/format";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

import { PromptViewer } from "./prompt-viewer";

type Kind = "build" | "review";

function configFor(kind: Kind, dict: Dictionary) {
  const Icon = kind === "build" ? RocketIcon : MagnifyingGlassIcon;
  return kind === "build"
    ? {
        title: dict.taskWorkspace.buildTitle,
        role: dict.taskWorkspace.buildRole,
        Icon,
        generatingTitle: dict.taskWorkspace.buildGeneratingTitle,
        generatingBody: dict.taskWorkspace.buildGeneratingBody,
        empty: dict.taskWorkspace.buildEmpty,
        cta: dict.taskWorkspace.buildCta,
        regenTitle: dict.taskWorkspace.buildRegenTitle,
      }
    : {
        title: dict.taskWorkspace.reviewTitle,
        role: dict.taskWorkspace.reviewRole,
        Icon,
        generatingTitle: dict.taskWorkspace.reviewGeneratingTitle,
        generatingBody: dict.taskWorkspace.reviewGeneratingBody,
        empty: dict.taskWorkspace.reviewEmpty,
        cta: dict.taskWorkspace.reviewCta,
        regenTitle: dict.taskWorkspace.reviewRegenTitle,
      };
}

interface Props {
  kind: Kind;
  step: number;
  slug: string;
  prompts: GeneratedPromptDTO[];
  blocked: boolean;
  unfinished: string[];
  dependencies: DependencyState[];
  /** review only: whether a Build Prompt exists to use as supporting context */
  hasBuildPrompt?: boolean;
  generating: boolean;
  error: ApiRequestError | null;
  onGenerate: () => void;
}

export function PromptPanel({
  kind,
  step,
  slug,
  prompts,
  blocked,
  unfinished,
  dependencies,
  hasBuildPrompt,
  generating,
  error,
  onGenerate,
}: Props) {
  const { dict } = useLanguage();
  const cfg = configFor(kind, dict);
  const [confirmRegen, setConfirmRegen] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const selected = prompts.find((p) => p.id === selectedId) ?? prompts[0] ?? null;
  const missingKey = error?.code === "missing_api_key";
  const staleContext = error?.code === "stale_context";
  const accent = kind === "build";

  const header = (
    <div className="flex items-start gap-3">
      <span
        aria-hidden
        className={
          "grid size-8 shrink-0 place-items-center rounded-md border " +
          (accent
            ? "border-accent/30 bg-accent/10 text-accent"
            : "border-line-strong bg-surface text-fg-muted")
        }
      >
        <cfg.Icon className="size-4" />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-fg">
          <span className="font-mono text-xs text-fg-subtle">{step}</span>{" "}
          {cfg.title}
        </p>
        <p className="text-xs leading-relaxed text-fg-muted">{cfg.role}</p>
      </div>
      {prompts.length > 0 && !generating && (
        <Button
          variant="outline"
          size="sm"
          className="ms-auto shrink-0"
          onClick={() => setConfirmRegen(true)}
        >
          {dict.softwareShared.regenerate}
        </Button>
      )}
    </div>
  );

  const shell =
    "grid gap-4 rounded-xl border border-line border-s-2 bg-surface/40 p-5 " +
    (accent ? "border-s-accent/50" : "border-s-line-strong");

  if (blocked) {
    const names = unfinished.map((id) => {
      const d = dependencies.find((x) => x.id === id);
      return { id, label: d ? `${d.id} ${d.title}` : id };
    });
    return (
      <div className={shell}>
        {header}
        <div className="rounded-md border border-warning/25 bg-warning/10 p-3">
          <p className="text-sm text-warning">
            {dict.taskWorkspace.blockedFinishFirst}
          </p>
          <ul className="mt-1.5 grid gap-1 text-sm text-warning/90">
            {names.map((n) => (
              <li key={n.id}>
                <Link
                  href={`/projects/${slug}/roadmap/tasks/${n.id}`}
                  className="underline underline-offset-4 hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  {n.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <Button disabled className="w-fit">
          {cfg.cta}
        </Button>
      </div>
    );
  }

  if (generating) {
    return (
      <div className={shell} aria-live="polite">
        {header}
        <div className="flex items-center gap-3">
          <Spinner className="size-5 text-accent" />
          <div>
            <p className="text-sm font-medium text-fg">{cfg.generatingTitle}</p>
            <p className="text-sm text-fg-muted">{cfg.generatingBody}</p>
          </div>
        </div>
      </div>
    );
  }

  const errorBlock = (
    <>
      {error && !missingKey && (
        <p role="alert" className="text-sm text-danger">
          {staleContext
            ? error.message
            : `${prompts.length ? dict.common.couldntRegeneratePrefix : ""}${error.message}${
                !prompts.length && error.retryable ? ` ${dict.common.tryAgainSentence}` : ""
              }`}
        </p>
      )}
      {missingKey && <AiUnconfiguredNotice />}
    </>
  );

  if (prompts.length === 0) {
    return (
      <div className={shell}>
        {header}
        <p className="text-sm leading-relaxed text-fg-muted">{cfg.empty}</p>
        {kind === "review" && !hasBuildPrompt && (
          <p className="text-xs text-fg-subtle">
            {dict.taskWorkspace.noBuildPromptYet}
          </p>
        )}
        <Button className="w-fit" onClick={onGenerate}>
          {cfg.cta}
        </Button>
        {errorBlock}
      </div>
    );
  }

  return (
    <div className={shell}>
      {header}
      {errorBlock}
      {selected && <PromptViewer prompt={selected} />}

      {prompts.length > 1 && (
        <details className="rounded-md border border-line bg-bg/40">
          <summary className="cursor-pointer p-3 text-xs font-medium text-fg-muted marker:content-none">
            {interpolate(dict.taskWorkspace.previousVersions, { n: String(prompts.length - 1) })}
          </summary>
          <ul className="grid gap-1 border-t border-line p-2">
            {prompts.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(p.id)}
                  className={
                    "w-full rounded px-2 py-1.5 text-start text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent " +
                    (p.id === selected?.id
                      ? "bg-surface text-fg"
                      : "text-fg-muted hover:bg-surface")
                  }
                >
                  {formatDateTime(p.created_at)}
                  {p.id === prompts[0].id ? ` · ${dict.taskWorkspace.latest}` : ""}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      <ConfirmDialog
        open={confirmRegen}
        title={cfg.regenTitle}
        description={dict.taskWorkspace.regenerateConfirmDesc}
        confirmLabel={dict.softwareShared.regenerate}
        busy={generating}
        onConfirm={() => {
          setConfirmRegen(false);
          onGenerate();
        }}
        onCancel={() => setConfirmRegen(false)}
      />
    </div>
  );
}
