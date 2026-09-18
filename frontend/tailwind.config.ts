import type { Config } from "tailwindcss";

import { tokens } from "./src/lib/design-tokens";

/**
 * The Tailwind theme reads CSS custom properties (declared once in
 * globals.css from `tokens.color.dark` / `tokens.color.light`) rather than
 * static hex values, so a semantic class like `bg-surface` resolves
 * correctly under the system theme, an explicit override, and the runtime
 * theme toggle alike — see `src/components/theme/`. Every component still
 * only ever writes a semantic class name; it never sees a hex value.
 */
const colorTokens = Object.fromEntries(
  Object.keys(tokens.color.dark).map((name) => [name, `var(--${name})`]),
);

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: colorTokens,
      borderColor: { DEFAULT: "var(--line)" },
      ringColor: { DEFAULT: "var(--accent)" },
      borderRadius: tokens.radius,
      fontFamily: {
        sans: [...tokens.font.sans],
        mono: [...tokens.font.mono],
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "rise-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          from: { transform: "translateX(-100%)" },
          to: { transform: "translateX(100%)" },
        },
        "pulse-ring": {
          "0%": { opacity: "0.85", transform: "scale(0.85)" },
          "70%, 100%": { opacity: "0", transform: "scale(2.2)" },
        },
        "baton-travel": {
          from: { strokeDashoffset: "24" },
          to: { strokeDashoffset: "0" },
        },
        // Landing-page-only ambient motion (Phase: Landing redesign). Slow,
        // small-amplitude, and — like every other keyframe here — already
        // silenced by the global `prefers-reduced-motion` reset in
        // globals.css, which zeroes animation-duration for every animated
        // element on the page, this one included.
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        "glow-breathe": {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.4s cubic-bezier(0.16, 1, 0.3, 1) both",
        "rise-in": "rise-in 0.5s cubic-bezier(0.16, 1, 0.3, 1) both",
        shimmer: "shimmer 1.6s ease-in-out infinite",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.16, 1, 0.3, 1) infinite",
        "baton-travel": "baton-travel 0.45s cubic-bezier(0.16, 1, 0.3, 1) both",
        float: "float 6s cubic-bezier(0.45, 0, 0.55, 1) infinite",
        "float-delayed": "float 7s cubic-bezier(0.45, 0, 0.55, 1) infinite 1.2s",
        "float-slow": "float 9s cubic-bezier(0.45, 0, 0.55, 1) infinite 0.5s",
        "glow-breathe": "glow-breathe 4.5s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
