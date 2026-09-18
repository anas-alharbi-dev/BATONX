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

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupForm />
    </Suspense>
  );
}

function SignupForm() {
  const { signup, status } = useAuth();
  const { dict } = useLanguage();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/projects/new";

  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      signup({ email: email.trim(), password, confirm_password: confirmPassword }),
    onSuccess: () => router.push(next),
  });

  const apiError = mutation.error as ApiRequestError | null;

  function submit() {
    if (!email.trim() || !password || !confirmPassword) {
      setValidationError(dict.auth.fillEveryField);
      return;
    }
    if (password !== confirmPassword) {
      setValidationError(dict.auth.passwordsMismatch);
      return;
    }
    setValidationError(null);
    mutation.mutate();
  }

  return (
    <AuthShell
      title={dict.auth.signupTitle}
      subtitle={dict.auth.signupSubtitleShort}
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
          <label htmlFor="password" className="text-sm font-medium text-fg">
            {dict.auth.password}
          </label>
          <input
            id="password"
            type="password"
            dir="ltr"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
            placeholder={dict.auth.passwordHint}
          />
        </div>

        <div className="grid gap-1.5">
          <label htmlFor="confirm-password" className="text-sm font-medium text-fg">
            {dict.auth.confirmPassword}
          </label>
          <input
            id="confirm-password"
            type="password"
            dir="ltr"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className={inputClass}
            placeholder={dict.auth.typeItAgain}
          />
        </div>

        <div aria-live="polite" className="min-h-5 text-sm text-danger">
          {validationError}
          {!validationError && apiError && apiError.message}
        </div>

        <Button type="submit" size="lg" loading={mutation.isPending} className="w-full">
          {mutation.isPending ? dict.auth.signingUp : dict.auth.signUp}
        </Button>

        <p className="text-center text-sm text-fg-muted">
          {dict.auth.haveAccount}{" "}
          <Link href="/login" className="font-medium text-accent hover:text-accent-strong">
            {dict.auth.logInLink}
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
