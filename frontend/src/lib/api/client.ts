/**
 * Typed API client. Unwraps the backend's uniform error envelope
 * ({ error: { code, message, retryable, details } }) into a typed
 * ApiRequestError. Works from the browser and (for RSC) the server.
 */
import type {
  AnalysisPlan,
  AnalysisResult,
  ApiError,
  ArchitectureContent,
  AuthUser,
  BlueprintContent,
  BusinessLogicContent,
  Conversation,
  ConversationTurnResult,
  CreateProjectResponse,
  DashboardBlueprintContent,
  DashboardView,
  DataBriefContent,
  DataGoal,
  DataQualityContent,
  DataQualityView,
  Dataset,
  DatasetDetail,
  DataQuery,
  DataProgress,
  DataReadiness,
  DiscoveryAnswer,
  HealthResponse,
  Insight,
  Job,
  LineageResult,
  MetricDefinition,
  MetricEditableFields,
  Project,
  ProjectProgress,
  ProjectType,
  ProposalDecisionResult,
  QueryPlan,
  RoadmapPhase,
  ShipChecklist,
  SourceInterpretationContent,
  TaskStatus,
  TaskWorkspace,
  TransformationPlanContent,
  TransformationPreviewResult,
  TransformationView,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/**
 * Phase P-2: session-cookie auth. The session cookie itself is HttpOnly
 * (never readable here, never should be); the CSRF cookie is deliberately
 * JS-readable (Django's own default) so it can be echoed back as
 * `X-CSRFToken` on every unsafe request, exactly as Django's CSRF
 * middleware expects — no token is ever placed in localStorage.
 */
function csrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function authHeaders(method: string | undefined): Record<string, string> {
  const m = (method ?? "GET").toUpperCase();
  if (SAFE_METHODS.has(m)) return {};
  const token = csrfToken();
  return token ? { "X-CSRFToken": token } : {};
}

export class ApiRequestError extends Error {
  code: string;
  retryable: boolean;
  status: number;
  details?: unknown;

  constructor(error: ApiError, status = 0) {
    super(error.message);
    this.name = "ApiRequestError";
    this.code = error.code;
    this.retryable = error.retryable;
    this.status = status;
    this.details = error.details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      cache: "no-store",
      credentials: "include",
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(init?.method),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiRequestError({
      code: "network_error",
      message: "Can't reach the BATONX API. Make sure the backend is running on port 8000.",
      retryable: true,
    });
  }

  const body = (await response.json().catch(() => null)) as
    | ({ error?: ApiError } & Record<string, unknown>)
    | null;

  if (!response.ok) {
    throw new ApiRequestError(
      body?.error ?? {
        code: "unknown_error",
        message: `Request failed (${response.status}).`,
        retryable: response.status >= 500,
      },
      response.status,
    );
  }

  return body as T;
}

async function requestMultipart<T>(path: string, form: FormData): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      cache: "no-store",
      credentials: "include",
      headers: authHeaders("POST"),
      body: form,
    });
  } catch {
    throw new ApiRequestError({
      code: "network_error",
      message:
        "Can't reach the BATONX API. Make sure the backend is running on port 8000.",
      retryable: true,
    });
  }
  const body = (await response.json().catch(() => null)) as
    | ({ error?: ApiError } & Record<string, unknown>)
    | null;
  if (!response.ok) {
    throw new ApiRequestError(
      body?.error ?? {
        code: "unknown_error",
        message: `Upload failed (${response.status}).`,
        retryable: response.status >= 500,
      },
      response.status,
    );
  }
  return body as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health/"),

  createProject: (
    idea: string,
    opts?: { project_type?: ProjectType; data_goal?: DataGoal },
  ) =>
    request<CreateProjectResponse>("/api/projects/", {
      method: "POST",
      body: JSON.stringify({ idea, ...opts }),
    }),

  getProject: (slug: string) =>
    request<Project>(`/api/projects/${encodeURIComponent(slug)}/`),

  submitDiscoveryAnswers: (
    slug: string,
    answers: Record<string, DiscoveryAnswer>,
  ) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/discovery/answers/`,
      { method: "POST", body: JSON.stringify({ answers }) },
    ),

  generateBlueprint: (slug: string) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/blueprint/generate/`,
      { method: "POST" },
    ),

  updateBlueprint: (slug: string, patch: Partial<BlueprintContent>) =>
    request<Project>(`/api/projects/${encodeURIComponent(slug)}/blueprint/`, {
      method: "PATCH",
      body: JSON.stringify({ content: patch }),
    }),

  approveBlueprint: (slug: string) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/blueprint/approve/`,
      { method: "POST" },
    ),

  generateBusinessLogic: (slug: string) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/business-logic/generate/`,
      { method: "POST" },
    ),

  updateBusinessLogic: (slug: string, patch: Partial<BusinessLogicContent>) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/business-logic/`,
      { method: "PATCH", body: JSON.stringify({ content: patch }) },
    ),

  approveBusinessLogic: (slug: string) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/business-logic/approve/`,
      { method: "POST" },
    ),

  generateArchitecture: (slug: string) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/architecture/generate/`,
      { method: "POST" },
    ),

  updateArchitecture: (slug: string, patch: Partial<ArchitectureContent>) =>
    request<Project>(`/api/projects/${encodeURIComponent(slug)}/architecture/`, {
      method: "PATCH",
      body: JSON.stringify({ content: patch }),
    }),

  approveArchitecture: (slug: string) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/architecture/approve/`,
      { method: "POST" },
    ),

  generateRoadmap: (slug: string) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/roadmap/generate/`,
      { method: "POST" },
    ),

  updateRoadmap: (slug: string, phases: RoadmapPhase[]) =>
    request<Project>(`/api/projects/${encodeURIComponent(slug)}/roadmap/`, {
      method: "PATCH",
      body: JSON.stringify({ content: { phases } }),
    }),

  approveRoadmap: (slug: string) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/roadmap/approve/`,
      { method: "POST" },
    ),

  setTaskStatus: (slug: string, taskId: string, status: TaskStatus) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/roadmap/tasks/${encodeURIComponent(taskId)}/`,
      { method: "PATCH", body: JSON.stringify({ status }) },
    ),

  getTaskWorkspace: (slug: string, taskId: string) =>
    request<TaskWorkspace>(
      `/api/projects/${encodeURIComponent(slug)}/roadmap/tasks/${encodeURIComponent(taskId)}/`,
    ),

  generateBuildPrompt: (slug: string, taskId: string) =>
    request<TaskWorkspace>(
      `/api/projects/${encodeURIComponent(slug)}/roadmap/tasks/${encodeURIComponent(taskId)}/build-prompt/`,
      { method: "POST" },
    ),

  generateReviewPrompt: (slug: string, taskId: string) =>
    request<TaskWorkspace>(
      `/api/projects/${encodeURIComponent(slug)}/roadmap/tasks/${encodeURIComponent(taskId)}/review-prompt/`,
      { method: "POST" },
    ),

  getProgress: (slug: string) =>
    request<ProjectProgress>(
      `/api/projects/${encodeURIComponent(slug)}/progress/`,
    ),

  getShipChecklist: (slug: string) =>
    request<ShipChecklist>(
      `/api/projects/${encodeURIComponent(slug)}/ship-checklist/`,
    ),

  createConversation: (slug: string) =>
    request<Conversation>(
      `/api/projects/${encodeURIComponent(slug)}/conversations/`,
      { method: "POST" },
    ),

  getConversation: (slug: string, conversationId: string) =>
    request<Conversation>(
      `/api/projects/${encodeURIComponent(slug)}/conversations/${encodeURIComponent(conversationId)}/`,
    ),

  sendConversationMessage: (
    slug: string,
    conversationId: string,
    content: string,
  ) =>
    request<ConversationTurnResult>(
      `/api/projects/${encodeURIComponent(slug)}/conversations/${encodeURIComponent(conversationId)}/messages/`,
      { method: "POST", body: JSON.stringify({ content }) },
    ),

  approveProposal: (slug: string, proposalId: string) =>
    request<ProposalDecisionResult>(
      `/api/projects/${encodeURIComponent(slug)}/proposals/${encodeURIComponent(proposalId)}/approve/`,
      { method: "POST" },
    ),

  rejectProposal: (slug: string, proposalId: string) =>
    request<ProposalDecisionResult>(
      `/api/projects/${encodeURIComponent(slug)}/proposals/${encodeURIComponent(proposalId)}/reject/`,
      { method: "POST" },
    ),

  confirmShipItem: (
    slug: string,
    itemId: string,
    confirmed: boolean,
    note?: string,
  ) =>
    request<ShipChecklist>(
      `/api/projects/${encodeURIComponent(slug)}/ship-checklist/`,
      {
        method: "PATCH",
        body: JSON.stringify({ item_id: itemId, confirmed, note }),
      },
    ),

  // --- Data & Analytics (Phase I-1) ---

  generateDataBrief: (slug: string) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/data-brief/generate/`,
      { method: "POST" },
    ),

  updateDataBrief: (slug: string, content: Partial<DataBriefContent>) =>
    request<Project>(`/api/projects/${encodeURIComponent(slug)}/data-brief/`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    }),

  approveDataBrief: (slug: string) =>
    request<Project>(
      `/api/projects/${encodeURIComponent(slug)}/data-brief/approve/`,
      { method: "POST" },
    ),

  listDatasets: (slug: string) =>
    request<{ datasets: Dataset[] }>(
      `/api/projects/${encodeURIComponent(slug)}/datasets/`,
    ),

  uploadDataset: (slug: string, file: File, name?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    return requestMultipart<Dataset>(
      `/api/projects/${encodeURIComponent(slug)}/datasets/`,
      form,
    );
  },

  getDataset: (slug: string, datasetId: string) =>
    request<DatasetDetail>(
      `/api/projects/${encodeURIComponent(slug)}/datasets/${encodeURIComponent(datasetId)}/`,
    ),

  profileDataset: (slug: string, datasetId: string) =>
    request<DatasetDetail>(
      `/api/projects/${encodeURIComponent(slug)}/datasets/${encodeURIComponent(datasetId)}/profile/`,
      { method: "POST" },
    ),

  generateSourceInterpretation: (slug: string, datasetId: string) =>
    request<Dataset>(
      `/api/projects/${encodeURIComponent(slug)}/datasets/${encodeURIComponent(datasetId)}/interpret/`,
      { method: "POST" },
    ),

  updateSourceInterpretation: (
    slug: string,
    datasetId: string,
    content: Partial<SourceInterpretationContent>,
  ) =>
    request<Dataset>(
      `/api/projects/${encodeURIComponent(slug)}/datasets/${encodeURIComponent(datasetId)}/interpretation/`,
      { method: "PATCH", body: JSON.stringify({ content }) },
    ),

  approveSourceInterpretation: (slug: string, datasetId: string) =>
    request<Dataset>(
      `/api/projects/${encodeURIComponent(slug)}/datasets/${encodeURIComponent(datasetId)}/interpret/approve/`,
      { method: "POST" },
    ),

  getJob: (slug: string, jobId: string) =>
    request<Job>(
      `/api/projects/${encodeURIComponent(slug)}/jobs/${encodeURIComponent(jobId)}/`,
    ),

  // --- Data Quality (Phase I-2) ---
  getDataQuality: (slug: string) =>
    request<DataQualityView>(
      `/api/projects/${encodeURIComponent(slug)}/data-quality/`,
    ),
  observeDataQuality: (slug: string) =>
    request<DataQualityView>(
      `/api/projects/${encodeURIComponent(slug)}/data-quality/observe/`,
      { method: "POST" },
    ),
  proposeQualityRules: (slug: string) =>
    request<DataQualityView>(
      `/api/projects/${encodeURIComponent(slug)}/data-quality/propose-rules/`,
      { method: "POST" },
    ),
  updateDataQuality: (slug: string, content: Partial<DataQualityContent>) =>
    request<DataQualityView>(
      `/api/projects/${encodeURIComponent(slug)}/data-quality/`,
      { method: "PATCH", body: JSON.stringify({ content }) },
    ),
  approveDataQuality: (slug: string) =>
    request<DataQualityView>(
      `/api/projects/${encodeURIComponent(slug)}/data-quality/approve/`,
      { method: "POST" },
    ),
  runQualityChecks: (slug: string) =>
    request<DataQualityView>(
      `/api/projects/${encodeURIComponent(slug)}/data-quality/check/`,
      { method: "POST" },
    ),

  // --- Transformation Plan (Phase I-2) ---
  getTransformation: (slug: string) =>
    request<TransformationView>(
      `/api/projects/${encodeURIComponent(slug)}/transformation/`,
    ),
  generateTransformation: (slug: string) =>
    request<TransformationView>(
      `/api/projects/${encodeURIComponent(slug)}/transformation/generate/`,
      { method: "POST" },
    ),
  updateTransformation: (
    slug: string,
    content: Partial<TransformationPlanContent>,
  ) =>
    request<TransformationView>(
      `/api/projects/${encodeURIComponent(slug)}/transformation/`,
      { method: "PATCH", body: JSON.stringify({ content }) },
    ),
  approveTransformation: (slug: string) =>
    request<TransformationView>(
      `/api/projects/${encodeURIComponent(slug)}/transformation/approve/`,
      { method: "POST" },
    ),
  previewTransformation: (slug: string) =>
    request<TransformationPreviewResult>(
      `/api/projects/${encodeURIComponent(slug)}/transformation/preview/`,
      { method: "POST" },
    ),

  // --- Metrics / KPIs (Phase I-3) ---
  listMetrics: (slug: string) =>
    request<MetricDefinition[]>(
      `/api/projects/${encodeURIComponent(slug)}/metrics/`,
    ),
  generateMetrics: (slug: string) =>
    request<MetricDefinition[]>(
      `/api/projects/${encodeURIComponent(slug)}/metrics/generate/`,
      { method: "POST" },
    ),
  updateMetric: (
    slug: string,
    metricId: string,
    patch: Partial<MetricEditableFields>,
  ) =>
    request<MetricDefinition>(
      `/api/projects/${encodeURIComponent(slug)}/metrics/${encodeURIComponent(metricId)}/`,
      { method: "PATCH", body: JSON.stringify(patch) },
    ),
  approveMetric: (slug: string, metricId: string) =>
    request<MetricDefinition>(
      `/api/projects/${encodeURIComponent(slug)}/metrics/${encodeURIComponent(metricId)}/approve/`,
      { method: "POST" },
    ),
  validateMetric: (slug: string, metricId: string) =>
    request<MetricDefinition>(
      `/api/projects/${encodeURIComponent(slug)}/metrics/${encodeURIComponent(metricId)}/validate/`,
      { method: "POST" },
    ),

  // --- Queries (Phase I-3) ---
  listQueries: (slug: string) =>
    request<DataQuery[]>(`/api/projects/${encodeURIComponent(slug)}/queries/`),
  createQuery: (slug: string, question: string) =>
    request<DataQuery>(`/api/projects/${encodeURIComponent(slug)}/queries/`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  getQuery: (slug: string, queryId: string) =>
    request<DataQuery>(
      `/api/projects/${encodeURIComponent(slug)}/queries/${encodeURIComponent(queryId)}/`,
    ),
  updateQueryPlan: (slug: string, queryId: string, plan: Partial<QueryPlan>) =>
    request<DataQuery>(
      `/api/projects/${encodeURIComponent(slug)}/queries/${encodeURIComponent(queryId)}/plan/`,
      { method: "PATCH", body: JSON.stringify({ plan }) },
    ),
  approveQueryPlan: (slug: string, queryId: string) =>
    request<DataQuery>(
      `/api/projects/${encodeURIComponent(slug)}/queries/${encodeURIComponent(queryId)}/approve-plan/`,
      { method: "POST" },
    ),
  generateQuerySql: (slug: string, queryId: string) =>
    request<DataQuery>(
      `/api/projects/${encodeURIComponent(slug)}/queries/${encodeURIComponent(queryId)}/generate-sql/`,
      { method: "POST" },
    ),
  reviewQuerySql: (slug: string, queryId: string) =>
    request<DataQuery>(
      `/api/projects/${encodeURIComponent(slug)}/queries/${encodeURIComponent(queryId)}/review/`,
      { method: "POST" },
    ),
  markQueryReviewed: (slug: string, queryId: string) =>
    request<DataQuery>(
      `/api/projects/${encodeURIComponent(slug)}/queries/${encodeURIComponent(queryId)}/mark-reviewed/`,
      { method: "POST" },
    ),
  executeQuery: (slug: string, queryId: string) =>
    request<DataQuery>(
      `/api/projects/${encodeURIComponent(slug)}/queries/${encodeURIComponent(queryId)}/execute/`,
      { method: "POST" },
    ),

  // --- Data Lineage (Phase I-3) ---
  getLineage: (slug: string, node: string) =>
    request<LineageResult>(
      `/api/projects/${encodeURIComponent(slug)}/lineage/?node=${encodeURIComponent(node)}`,
    ),

  // --- Data Progress / Delivery Readiness (Phase I-5) ---
  getDataProgress: (slug: string) =>
    request<DataProgress>(`/api/projects/${encodeURIComponent(slug)}/data-progress/`),
  getDataReadiness: (slug: string) =>
    request<DataReadiness>(`/api/projects/${encodeURIComponent(slug)}/data-readiness/`),
  confirmDataReadinessItem: (slug: string, itemId: string, confirmed: boolean, note?: string) =>
    request<DataReadiness>(
      `/api/projects/${encodeURIComponent(slug)}/data-readiness/`,
      { method: "PATCH", body: JSON.stringify({ item_id: itemId, confirmed, note }) },
    ),

  // --- Analysis Plans (Phase I-4) ---
  listAnalysisPlans: (slug: string) =>
    request<AnalysisPlan[]>(`/api/projects/${encodeURIComponent(slug)}/analysis/plans/`),
  createAnalysisPlan: (slug: string, payload: Partial<AnalysisPlan>) =>
    request<AnalysisPlan>(`/api/projects/${encodeURIComponent(slug)}/analysis/plans/`, {
      method: "POST", body: JSON.stringify(payload),
    }),
  generateAnalysisPlan: (slug: string, businessQuestion?: string) =>
    request<AnalysisPlan>(
      `/api/projects/${encodeURIComponent(slug)}/analysis/plans/generate/`,
      { method: "POST", body: JSON.stringify({ business_question: businessQuestion || "" }) },
    ),
  getAnalysisPlan: (slug: string, planId: string) =>
    request<AnalysisPlan>(
      `/api/projects/${encodeURIComponent(slug)}/analysis/plans/${encodeURIComponent(planId)}/`,
    ),
  updateAnalysisPlan: (slug: string, planId: string, patch: Partial<AnalysisPlan>) =>
    request<AnalysisPlan>(
      `/api/projects/${encodeURIComponent(slug)}/analysis/plans/${encodeURIComponent(planId)}/`,
      { method: "PATCH", body: JSON.stringify(patch) },
    ),
  approveAnalysisPlan: (slug: string, planId: string) =>
    request<AnalysisPlan>(
      `/api/projects/${encodeURIComponent(slug)}/analysis/plans/${encodeURIComponent(planId)}/approve/`,
      { method: "POST" },
    ),
  runAnalysisPlan: (slug: string, planId: string) =>
    request<AnalysisResult>(
      `/api/projects/${encodeURIComponent(slug)}/analysis/plans/${encodeURIComponent(planId)}/run/`,
      { method: "POST" },
    ),

  // --- Analysis Results / Insights (Phase I-4) ---
  getAnalysisResult: (slug: string, resultId: string) =>
    request<AnalysisResult>(
      `/api/projects/${encodeURIComponent(slug)}/analysis/results/${encodeURIComponent(resultId)}/`,
    ),
  generateInsights: (slug: string, resultId: string) =>
    request<Insight[]>(
      `/api/projects/${encodeURIComponent(slug)}/analysis/results/${encodeURIComponent(resultId)}/insights/generate/`,
      { method: "POST" },
    ),
  acceptInsight: (slug: string, insightId: string) =>
    request<Insight>(
      `/api/projects/${encodeURIComponent(slug)}/analysis/insights/${encodeURIComponent(insightId)}/accept/`,
      { method: "POST" },
    ),

  // --- Dashboard Blueprint (Phase I-4) ---
  getDashboard: (slug: string) =>
    request<DashboardView>(`/api/projects/${encodeURIComponent(slug)}/dashboard/`),
  generateDashboard: (slug: string) =>
    request<DashboardView>(`/api/projects/${encodeURIComponent(slug)}/dashboard/generate/`, {
      method: "POST",
    }),
  updateDashboard: (slug: string, content: Partial<DashboardBlueprintContent>) =>
    request<DashboardView>(`/api/projects/${encodeURIComponent(slug)}/dashboard/`, {
      method: "PATCH", body: JSON.stringify({ content }),
    }),
  approveDashboard: (slug: string) =>
    request<DashboardView>(`/api/projects/${encodeURIComponent(slug)}/dashboard/approve/`, {
      method: "POST",
    }),
  generateDashboardBuildPrompt: (slug: string) =>
    request<DashboardView>(
      `/api/projects/${encodeURIComponent(slug)}/dashboard/build-prompt/`,
      { method: "POST" },
    ),

  // --- Projects list (Phase P-2: scoped server-side to the caller) ---
  listProjects: () => request<{ projects: Project[] }>("/api/projects/"),

  // --- Auth (Phase P-2) ---
  signup: (input: { email: string; password: string; confirm_password: string; display_name?: string }) =>
    request<AuthUser>("/api/auth/signup/", { method: "POST", body: JSON.stringify(input) }),
  login: (input: { email: string; password: string }) =>
    request<AuthUser>("/api/auth/login/", { method: "POST", body: JSON.stringify(input) }),
  logout: () => request<void>("/api/auth/logout/", { method: "POST" }),
  me: () => request<AuthUser>("/api/auth/me/"),
};
