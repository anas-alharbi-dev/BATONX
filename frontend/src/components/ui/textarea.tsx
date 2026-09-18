import { forwardRef } from "react";
import type { TextareaHTMLAttributes } from "react";

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className = "", rows = 3, ...props }, ref) => (
  <textarea
    ref={ref}
    rows={rows}
    className={
      "w-full resize-y rounded-md border border-line bg-bg-subtle px-3.5 py-2.5 " +
      "text-sm text-fg placeholder:text-fg-subtle " +
      "transition-colors duration-150 " +
      "focus-visible:outline-none focus-visible:border-accent focus-visible:ring-2 " +
      "focus-visible:ring-accent/25 " +
      className
    }
    {...props}
  />
));

Textarea.displayName = "Textarea";
