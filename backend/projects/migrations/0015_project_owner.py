import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Step 1 of 3 (Phase P-2 ownership migration): add ``owner`` nullable so
    existing local Project rows aren't broken by a NOT NULL column with no
    default. See 0016 (backfill) and 0017 (enforce non-null).
    """

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects", "0014_analysisplan_stale_analysisplan_stale_reason_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="projects",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
