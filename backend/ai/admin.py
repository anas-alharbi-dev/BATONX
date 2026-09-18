from django.contrib import admin

from ai.models import AIRequestLog


@admin.register(AIRequestLog)
class AIRequestLogAdmin(admin.ModelAdmin):
    list_display = [
        "operation",
        "outcome",
        "model",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "created_at",
    ]
    list_filter = ["operation", "outcome", "model"]
    readonly_fields = [f.name for f in AIRequestLog._meta.fields]
