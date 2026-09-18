/**
 * The BATONX mark — a geometric X built from two baton strokes, not a
 * monogram. One stroke is the fixed axis (foreground color); the crossing
 * stroke carries the accent and terminates in a small resolved point, read
 * as direction/intent rather than a static crest. Deliberately not a music
 * note, not a spark/star, not a literal conductor's baton — see the P-0
 * plan's logo-system direction.
 *
 * Pure inline SVG (no raster asset) so it scales cleanly from a 16px
 * favicon-adjacent size up to a landing hero mark without a second asset,
 * and so both strokes can read their color from the current theme's tokens.
 */
export function BrandMark({
  size = 22,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 26 26"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <path
        d="M4.5 21.5 L14.5 4.5"
        stroke="currentColor"
        className="text-fg-muted"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M11 21.5 L21.5 4.5"
        stroke="currentColor"
        className="text-accent"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <circle cx="21.5" cy="4.5" r="2.1" className="fill-accent" />
    </svg>
  );
}

/**
 * Symbol + wordmark lockup — the primary lockup for the top bar and any
 * marketing surface. "BATON" in the foreground weight, "X" in the accent
 * weight, tight tracking.
 */
export function BrandLogo({
  size = 22,
  className = "",
  markClassName = "",
}: {
  size?: number;
  className?: string;
  markClassName?: string;
}) {
  return (
    <span className={"inline-flex items-center gap-2 " + className}>
      <BrandMark size={size} className={markClassName} />
      <span
        translate="no"
        className="text-[15px] font-extrabold tracking-[-0.01em] text-fg"
      >
        BATON<span className="text-accent">X</span>
      </span>
    </span>
  );
}
