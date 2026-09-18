interface SkeletonProps {
  className?: string;
}

/** Shimmering placeholder. Match the size of the content it replaces. */
export function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={`relative overflow-hidden rounded-md bg-surface-hover ${className}`}
    >
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/[0.04] to-transparent motion-reduce:animate-none" />
    </div>
  );
}
