"""
REST surface (Phases 0-2).

- GET  /api/health/                             -> liveness + DB connectivity
- POST /api/projects/                           -> create; idea_analysis +
                                                  discovery_generation
- GET  /api/projects/<slug>/                    -> fetch a project
- POST /api/projects/<slug>/discovery/answers/  -> validate + persist answers
- POST /api/projects/<slug>/blueprint/generate/ -> generate / regenerate (draft)
- PATCH /api/projects/<slug>/blueprint/         -> section-level edit (-> draft)
- POST /api/projects/<slug>/blueprint/approve/  -> approve + rebuild context digest

This layer only translates HTTP <-> domain services. Domain/AI errors become the
uniform envelope via ``common.exception_handler``.
"""
from django.db import connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.conversation_services import (
    approve_proposal,
    create_conversation,
    get_conversation,
    post_message,
    reject_proposal,
    serialize_conversation,
)
from projects.data.services import (
    approve_data_brief,
    approve_source_interpretation,
    generate_data_brief,
    generate_source_interpretation,
    get_job,
    list_datasets,
    run_dataset_profiling,
    serialize_dataset,
    serialize_dataset_detail,
    serialize_job,
    update_data_brief,
    update_source_interpretation,
    upload_dataset,
)
from projects.data.services import get_dataset as get_dataset_service
from projects.data.quality_services import (
    approve_data_quality,
    observe_data_quality,
    propose_quality_rules,
    run_quality_checks,
    serialize_data_quality,
    update_data_quality,
)
from projects.data.transformation_services import (
    approve_transformation_plan,
    generate_transformation_plan,
    preview_transformation,
    serialize_transformation_plan,
    update_transformation_plan,
)
from projects.data.lineage import resolve_lineage
from projects.data.metrics_services import (
    approve_metric,
    generate_metrics,
    list_metrics,
    update_metric,
    validate_metric,
)
from projects.data.query_services import (
    approve_query_plan,
    create_query,
    execute_query,
    generate_query_sql,
    list_queries,
    mark_query_reviewed,
    review_query_sql,
    serialize_query,
    update_query_plan,
)
from projects.data.query_services import _get_query as get_query_service
from projects.data.analysis_services import (
    approve_analysis_plan,
    create_analysis_plan,
    generate_analysis_plan,
    get_analysis_plan,
    list_analysis_plans,
    run_analysis_plan,
    serialize_analysis_result,
    update_analysis_plan,
)
from projects.data.analysis_services import _get_result as get_analysis_result_service
from projects.data.insights_services import accept_insight, generate_insights
from projects.data.dashboard_services import (
    approve_dashboard_blueprint,
    generate_dashboard_blueprint,
    generate_dashboard_build_prompt,
    serialize_dashboard,
    update_dashboard_blueprint,
)
from projects.data.progress import compute_data_progress
from projects.data.readiness import compute_data_readiness, confirm_data_readiness_item
from projects.exceptions import ProjectWorkflowError
from projects.models import Project
from projects.serializers import ProjectSerializer
from projects.services import (
    approve_architecture,
    approve_blueprint,
    approve_business_logic,
    approve_roadmap,
    create_project,
    generate_architecture,
    generate_blueprint,
    generate_build_prompt,
    generate_business_logic,
    confirm_ship_item,
    generate_review_prompt,
    generate_roadmap,
    get_project,
    get_ship_checklist,
    project_progress,
    set_task_status,
    submit_discovery_answers,
    task_workspace,
    update_architecture,
    update_blueprint,
    update_business_logic,
    update_roadmap,
)


def _error(code: str, message: str, http_status: int, *, retryable: bool = False):
    return Response(
        {"error": {"code": code, "message": message, "retryable": retryable}},
        status=http_status,
    )


def _project_not_found():
    return ProjectWorkflowError(
        "project_not_found", "Project not found.", status=status.HTTP_404_NOT_FOUND
    )


def _project_or_404(request, slug: str) -> Project:
    """
    THE single authorization choke point for every project-scoped endpoint
    (Phase P-2): every view below resolves its ``Project`` through this
    function, so gating ownership here — and nowhere else — secures the
    entire Software and Data surface, including every nested resource
    (Dataset, Query, MetricDefinition, Conversation, Proposal, ...), since
    each of those is always looked up scoped to the specific ``Project``
    instance this function returns (``Model.objects.get(id=..., project=project)``
    throughout). A project that exists but belongs to someone else 404s
    exactly like one that doesn't exist — deliberately non-disclosing;
    the response never reveals that the slug belongs to another user.
    """
    try:
        project = get_project(slug)
    except Project.DoesNotExist:
        raise _project_not_found()
    if project.owner_id != request.user.id:
        raise _project_not_found()
    return project


class HealthView(APIView):
    # Public — infra health checks (uptime monitors, load balancers) never
    # carry a session; liveness/DB-connectivity is not sensitive information.
    permission_classes = [AllowAny]

    def get(self, request):
        database = "ok"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            database = "unavailable"
        return Response(
            {
                "status": "ok" if database == "ok" else "degraded",
                "database": database,
                "service": "vyra-api",
            }
        )


class ProjectListCreateView(APIView):
    def get(self, request):
        # Phase P-2: scoped to the caller — never another user's Projects.
        projects = Project.objects.filter(owner=request.user)
        return Response({"projects": [ProjectSerializer(p).data for p in projects]})

    def post(self, request):
        idea = (request.data.get("idea") or "").strip()
        if not idea:
            return _error(
                "empty_idea",
                "Describe what you want to build to continue.",
                status.HTTP_400_BAD_REQUEST,
            )
        project = create_project(
            idea,
            owner=request.user,
            project_type=(request.data.get("project_type") or "software"),
            data_goal=request.data.get("data_goal"),
        )
        return Response(
            {"project": ProjectSerializer(project).data},
            status=status.HTTP_201_CREATED,
        )


class ProjectDetailView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(ProjectSerializer(project).data)


class DiscoveryAnswersView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = submit_discovery_answers(project, request.data.get("answers"))
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class BlueprintGenerateView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = generate_blueprint(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class BlueprintUpdateView(APIView):
    def patch(self, request, slug):
        project = _project_or_404(request, slug)
        project = update_blueprint(project, request.data.get("content"))
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class BlueprintApproveView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = approve_blueprint(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class BusinessLogicGenerateView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = generate_business_logic(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class BusinessLogicUpdateView(APIView):
    def patch(self, request, slug):
        project = _project_or_404(request, slug)
        project = update_business_logic(project, request.data.get("content"))
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class BusinessLogicApproveView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = approve_business_logic(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class ArchitectureGenerateView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = generate_architecture(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class ArchitectureUpdateView(APIView):
    def patch(self, request, slug):
        project = _project_or_404(request, slug)
        project = update_architecture(project, request.data.get("content"))
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class ArchitectureApproveView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = approve_architecture(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class RoadmapGenerateView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = generate_roadmap(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class RoadmapUpdateView(APIView):
    def patch(self, request, slug):
        project = _project_or_404(request, slug)
        project = update_roadmap(project, request.data.get("content"))
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class RoadmapApproveView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = approve_roadmap(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class RoadmapTaskView(APIView):
    def get(self, request, slug, task_id):
        project = _project_or_404(request, slug)
        return Response(task_workspace(project, task_id))

    def patch(self, request, slug, task_id):
        project = _project_or_404(request, slug)
        project = set_task_status(project, task_id, request.data.get("status"))
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class BuildPromptGenerateView(APIView):
    def post(self, request, slug, task_id):
        project = _project_or_404(request, slug)
        return Response(
            generate_build_prompt(project, task_id), status=status.HTTP_200_OK
        )


class ReviewPromptGenerateView(APIView):
    def post(self, request, slug, task_id):
        project = _project_or_404(request, slug)
        return Response(
            generate_review_prompt(project, task_id), status=status.HTTP_200_OK
        )


class ProgressView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(project_progress(project))


class ShipChecklistView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(get_ship_checklist(project))

    def patch(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(
            confirm_ship_item(
                project,
                request.data.get("item_id"),
                request.data.get("confirmed"),
                request.data.get("note"),
            )
        )


class ConversationCreateView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        conversation = create_conversation(project)
        return Response(
            serialize_conversation(conversation), status=status.HTTP_201_CREATED
        )


class ConversationDetailView(APIView):
    def get(self, request, slug, conversation_id):
        project = _project_or_404(request, slug)
        conversation = get_conversation(project, conversation_id)
        return Response(serialize_conversation(conversation))


class ConversationMessageView(APIView):
    def post(self, request, slug, conversation_id):
        project = _project_or_404(request, slug)
        conversation = get_conversation(project, conversation_id)
        return Response(
            post_message(project, conversation, request.data.get("content")),
            status=status.HTTP_200_OK,
        )


class ProposalApproveView(APIView):
    def post(self, request, slug, proposal_id):
        project = _project_or_404(request, slug)
        result = approve_proposal(project, proposal_id)
        return Response(
            {
                "project": ProjectSerializer(result["project"]).data,
                "proposal": result["proposal"],
            },
            status=status.HTTP_200_OK,
        )


class ProposalRejectView(APIView):
    def post(self, request, slug, proposal_id):
        project = _project_or_404(request, slug)
        return Response(
            reject_proposal(project, proposal_id), status=status.HTTP_200_OK
        )


# --- Data & Analytics (Phase I-1) ---------------------------------------------


class DataBriefGenerateView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = generate_data_brief(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class DataBriefUpdateView(APIView):
    def patch(self, request, slug):
        project = _project_or_404(request, slug)
        project = update_data_brief(project, request.data.get("content"))
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class DataBriefApproveView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        project = approve_data_brief(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_200_OK)


class DatasetListCreateView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(
            {"datasets": [serialize_dataset(d) for d in list_datasets(project)]}
        )

    def post(self, request, slug):
        project = _project_or_404(request, slug)
        dataset = upload_dataset(
            project,
            request.FILES.get("file"),
            (request.data.get("name") or "").strip() or None,
        )
        return Response(
            serialize_dataset(dataset), status=status.HTTP_201_CREATED
        )


class DatasetDetailView(APIView):
    def get(self, request, slug, dataset_id):
        project = _project_or_404(request, slug)
        dataset = get_dataset_service(project, dataset_id)
        return Response(serialize_dataset_detail(dataset))


class DatasetProfileView(APIView):
    def post(self, request, slug, dataset_id):
        project = _project_or_404(request, slug)
        return Response(
            run_dataset_profiling(project, dataset_id), status=status.HTTP_200_OK
        )


class SourceInterpretationGenerateView(APIView):
    def post(self, request, slug, dataset_id):
        project = _project_or_404(request, slug)
        return Response(
            generate_source_interpretation(project, dataset_id),
            status=status.HTTP_200_OK,
        )


class SourceInterpretationUpdateView(APIView):
    def patch(self, request, slug, dataset_id):
        project = _project_or_404(request, slug)
        return Response(
            update_source_interpretation(
                project, dataset_id, request.data.get("content")
            ),
            status=status.HTTP_200_OK,
        )


class SourceInterpretationApproveView(APIView):
    def post(self, request, slug, dataset_id):
        project = _project_or_404(request, slug)
        return Response(
            approve_source_interpretation(project, dataset_id),
            status=status.HTTP_200_OK,
        )


class JobDetailView(APIView):
    def get(self, request, slug, job_id):
        project = _project_or_404(request, slug)
        return Response(serialize_job(get_job(project, job_id)))


# --- Data Quality (Phase I-2) ---


class DataQualityView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(serialize_data_quality(project))

    def patch(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(update_data_quality(project, request.data.get("content")))


class DataQualityObserveView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(observe_data_quality(project))


class DataQualityProposeRulesView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(propose_quality_rules(project))


class DataQualityApproveView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(approve_data_quality(project))


class DataQualityCheckView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(run_quality_checks(project))


# --- Transformation Plan (Phase I-2) ---


class TransformationView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(serialize_transformation_plan(project))

    def patch(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(
            update_transformation_plan(project, request.data.get("content"))
        )


class TransformationGenerateView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(generate_transformation_plan(project))


class TransformationApproveView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(approve_transformation_plan(project))


class TransformationPreviewView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(preview_transformation(project))


# --- Metrics / KPIs (Phase I-3) ---


class MetricListView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(list_metrics(project))


class MetricGenerateView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(generate_metrics(project))


class MetricDetailView(APIView):
    def patch(self, request, slug, metric_id):
        project = _project_or_404(request, slug)
        return Response(update_metric(project, metric_id, request.data))


class MetricApproveView(APIView):
    def post(self, request, slug, metric_id):
        project = _project_or_404(request, slug)
        return Response(approve_metric(project, metric_id))


class MetricValidateView(APIView):
    def post(self, request, slug, metric_id):
        project = _project_or_404(request, slug)
        return Response(validate_metric(project, metric_id))


# --- Queries (Phase I-3) ---


class QueryListCreateView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(list_queries(project))

    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(create_query(project, request.data.get("question")))


class QueryDetailView(APIView):
    def get(self, request, slug, query_id):
        project = _project_or_404(request, slug)
        return Response(serialize_query(get_query_service(project, query_id)))


class QueryPlanUpdateView(APIView):
    def patch(self, request, slug, query_id):
        project = _project_or_404(request, slug)
        return Response(update_query_plan(project, query_id, request.data.get("plan")))


class QueryPlanApproveView(APIView):
    def post(self, request, slug, query_id):
        project = _project_or_404(request, slug)
        return Response(approve_query_plan(project, query_id))


class QueryGenerateSqlView(APIView):
    def post(self, request, slug, query_id):
        project = _project_or_404(request, slug)
        return Response(generate_query_sql(project, query_id))


class QueryReviewView(APIView):
    def post(self, request, slug, query_id):
        project = _project_or_404(request, slug)
        return Response(review_query_sql(project, query_id))


class QueryMarkReviewedView(APIView):
    def post(self, request, slug, query_id):
        project = _project_or_404(request, slug)
        return Response(mark_query_reviewed(project, query_id))


class QueryExecuteView(APIView):
    def post(self, request, slug, query_id):
        project = _project_or_404(request, slug)
        return Response(execute_query(project, query_id))


# --- Data Lineage (Phase I-3) ---


class DataLineageView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        node = request.query_params.get("node", "")
        return Response(resolve_lineage(project, node))


# --- Analysis Plans (Phase I-4) ---


class AnalysisPlanListCreateView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(list_analysis_plans(project))

    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(create_analysis_plan(project, request.data))


class AnalysisPlanGenerateView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(
            generate_analysis_plan(project, request.data.get("business_question"))
        )


class AnalysisPlanDetailView(APIView):
    def get(self, request, slug, plan_id):
        project = _project_or_404(request, slug)
        return Response(get_analysis_plan(project, plan_id))

    def patch(self, request, slug, plan_id):
        project = _project_or_404(request, slug)
        return Response(update_analysis_plan(project, plan_id, request.data))


class AnalysisPlanApproveView(APIView):
    def post(self, request, slug, plan_id):
        project = _project_or_404(request, slug)
        return Response(approve_analysis_plan(project, plan_id))


class AnalysisPlanRunView(APIView):
    def post(self, request, slug, plan_id):
        project = _project_or_404(request, slug)
        return Response(run_analysis_plan(project, plan_id))


# --- Analysis Results / Insights (Phase I-4) ---


class AnalysisResultDetailView(APIView):
    def get(self, request, slug, result_id):
        project = _project_or_404(request, slug)
        return Response(serialize_analysis_result(get_analysis_result_service(project, result_id)))


class InsightGenerateView(APIView):
    def post(self, request, slug, result_id):
        project = _project_or_404(request, slug)
        return Response(generate_insights(project, result_id))


class InsightAcceptView(APIView):
    def post(self, request, slug, insight_id):
        project = _project_or_404(request, slug)
        return Response(accept_insight(project, insight_id))


# --- Dashboard Blueprint (Phase I-4) ---


class DashboardView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(serialize_dashboard(project))

    def patch(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(update_dashboard_blueprint(project, request.data.get("content")))


class DashboardGenerateView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(generate_dashboard_blueprint(project))


class DashboardApproveView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(approve_dashboard_blueprint(project))


class DashboardBuildPromptView(APIView):
    def post(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(generate_dashboard_build_prompt(project))


# --- Data Progress / Delivery Readiness (Phase I-5) ---


class DataProgressView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(compute_data_progress(project))


class DataReadinessView(APIView):
    def get(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(compute_data_readiness(project))

    def patch(self, request, slug):
        project = _project_or_404(request, slug)
        return Response(
            confirm_data_readiness_item(
                project,
                request.data.get("item_id"),
                request.data.get("confirmed"),
                request.data.get("note"),
            )
        )
