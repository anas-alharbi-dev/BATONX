"use client";

import { AgentPositioningSection } from "@/components/landing/agent-positioning-section";
import { ConceptSection } from "@/components/landing/concept-section";
import { FinalCtaSection } from "@/components/landing/final-cta-section";
import { Hero } from "@/components/landing/hero";
import { HumanControlSection } from "@/components/landing/human-control-section";
import { IntelligenceSection } from "@/components/landing/intelligence-section";
import { TraceabilitySection } from "@/components/landing/traceability-section";
import { WorkflowSection } from "@/components/landing/workflow-section";
import { DATA_STAGE_META, SOFTWARE_STAGES } from "@/lib/journey-model";
import { useLanguage } from "@/lib/i18n";

export default function LandingPage() {
  const { dict } = useLanguage();
  const softwareStageLabels = SOFTWARE_STAGES.map((s) => dict.journeySoftware[s.id].label);
  const dataStageLabels = Object.keys(DATA_STAGE_META).map(
    (id) => dict.journeyData[id as keyof typeof dict.journeyData].label,
  );

  return (
    <main>
      <Hero />

      <ConceptSection />

      <WorkflowSection
        id="software"
        eyebrow={dict.landing.softwareEyebrow}
        title={dict.landing.softwareWorkflowTitle}
        description={dict.landing.softwareWorkflowDescription}
        stages={softwareStageLabels}
      />

      <WorkflowSection
        id="data"
        reverse
        eyebrow={dict.landing.dataEyebrow}
        title={dict.landing.dataWorkflowTitle}
        description={dict.landing.dataWorkflowDescription}
        stages={dataStageLabels}
        note={{
          title: dict.landing.dataNoteTitle,
          items: [
            { label: dict.concepts.observedFactPlural, body: dict.concepts.observedFactBody },
            { label: dict.concepts.aiInterpretation, body: dict.concepts.aiInterpretationBody },
            { label: dict.concepts.humanDecisionPlural, body: dict.concepts.humanDecisionBody },
          ],
        }}
      />

      <HumanControlSection />
      <IntelligenceSection />
      <AgentPositioningSection />
      <TraceabilitySection />
      <FinalCtaSection />

      <footer className="mx-auto max-w-6xl border-t border-line py-10 safe-px">
        <p className="text-xs text-fg-subtle">{dict.landing.footer}</p>
      </footer>
    </main>
  );
}
