import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";

import { Spinner } from "./spinner";

type Variant = "solid" | "outline" | "ghost";
type Size = "sm" | "md" | "lg";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium " +
  "transition-[transform,background-color,border-color,color,opacity] duration-150 " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-bg " +
  "active:translate-y-px active:scale-[0.99] motion-reduce:active:translate-y-0 " +
  "motion-reduce:active:scale-100 disabled:opacity-50 disabled:pointer-events-none " +
  "[touch-action:manipulation] select-none";

const VARIANTS: Record<Variant, string> = {
  solid: "bg-accent text-accent-fg hover:bg-accent-strong",
  outline:
    "border border-line-strong bg-transparent text-fg hover:bg-surface",
  ghost: "bg-transparent text-fg-muted hover:bg-surface hover:text-fg",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-[15px]",
};

export function buttonClasses(
  variant: Variant = "solid",
  size: Size = "md",
  extra = "",
) {
  return `${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${extra}`.trim();
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "solid",
      size = "md",
      loading = false,
      className = "",
      type = "button",
      disabled,
      children,
      ...props
    },
    ref,
  ) => (
    <button
      ref={ref}
      type={type}
      aria-busy={loading || undefined}
      disabled={disabled ?? loading}
      className={buttonClasses(variant, size, className)}
      {...props}
    >
      {loading && <Spinner className="size-4" />}
      {children}
    </button>
  ),
);

Button.displayName = "Button";
