from django.db import models


class AIRequestLog(models.Model):
    """One row per AI operation attempt — for cost, latency and debugging."""

    OUTCOME_CHOICES = [
        ("ok", "ok"),
        ("error", "error"),
    ]

    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_requests",
    )
    operation = models.CharField(max_length=64)
    # Foundation metadata (Phase A). ``provider`` defaults to "anthropic" - the
    # only provider today; the AI provider abstraction is Phase B.
    provider = models.CharField(max_length=32, default="anthropic")
    model = models.CharField(max_length=128)
    prompt_version = models.CharField(max_length=32, blank=True, default="")
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)
    outcome = models.CharField(max_length=16, choices=OUTCOME_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.operation} [{self.outcome}] {self.latency_ms}ms"
