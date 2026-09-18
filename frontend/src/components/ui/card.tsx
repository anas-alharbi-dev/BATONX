import type { HTMLAttributes } from "react";

/** Elevation container. Used only where grouping/elevation carries meaning. */
export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={
        "rounded-lg border border-line bg-surface " +
        "shadow-[0_1px_0_0_rgb(255_255_255_/_0.02)_inset,0_16px_40px_-24px_rgb(0_0_0_/_0.6)] " +
        className
      }
      {...props}
    />
  );
}
