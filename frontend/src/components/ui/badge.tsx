import type { HTMLAttributes } from "react";

type Tone = "neutral" | "accent" | "success" | "danger" | "warning";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-hover text-fg-muted border-line",
  accent: "bg-accent/10 text-accent border-accent/25",
  success: "bg-accent/10 text-accent border-accent/25",
  danger: "bg-danger/10 text-danger border-danger/25",
  warning: "bg-warning/10 text-warning border-warning/25",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ tone = "neutral", className = "", ...props }: BadgeProps) {
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 " +
        `text-xs font-medium ${TONES[tone]} ${className}`
      }
      {...props}
    />
  );
}
