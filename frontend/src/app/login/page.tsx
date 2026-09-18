"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";

import { AuthJourneyPreview } from "@/components/auth/auth-journey-preview";
import { AuthShell } from "@/components/auth/auth-shell";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { inputClass } from "@/components/ui/editor-primitives";
import { ApiRequestError } from "@/lib/api/client";
import { useLanguage } from "@/lib/i18n";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const { login, status } = useAuth();
  const { dict } = useLanguage();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/projects";

  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => login(email.trim(), password),
    onSuccess: () => router.push(next),
  });

  const apiError = mutation.error as ApiRequestError | null;

  function submit() {
    if (!email.trim() || !password) {
      setValidationError(dict.auth.validationMissing);
      return;
    }
    setValidationError(null);
    mutation.mutate();
  }

  return (
    <AuthShell
      title={dict.auth.loginTitle}
      subtitle={dict.auth.loginSubtitleShort}
      visual={<AuthJourneyPreview />}
    >
      <form
        className="grid gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="grid gap-1.5">
          <label htmlFor="email" className="text-sm font-medium text-fg">
            {dict.auth.email}
          </label>
          {/* Email is a technical/machine value — keep it LTR even inside an
              Arabic-language form, same convention as an identifier. */}
          <input
            id="email"
            type="email"
            dir="ltr"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
            placeholder="you@example.com"
          />
        </div>

        <div className="grid gap-1.5">
          <div className="flex items-center justify-between">
            <label htmlFor="password" className="text-sm font-medium text-fg">
              {dict.auth.password}
            </label>
            {/* Forgot Password is a planned state — no email delivery is
                configured in local-first development yet (see the P-2
                report); this is an honest placeholder, not a fake flow. */}
            <span className="text-xs text-fg-subtle" title={dict.auth.forgotPasswordTooltip}>
              {dict.auth.forgotPassword}
            </span>
          </div>
          <input
            id="password"
            type="password"
            dir="ltr"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
            placeholder="••••••••"
          />
        </div>

        <div aria-live="polite" className="min-h-5 text-sm text-danger">
          {validationError}
          {!validationError && apiError && apiError.message}
        </div>

        <Button type="submit" size="lg" loading={mutation.isPending} className="w-full">
          {mutation.isPending ? dict.auth.loggingIn : dict.auth.logIn}
        </Button>

        <p className="text-center text-sm text-fg-muted">
          {dict.auth.newToBatonx}{" "}
          <Link href="/signup" className="font-medium text-accent hover:text-accent-strong">
            {dict.auth.createAccountLink}
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
