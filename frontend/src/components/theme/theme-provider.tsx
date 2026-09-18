"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type ThemePreference = "system" | "light" | "dark";
type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "batonx:theme";

interface ThemeContextValue {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (pref: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemPrefersDark(): boolean {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return true; // dark-first fallback
  }
}

function readStoredPreference(): ThemePreference {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
  } catch {
    /* ignore — private mode / blocked storage */
  }
  return "system";
}

function applyResolvedTheme(resolved: ResolvedTheme) {
  document.documentElement.setAttribute("data-resolved-theme", resolved);
}

/**
 * Theme preference: system | light | dark, persisted client-side only
 * (localStorage — no backend, no auth yet; see brand.ts / P-2 for the future
 * account-level preference). The initial resolved value is stamped
 * synchronously before hydration by the inline script in the root layout
 * (see `themeInitScript`), so there is no flash of the wrong theme; this
 * provider takes over from that point for live updates (toggle clicks, OS
 * theme changes while "system" is selected).
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>("system");
  const [resolved, setResolved] = useState<ResolvedTheme>("dark");

  useEffect(() => {
    const stored = readStoredPreference();
    setPreferenceState(stored);
    const next = stored === "system" ? (systemPrefersDark() ? "dark" : "light") : stored;
    setResolved(next);
    applyResolvedTheme(next);

    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      setPreferenceState((current) => {
        if (current === "system") {
          const sysNext = mql.matches ? "dark" : "light";
          setResolved(sysNext);
          applyResolvedTheme(sysNext);
        }
        return current;
      });
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  const setPreference = useCallback((pref: ThemePreference) => {
    setPreferenceState(pref);
    try {
      window.localStorage.setItem(STORAGE_KEY, pref);
    } catch {
      /* ignore */
    }
    const next = pref === "system" ? (systemPrefersDark() ? "dark" : "light") : pref;
    setResolved(next);
    applyResolvedTheme(next);
  }, []);

  const value = useMemo(
    () => ({ preference, resolved, setPreference }),
    [preference, resolved, setPreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

/**
 * Inlined verbatim as a blocking <script> at the top of <head> so the
 * resolved theme is stamped on <html> before first paint — no flash of the
 * wrong theme on load or reload. Kept as a plain string (not a component)
 * since it must run before React hydrates.
 */
export const themeInitScript = `(function(){try{
  var KEY="${STORAGE_KEY}";
  var pref=localStorage.getItem(KEY);
  var resolved=(pref==="light"||pref==="dark")?pref:(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");
  document.documentElement.setAttribute("data-resolved-theme", resolved);
}catch(e){document.documentElement.setAttribute("data-resolved-theme","dark");}})();`;
