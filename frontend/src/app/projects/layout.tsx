"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/components/auth/auth-provider";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * The single auth gate for every authenticated route (Phase P-2):
 * `/projects`, `/projects/new`, and `/projects/[slug]/*` all nest under this
 * one layout, so route protection lives in exactly one place rather than
 * being scattered across each page.
 */
export default function ProjectsAuthLayout({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "unauthenticated") {
      const next = encodeURIComponent(pathname || "/projects");
      router.replace(`/login?next=${next}`);
    }
  }, [status, pathname, router]);

  if (status !== "authenticated") {
    // Covers both "loading" (first check in flight) and "unauthenticated"
    // (redirect just fired, this frame still rendering) — never flash any
    // authenticated content, and never flash the redirect target's content
    // either.
    return (
      <div className="grid gap-3 p-8">
        <Skeleton className="h-8 w-52" />
        <Skeleton className="h-4 w-72" />
      </div>
    );
  }

  return <>{children}</>;
}
