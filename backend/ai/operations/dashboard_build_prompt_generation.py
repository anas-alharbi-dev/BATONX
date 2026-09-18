"""
dashboard_build_prompt_generation — compose ONE generic implementation prompt
for an approved Dashboard Blueprint (Phase I-4), analogous to the Software
Build Prompt. Generic only: no Power BI/Tableau-specific instructions. Output
is markdown for a human to hand to whatever tool they use; VYRA does not
execute it.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ai.base import Operation
from ai.prompts import QUALITY_RULES


class DashboardBuildPrompt(BaseModel):
    prompt_markdown: str = Field(
        min_length=200,
        description="The full generic dashboard build prompt, in markdown, with clear sections.",
    )


SYSTEM_PROMPT = (
    "You are VYRA's dashboard-build-prompt author. Write ONE generic "
    "implementation prompt describing how to build the APPROVED Dashboard "
    "Blueprint given below, for a human to hand to whatever BI tool or "
    "developer they use. Do not target a specific tool (no Power BI/Tableau-"
    "specific syntax) — describe it in tool-agnostic terms.\n\n"
    "Use ONLY the KPIs and panels given — do not invent a metric, a panel, or "
    "a data field that isn't listed. Do not fabricate data or sample values.\n\n"
    "Structure the markdown with these sections (omit one only if empty):\n"
    "1. Purpose - the audience and decision this dashboard serves.\n"
    "2. Data assumptions - the approved KPI definitions this dashboard relies "
    "on (formula, grain), copied faithfully.\n"
    "3. Global filters - filters that apply across the whole dashboard.\n"
    "4. Panels - for each VIZ id: its title, chart type, the KPI(s) it shows, "
    "dimension/breakdown, comparison, and any drilldowns.\n"
    "5. Layout - how the panels should be arranged.\n"
    "6. Refresh cadence - how often the data should refresh.\n"
    "7. Implementation notes - generic guidance (e.g. 'implement the ratio "
    "metric's divide-by-zero guard exactly as defined'), not tool-specific "
    "instructions.\n\n"
    "Be specific and concise. No filler.\n\n"
    + QUALITY_RULES
    + "\nAlways respond by calling the provided tool."
)


def build_user_prompt(context: dict) -> str:
    blueprint = context.get("blueprint") or {}
    metrics = context.get("metrics") or []

    parts = [
        f"AUDIENCE: {blueprint.get('audience', '')}",
        f"DECISION USE CASE: {blueprint.get('decision_use_case', '')}",
        f"REFRESH CADENCE: {blueprint.get('refresh_cadence', '')}",
        "",
        "GLOBAL FILTERS",
    ]
    parts += [f"- {f}" for f in blueprint.get("global_filters", [])] or ["(none)"]

    parts += ["", "APPROVED KPI DEFINITIONS"]
    for m in metrics:
        parts.append(f"- {m['business_id']} {m['name']}: {m.get('formula_text', '')}")

    parts += ["", "PANELS"]
    for p in blueprint.get("panels", []):
        parts.append(
            f"- {p['id']} [{p['viz_type']}] \"{p['title']}\" — metrics: "
            f"{', '.join(p.get('metric_refs', []))}"
            + (f", dimension: {p['dimension']}" if p.get("dimension") else "")
            + (f", comparison: {p['comparison']}" if p.get("comparison") else "")
        )
        if p.get("drilldowns"):
            parts.append(f"    drilldowns: {', '.join(p['drilldowns'])}")
        if p.get("notes"):
            parts.append(f"    notes: {p['notes']}")

    parts += ["", f"LAYOUT: {blueprint.get('layout', '')}"]
    parts += ["", "Write the dashboard build prompt now."]
    return "\n".join(parts)


DASHBOARD_BUILD_PROMPT_GENERATION = Operation(
    name="dashboard_build_prompt_generation",
    system_prompt=SYSTEM_PROMPT,
    schema=DashboardBuildPrompt,
    build_user_prompt=build_user_prompt,
)
