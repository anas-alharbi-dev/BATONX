"""
Domain services for projects.

The REST layer calls these; these call the AI service layer. The REST layer never
talks to Anthropic directly.
"""
from __future__ import annotations

from datetime import datetime, timezone

from django.db import transaction
from django.utils import timezone as dj_timezone
from pydantic import ValidationError

from ai.base import run_operation
from ai.client import get_model
from ai.exceptions import AIOperationError
from ai.operations.architecture_generation import ARCHITECTURE_GENERATION
from ai.operations.blueprint_generation import BLUEPRINT_GENERATION
from ai.operations.build_prompt_generation import BUILD_PROMPT_GENERATION
from ai.operations.business_logic_generation import BUSINESS_LOGIC_GENERATION
from ai.operations.discovery_generation import DISCOVERY_GENERATION
from ai.operations.idea_analysis import IDEA_ANALYSIS
from ai.operations.review_prompt_generation import REVIEW_PROMPT_GENERATION
from ai.operations.roadmap_generation import ROADMAP_GENERATION
from projects.architecture import (
    ArchitectureContent,
    normalize_architecture_content,
)
from projects.blueprint import BlueprintContent, normalize_blueprint_content
from projects.business_logic import (
    BusinessLogicContent,
    normalize_business_logic_content,
)
from projects.context import build_context_digest
from projects.context_selection import assemble_task_context
from projects.dependencies import clear_stale, is_stale, mark_downstream_stale
from projects.exceptions import ProjectWorkflowError
from projects.models import (
    DataGoal,
    GeneratedPrompt,
    Project,
    ProjectStage,
    ProjectType,
)
from projects.progress import compute_project_progress
from projects.ship_checklist import (
    READY_TO_SHIP,
    apply_manual_confirmation,
    compute_ship_checklist,
)
from projects.roadmap import (
    ACTIVE_STATUSES,
    ALLOWED_TRANSITIONS,
    RoadmapContent,
    VALID_STATUSES,
    can_transition,
    find_task,
    normalize_roadmap_content,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pydantic_details(error: ValidationError) -> list[dict]:
    return [
        {"loc": ".".join(str(p) for p in item["loc"]), "msg": item["msg"]}
        for item in error.errors()
    ]


# --- Creation -----------------------------------------------------------------


_VALID_DATA_GOALS = {choice.value for choice in DataGoal}


def create_project(
    idea: str, owner, project_type: str = "software", data_goal: str | None = None
) -> Project:
    """
    Create a project from a raw idea, owned by ``owner`` (Phase P-2:
    ``request.user`` — server-controlled, never accepted from request input).

    ``project_type`` selects the domain workflow:

    - ``software`` (default): runs ``idea_analysis`` then ``discovery_generation``
      and creates a project at stage ``discovery`` (behaviour unchanged).
    - ``data``: runs ``idea_analysis`` only and creates a project at stage
      ``data_brief`` with ``data_goal`` set. The Software discovery/blueprint
      pipeline is NOT reused.

    Only a fully valid AI result produces a persisted ``Project`` (one insert
    inside ``transaction.atomic()``). AI failure -> no ``Project`` row; the
    ``AIRequestLog`` rows are still written (calls run before the atomic block).
    """
    idea = (idea or "").strip()
    project_type = (project_type or "software").strip() or "software"
    if project_type not in (ProjectType.SOFTWARE, ProjectType.DATA):
        raise ProjectWorkflowError(
            "invalid_project_type",
            "project_type must be 'software' or 'data'.",
        )

    data_goal = (data_goal or "").strip()
    if project_type == ProjectType.SOFTWARE:
        if data_goal:
            raise ProjectWorkflowError(
                "invalid_project_type",
                "data_goal only applies to data projects.",
            )
    else:  # data project
        data_goal = data_goal or DataGoal.ANALYTICS.value
        if data_goal not in _VALID_DATA_GOALS:
            raise ProjectWorkflowError(
                "invalid_data_goal",
                "data_goal must be one of: " + ", ".join(sorted(_VALID_DATA_GOALS)) + ".",
                details={"allowed": sorted(_VALID_DATA_GOALS)},
            )

    analysis = run_operation(IDEA_ANALYSIS, {"idea": idea}, project=None)
    analysis_dict = analysis.model_dump()

    if project_type == ProjectType.DATA:
        with transaction.atomic():
            project = Project.objects.create(
                original_idea=idea,
                owner=owner,
                project_type=ProjectType.DATA,
                data_goal=data_goal,
                stage=ProjectStage.DATA_BRIEF,
                context_digest={"idea_analysis": analysis_dict},
            )
        return project

    generated = run_operation(
        DISCOVERY_GENERATION, {"idea": idea, "analysis": analysis_dict}, project=None
    )
    questions = [
        {
            "id": f"q{index + 1}",
            "question": spec.question,
            "type": spec.type.value,
            "options": list(spec.options),
            "why_it_matters": spec.why_it_matters,
        }
        for index, spec in enumerate(generated.questions)
    ]

    with transaction.atomic():
        project = Project.objects.create(
            original_idea=idea,
            owner=owner,
            stage=ProjectStage.DISCOVERY,
            context_digest={"idea_analysis": analysis_dict},
            discovery={
                "questions": questions,
                "answers": {},
                "generated_at": _now_iso(),
                "answered_at": None,
            },
        )

    return project


# --- Reads ------------------------------------------------------------------


def get_project(slug: str) -> Project:
    return Project.objects.get(slug=slug)


# --- Discovery answers -----------------------------------------------------


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    return False


def _validate_answer(question: dict, answer) -> None:
    qid = question["id"]
    qtype = question["type"]
    options = question.get("options") or []

    if qtype == "text":
        if not isinstance(answer, str) or _is_blank(answer):
            raise ProjectWorkflowError(
                "invalid_answer",
                "A text answer is required.",
                details={"question_id": qid, "reason": "expected non-empty text"},
            )
        return

    if qtype == "single_select":
        if not isinstance(answer, str) or answer not in options:
            raise ProjectWorkflowError(
                "invalid_answer",
                "Pick one of the provided options.",
                details={"question_id": qid, "reason": "value not in options"},
            )
        return

    if qtype == "multi_select":
        if not isinstance(answer, list) or _is_blank(answer):
            raise ProjectWorkflowError(
                "invalid_answer",
                "Pick at least one option.",
                details={"question_id": qid, "reason": "expected a non-empty list"},
            )
        unknown = [value for value in answer if value not in options]
        if unknown:
            raise ProjectWorkflowError(
                "invalid_answer",
                "One or more selected options are not valid.",
                details={"question_id": qid, "reason": "values not in options", "values": unknown},
            )
        return

    raise ProjectWorkflowError(
        "invalid_answer",
        "Unknown question type.",
        details={"question_id": qid, "reason": f"unsupported type {qtype!r}"},
    )


def submit_discovery_answers(project: Project, answers) -> Project:
    """
    Validate and persist discovery answers. Idempotent: re-submitting overwrites
    the previous answer set (the user can edit). Stage stays ``discovery`` -
    the next phase advances it when the blueprint is generated.
    """
    if project.stage != ProjectStage.DISCOVERY:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"This project is past discovery (stage: {project.stage}).",
            status=409,
        )

    if not isinstance(answers, dict):
        raise ProjectWorkflowError(
            "invalid_answers", "Answers must be an object keyed by question id."
        )

    questions = (project.discovery or {}).get("questions") or []
    if not questions:
        raise ProjectWorkflowError(
            "no_questions", "This project has no discovery questions.", status=409
        )

    missing: list[str] = []
    for question in questions:
        answer = answers.get(question["id"])
        if _is_blank(answer):
            missing.append(question["id"])
            continue
        _validate_answer(question, answer)

    if missing:
        raise ProjectWorkflowError(
            "incomplete_answers",
            "Answer every question to continue.",
            details={"missing": missing},
        )

    known_ids = {question["id"] for question in questions}
    project.discovery["answers"] = {
        qid: answers[qid] for qid in answers if qid in known_ids
    }
    project.discovery["answered_at"] = _now_iso()
    project.save(update_fields=["discovery", "updated_at"])
    return project


# --- Blueprint ------------------------------------------------------------

_BLUEPRINT_EDITABLE_STAGES = (ProjectStage.DISCOVERY, ProjectStage.BLUEPRINT)


def generate_blueprint(project: Project) -> Project:
    """
    Generate (or regenerate) the Product Blueprint from the approved discovery
    answers. Always produces a DRAFT (unapproved). Advances stage
    ``discovery -> blueprint`` on first generation.

    The AI call runs before the atomic block so its ``AIRequestLog`` survives a
    rollback (same pattern as ``create_project``). AI failure -> the existing
    blueprint (if any) is left untouched.
    """
    if project.stage not in _BLUEPRINT_EDITABLE_STAGES:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"The Blueprint is locked at stage '{project.stage}'.",
            status=409,
        )
    if not (project.discovery or {}).get("answered_at"):
        raise ProjectWorkflowError(
            "discovery_incomplete",
            "Answer the discovery questions before generating a Blueprint.",
            status=409,
        )

    context = {
        "idea": project.original_idea,
        "analysis": (project.context_digest or {}).get("idea_analysis") or {},
        "discovery": project.discovery or {},
    }
    draft = run_operation(BLUEPRINT_GENERATION, context, project=project)

    content = normalize_blueprint_content(draft.model_dump(mode="json"))
    try:
        validated = BlueprintContent.model_validate(content)
    except ValidationError as error:
        raise AIOperationError(
            code="ai_invalid_output",
            message="The generated Blueprint did not match the expected structure.",
            retryable=True,
            details=_pydantic_details(error),
        )

    now = _now_iso()
    with transaction.atomic():
        project.blueprint = {
            "content": validated.model_dump(mode="json"),
            "generated_at": now,
            "updated_at": now,
            "approved_at": None,
        }
        project.blueprint_approved_at = None
        project.stage = ProjectStage.BLUEPRINT
        fields = ["blueprint", "blueprint_approved_at", "stage", "updated_at"]
        # No-op today (stage locks keep architecture/roadmap from being approved
        # while a Blueprint can still be regenerated); readiness for mid-chain
        # edits in later phases.
        if mark_downstream_stale(project, "blueprint"):
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


def update_blueprint(project: Project, content_patch) -> Project:
    """
    Section-level edit. ``content_patch`` is a partial ``content`` dict (one or
    more whole sections). The merged result is re-validated. Editing always
    reverts an approved Blueprint to draft.
    """
    if project.stage != ProjectStage.BLUEPRINT:
        message = (
            "Generate a Blueprint before editing it."
            if project.stage == ProjectStage.DISCOVERY
            else f"The Blueprint is locked at stage '{project.stage}'."
        )
        raise ProjectWorkflowError("invalid_workflow_state", message, status=409)

    current = (project.blueprint or {}).get("content")
    if not current:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate a Blueprint before editing it.",
            status=409,
        )

    if not isinstance(content_patch, dict) or not content_patch:
        raise ProjectWorkflowError(
            "invalid_blueprint", "Provide one or more Blueprint sections to update."
        )

    unknown = sorted(set(content_patch) - set(BlueprintContent.model_fields))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_blueprint",
            f"Unknown Blueprint section(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    merged = normalize_blueprint_content({**current, **content_patch})
    try:
        validated = BlueprintContent.model_validate(merged)
    except ValidationError as error:
        raise ProjectWorkflowError(
            "invalid_blueprint",
            "The edited Blueprint is not valid. Check the highlighted sections.",
            details={"errors": _pydantic_details(error)},
        )

    was_approved = project.blueprint_approved_at is not None
    with transaction.atomic():
        project.blueprint["content"] = validated.model_dump(mode="json")
        project.blueprint["updated_at"] = _now_iso()
        project.blueprint["approved_at"] = None
        project.blueprint_approved_at = None
        fields = ["blueprint", "blueprint_approved_at", "updated_at"]
        if was_approved:
            # The approved artifact changed -> drop it from Project Context.
            project.context_digest = build_context_digest(project)
            fields.append("context_digest")
        # No-op today under stage locks; marks approved downstream artifacts
        # stale when a later phase permits editing an already-superseded
        # Blueprint (or a Conversation proposal is applied to it).
        if mark_downstream_stale(project, "blueprint"):
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


def approve_blueprint(project: Project) -> Project:
    """
    Mark the Blueprint authoritative and rebuild the Project Context digest.
    Stage stays ``blueprint``; the architecture phase advances it.
    """
    if project.stage != ProjectStage.BLUEPRINT:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"There is no Blueprint to approve at stage '{project.stage}'.",
            status=409,
        )
    if not (project.blueprint or {}).get("content"):
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate a Blueprint before approving it.",
            status=409,
        )

    approved_at = dj_timezone.now()
    with transaction.atomic():
        project.blueprint_approved_at = approved_at
        project.blueprint["approved_at"] = approved_at.isoformat()
        project.context_digest = build_context_digest(project)
        project.save(
            update_fields=[
                "blueprint",
                "blueprint_approved_at",
                "context_digest",
                "updated_at",
            ]
        )
    return project


# --- Business Logic ---------------------------------------------------

_BUSINESS_LOGIC_EDITABLE_STAGES = (
    ProjectStage.BLUEPRINT,
    ProjectStage.BUSINESS_LOGIC,
)


def generate_business_logic(project: Project) -> Project:
    """
    Generate (or regenerate) the Business Logic from the APPROVED Blueprint +
    discovery. Always a DRAFT. Advances ``blueprint -> business_logic`` on first
    generation. AI-first / transactional, same guarantees as the other
    generators.
    """
    if project.stage not in _BUSINESS_LOGIC_EDITABLE_STAGES:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"Business Logic is locked at stage '{project.stage}'.",
            status=409,
        )
    if not project.blueprint_approved_at:
        raise ProjectWorkflowError(
            "blueprint_not_approved",
            "Approve the Blueprint before generating Business Logic.",
            status=409,
        )

    context = {
        "idea": project.original_idea,
        "digest": project.context_digest or {},
        "blueprint": (project.blueprint or {}).get("content") or {},
        "discovery": project.discovery or {},
    }
    draft = run_operation(BUSINESS_LOGIC_GENERATION, context, project=project)

    content = normalize_business_logic_content(draft.model_dump(mode="json"))
    try:
        validated = BusinessLogicContent.model_validate(content)
    except ValidationError as error:
        raise AIOperationError(
            code="ai_invalid_output",
            message="The generated Business Logic did not match the expected structure.",
            retryable=True,
            details=_pydantic_details(error),
        )

    now = _now_iso()
    with transaction.atomic():
        project.business_logic = {
            "content": validated.model_dump(mode="json"),
            "generated_at": now,
            "updated_at": now,
            "approved_at": None,
        }
        project.business_logic_approved_at = None
        project.stage = ProjectStage.BUSINESS_LOGIC
        fields = [
            "business_logic",
            "business_logic_approved_at",
            "stage",
            "updated_at",
        ]
        stale_changed = clear_stale(project, "business_logic")
        stale_changed = (
            mark_downstream_stale(project, "business_logic") or stale_changed
        )
        if stale_changed:
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


def update_business_logic(project: Project, content_patch) -> Project:
    """Section-level edit. Reverts an approved Business Logic to draft."""
    if project.stage != ProjectStage.BUSINESS_LOGIC:
        message = (
            "Generate Business Logic before editing it."
            if project.stage in (ProjectStage.DISCOVERY, ProjectStage.BLUEPRINT)
            else f"Business Logic is locked at stage '{project.stage}'."
        )
        raise ProjectWorkflowError("invalid_workflow_state", message, status=409)

    current = (project.business_logic or {}).get("content")
    if not current:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate Business Logic before editing it.",
            status=409,
        )

    if not isinstance(content_patch, dict) or not content_patch:
        raise ProjectWorkflowError(
            "invalid_business_logic",
            "Provide one or more Business Logic sections to update.",
        )

    unknown = sorted(set(content_patch) - set(BusinessLogicContent.model_fields))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_business_logic",
            f"Unknown Business Logic section(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    merged = normalize_business_logic_content({**current, **content_patch})
    try:
        validated = BusinessLogicContent.model_validate(merged)
    except ValidationError as error:
        raise ProjectWorkflowError(
            "invalid_business_logic",
            "The edited Business Logic is not valid. Check the highlighted sections.",
            details={"errors": _pydantic_details(error)},
        )

    was_approved = project.business_logic_approved_at is not None
    with transaction.atomic():
        project.business_logic["content"] = validated.model_dump(mode="json")
        project.business_logic["updated_at"] = _now_iso()
        project.business_logic["approved_at"] = None
        project.business_logic_approved_at = None
        fields = ["business_logic", "business_logic_approved_at", "updated_at"]
        if was_approved:
            project.context_digest = build_context_digest(project)
            fields.append("context_digest")
        if mark_downstream_stale(project, "business_logic"):
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


def approve_business_logic(project: Project) -> Project:
    """
    Mark Business Logic authoritative and rebuild the Project Context digest.
    Stage stays ``business_logic``; the architecture phase advances it.
    """
    if project.stage != ProjectStage.BUSINESS_LOGIC:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"There is no Business Logic to approve at stage '{project.stage}'.",
            status=409,
        )
    if not (project.business_logic or {}).get("content"):
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate Business Logic before approving it.",
            status=409,
        )

    approved_at = dj_timezone.now()
    with transaction.atomic():
        project.business_logic_approved_at = approved_at
        project.business_logic["approved_at"] = approved_at.isoformat()
        project.context_digest = build_context_digest(project)
        fields = [
            "business_logic",
            "business_logic_approved_at",
            "context_digest",
            "updated_at",
        ]
        if clear_stale(project, "business_logic"):
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


# --- Architecture -------------------------------------------------------

_ARCHITECTURE_EDITABLE_STAGES = (
    ProjectStage.BLUEPRINT,
    ProjectStage.BUSINESS_LOGIC,
    ProjectStage.ARCHITECTURE,
)


def _business_logic_gate_applies(project: Project) -> bool:
    """
    Grandfathering: the Business Logic gate applies to a project ONLY if it has
    not yet progressed to Architecture. A project that already has Architecture
    content was created before Phase D (or before Business Logic existed) and
    keeps working without a retroactive Business Logic requirement.
    """
    return not bool((project.architecture or {}).get("content"))


def generate_architecture(project: Project) -> Project:
    """
    Generate (or regenerate) the Architecture from the APPROVED Blueprint +
    Project Context. Always a DRAFT. Advances ``blueprint -> architecture`` on
    first generation. Same AI-first / transactional guarantees as
    ``generate_blueprint``.
    """
    if project.stage not in _ARCHITECTURE_EDITABLE_STAGES:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"The Architecture is locked at stage '{project.stage}'.",
            status=409,
        )
    if not project.blueprint_approved_at:
        raise ProjectWorkflowError(
            "blueprint_not_approved",
            "Approve the Blueprint before generating the Architecture.",
            status=409,
        )
    # Business Logic gate (grandfathered projects that already have Architecture
    # content are exempt — see _business_logic_gate_applies).
    if _business_logic_gate_applies(project) and not project.business_logic_approved_at:
        raise ProjectWorkflowError(
            "business_logic_not_approved",
            "Approve Business Logic before generating the Architecture.",
            status=409,
        )

    context = {
        "idea": project.original_idea,
        "digest": project.context_digest or {},
        "blueprint": (project.blueprint or {}).get("content") or {},
        "business_logic": (project.business_logic or {}).get("content") or {},
    }
    draft = run_operation(ARCHITECTURE_GENERATION, context, project=project)

    content = normalize_architecture_content(draft.model_dump(mode="json"))
    try:
        validated = ArchitectureContent.model_validate(content)
    except ValidationError as error:
        raise AIOperationError(
            code="ai_invalid_output",
            message="The generated Architecture did not match the expected structure.",
            retryable=True,
            details=_pydantic_details(error),
        )

    now = _now_iso()
    with transaction.atomic():
        project.architecture = {
            "content": validated.model_dump(mode="json"),
            "generated_at": now,
            "updated_at": now,
            "approved_at": None,
        }
        project.architecture_approved_at = None
        project.stage = ProjectStage.ARCHITECTURE
        fields = ["architecture", "architecture_approved_at", "stage", "updated_at"]
        # Regenerating from current upstream reconciles this node; any approved
        # downstream (roadmap) becomes stale. Both no-ops under today's locks.
        stale_changed = clear_stale(project, "architecture")
        stale_changed = mark_downstream_stale(project, "architecture") or stale_changed
        if stale_changed:
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


def update_architecture(project: Project, content_patch) -> Project:
    """Section-level edit. Reverts an approved Architecture to draft."""
    if project.stage != ProjectStage.ARCHITECTURE:
        message = (
            "Generate an Architecture before editing it."
            if project.stage in (ProjectStage.DISCOVERY, ProjectStage.BLUEPRINT)
            else f"The Architecture is locked at stage '{project.stage}'."
        )
        raise ProjectWorkflowError("invalid_workflow_state", message, status=409)

    current = (project.architecture or {}).get("content")
    if not current:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate an Architecture before editing it.",
            status=409,
        )

    if not isinstance(content_patch, dict) or not content_patch:
        raise ProjectWorkflowError(
            "invalid_architecture",
            "Provide one or more Architecture sections to update.",
        )

    unknown = sorted(set(content_patch) - set(ArchitectureContent.model_fields))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_architecture",
            f"Unknown Architecture section(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    merged = normalize_architecture_content({**current, **content_patch})
    try:
        validated = ArchitectureContent.model_validate(merged)
    except ValidationError as error:
        raise ProjectWorkflowError(
            "invalid_architecture",
            "The edited Architecture is not valid. Check the highlighted sections.",
            details={"errors": _pydantic_details(error)},
        )

    was_approved = project.architecture_approved_at is not None
    with transaction.atomic():
        project.architecture["content"] = validated.model_dump(mode="json")
        project.architecture["updated_at"] = _now_iso()
        project.architecture["approved_at"] = None
        project.architecture_approved_at = None
        fields = ["architecture", "architecture_approved_at", "updated_at"]
        if was_approved:
            project.context_digest = build_context_digest(project)
            fields.append("context_digest")
        # Editing the Architecture makes an approved Roadmap stale (no-op today:
        # a Roadmap cannot be approved while the Architecture is still editable).
        if mark_downstream_stale(project, "architecture"):
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


def approve_architecture(project: Project) -> Project:
    """
    Mark the Architecture authoritative and rebuild the Project Context digest.
    Stage stays ``architecture``; the roadmap phase advances it.
    """
    if project.stage != ProjectStage.ARCHITECTURE:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"There is no Architecture to approve at stage '{project.stage}'.",
            status=409,
        )
    if not (project.architecture or {}).get("content"):
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate an Architecture before approving it.",
            status=409,
        )

    approved_at = dj_timezone.now()
    with transaction.atomic():
        project.architecture_approved_at = approved_at
        project.architecture["approved_at"] = approved_at.isoformat()
        project.context_digest = build_context_digest(project)
        fields = [
            "architecture",
            "architecture_approved_at",
            "context_digest",
            "updated_at",
        ]
        # Re-approving reconciles this node. Downstream (roadmap) stays stale
        # until it too is reconciled.
        if clear_stale(project, "architecture"):
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


# --- Roadmap -----------------------------------------------------------

_ROADMAP_EDITABLE_STAGES = (ProjectStage.ARCHITECTURE, ProjectStage.ROADMAP)


def generate_roadmap(project: Project) -> Project:
    """
    Generate (or regenerate) the Development Roadmap from the APPROVED Blueprint +
    Architecture. Always a DRAFT. Advances ``architecture -> roadmap`` on first
    generation. AI-first / transactional, like the other generators.
    """
    if project.stage not in _ROADMAP_EDITABLE_STAGES:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"The Roadmap is locked at stage '{project.stage}'.",
            status=409,
        )
    if not project.architecture_approved_at:
        raise ProjectWorkflowError(
            "architecture_not_approved",
            "Approve the Architecture before generating the Roadmap.",
            status=409,
        )

    context = {
        "idea": project.original_idea,
        "digest": project.context_digest or {},
        "blueprint": (project.blueprint or {}).get("content") or {},
        "business_logic": (project.business_logic or {}).get("content") or {},
        "architecture": (project.architecture or {}).get("content") or {},
    }
    draft = run_operation(ROADMAP_GENERATION, context, project=project)

    content = normalize_roadmap_content(draft.model_dump(mode="json"))
    try:
        validated = RoadmapContent.model_validate(content)
    except ValidationError as error:
        raise AIOperationError(
            code="ai_invalid_output",
            message="The generated Roadmap did not match the expected structure.",
            retryable=True,
            details=_pydantic_details(error),
        )

    now = _now_iso()
    with transaction.atomic():
        project.roadmap = {
            "content": validated.model_dump(mode="json"),
            "generated_at": now,
            "updated_at": now,
            "approved_at": None,
        }
        project.roadmap_approved_at = None
        project.stage = ProjectStage.ROADMAP
        fields = ["roadmap", "roadmap_approved_at", "stage", "updated_at"]
        # Regenerating from current upstream reconciles the Roadmap node.
        if clear_stale(project, "roadmap"):
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


def update_roadmap(project: Project, content_patch) -> Project:
    """
    Structured edit. The only editable section is the full ``phases`` tree.
    Reverts an approved Roadmap to draft.
    """
    if project.stage != ProjectStage.ROADMAP:
        message = (
            "Generate a Roadmap before editing it."
            if project.stage
            in (
                ProjectStage.DISCOVERY,
                ProjectStage.BLUEPRINT,
                ProjectStage.ARCHITECTURE,
            )
            else f"The Roadmap is locked at stage '{project.stage}'."
        )
        raise ProjectWorkflowError("invalid_workflow_state", message, status=409)

    if not (project.roadmap or {}).get("content"):
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate a Roadmap before editing it.",
            status=409,
        )

    if not isinstance(content_patch, dict) or not content_patch:
        raise ProjectWorkflowError(
            "invalid_roadmap", "Provide the 'phases' array to update."
        )

    unknown = sorted(set(content_patch) - {"phases"})
    if unknown:
        raise ProjectWorkflowError(
            "invalid_roadmap",
            f"Unknown Roadmap section(s): {', '.join(unknown)}.",
            details={"unknown": unknown},
        )

    merged = normalize_roadmap_content({"phases": content_patch["phases"]})
    try:
        validated = RoadmapContent.model_validate(merged)
    except ValidationError as error:
        raise ProjectWorkflowError(
            "invalid_roadmap",
            "The edited Roadmap is not valid. Check the highlighted parts.",
            details={"errors": _pydantic_details(error)},
        )

    was_approved = project.roadmap_approved_at is not None
    with transaction.atomic():
        project.roadmap["content"] = validated.model_dump(mode="json")
        project.roadmap["updated_at"] = _now_iso()
        project.roadmap["approved_at"] = None
        project.roadmap_approved_at = None
        fields = ["roadmap", "roadmap_approved_at", "updated_at"]
        if was_approved:
            project.context_digest = build_context_digest(project)
            fields.append("context_digest")
        project.save(update_fields=fields)
    return project


def approve_roadmap(project: Project) -> Project:
    """Mark the Roadmap authoritative and rebuild the Project Context digest."""
    if project.stage != ProjectStage.ROADMAP:
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            f"There is no Roadmap to approve at stage '{project.stage}'.",
            status=409,
        )
    if not (project.roadmap or {}).get("content"):
        raise ProjectWorkflowError(
            "invalid_workflow_state",
            "Generate a Roadmap before approving it.",
            status=409,
        )

    approved_at = dj_timezone.now()
    with transaction.atomic():
        project.roadmap_approved_at = approved_at
        project.roadmap["approved_at"] = approved_at.isoformat()
        project.context_digest = build_context_digest(project)
        fields = [
            "roadmap",
            "roadmap_approved_at",
            "context_digest",
            "updated_at",
        ]
        # Re-approving the Roadmap reconciles it.
        if clear_stale(project, "roadmap"):
            fields.append("downstream_stale")
        project.save(update_fields=fields)
    return project


def set_task_status(project: Project, task_id: str, status) -> Project:
    """
    Progress tracking against the APPROVED Roadmap (Phase F). Does NOT revert
    approval. Validates: allowed status value, allowed transition from the task's
    current status, and (for active statuses) that every dependency is completed.
    Re-setting a task to its current status is an accepted no-op.
    """
    if not project.roadmap_approved_at:
        raise ProjectWorkflowError(
            "roadmap_not_approved",
            "Approve the Roadmap before tracking task progress.",
            status=409,
        )
    if status not in VALID_STATUSES:
        raise ProjectWorkflowError(
            "invalid_status",
            "Status must be one of: not_started, in_progress, ready_for_review, "
            "completed.",
        )

    content = project.roadmap["content"]
    task = find_task(content, task_id)
    if task is None:
        raise ProjectWorkflowError(
            "task_not_found", f"No task '{task_id}' in this Roadmap.", status=404
        )

    current = task["status"]
    if status == current:
        return project  # no-op: nothing to write, no digest rebuild

    if not can_transition(current, status):
        raise ProjectWorkflowError(
            "invalid_transition",
            f"A task cannot move from '{current}' to '{status}'.",
            status=409,
            details={
                "from": current,
                "to": status,
                "allowed": sorted(ALLOWED_TRANSITIONS.get(current, set())),
            },
        )

    if status in ACTIVE_STATUSES:
        status_by_id = {
            t["id"]: t["status"]
            for phase in content["phases"]
            for t in phase["tasks"]
        }
        unfinished = [
            dep for dep in task["dependencies"] if status_by_id.get(dep) != "completed"
        ]
        if unfinished:
            raise ProjectWorkflowError(
                "dependencies_incomplete",
                "Finish this task's dependencies first.",
                status=409,
                details={"unfinished": unfinished},
            )

    task["status"] = status
    with transaction.atomic():
        project.roadmap["content"] = content
        project.roadmap["updated_at"] = _now_iso()
        project.context_digest = build_context_digest(project)
        project.save(update_fields=["roadmap", "context_digest", "updated_at"])
    return project


def project_progress(project: Project) -> dict:
    """
    Deterministic Progress Tracking payload for the approved Roadmap. No AI.
    See ``projects.progress.compute_project_progress``.
    """
    if not project.roadmap_approved_at:
        raise ProjectWorkflowError(
            "roadmap_not_approved",
            "Approve the Roadmap to view implementation progress.",
            status=409,
        )
    return compute_project_progress(project)


# --- Ship Checklist (Phase G) ---------------------------------------------


def get_ship_checklist(project: Project) -> dict:
    """
    Deterministic Ship Checklist. No AI, no gate: the checklist is useful before
    the project is ready precisely because it lists what remains.
    """
    return compute_ship_checklist(project)


def confirm_ship_item(project: Project, item_id, confirmed, note=None) -> dict:
    """
    Persist ONE manual Ship Checklist confirmation, then return the recomputed
    checklist. Only manual items are writable; automatic checks are always
    derived from authoritative state.

    Stage policy: a project advances ``roadmap -> ship`` the first time the
    checklist reaches READY_TO_SHIP (every required automatic check passes AND
    every required manual confirmation is complete). The advance is monotonic -
    a later regression (task reopened, context gone stale) flips the *checklist
    result* back to NOT_READY but does not move the stage backwards, consistent
    with every other VYRA stage gate.
    """
    if not isinstance(item_id, str) or not item_id:
        raise ProjectWorkflowError(
            "invalid_checklist_item", "A manual checklist item id is required."
        )
    try:
        stored, _ = apply_manual_confirmation(project, item_id, confirmed, note)
    except ValueError:
        raise ProjectWorkflowError(
            "invalid_checklist_item",
            f"'{item_id}' is not a manual Ship Checklist item.",
            details={"item_id": item_id},
        )

    result = compute_ship_checklist(project)
    with transaction.atomic():
        fields = ["ship_checklist", "updated_at"]
        if (
            result["overall_status"] == READY_TO_SHIP
            and project.stage == ProjectStage.ROADMAP
        ):
            project.stage = ProjectStage.SHIP
            fields.append("stage")
            result["stage"] = project.stage
        project.save(update_fields=fields)
    return result


# --- Task Workspace + Build Prompt -----------------------------------


def _serialize_prompt(prompt: GeneratedPrompt) -> dict:
    return {
        "id": prompt.id,
        "kind": prompt.kind,
        "content": prompt.content,
        "model": prompt.model,
        "created_at": prompt.created_at.isoformat(),
    }


def _require_approved_roadmap(project: Project) -> dict:
    if not project.roadmap_approved_at:
        raise ProjectWorkflowError(
            "roadmap_not_approved",
            "Approve the Roadmap to open a Task Workspace.",
            status=409,
        )
    return project.roadmap["content"]


def _unfinished_dependencies(roadmap: dict, task: dict) -> list[str]:
    status_by_id = {
        t["id"]: t["status"] for p in roadmap["phases"] for t in p["tasks"]
    }
    return [
        dep for dep in task["dependencies"] if status_by_id.get(dep) != "completed"
    ]


def task_workspace(project: Project, task_id: str) -> dict:
    """Everything the Task Workspace needs. Never includes context_digest."""
    roadmap = _require_approved_roadmap(project)
    context = assemble_task_context(project, task_id)
    if context is None:
        raise ProjectWorkflowError(
            "task_not_found", f"No task '{task_id}' in this Roadmap.", status=404
        )

    task = find_task(roadmap, task_id)
    phase = next(p for p in roadmap["phases"] if p["id"] == task["phase_id"])
    unfinished = _unfinished_dependencies(roadmap, task)
    prompts = list(project.prompts.filter(task_id=task_id))  # newest first (Meta)

    return {
        "task": task,
        "phase": {
            "id": phase["id"],
            "order": phase["order"],
            "title": phase["title"],
            "objective": phase["objective"],
        },
        "dependencies": context["dependencies"],
        "blocked": bool(unfinished),
        "unfinished_dependencies": unfinished,
        "requirements": context["requirements"],
        "requirement_notes": context["requirement_notes"],
        "relevant_context": context,
        "roadmap_approved": True,
        "prompts": [_serialize_prompt(p) for p in prompts],
    }


def generate_build_prompt(project: Project, task_id: str) -> dict:
    """
    Generate + persist a Build Prompt for a task. AI-first / transactional.
    Blocked tasks (unfinished dependencies) cannot generate. Generating does NOT
    change task status.
    """
    roadmap = _require_approved_roadmap(project)
    context = assemble_task_context(project, task_id)
    if context is None:
        raise ProjectWorkflowError(
            "task_not_found", f"No task '{task_id}' in this Roadmap.", status=404
        )

    task = find_task(roadmap, task_id)
    unfinished = _unfinished_dependencies(roadmap, task)
    if unfinished:
        raise ProjectWorkflowError(
            "task_blocked",
            "Finish this task's dependencies before generating a Build Prompt.",
            status=409,
            details={"unfinished": unfinished},
        )

    result = run_operation(BUILD_PROMPT_GENERATION, context, project=project)
    content = result.prompt_markdown.strip()

    with transaction.atomic():
        GeneratedPrompt.objects.create(
            project=project,
            task_id=task_id,
            task_title=task["title"],
            kind=GeneratedPrompt.Kind.BUILD,
            content=content,
            context_snapshot=context,
            model=get_model(),
        )

    return task_workspace(project, task_id)


# Authoritative context the Review Prompt asserts correctness against. If any of
# these is flagged stale (Phase C), a review generated now could validate an
# implementation against a superseded decision — so generation is blocked until a
# human reconciles. No resolution workflow here; this mirrors VYRA's authority
# semantics ("stale = previously approved, may now be inconsistent"). No-op under
# today's stage locks (nothing can set the flag through an allowed flow yet).
_REVIEW_STALE_GUARD = ("business_logic", "architecture", "roadmap")


def generate_review_prompt(project: Project, task_id: str) -> dict:
    """
    Generate + persist a Review Prompt (``kind="review"``) for a task. AI-first /
    transactional, same guards as the Build Prompt (roadmap approved, task
    exists, not dependency-blocked) plus a stale-context guard. Does NOT require a
    stored Build Prompt; if the latest one exists it is included as supporting
    context. Generating does NOT change task status.
    """
    roadmap = _require_approved_roadmap(project)
    context = assemble_task_context(project, task_id)
    if context is None:
        raise ProjectWorkflowError(
            "task_not_found", f"No task '{task_id}' in this Roadmap.", status=404
        )

    task = find_task(roadmap, task_id)
    unfinished = _unfinished_dependencies(roadmap, task)
    if unfinished:
        raise ProjectWorkflowError(
            "task_blocked",
            "Finish this task's dependencies before generating a Review Prompt.",
            status=409,
            details={"unfinished": unfinished},
        )

    stale = [name for name in _REVIEW_STALE_GUARD if is_stale(project, name)]
    if stale:
        raise ProjectWorkflowError(
            "stale_context",
            "Reconcile the flagged upstream artifacts before generating a "
            "Review Prompt: " + ", ".join(stale) + ".",
            status=409,
            details={"stale": stale},
        )

    latest_build = (
        project.prompts.filter(
            task_id=task_id, kind=GeneratedPrompt.Kind.BUILD
        ).first()  # newest first (Meta.ordering)
    )
    if latest_build is not None:
        context["build_prompt"] = {
            "id": latest_build.id,
            "created_at": latest_build.created_at.isoformat(),
            "model": latest_build.model,
            "content": latest_build.content,
        }

    result = run_operation(REVIEW_PROMPT_GENERATION, context, project=project)
    content = result.prompt_markdown.strip()

    with transaction.atomic():
        GeneratedPrompt.objects.create(
            project=project,
            task_id=task_id,
            task_title=task["title"],
            kind=GeneratedPrompt.Kind.REVIEW,
            content=content,
            context_snapshot=context,
            model=get_model(),
        )

    return task_workspace(project, task_id)
