import secrets
import uuid

from django.conf import settings
from django.db import models


class ProjectStage(models.TextChoices):
    """Where a project sits in the VYRA pipeline. Advanced by approval gates."""

    DISCOVERY = "discovery", "Discovery"
    BLUEPRINT = "blueprint", "Blueprint"
    BUSINESS_LOGIC = "business_logic", "Business Logic"
    ARCHITECTURE = "architecture", "Architecture"
    ROADMAP = "roadmap", "Roadmap"
    BUILDING = "building", "Building"
    SHIP = "ship", "Ship"

    # Data & Analytics workflow (Phase I-1 implements the first two).
    DATA_BRIEF = "data_brief", "Data Brief"
    DATA_SOURCES = "data_sources", "Data Sources"


class ProjectType(models.TextChoices):
    """
    Which domain workflow a project follows. Phase A added the discriminator; the
    Data & Analytics workflow begins in Phase I-1.
    """

    SOFTWARE = "software", "Software"
    DATA = "data", "Data & Analytics"


class DataGoal(models.TextChoices):
    """
    The lens that tunes which Data-workflow stages are required for a project.
    Set only on ``project_type == "data"`` projects; blank for software.
    """

    ANALYTICS = "analytics", "Analytics"
    BI = "bi", "BI / Dashboards"
    ENGINEERING = "engineering", "Data Engineering"
    WAREHOUSE = "warehouse", "Warehouse / Marts"
    QUALITY = "quality", "Data Quality"
    MIXED = "mixed", "Mixed"


def generate_slug() -> str:
    """Unguessable, URL-safe identifier used in project URLs (no auth in the MVP)."""
    return secrets.token_urlsafe(9)


class Project(models.Model):
    """
    The hub record and single source of truth for a VYRA project.

    Generated-as-a-whole artifacts (discovery, and later blueprint/architecture)
    are stored as validated JSON documents. Iterated/queried concepts
    (phases, tasks, prompts) become their own tables in later phases.

    ``owner`` (Phase P-2) is the sole authorization boundary for every
    Project-scoped resource: every nested entity (Dataset, Query,
    MetricDefinition, Conversation, Proposal, ...) is looked up scoped to a
    specific ``Project`` instance, so gating access to the ``Project`` itself
    (see ``api.views._project_or_404``) is sufficient — no child model needs
    its own owner field. Server-controlled only: never accepted from request
    input, always taken from ``request.user`` at creation.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(
        max_length=32, unique=True, default=generate_slug, editable=False
    )
    name = models.CharField(max_length=200, blank=True)
    original_idea = models.TextField()
    project_type = models.CharField(
        max_length=16,
        choices=ProjectType.choices,
        default=ProjectType.SOFTWARE,
    )
    # Only set for data projects; blank for software.
    data_goal = models.CharField(
        max_length=16, choices=DataGoal.choices, blank=True, default=""
    )
    stage = models.CharField(
        max_length=32, choices=ProjectStage.choices, default=ProjectStage.DISCOVERY
    )

    # Structured, generated documents (schema-validated before write).
    # discovery: {questions, answers, generated_at, answered_at}
    discovery = models.JSONField(default=dict, blank=True)
    # blueprint: {content, generated_at, updated_at, approved_at?}
    blueprint = models.JSONField(default=dict, blank=True)
    blueprint_approved_at = models.DateTimeField(null=True, blank=True)
    # business_logic: {content, generated_at, updated_at, approved_at?}
    business_logic = models.JSONField(default=dict, blank=True)
    business_logic_approved_at = models.DateTimeField(null=True, blank=True)
    # architecture: {content, generated_at, updated_at, approved_at?}
    architecture = models.JSONField(default=dict, blank=True)
    architecture_approved_at = models.DateTimeField(null=True, blank=True)
    # roadmap: {content: {phases:[...]}, generated_at, updated_at, approved_at?}
    roadmap = models.JSONField(default=dict, blank=True)
    roadmap_approved_at = models.DateTimeField(null=True, blank=True)

    # Small derived summary of APPROVED artifacts. Rebuilt on each approval;
    # base context for downstream AI operations (see projects.context).
    context_digest = models.JSONField(default=dict, blank=True)

    # Foundation metadata (Phase A): advisory "a downstream approved artifact may
    # be out of date". Not populated or acted on yet - propagation logic is
    # Phase C. Shape (once used): {"architecture": true, "roadmap": true}.
    downstream_stale = models.JSONField(default=dict, blank=True)

    # Ship Checklist (Phase G): ONLY user-confirmed manual confirmations, shape
    # {item_id: {confirmed: bool, confirmed_at: iso|null, note: str}}. Automatic
    # readiness checks are always recomputed from authoritative state and are
    # never stored here.
    ship_checklist = models.JSONField(default=dict, blank=True)

    # Data & Analytics — first approved data artifact (Phase I-1).
    # data_brief: {content, generated_at, updated_at, approved_at?}
    data_brief = models.JSONField(default=dict, blank=True)
    data_brief_approved_at = models.DateTimeField(null=True, blank=True)

    # Data Quality (Phase I-2): {content: {observations, rules}, ...}. Only the
    # rules require approval; observations are deterministic, check results live
    # in QualityCheckRun.
    data_quality = models.JSONField(default=dict, blank=True)
    data_quality_approved_at = models.DateTimeField(null=True, blank=True)

    # Transformation Plan (Phase I-2): {content: {source_dataset_id, steps,
    # outputs}, ...}. Structured steps are the Source of Truth; SQL is derived.
    transformation_plan = models.JSONField(default=dict, blank=True)
    transformation_plan_approved_at = models.DateTimeField(null=True, blank=True)

    # Dashboard Blueprint (Phase I-4): {content: {audience, decision_use_case,
    # refresh_cadence, global_filters, panels: [{id: VIZ-xx, ...}], layout}, ...}.
    # A generic design artifact only — no BI-tool-specific implementation, no
    # dashboard renderer.
    dashboard_blueprint = models.JSONField(default=dict, blank=True)
    dashboard_blueprint_approved_at = models.DateTimeField(null=True, blank=True)

    # Delivery Readiness (Phase I-5) — ONLY manual confirmations persist, same
    # shape/philosophy as ``ship_checklist``: {item_id: {confirmed,
    # confirmed_at, note}}. Automatic checks are always recomputed.
    data_readiness = models.JSONField(default=dict, blank=True)

    # Ownership (Phase P-2). Final state is non-null — added nullable, backfilled
    # onto one designated legacy-local-projects user, then enforced non-null
    # across three migrations (0015/0016/0017); see migration 0016's
    # LEGACY_LOCAL_OWNER_USERNAME for exactly how existing local projects were
    # assigned.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name or 'Untitled project'} ({self.slug})"


class GeneratedPrompt(models.Model):
    """
    An append-only record of a prompt VYRA generated for a Roadmap task.

    First relational child of ``Project``. Chosen over stashing prompts in the
    roadmap JSON because prompts are versioned history, queried per task, and
    independent of the roadmap document's lifecycle (editing the roadmap must not
    touch prompt history). ``context_snapshot`` stores the exact deterministic
    context that produced the prompt - all derived from approved artifacts, no
    secrets, no ``context_digest``.
    """

    class Kind(models.TextChoices):
        BUILD = "build", "Build"
        REVIEW = "review", "Review"  # reserved for the review-prompt phase

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="prompts"
    )
    task_id = models.CharField(max_length=16)
    task_title = models.CharField(max_length=300, blank=True)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.BUILD)
    content = models.TextField()
    context_snapshot = models.JSONField(default=dict)
    model = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "task_id", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.kind} prompt for {self.task_id} ({self.project.slug})"


class Conversation(models.Model):
    """
    A project-scoped conversation with the Conversational Layer (Phase H).

    The conversation is NOT a source of truth. It reads, explains, and proposes;
    only an explicitly approved ``Proposal`` mutates authoritative state, and only
    through the existing domain services.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="conversations"
    )
    # Compact rolling summary of older turns. Conversation memory only — kept
    # strictly separate from approved project memory (context_digest). Blank in
    # Phase H: the AI receives a bounded window of recent messages, not a summary.
    summary = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"conversation {self.id} ({self.project.slug})"


class ConversationMessage(models.Model):
    """One turn in a ``Conversation``. Append-only."""

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    # e.g. {"intent", "referenced_artifacts", "prompt_version", "proposal_id"}.
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.role} @ {self.conversation_id}"


class Proposal(models.Model):
    """
    A structured, AI-authored change proposal awaiting explicit human review.

    A proposal never mutates anything by existing. On approval it is applied
    through the same domain service that owns the artifact
    (``update_blueprint`` / ``update_business_logic`` / ``update_architecture``),
    so validation, normalization and Phase C stale propagation all apply.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        APPLIED = "applied", "Applied"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="proposals"
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="proposals"
    )
    # blueprint | business_logic | architecture (the supported targets).
    target_artifact = models.CharField(max_length=32)
    proposal_type = models.CharField(max_length=32, default="section_patch")
    # {"sections": {<section>: <value>, ...}, "summary": "..."} — a partial
    # ``content`` patch in the same shape ``update_<artifact>`` accepts.
    proposed_change = models.JSONField(default=dict)
    rationale = models.TextField(blank=True, default="")
    impact_summary = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"proposal {self.id} -> {self.target_artifact} [{self.status}]"


class Dataset(models.Model):
    """
    A registered data source for a Data project (Phase I-1). Raw bytes live in a
    ``FileStore`` (see ``common.storage``); this row holds metadata + the
    inferred schema + a per-dataset source interpretation. Only exists on
    ``project_type == "data"`` projects.
    """

    class SourceType(models.TextChoices):
        CSV = "csv", "CSV"
        JSON = "json", "JSON"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PROFILING = "profiling", "Profiling"
        PROFILED = "profiled", "Profiled"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="datasets"
    )
    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=8, choices=SourceType.choices)
    # FileStore key — server-generated, never a filesystem path.
    storage_ref = models.CharField(max_length=500)
    original_filename = models.CharField(max_length=300, blank=True)  # metadata only
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)  # sha256 hex
    encoding = models.CharField(max_length=32, null=True, blank=True)
    delimiter = models.CharField(max_length=4, null=True, blank=True)
    # Headline stats cached from the latest ProfilingRun (history lives there).
    row_count = models.IntegerField(null=True, blank=True)
    column_count = models.IntegerField(null=True, blank=True)
    inferred_schema = models.JSONField(default=list, blank=True)
    sampled = models.BooleanField(default=False)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.UPLOADED
    )
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_by",
    )
    profiling_stale = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    # Source interpretation (AI-proposed, human-approved) —
    # {content, generated_at, updated_at, approved_at?}.
    interpretation = models.JSONField(default=dict, blank=True)
    interpretation_approved_at = models.DateTimeField(null=True, blank=True)
    # Phase I-5: the approved interpretation may now be inconsistent with an
    # upstream change (e.g. the Data Brief changed) — content/approval kept,
    # cleared only by re-approving the interpretation.
    interpretation_stale = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    profiled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "-created_at"])]

    def __str__(self) -> str:
        return f"dataset {self.name} ({self.project.slug})"


class Job(models.Model):
    """
    A unit of deterministic work over data (Phase I-1: ``profile_dataset`` only).
    Execution in I-1 is synchronous; the shape is future-compatible with an
    async backend without redesign.
    """

    class Kind(models.TextChoices):
        PROFILE_DATASET = "profile_dataset", "Profile dataset"
        RUN_QUALITY_CHECKS = "run_quality_checks", "Run quality checks"
        RUN_TRANSFORMATION_PREVIEW = (
            "run_transformation_preview",
            "Run transformation preview",
        )
        VALIDATE_METRIC = "validate_metric", "Validate metric"
        EXECUTE_QUERY = "execute_query", "Execute query"
        RUN_ANALYSIS = "run_analysis", "Run analysis"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="jobs"
    )
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="jobs",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.QUEUED
    )
    params = models.JSONField(default=dict, blank=True)
    # e.g. {"profiling_run": "<uuid>"} — where the output artifact lives.
    result_ref = models.JSONField(default=dict, blank=True)
    progress = models.IntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "-created_at"])]

    def __str__(self) -> str:
        return f"job {self.kind} [{self.status}] ({self.project.slug})"


class ProfilingRun(models.Model):
    """
    An immutable snapshot of deterministic profiling for a dataset. A re-profile
    creates a NEW row; existing rows are never mutated, so profiling history
    stays traceable. ``Dataset`` only caches headline fields (row_count,
    column_count, profiled_at, status).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="profiling_runs"
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profiling_runs",
    )
    # {row_count, column_count, duplicate_row_count, sampled, sample_size}
    table_stats = models.JSONField(default=dict)
    # [{name, dtype, count, null_count, null_pct, distinct_count, ...}]
    columns = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"profiling {self.id} of {self.dataset_id}"


class QualityCheckRun(models.Model):
    """
    An immutable snapshot of a deterministic Data Quality check pass (Phase I-2).
    A re-run creates a NEW row; nothing here is mutated. Pass/fail comes from
    real data via the DuckDB boundary — never from AI. Failure samples are
    capped and sensitive columns are redacted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="quality_check_runs"
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quality_check_runs",
    )
    # [{rule_id, dataset_ref, assertion, passed, failing_row_count, checked_at,
    #   sample_failures: [...capped/redacted...], error?}]
    results = models.JSONField(default=list)
    # {total, passed, failed, critical_failed}
    summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"quality run {self.id} ({self.project.slug})"


class MetricDefinition(models.Model):
    """
    An authoritative KPI/metric definition (Phase I-3). Multi-instance, own
    table (unlike the single Project-level artifacts). ``business_id`` (KPI-01,
    KPI-02, ...) is deterministic and unique per project.

    Definition != Result: no computed value is ever stored here. Validation
    facts live in the immutable ``MetricValidationRun``.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_id = models.CharField(max_length=16)  # "KPI-01"
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="metrics"
    )
    name = models.CharField(max_length=200)
    business_meaning = models.TextField(blank=True, default="")
    formula_text = models.TextField(blank=True, default="")
    # {aggregation, base_table_ref, measure?, numerator?, denominator?,
    #  default_filters, time_field, dimensions}
    structured = models.JSONField(default=dict)
    time_grain = models.CharField(max_length=16, blank=True, default="")
    allowed_dimensions = models.JSONField(default=list, blank=True)
    # ["<dataset_or_field ref>", ...] — concise, human-readable lineage hints
    source_fields = models.JSONField(default=list, blank=True)
    owner = models.CharField(max_length=200, blank=True, default="")
    related_goal_ref = models.CharField(max_length=64, blank=True, default="")
    caveats = models.JSONField(default=list, blank=True)
    # human-readable description of what validation checks apply (not results)
    validation_checks = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    # Phase I-5 entity-level stale: an upstream change (Data Brief, Quality,
    # Transformation, or the dataset itself) may make this definition's
    # approval inconsistent. Content/approval are kept; only
    # regenerate/edit-then-approve clears it (see ``projects.data.stale``).
    stale = models.BooleanField(default=False)
    stale_reason = models.TextField(blank=True, default="")
    stale_since = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["business_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "business_id"], name="unique_metric_business_id"
            )
        ]

    def __str__(self) -> str:
        return f"{self.business_id} {self.name} ({self.project.slug})"


class MetricValidationRun(models.Model):
    """
    Immutable fact: "BATONX could compute this metric from the current data" (or
    not) — never a business-correctness judgement, which stays the human-approved
    definition. AI never decides pass/fail.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    metric = models.ForeignKey(
        MetricDefinition, on_delete=models.CASCADE, related_name="validation_runs"
    )
    job = models.ForeignKey(
        Job, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="metric_validation_runs",
    )
    query_sql = models.TextField(blank=True, default="")
    result = models.JSONField(default=dict, blank=True)  # {value, row_count, ...}
    passed = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"validation {self.id} of {self.metric_id} [{self.passed}]"


class Query(models.Model):
    """
    A business question turned into a structured, approved Query Plan, then
    generated SQL, then a human review, then a bounded execution (Phase I-3).
    Multi-instance, own table.
    """

    class Status(models.TextChoices):
        DRAFT_PLAN = "draft_plan", "Draft plan"
        PLAN_APPROVED = "plan_approved", "Plan approved"
        SQL_GENERATED = "sql_generated", "SQL generated"
        REVIEWED = "reviewed", "Reviewed"
        EXECUTED = "executed", "Executed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_id = models.CharField(max_length=16)  # "Q-01"
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="queries"
    )
    question = models.TextField()
    # {objective, required_kpi_refs, required_fields, base_table_ref, grain,
    #  dimensions, filters, joins, sort, expected_result_shape, assumptions}
    plan = models.JSONField(default=dict, blank=True)
    plan_approved_at = models.DateTimeField(null=True, blank=True)
    sql = models.TextField(blank=True, default="")
    dialect = models.CharField(max_length=16, default="duckdb")
    kpi_refs = models.JSONField(default=list, blank=True)
    # {ai: {...sql_review output...}?, human_reviewed: bool, human_reviewed_at}
    review = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT_PLAN
    )
    last_run_job = models.ForeignKey(
        Job, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Phase I-5 entity-level stale — see ``MetricDefinition.stale``. Cleared
    # only by ``mark_query_reviewed()`` (the query's own reconciliation step).
    stale = models.BooleanField(default=False)
    stale_reason = models.TextField(blank=True, default="")
    stale_since = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["business_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "business_id"], name="unique_query_business_id"
            )
        ]

    def __str__(self) -> str:
        return f"{self.business_id} [{self.status}] ({self.project.slug})"


class QueryRun(models.Model):
    """
    Immutable, bounded execution result for a ``Query``. Only reviewed SQL may
    produce one. Results are capped — never a full unrestricted result set.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.ForeignKey(
        Query, on_delete=models.CASCADE, related_name="runs"
    )
    job = models.ForeignKey(
        Job, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    executed_sql = models.TextField()
    columns = models.JSONField(default=list)
    rows = models.JSONField(default=list)  # capped
    row_count = models.IntegerField(default=0)
    truncated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"query run {self.id} of {self.query_id}"


class AnalysisMethod(models.TextChoices):
    """The only Analysis methods implemented in Phase I-4 — each has a known,
    deterministic execution strategy. Not a general-purpose statistics engine;
    cohort/correlation are deliberately not offered."""

    DESCRIPTIVE = "descriptive", "Descriptive"
    TREND = "trend", "Trend"
    SEGMENTATION = "segmentation", "Segmentation"
    COMPARISON = "comparison", "Comparison"
    FUNNEL = "funnel", "Funnel"


class AnalysisPlan(models.Model):
    """
    A human-decided (or AI-drafted, human-approved) plan for what to compute and
    why (Phase I-4). ``business_id`` (AN-01, AN-02, ...) is deterministic and
    unique per project. Execution itself is always deterministic — see
    ``AnalysisResult``.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_id = models.CharField(max_length=16)  # "AN-01"
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="analysis_plans"
    )
    business_question = models.TextField()
    hypotheses = models.JSONField(default=list, blank=True)
    required_metrics = models.JSONField(default=list, blank=True)  # ["KPI-01", ...]
    segments = models.JSONField(default=list, blank=True)  # dimension/column names
    # [{label, time_range?: {start, end}, filters: [{field, operator, value}]}]
    comparisons = models.JSONField(default=list, blank=True)
    time_range = models.JSONField(default=dict, blank=True)  # {start, end}? optional
    method = models.CharField(max_length=16, choices=AnalysisMethod.choices)
    expected_outputs = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    # Phase I-5 entity-level stale — see ``MetricDefinition.stale``. Cleared
    # only by a fresh successful ``run_analysis_plan()`` (the plan's own
    # reconciliation step — re-approving alone is not enough).
    stale = models.BooleanField(default=False)
    stale_reason = models.TextField(blank=True, default="")
    stale_since = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["business_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "business_id"], name="unique_analysis_plan_business_id"
            )
        ]

    def __str__(self) -> str:
        return f"{self.business_id} [{self.method}] ({self.project.slug})"


class AnalysisResult(models.Model):
    """
    Immutable fact storage. Produced ONLY by deterministic execution of an
    approved ``AnalysisPlan`` — never by AI. Re-running a plan creates a new
    row; old results/findings are never overwritten or deleted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="analysis_results"
    )
    plan = models.ForeignKey(
        AnalysisPlan, on_delete=models.CASCADE, related_name="results"
    )
    job = models.ForeignKey(
        Job, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # [{id: "F-01", statement, metric_values, breakdown, evidence, computed_at}]
    findings = models.JSONField(default=list)
    data_caveats = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"analysis result {self.id} of {self.plan_id}"


class Insight(models.Model):
    """
    An AI interpretation/recommendation, evidence-bound to a specific
    ``AnalysisResult``'s findings (Phase I-4). ``business_id`` (INS-01, ...) is
    deterministic and unique per project. Accepting an Insight records a human
    decision about the INTERPRETATION — it never alters the underlying
    deterministic facts.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACCEPTED = "accepted", "Accepted"

    class Confidence(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_id = models.CharField(max_length=16)  # "INS-01"
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="insights"
    )
    analysis_result = models.ForeignKey(
        AnalysisResult, on_delete=models.CASCADE, related_name="insights"
    )
    # must exactly match one supporting finding's deterministic ``statement`` —
    # enforced by the evidence validator, never freely AI-authored.
    fact = models.TextField()
    interpretation = models.TextField(blank=True, default="")
    recommendation = models.TextField(blank=True, default="")
    confidence = models.CharField(
        max_length=8, choices=Confidence.choices, default=Confidence.MEDIUM
    )
    supporting_finding_ids = models.JSONField(default=list)
    caveats = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["business_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "business_id"], name="unique_insight_business_id"
            )
        ]

    def __str__(self) -> str:
        return f"{self.business_id} [{self.status}] ({self.project.slug})"


class DashboardBuildPrompt(models.Model):
    """
    An append-only, immutable record of a generated generic Dashboard Build
    Prompt (Phase I-4). Deliberately a separate minimal model rather than
    reusing ``GeneratedPrompt`` — that model is shaped around a Roadmap
    ``task_id`` (Software-specific); the Dashboard Blueprint is a single
    Project-level artifact with no task to key off.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="dashboard_build_prompts"
    )
    content = models.TextField()
    context_snapshot = models.JSONField(default=dict)
    model = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"dashboard build prompt {self.id} ({self.project.slug})"
