# Data Journey

The real, end-to-end path a Data project follows in BATONX. Each stage's input, purpose, and output.

## The core distinction: Fact, Interpretation, Decision

Every Data stage respects one rule, deterministically enforced end to end:

- **Observed Fact** — what the data actually shows. Computed directly from the data (profiling stats, query results, validation outcomes). Never AI-generated, never guessed.
- **AI Interpretation** — what an observation might *mean*. Always explicitly labeled as AI-proposed, never presented as settled.
- **Human Decision** — what a person actually approved. The only thing any downstream step — a dashboard, a delivered report, an execution agent — is allowed to act on.

A Finding is a fact. An Insight's interpretation is a proposal. Only an approved artifact is authoritative.

## Brief

- **Input:** a business question or analysis goal.
- **Purpose:** capture the audience, success criteria, constraints, and candidate sources before any data work starts.
- **Output:** an approved Data Brief — the goal every later Data stage serves.

## Sources

- **Input:** the approved Brief.
- **Purpose:** register real datasets, profile them (row counts, columns, types, obvious quality signals), and capture an AI-proposed interpretation of what each source represents — kept visibly separate from the profiling facts themselves.
- **Output:** registered, profiled datasets with human-reviewed source interpretations.

## Quality

- **Input:** profiled datasets.
- **Purpose:** surface concrete data-quality observations (missing values, outliers, inconsistent formats, …) and record how each was resolved.
- **Output:** an approved Data Quality record — what's known-good, and what a downstream consumer should be careful of.

## Transformation

- **Input:** the approved Quality record.
- **Purpose:** define the plan for turning raw, registered sources into governed, analysis-ready data.
- **Output:** an approved Transformation Plan.

## Metrics

- **Input:** the approved Transformation Plan.
- **Purpose:** define specific metrics/KPIs with an explicit business meaning, not just a formula.
- **Output:** approved Metric definitions, each traceable to the business question that motivated it.

## Queries

- **Input:** approved Metrics.
- **Purpose:** define and execute query plans against the governed data.
- **Output:** approved Query Plans with their real, executed Query Results — a fact, not a projection.

## Analysis

- **Input:** Query Results.
- **Purpose:** surface Findings (facts) and Insights (AI-proposed interpretations plus a recommendation), kept visually and structurally distinct.
- **Output:** an approved Analysis Plan, with every Insight either accepted or left as a proposal.

## Progress

- **Input:** the real state of every Data artifact.
- **Purpose:** show what's validated, pending, or blocked — computed from actual artifact and dataset state.
- **Output:** a live progress view and the single deterministic "next action."

## Delivery

- **Input:** the approved Analysis.
- **Purpose:** produce a Dashboard Blueprint and a Build Prompt for it, then check real delivery readiness.
- **Output:** a readiness-checked deliverable — BATONX does not build the dashboard itself; the Build Prompt is handed to whatever renders it.
