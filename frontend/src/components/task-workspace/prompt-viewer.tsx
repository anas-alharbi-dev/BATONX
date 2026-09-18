"use client";

import type { GeneratedPromptDTO } from "@/lib/api/types";
import { CopyButton } from "@/components/ui/copy-button";
import { formatDateTime } from "@/lib/format";
import { interpolate, useLanguage } from "@/lib/i18n";

export function PromptViewer({ prompt }: { prompt: GeneratedPromptDTO }) {
  const { dict } = useLanguage();
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-fg-subtle" dir="ltr">
          {interpolate(dict.taskWorkspace.generatedAt, { when: formatDateTime(prompt.created_at) })}
          {prompt.model ? ` · ${prompt.model}` : ""}
        </span>
        <CopyButton text={prompt.content} />
      </div>
      {/* The prompt itself is authored in English for the coding agent that
          consumes it (Phase P-7: a technical LTR island even in Arabic
          mode) — never mirrored or re-flowed regardless of UI language. */}
      <pre
        dir="ltr"
        className="max-h-[34rem] overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-bg-subtle p-4 text-start font-mono text-xs leading-relaxed text-fg-muted"
      >
        {prompt.content}
      </pre>
      <p className="text-xs text-fg-subtle">
        {dict.taskWorkspace.copyPromptHint}
      </p>
    </div>
  );
}
