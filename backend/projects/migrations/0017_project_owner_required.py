import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Step 3 of 3 (Phase P-2 ownership migration): every row now has an owner
    (0016 ran first), so enforce it at the schema level. Ownership is
    server-controlled from here on — see ``projects.services.create_project``
    and ``api.views._project_or_404``.
    """

    dependencies = [
        ("projects", "0016_assign_legacy_owner"),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="projects",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
