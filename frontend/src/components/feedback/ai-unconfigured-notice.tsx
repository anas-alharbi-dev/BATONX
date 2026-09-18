"use client";

import { interpolate, useLanguage } from "@/lib/i18n";

/**
 * Shown when the backend returns `missing_api_key`. Honest, not an error
 * dead-end. Deliberately doesn't name a specific AI vendor (Phase P-6:
 * BATONX stays model-agnostic in its user-facing language) even though this
 * dev environment only has one provider wired up today.
 */
export function AiUnconfiguredNotice() {
  const { dict } = useLanguage();
  const body = interpolate(dict.intelligence.aiUnconfiguredBody, { path: "backend/.env" });
  // The path is a real filesystem path — render it as a technical LTR
  // island (Phase P-7) even mid-sentence in an Arabic paragraph.
  const [before, after] = body.split("backend/.env");

  return (
    <div className="rounded-md border border-warning/25 bg-warning/10 px-4 py-3 text-sm text-warning">
      <p className="font-medium">{dict.intelligence.aiUnconfiguredTitle}</p>
      <p className="mt-1 text-warning/90">
        {before}
        <span dir="ltr" className="font-mono">
          backend/.env
        </span>
        {after}
      </p>
    </div>
  );
}
