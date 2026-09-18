from rest_framework import serializers

from projects.models import Project
from projects.roadmap import compute_progress, next_recommended_task


class ProjectSerializer(serializers.ModelSerializer):
    """
    Public project shape. Generated documents (discovery / blueprint /
    architecture / roadmap) are returned in full so the UI can rehydrate on
    reload. ``context_digest`` is internal and deliberately not exposed.

    ``roadmap_meta`` is derived (progress + dependency-aware next task); ``null``
    until a Roadmap exists.
    """

    roadmap_meta = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "slug",
            "name",
            "original_idea",
            "project_type",
            "data_goal",
            "stage",
            "downstream_stale",
            "discovery",
            "data_brief",
            "data_brief_approved_at",
            "data_quality",
            "data_quality_approved_at",
            "transformation_plan",
            "transformation_plan_approved_at",
            "dashboard_blueprint",
            "dashboard_blueprint_approved_at",
            "blueprint",
            "blueprint_approved_at",
            "business_logic",
            "business_logic_approved_at",
            "architecture",
            "architecture_approved_at",
            "roadmap",
            "roadmap_approved_at",
            "roadmap_meta",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_roadmap_meta(self, obj):
        content = (obj.roadmap or {}).get("content")
        if not content:
            return None
        return {
            "approved": obj.roadmap_approved_at is not None,
            "progress": compute_progress(content),
            **next_recommended_task(content),
        }
