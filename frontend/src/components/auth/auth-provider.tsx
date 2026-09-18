"use client";

import { createContext, useCallback, useContext, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type { AuthUser } from "@/lib/api/types";

/**
 * Central auth state (Phase P-2) — the ONLY place that fetches
 * `/api/auth/me/`. Every consumer (route guards, the top bar, auth pages)
 * reads from this one React Query cache entry instead of fetching
 * independently, so there is exactly one source of truth and no duplicate
 * network calls.
 *
 * "loading" vs "unauthenticated" are deliberately distinct: a route guard
 * must never redirect to /login while the very first check is still in
 * flight (that would flash-redirect an already-signed-in user on reload).
 */
export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<AuthUser>;
  signup: (input: { email: string; password: string; confirm_password: string; display_name?: string }) => Promise<AuthUser>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const ME_KEY = ["auth", "me"] as const;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ME_KEY,
    queryFn: async (): Promise<AuthUser | null> => {
      try {
        return await api.me();
      } catch (error) {
        // A 401 here means "confirmed signed out," not a failed request —
        // never surface it as a query error (which would trigger retries
        // and error UI); every other failure (network down, 500) is a real
        // error and should propagate as one.
        if (error instanceof ApiRequestError && error.status === 401) {
          return null;
        }
        throw error;
      }
    },
    retry: false,
    staleTime: 60_000,
  });

  const login = useCallback(
    async (email: string, password: string) => {
      const user = await api.login({ email, password });
      queryClient.setQueryData(ME_KEY, user);
      return user;
    },
    [queryClient],
  );

  const signup = useCallback(
    async (input: { email: string; password: string; confirm_password: string; display_name?: string }) => {
      const user = await api.signup(input);
      queryClient.setQueryData(ME_KEY, user);
      return user;
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      // Session expiry / already-logged-out-elsewhere must land here too —
      // always end in a confirmed signed-out client state.
      queryClient.setQueryData(ME_KEY, null);
    }
  }, [queryClient]);

  const status: AuthStatus = query.isPending
    ? "loading"
    : query.data
      ? "authenticated"
      : "unauthenticated";

  const value = useMemo<AuthContextValue>(
    () => ({ status, user: query.data ?? null, login, signup, logout }),
    [status, query.data, login, signup, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
