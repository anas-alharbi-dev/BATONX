"use client";

import { useParams } from "next/navigation";

import { ShipChecklistView } from "@/components/ship/ship-checklist-view";

export default function ShipChecklistPage() {
  const params = useParams<{ slug: string }>();
  return <ShipChecklistView slug={params.slug} />;
}
