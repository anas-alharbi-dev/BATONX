"use client";

import { memo } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";

type Health = "checking" | "online" | "offline";

/** Live backend indicator for local development. Real check against /api/health/. */
function ApiStatusImpl() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 20_000,
    staleTime: 10_000,
  });

  const state: Health = isLoading
    ? "checking"
    : isError || data?.database !== "ok"
      ? "offline"
      : "online";

  const label =
    state === "online"
      ? "API online"
      : state === "offline"
        ? "API offline"
        : "Checking API";

  return (
    <span
      className="inline-flex items-center gap-2 text-xs text-fg-muted"
      aria-live="polite"
    >
      <span className="relative inline-flex size-2">
        {state === "online" && (
          <span className="absolute inline-flex size-full rounded-full bg-accent/60 animate-pulse-ring motion-reduce:hidden" />
        )}
        <span
          className={
            "relative inline-flex size-2 rounded-full " +
            (state === "online"
              ? "bg-accent"
              : state === "offline"
                ? "bg-danger"
                : "bg-fg-subtle")
          }
        />
      </span>
      <span className="hidden sm:inline">{label}</span>
    </span>
  );
}

export const ApiStatus = memo(ApiStatusImpl);
