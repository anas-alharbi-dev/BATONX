interface SpinnerProps {
  className?: string;
  label?: string;
}

/** Accessible loading indicator. Rotation only (compositor-friendly); halts under reduced motion. */
export function Spinner({ className = "size-4", label = "Loading" }: SpinnerProps) {
  return (
    <svg
      className={`animate-[spin_0.7s_linear_infinite] motion-reduce:animate-none ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label={label}
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="3"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
