/**
 * TypeScript mirrors of the backend contracts (DRF serializers + Pydantic
 * schemas). Kept in one place so the frontend has a single typed source.
 */

export type ProjectStage =
  | "discovery"
  | "blueprint"
  | "business_logic"
  | "architecture"
  | "roadmap"
  | "building"
  | "ship"
  | "data_brief"
  | "data_sources";

/** Domain-workflow discriminator. */
export type ProjectType = "software" | "data";

/** The lens that tunes which Data-workflow stages are required (Phase I). */
export type DataGoal =
  | "analytics"
  | "bi"
  | "engineering"
  | "warehouse"
  | "quality"
  | "mixed";

/** Advisory downstream-stale flags (Phase C / D). Set by backend domain logic only. */
export type DownstreamStale = Partial<
  Record<"business_logic" | "architecture" | "roadmap", boolean>
>;

export type QuestionType = "text" | "single_select" | "multi_select";

/** A single generated discovery question (backend assigns the id). */
export interface DiscoveryQuestion {
  id: string;
  question: string;
  type: QuestionType;
  options: string[];
  why_it_matters: string;
}

/** text -> string; single_select -> string; multi_select -> string[] */
export type DiscoveryAnswer = string | string[];

export interface Discovery {
  questions: DiscoveryQuestion[];
  answers: Record<string, DiscoveryAnswer>;
  generated_at: string | null;
  answered_at: string | null;
}

// --- Blueprint ---

export type Priority = "must" | "should" | "could";

export interface UserRole {
  name: string;
  description: string;
}

export interface FunctionalRequirement {
  id: string;
  text: string;
  priority: Priority;
}

export interface UserFlow {
  name: string;
  steps: string[];
}

export interface BlueprintContent {
  product_summary: string;
  problem: string;
  solution: string;
  target_users: string[];
  user_roles: UserRole[];
  core_features: string[];
  mvp_features: string[];
  future_features: string[];
  functional_requirements: FunctionalRequirement[];
  business_rules: string[];
  user_flows: UserFlow[];
  out_of_scope: string[];
}

/** `{}` (no `content`) until the Blueprint has been generated. */
export interface Blueprint {
  content?: BlueprintContent;
  generated_at?: string;
  updated_at?: string;
  approved_at?: string | null;
}

// --- Architecture ---

export interface TechChoice {
  choice: string;
  why: string;
}
export interface AuthApproach {
  approach: string;
  why: string;
}
export interface ArchOverview {
  style: string;
  summary: string;
}
export interface ArchComponent {
  name: string;
  responsibility: string;
}
export interface ApiArea {
  name: string;
  purpose: string;
}
export interface DataEntity {
  entity: string;
  fields: string[];
  relationships: string[];
}
export interface Integration {
  name: string;
  purpose: string;
  why: string;
}
export interface ArchDecision {
  decision: string;
  rationale: string;
}

export interface ArchitectureContent {
  overview: ArchOverview;
  frontend: TechChoice;
  backend: TechChoice;
  database: TechChoice;
  auth: AuthApproach;
  components: ArchComponent[];
  api_areas: ApiArea[];
  data_model: DataEntity[];
  integrations: Integration[];
  security: string[];
  deployment: AuthApproach;
  key_decisions: ArchDecision[];
  constraints: string[];
}

/** `{}` (no `content`) until the Architecture has been generated. */
export interface Architecture {
  content?: ArchitectureContent;
  generated_at?: string;
  updated_at?: string;
  approved_at?: string | null;
}

// --- Roadmap ---

export type TaskStatus =
  | "not_started"
  | "in_progress"
  | "ready_for_review"
  | "completed";

export interface RoadmapTask {
  id: string;
  order: number;
  phase_id: string;
  title: string;
  objective: string;
  why: string;
  requirements: string[];
  dependencies: string[];
  expected_output: string;
  acceptance_criteria: string[];
  status: TaskStatus;
}

export interface RoadmapPhase {
  id: string;
  order: number;
  title: string;
  objective: string;
  tasks: RoadmapTask[];
}

export interface RoadmapContent {
  phases: RoadmapPhase[];
}

export interface Roadmap {
  content?: RoadmapContent;
  generated_at?: string;
  updated_at?: string;
  approved_at?: string | null;
}

export interface PhaseProgress {
  phase_id: string;
  total: number;
  completed: number;
  done: boolean;
}

export interface RoadmapProgress {
  total: number;
  completed: number;
  in_progress: number;
  not_started: number;
  percent: number;
  phases: PhaseProgress[];
}

/** Derived server-side: progress + dependency-aware task pointers. */
export interface RoadmapMeta {
  approved: boolean;
  progress: RoadmapProgress;
  current_task_id: string | null;
  next_recommended_task_id: string | null;
}

// --- Task Workspace / Build Prompt ---

export interface DependencyState {
  id: string;
  title: string;
  status: TaskStatus | "unknown";
  expected_output: string;
}

export interface ContextRequirement {
  id: string;
  text: string;
  priority: Priority;
}

export interface RelevantArchitecture {
  style: string;
  summary: string;
  frontend: string;
  backend: string;
  database: string;
  auth: string;
  components: ArchComponent[];
  api_areas: ApiArea[];
  data_model: DataEntity[];
  integrations: { name: string; purpose: string }[];
  security: string[];
  key_decisions: ArchDecision[];
  constraints: string[];
}

export interface RelevantBusinessRule {
  id: string;
  statement: string;
  actor: string;
  conditions: string[];
  outcome: string;
  exceptions: string[];
  related_requirements: string[];
}

export interface RelevantBusinessLogic {
  summary?: string;
  business_rules?: RelevantBusinessRule[];
  validations?: { id: string; rule: string; applies_to: string }[];
  state_transitions?: {
    entity: string;
    from: string;
    to: string;
    trigger: string;
    actor: string;
    guards: string[];
  }[];
  permissions?: { actor: string; can: string[]; conditions: string[] }[];
  edge_cases?: { id: string; scenario: string; expected_behavior: string }[];
}

export interface RelevantContext {
  product: { idea: string; domain: string; problem: string; solution: string };
  task: {
    id: string;
    order: number;
    phase_id: string;
    phase_title: string;
    title: string;
    objective: string;
    why: string;
    expected_output: string;
    acceptance_criteria: string[];
    status: TaskStatus;
  };
  dependencies: DependencyState[];
  requirements: ContextRequirement[];
  requirement_notes: string[];
  user_roles: UserRole[];
  business_rules: string[];
  business_logic: RelevantBusinessLogic;
  architecture: RelevantArchitecture;
}

export type PromptKind = "build" | "review";

export interface GeneratedPromptDTO {
  id: number;
  kind: PromptKind;
  content: string;
  model: string;
  created_at: string;
}

export interface TaskWorkspace {
  task: RoadmapTask;
  phase: { id: string; order: number; title: string; objective: string };
  dependencies: DependencyState[];
  blocked: boolean;
  unfinished_dependencies: string[];
  requirements: ContextRequirement[];
  requirement_notes: string[];
  relevant_context: RelevantContext;
  roadmap_approved: boolean;
  prompts: GeneratedPromptDTO[];
}

// --- Business Logic ---

export interface BLActor {
  name: string;
  description: string;
}
export interface BLPermission {
  actor: string;
  can: string[];
  conditions: string[];
}
export interface BusinessRule {
  id: string;
  statement: string;
  actor: string;
  conditions: string[];
  outcome: string;
  exceptions: string[];
  validations: string[];
  related_requirements: string[];
  derived: boolean;
}
export interface BLValidation {
  id: string;
  rule: string;
  applies_to: string;
  related_requirements: string[];
}
export interface BLApprovalFlow {
  name: string;
  approver: string;
  steps: string[];
  conditions: string[];
  related_requirements: string[];
}
export interface BLStateTransition {
  entity: string;
  from_state: string;
  to_state: string;
  trigger: string;
  actor: string;
  guards: string[];
  effects: string[];
  related_requirements: string[];
}
export interface BLEdgeCase {
  id: string;
  scenario: string;
  expected_behavior: string;
  related_requirements: string[];
}

export interface BusinessLogicContent {
  summary: string;
  actors: BLActor[];
  permissions: BLPermission[];
  business_rules: BusinessRule[];
  validations: BLValidation[];
  approval_flows: BLApprovalFlow[];
  state_transitions: BLStateTransition[];
  edge_cases: BLEdgeCase[];
  open_questions: string[];
}

/** `{}` (no `content`) until Business Logic has been generated. */
export interface BusinessLogic {
  content?: BusinessLogicContent;
  generated_at?: string;
  updated_at?: string;
  approved_at?: string | null;
}

export interface Project {
  id: string;
  slug: string;
  name: string;
  original_idea: string;
  project_type: ProjectType;
  data_goal: DataGoal | "";
  stage: ProjectStage;
  downstream_stale: DownstreamStale;
  discovery: Discovery;
  blueprint: Blueprint;
  blueprint_approved_at: string | null;
  business_logic: BusinessLogic;
  business_logic_approved_at: string | null;
  architecture: Architecture;
  architecture_approved_at: string | null;
  roadmap: Roadmap;
  roadmap_approved_at: string | null;
  roadmap_meta: RoadmapMeta | null;
  data_brief: DataBrief;
  data_brief_approved_at: string | null;
  data_quality: { content?: DataQualityContent; generated_at?: string; updated_at?: string; approved_at?: string | null };
  data_quality_approved_at: string | null;
  transformation_plan: {
    content?: TransformationPlanContent;
    generated_at?: string;
    updated_at?: string;
    approved_at?: string | null;
  };
  transformation_plan_approved_at: string | null;
  dashboard_blueprint: {
    content?: DashboardBlueprintContent;
    generated_at?: string;
    updated_at?: string;
    approved_at?: string | null;
  };
  dashboard_blueprint_approved_at: string | null;
  created_at: string;
  updated_at: string;
}

// --- Data & Analytics (Phase I-1) ---

export interface DataBriefContent {
  business_goal: string;
  decision_context: string;
  audience: string[];
  success_criteria: string[];
  constraints: string[];
  candidate_sources: string[];
  out_of_scope: string[];
  data_goal: string;
}

export interface DataBrief {
  content?: DataBriefContent;
  generated_at?: string;
  updated_at?: string;
  approved_at?: string | null;
}

export interface DatasetSchemaColumn {
  name: string;
  dtype: string;
  nullable: boolean;
  sensitivity: string | null;
}

export interface SourceInterpretationContent {
  business_entity: string;
  grain: string;
  key_columns: string[];
  column_meanings: { column: string; meaning: string }[];
  caveats: string[];
  sensitivity_flags: { column: string; kind: string; note?: string }[];
}

export interface SourceInterpretation {
  content?: SourceInterpretationContent;
  generated_at?: string;
  updated_at?: string;
  approved_at?: string | null;
}

export type DatasetStatus = "uploaded" | "profiling" | "profiled" | "failed";

export interface Dataset {
  id: string;
  name: string;
  source_type: "csv" | "json";
  original_filename: string;
  content_type: string;
  size_bytes: number;
  encoding: string | null;
  delimiter: string | null;
  row_count: number | null;
  column_count: number | null;
  inferred_schema: DatasetSchemaColumn[];
  sampled: boolean;
  status: DatasetStatus;
  profiling_stale: boolean;
  error: string;
  supersedes: string | null;
  uploaded_at: string;
  profiled_at: string | null;
  interpretation: SourceInterpretation;
  interpretation_approved_at: string | null;
  interpretation_stale: boolean;
  latest_profiling_run_id: string | null;
}

export interface ProfilingColumn {
  name: string;
  dtype: string;
  count: number;
  null_count: number;
  null_pct: number;
  distinct_count: number;
  distinct_pct: number;
  probable_key: boolean;
  sensitivity: string | null;
  sensitivity_kind: string | null;
  top_values?: { value: string; count: number }[];
  sample?: string[];
  min?: number;
  max?: number;
  mean?: number;
  median?: number;
  stddev?: number;
  p25?: number;
  p75?: number;
  numeric_range?: string;
  date_range?: string;
  min_date?: string;
  max_date?: string;
  min_length?: number;
  max_length?: number;
  blank_count?: number;
}

export interface ProfilingRun {
  id: string;
  table_stats: {
    row_count: number;
    column_count: number;
    duplicate_row_count: number;
    sampled: boolean;
    sample_size: number;
  };
  columns: ProfilingColumn[];
  created_at: string;
}

export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface Job {
  id: string;
  kind: string;
  status: JobStatus;
  progress: number;
  params: Record<string, unknown>;
  result_ref: Record<string, unknown>;
  error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DatasetDetail {
  dataset: Dataset;
  profiling_run: ProfilingRun | null;
  job: Job | null;
}

// --- Data Quality + Transformation (Phase I-2) ---

export type QualityDimension =
  | "completeness"
  | "uniqueness"
  | "validity"
  | "consistency"
  | "duplicates"
  | "schema"
  | "freshness";
export type QualitySeverity = "info" | "warn" | "critical";
export type QualityAssertion =
  | "not_null"
  | "unique"
  | "in_set"
  | "range"
  | "regex"
  | "row_count_gt";

export interface QualityObservation {
  id: string;
  dataset_ref: string;
  column: string;
  dimension: QualityDimension;
  severity: QualitySeverity;
  statement: string;
  evidence: Record<string, unknown>;
  heuristic: boolean;
}

export interface QualityRule {
  id: string;
  dataset_ref: string;
  column: string;
  dimension: QualityDimension;
  assertion: QualityAssertion;
  params: Record<string, unknown>;
  rationale: string;
  related_observations: string[];
  accepted_risk: boolean;
  status: "draft" | "approved";
}

export interface DataQualityContent {
  observations: QualityObservation[];
  rules: QualityRule[];
}

export interface QualityCheckResult {
  rule_id: string;
  dataset_ref: string;
  assertion: string;
  column: string;
  accepted_risk: boolean;
  related_observations: string[];
  passed: boolean;
  failing_row_count: number | null;
  sample_failures: Record<string, unknown>[];
  error: string;
  checked_at: string;
}

export interface QualityCheckRun {
  id: string;
  results: QualityCheckResult[];
  summary: {
    total: number;
    passed: number;
    failed: number;
    critical_failed: number;
  };
  job: Job | null;
  created_at: string;
}

export interface DataQualityView {
  content: DataQualityContent;
  approved: boolean;
  approved_at: string | null;
  unresolved_critical: number;
  latest_check_run: QualityCheckRun | null;
}

export type TransformOp =
  | "drop_columns"
  | "rename"
  | "cast"
  | "fill_na"
  | "dedupe"
  | "standardize_values"
  | "parse_date"
  | "derive_column"
  | "filter_rows";

export interface TransformStep {
  id: string;
  op: TransformOp;
  params: Record<string, unknown>;
  input_refs: string[];
  output_name: string;
  rationale: string;
  related_quality_rules: string[];
}

export interface TransformOutput {
  name: string;
  description: string;
  grain: string;
  columns: Record<string, unknown>[];
}

export interface TransformationPlanContent {
  source_dataset_id: string;
  steps: TransformStep[];
  outputs: TransformOutput[];
}

export interface TransformationPreview {
  output_name: string;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  rendered_sql: string;
}

export interface TransformationView {
  content: TransformationPlanContent | null;
  approved: boolean;
  approved_at: string | null;
  generated_at?: string;
  updated_at?: string;
  rendered_sql: string | null;
  latest_preview: { job: Job; preview: TransformationPreview } | null;
}

export interface TransformationPreviewResult {
  job: Job;
  preview: TransformationPreview;
}

// --- Metrics / KPIs (Phase I-3) ---

export type MetricAggregation =
  | "sum"
  | "count"
  | "count_distinct"
  | "avg"
  | "min"
  | "max"
  | "ratio";
export type MetricFilterOp = "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "in" | "not_in";

export interface MetricMeasure {
  field: string;
}

export interface MetricFilter {
  field: string;
  operator: MetricFilterOp;
  value: unknown;
}

export interface MetricStructured {
  aggregation: MetricAggregation;
  base_table_ref: string;
  measure?: MetricMeasure | null;
  numerator?: MetricMeasure | null;
  denominator?: MetricMeasure | null;
  default_filters: MetricFilter[];
  time_field: string;
  dimensions: string[];
}

export interface MetricValidationRun {
  id: string;
  query_sql: string;
  result: { value: unknown; row_count: number; null_result: boolean } | Record<string, never>;
  passed: boolean;
  error: string;
  created_at: string;
}

export type MetricStatus = "draft" | "approved";

export interface MetricDefinition {
  id: string;
  business_id: string;
  name: string;
  business_meaning: string;
  formula_text: string;
  structured: MetricStructured;
  time_grain: string;
  allowed_dimensions: string[];
  source_fields: string[];
  owner: string;
  related_goal_ref: string;
  caveats: string[];
  validation_checks: string[];
  status: MetricStatus;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  latest_validation: MetricValidationRun | null;
}

export interface MetricEditableFields {
  name: string;
  business_meaning: string;
  formula_text: string;
  structured: MetricStructured;
  time_grain: string;
  allowed_dimensions: string[];
  source_fields: string[];
  owner: string;
  related_goal_ref: string;
  caveats: string[];
  validation_checks: string[];
}

// --- Queries (Phase I-3) ---

export interface QueryPlan {
  objective: string;
  required_kpi_refs: string[];
  required_fields: string[];
  base_table_ref: string;
  grain: string;
  dimensions: string[];
  filters: Record<string, unknown>[];
  joins: Record<string, unknown>[];
  sort: string[];
  expected_result_shape: string;
  assumptions: string[];
}

export interface QueryReview {
  generation?: {
    explanation: string;
    referenced_kpi_ids: string[];
    referenced_fields: string[];
  };
  ai?: {
    alignment_notes: string;
    kpi_compliance_notes: string;
    risks: string[];
    double_counting_risk: boolean;
    null_handling_notes: string;
    performance_notes: string;
    scope_notes: string;
    recommendation: "looks_good" | "needs_changes";
  };
  human_reviewed?: boolean;
  human_reviewed_at?: string;
}

export interface QueryRun {
  id: string;
  executed_sql: string;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  created_at: string;
}

export type QueryStatus =
  | "draft_plan"
  | "plan_approved"
  | "sql_generated"
  | "reviewed"
  | "executed";

export interface DataQuery {
  id: string;
  business_id: string;
  question: string;
  plan: QueryPlan | Record<string, never>;
  plan_approved_at: string | null;
  sql: string;
  dialect: string;
  kpi_refs: string[];
  review: QueryReview;
  status: QueryStatus;
  created_at: string;
  updated_at: string;
  latest_run: QueryRun | null;
}

// --- Data Lineage (Phase I-3) ---

export interface LineageEdge {
  from: string;
  to: string;
  type: string;
}

export interface LineageResult {
  node: string;
  exists: boolean;
  upstream: string[];
  downstream: string[];
  edges: LineageEdge[];
}

// --- Analysis / Insights / Dashboard (Phase I-4) ---

export type AnalysisMethod = "descriptive" | "trend" | "segmentation" | "comparison" | "funnel";

export interface AnalysisComparison {
  label: string;
  time_range?: { start: string; end: string } | null;
  filters: { field: string; operator: string; value: unknown }[];
}

export interface AnalysisPlan {
  id: string;
  business_id: string;
  business_question: string;
  method: AnalysisMethod;
  hypotheses: string[];
  required_metrics: string[];
  segments: string[];
  comparisons: AnalysisComparison[];
  time_range: { start: string; end: string } | Record<string, never>;
  expected_outputs: string[];
  status: "draft" | "approved";
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  results: { id: string; created_at: string; findings_count: number }[];
  latest_result_id: string | null;
}

export interface AnalysisFinding {
  id: string;
  statement: string;
  metric_values: Record<string, unknown>;
  breakdown: Record<string, unknown>[];
  evidence: {
    analysis_plan_ref: string;
    kpi_refs: string[];
    dataset_refs: string[];
    query_refs: string[];
  };
  computed_at: string;
}

export interface Insight {
  id: string;
  business_id: string;
  analysis_result_id: string;
  fact: string;
  interpretation: string;
  recommendation: string;
  confidence: "low" | "medium" | "high";
  supporting_finding_ids: string[];
  caveats: string[];
  status: "draft" | "accepted";
  accepted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnalysisResult {
  id: string;
  plan_id: string;
  plan_business_id: string;
  job_id: string | null;
  findings: AnalysisFinding[];
  data_caveats: string[];
  created_at: string;
  insights: Insight[];
}

export type VizType =
  | "kpi_card" | "line" | "bar" | "stacked_bar" | "table" | "scatter" | "funnel" | "heatmap";

export interface DashboardPanel {
  id: string;
  title: string;
  viz_type: VizType;
  metric_refs: string[];
  dimension: string;
  comparison: string;
  drilldowns: string[];
  anomaly_view: boolean;
  insight_refs: string[];
  notes: string;
}

export interface DashboardBlueprintContent {
  audience: string;
  decision_use_case: string;
  refresh_cadence: string;
  global_filters: string[];
  panels: DashboardPanel[];
  layout: string;
}

export interface DashboardBuildPromptRecord {
  id: string;
  content: string;
  model: string;
  created_at: string;
}

export interface DashboardView {
  content: DashboardBlueprintContent | null;
  approved: boolean;
  approved_at: string | null;
  generated_at?: string;
  updated_at?: string;
  latest_build_prompt: DashboardBuildPromptRecord | null;
}

// --- Data Progress / Delivery Readiness (Phase I-5) ---

export type DataStageId =
  | "data_brief" | "sources" | "data_quality" | "transformation_plan"
  | "metrics" | "queries" | "analysis" | "dashboard" | "delivery_readiness";
export type DataStageStatus =
  | "not_started" | "in_progress" | "needs_review" | "complete" | "blocked" | "skipped";

export interface DataProgressStage {
  id: DataStageId;
  name: string;
  status: DataStageStatus;
  blockers: string[];
}

export interface DataProgressSummary {
  stages_total: number;
  stages_complete: number;
  stages_in_review: number;
  stages_blocked: number;
  stages_skipped: number;
  completion_percentage: number;
  open_critical_quality: number;
  pending_proposals: number;
  stale_count: number;
}

export interface DataProgress {
  summary: DataProgressSummary;
  stages: DataProgressStage[];
  next_action: { stage: DataStageId; label: string; href: string } | null;
  stale_context: string[];
  deferred_future_stages: string[];
}

export type DataReadinessStatus = "NOT_READY" | "READY_WITH_MANUAL_CHECKS" | "READY_TO_DELIVER";

export interface DataReadiness {
  overall_status: DataReadinessStatus;
  readiness_summary: string;
  automatic_checks: AutomaticCheck[];
  manual_checks: ManualCheck[];
  blockers: ShipBlocker[];
  warnings: ShipBlocker[];
  pending_manual_confirmations: number;
}

// --- Progress (Phase F) ---

export interface ProgressSummary {
  total_tasks: number;
  not_started: number;
  in_progress: number;
  ready_for_review: number;
  completed: number;
  blocked: number;
  completion_percentage: number;
}

export interface PhaseProgress extends ProgressSummary {
  phase_id: string;
  title: string;
  order: number;
}

export interface ProgressTaskBrief {
  id: string;
  title: string;
  phase_id: string;
  status: TaskStatus;
}

export interface BlockedProgressTask extends ProgressTaskBrief {
  unfinished_dependencies: string[];
}

export interface NextProgressTask extends ProgressTaskBrief {
  phase_title: string;
}

export interface ProjectProgress {
  summary: ProgressSummary;
  phases: PhaseProgress[];
  next_task: NextProgressTask | null;
  blocked_tasks: BlockedProgressTask[];
  ready_for_review_tasks: ProgressTaskBrief[];
  completed_tasks: ProgressTaskBrief[];
  stale_context: string[];
  roadmap_stale: boolean;
}

// --- Ship Checklist (Phase G) ---

export type ShipCheckStatus = "pass" | "fail" | "warning";

export type ShipReadiness =
  | "NOT_READY"
  | "READY_WITH_MANUAL_CHECKS"
  | "READY_TO_SHIP";

export interface AutomaticCheck {
  id: string;
  category: string;
  title: string;
  kind: "automatic";
  status: ShipCheckStatus;
  required: boolean;
  evidence: string;
  action: string;
}

export interface ManualCheck {
  id: string;
  category: string;
  title: string;
  kind: "manual";
  required: boolean;
  confirmed: boolean;
  confirmed_at: string | null;
  note: string;
  why_manual: string;
}

export interface ShipBlocker {
  id: string;
  title: string;
  evidence: string;
}

export interface ShipChecklist {
  overall_status: ShipReadiness;
  readiness_summary: string;
  stage: ProjectStage;
  progress: {
    completion_percentage: number;
    total_tasks: number;
    completed: number;
    blocked: number;
    ready_for_review: number;
  };
  automatic_checks: AutomaticCheck[];
  manual_checks: ManualCheck[];
  blockers: ShipBlocker[];
  warnings: ShipBlocker[];
  stale_context: string[];
  roadmap_stale: boolean;
  pending_manual_confirmations: number;
}

// --- Conversational Layer (Phase H) ---

export type ProposalStatus = "pending" | "approved" | "rejected" | "applied";

export interface ProposalImpact {
  target_artifact: string;
  downstream_review_candidates: string[];
  stale_propagation_possible: boolean;
  notes: string[];
}

export interface Proposal {
  id: string;
  conversation_id: string;
  target_artifact: string;
  proposal_type: string;
  proposed_change: {
    sections?: Record<string, unknown>;
    summary?: string;
    entity_id?: string;
  };
  rationale: string;
  impact_summary: ProposalImpact;
  status: ProposalStatus;
  created_at: string;
  decided_at: string | null;
  applied_at: string | null;
}

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  metadata: {
    intent?: "informational" | "proposal";
    referenced_artifacts?: string[];
    prompt_version?: string;
    proposal_id?: string;
  };
  created_at: string;
}

export interface Conversation {
  id: string;
  project: string;
  summary: string;
  created_at: string;
  updated_at: string;
  messages: ConversationMessage[];
  proposals: Proposal[];
}

export interface ConversationTurnResult {
  message: ConversationMessage;
  proposal: Proposal | null;
}

export interface ProposalDecisionResult {
  project?: Project;
  proposal: Proposal;
}

export interface CreateProjectResponse {
  project: Project;
}

export interface HealthResponse {
  status: string;
  database: string;
  service: string;
}

export interface ApiError {
  code: string;
  message: string;
  retryable: boolean;
  details?: unknown;
}

// --- Auth (Phase P-2) ---

export interface AuthUser {
  id: number;
  email: string;
  display_name: string | null;
  plan: "free";
}
