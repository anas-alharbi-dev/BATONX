/**
 * Design tokens — the single source of visual truth (Phase P-1).
 *
 * Two full palettes (dark + light), same semantic shape, consumed as CSS
 * custom properties (see globals.css) rather than static Tailwind theme
 * values — Tailwind's JIT theme can't switch at runtime, so every color here
 * is also declared as a `var(--token)` in globals.css and Tailwind is
 * pointed at those variables. Components reference semantic Tailwind classes
 * (bg-surface, text-fg-muted, border-line, ring-accent, …) and never
 * hardcode a hex value — that discipline from Phase 0 is unchanged, only the
 * indirection layer underneath it gained a second palette.
 *
 * Direction: premium technical tool. Absolute near-black / soft off-white
 * neutrals, one desaturated accent (emerald/mint), restrained. No purple /
 * AI-gradient aesthetic. Semantic status colors are independent of the
 * accent so a KPI chart or a "stale" badge is never mistaken for "approved."
 */
export const tokens = {
  color: {
    dark: {
      // surfaces
      bg: "#0a0a0b",
      "bg-subtle": "#0f0f11",
      surface: "#141417",
      "surface-raised": "#1a1a1e",
      "surface-hover": "#1e1e23",
      // text
      fg: "#f4f4f5",
      "fg-muted": "#a1a1aa",
      "fg-subtle": "#71717a",
      "fg-inverse": "#0a0a0b",
      // hairlines
      line: "#26262b",
      "line-strong": "#33333b",
      // accent (single; saturation < 80%)
      accent: "#34d399",
      "accent-strong": "#10b981",
      "accent-soft": "rgba(52, 211, 153, 0.12)",
      "accent-fg": "#04160d",
      // status (independent of accent)
      success: "#34d399",
      "success-soft": "rgba(52, 211, 153, 0.12)",
      warning: "#fbbf24",
      "warning-soft": "rgba(251, 191, 36, 0.12)",
      danger: "#f87171",
      "danger-soft": "rgba(248, 113, 113, 0.12)",
      info: "#7dd3fc",
      "info-soft": "rgba(125, 211, 252, 0.12)",
      // workflow state (Journey / Progress / Readiness)
      completed: "#34d399",
      active: "#7dd3fc",
      "needs-review": "#fbbf24",
      stale: "#f0b429",
      blocked: "#f87171",
      upcoming: "#52525b",
      skipped: "#3f3f46",
    },
    light: {
      bg: "#f7f8f7",
      "bg-subtle": "#eef1ef",
      surface: "#ffffff",
      "surface-raised": "#ffffff",
      "surface-hover": "#eef1ef",
      fg: "#14181a",
      "fg-muted": "#52605c",
      "fg-subtle": "#7c8884",
      "fg-inverse": "#ffffff",
      line: "#dde3e0",
      "line-strong": "#c7cfcb",
      accent: "#0f9d70",
      "accent-strong": "#0b7d59",
      "accent-soft": "rgba(15, 157, 112, 0.10)",
      "accent-fg": "#ffffff",
      success: "#0f9d70",
      "success-soft": "rgba(15, 157, 112, 0.10)",
      warning: "#9a6407",
      "warning-soft": "rgba(154, 100, 7, 0.10)",
      danger: "#c23b34",
      "danger-soft": "rgba(194, 59, 52, 0.10)",
      info: "#0d7fa8",
      "info-soft": "rgba(13, 127, 168, 0.10)",
      completed: "#0f9d70",
      active: "#0d7fa8",
      "needs-review": "#9a6407",
      stale: "#a15c07",
      blocked: "#c23b34",
      upcoming: "#a7b0ac",
      skipped: "#c7cfcb",
    },
  },
  radius: {
    sm: "6px",
    md: "10px",
    lg: "14px",
    xl: "20px",
  },
  font: {
    sans: ["var(--font-geist-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
    mono: ["var(--font-geist-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
  },
} as const;
