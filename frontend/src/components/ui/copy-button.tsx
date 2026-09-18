"use client";

import { useState } from "react";
import { CheckIcon, CopyIcon } from "@radix-ui/react-icons";

import { Button } from "./button";

export function CopyButton({
  text,
  label = "Copy Prompt",
}: {
  text: string;
  label?: string;
}) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
    window.setTimeout(() => setState("idle"), 2500);
  }

  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={copy}>
        {state === "copied" ? (
          <CheckIcon className="size-3.5" aria-hidden />
        ) : (
          <CopyIcon className="size-3.5" aria-hidden />
        )}
        {state === "copied" ? "Copied" : label}
      </Button>
      <span aria-live="polite" className="text-xs text-fg-subtle">
        {state === "failed" ? "Copy failed — select the text and copy manually." : ""}
      </span>
    </div>
  );
}
