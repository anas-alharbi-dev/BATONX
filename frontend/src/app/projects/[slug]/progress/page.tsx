"use client";

import { useParams } from "next/navigation";

import { ProgressView } from "@/components/progress/progress-view";

export default function ProgressPage() {
  const params = useParams<{ slug: string }>();
  return <ProgressView slug={params.slug} />;
}
