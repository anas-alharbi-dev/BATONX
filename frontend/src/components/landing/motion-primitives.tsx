"use client";

import { useEffect, useState } from "react";
import { motion, type Variants } from "framer-motion";

/**
 * Shared scroll-reveal / stagger primitives for the Landing redesign.
 * Framer Motion only lives on the public Landing — the authenticated
 * Workspace stays exactly as it was (CSS `.stagger`/`animate-rise-in`,
 * unchanged). Motion is disabled for `prefers-reduced-motion` users so they
 * get an instantly-visible, static page — never a broken half-animated one.
 */

const EASE = [0.16, 1, 0.3, 1] as const;

/**
 * Deliberately does NOT use framer-motion's own `useReducedMotion()`. That
 * hook calls `window.matchMedia` synchronously during its first *client*
 * render (see `initPrefersReducedMotion` in
 * `framer-motion/dist/es/utils/reduced-motion/index.mjs`) — before
 * hydration commits — while the server (no `window`) always resolves it to
 * `null`. Server and the client's first render disagreeing is exactly a
 * hydration mismatch, and it would show up as a differing inline `style`
 * on every `motion.div` driven by it (its `initial` variant). Instead: the
 * first render — server and client alike — always assumes motion is safe
 * (`true`), matching what the server can only ever produce; the real OS
 * preference is read after mount, in an effect, the same "resolve after
 * hydration" pattern `theme-provider.tsx` and `language-provider.tsx`
 * already use for their own browser-only reads.
 */
export function useMotionSafe() {
  const [safe, setSafe] = useState(true);

  useEffect(() => {
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    setSafe(!mql.matches);
    const onChange = () => setSafe(!mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return safe;
}

const revealVariants: Variants = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE } },
};

const revealVariantsStill: Variants = {
  hidden: { opacity: 1, y: 0 },
  show: { opacity: 1, y: 0 },
};

/** Reveals once, the moment it scrolls into view. */
export function Reveal({
  children,
  className,
  delay = 0,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "span";
}) {
  const safe = useMotionSafe();
  const Comp = motion[as];
  return (
    <Comp
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-80px" }}
      variants={safe ? revealVariants : revealVariantsStill}
      transition={safe ? { delay } : { duration: 0 }}
    >
      {children}
    </Comp>
  );
}

const containerVariants: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09, delayChildren: 0.03 } },
};

const containerVariantsStill: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0 } },
};

/** Stagger container — pair with <StaggerItem> children. */
export function Stagger({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const safe = useMotionSafe();
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-60px" }}
      variants={safe ? containerVariants : containerVariantsStill}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const safe = useMotionSafe();
  return (
    <motion.div
      className={className}
      variants={
        safe
          ? {
              hidden: { opacity: 0, y: 18, scale: 0.98 },
              show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.55, ease: EASE } },
            }
          : revealVariantsStill
      }
    >
      {children}
    </motion.div>
  );
}

/** A card that lifts and gains a soft accent glow on hover — the one
 *  recurring tactile response every card type on the page shares. */
export function HoverCard({
  children,
  className = "",
  style,
}: {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  const safe = useMotionSafe();
  return (
    <motion.div
      className={className}
      style={style}
      whileHover={safe ? { y: -4 } : undefined}
      transition={{ duration: 0.25, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}
