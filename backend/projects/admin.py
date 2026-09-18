from django.contrib import admin

from projects.models import GeneratedPrompt, Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["slug", "name", "stage", "created_at"]
    search_fields = ["slug", "name", "original_idea"]
    readonly_fields = ["id", "slug", "created_at", "updated_at"]


@admin.register(GeneratedPrompt)
class GeneratedPromptAdmin(admin.ModelAdmin):
    list_display = ["project", "task_id", "task_title", "kind", "model", "created_at"]
    list_filter = ["kind", "model"]
    search_fields = ["project__slug", "task_id", "task_title"]
    readonly_fields = [f.name for f in GeneratedPrompt._meta.fields]
