import type {
  DataJourneyStageId,
  JourneyStageView,
  SoftwareStageId,
} from "@/lib/journey-model";
import type { Dictionary } from "./en";

/**
 * Localizes the Journey rail's user-facing label/purpose text in place
 * (Phase P-7) — deliberately a presentation-layer overlay applied after
 * `buildSoftwareJourney`/`buildDataJourney` run, not a change to those
 * functions themselves: `stage.id`, `status`, `reachable`, and `href` (the
 * actual workflow logic) are untouched, only the two display strings are
 * swapped from the dictionary keyed by the same stable stage id.
 */
export function localizeStages(
  stages: JourneyStageView[],
  dict: Dictionary,
  isData: boolean,
): JourneyStageView[] {
  return stages.map((s) => {
    if (isData) {
      const meta = dict.journeyData[s.id as DataJourneyStageId];
      return meta ? { ...s, label: meta.label } : s;
    }
    const meta = dict.journeySoftware[s.id as SoftwareStageId];
    return meta ? { ...s, label: meta.label, purpose: meta.purpose } : s;
  });
}

export function localizedStageLabel(
  id: string,
  isData: boolean,
  dict: Dictionary,
): string | null {
  if (isData) return dict.journeyData[id as DataJourneyStageId]?.label ?? null;
  return dict.journeySoftware[id as SoftwareStageId]?.label ?? null;
}
