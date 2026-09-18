from django.conf import settings
from django.db import migrations

# The one designated account existing (pre-P-2) local projects are assigned
# to. A real, log-in-able account — not a sentinel/system row — so local
# development can keep working with those projects immediately after
# upgrading: log in as this address (its password is unusable until reset;
# see the P-2 report for the documented local-dev path to claim it).
LEGACY_LOCAL_OWNER_USERNAME = "legacy-local-projects@batonx.local"


def assign_legacy_owner(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    orphaned = Project.objects.filter(owner__isnull=True)
    if not orphaned.exists():
        return

    user, created = User.objects.get_or_create(
        username=LEGACY_LOCAL_OWNER_USERNAME,
        defaults={"email": LEGACY_LOCAL_OWNER_USERNAME, "is_active": True},
    )
    if created:
        # No password was supplied — mark it explicitly unusable (Django's
        # own convention: a leading "!" in the stored hash) rather than
        # leaving an ambiguous empty string. A developer claims this account
        # locally via `manage.py changepassword legacy-local-projects@batonx.local`.
        user.set_unusable_password()
        user.save(update_fields=["password"])
    orphaned.update(owner=user)


def reverse_noop(apps, schema_editor):
    # Deliberately not reversed: nulling ``owner`` back out would only be
    # valid while the column is still nullable (pre-0017). A full P-2
    # rollback un-assigns ownership as a side effect of 0015's own reverse
    # (dropping the column entirely), so there is nothing safe for this
    # migration's reverse to do on its own.
    pass


class Migration(migrations.Migration):
    """
    Step 2 of 3 (Phase P-2 ownership migration): assign every existing,
    not-yet-owned Project to one designated legacy-local-projects user.
    Does not delete or recreate any Project data.
    """

    dependencies = [
        ("projects", "0015_project_owner"),
    ]

    operations = [
        migrations.RunPython(assign_legacy_owner, reverse_noop),
    ]
