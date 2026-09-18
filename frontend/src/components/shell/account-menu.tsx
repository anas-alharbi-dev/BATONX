"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ExitIcon, PersonIcon } from "@radix-ui/react-icons";

import { useAuth } from "@/components/auth/auth-provider";
import { useLanguage } from "@/lib/i18n";

/**
 * Replaces P-1's neutral "not signed in" placeholder with the real
 * authenticated identity + account menu. Deliberately minimal — only
 * Log out today; Profile/Preferences/Usage/Billing are named future slots
 * (see the P-2 report), not built here.
 */
export function AccountMenu() {
  const { user, logout } = useAuth();
  const { dict } = useLanguage();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      router.push("/");
    }
  }

  const initial = user!.email.charAt(0).toUpperCase();

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${dict.account.menuAria} — ${user.email}`}
        className="grid size-8 place-items-center rounded-full border border-line bg-surface text-xs font-semibold text-fg-muted transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        {initial}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute end-0 top-[calc(100%+8px)] z-20 w-56 rounded-lg border border-line bg-surface-raised p-1.5 shadow-lg motion-safe:animate-rise-in"
        >
          <div className="flex items-center gap-2 rounded-md px-2.5 py-2">
            <PersonIcon className="size-4 shrink-0 text-fg-subtle" aria-hidden />
            {/* The email is a technical identifier — keep it LTR even in
                Arabic mode so it never visually reverses. */}
            <div className="min-w-0">
              <p dir="ltr" className="truncate text-start text-sm font-medium text-fg">
                {user.email}
              </p>
              <p className="text-[11px] uppercase tracking-[0.06em] text-fg-subtle">
                {user.plan} {dict.account.plan}
              </p>
            </div>
          </div>
          <div className="my-1 h-px bg-line" role="none" />
          <button
            type="button"
            role="menuitem"
            onClick={handleLogout}
            disabled={loggingOut}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-start text-sm text-fg-muted transition-colors hover:bg-surface-hover hover:text-fg disabled:opacity-50"
          >
            <ExitIcon className="size-4" aria-hidden />
            {loggingOut ? dict.account.loggingOut : dict.account.logOut}
          </button>
        </div>
      )}
    </div>
  );
}
