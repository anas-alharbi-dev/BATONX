"""
Shared Phase P-2 test infrastructure.

Every one of the 522 pre-P-2 tests was written before ownership/auth
existed. Rather than touching each test's own body, every ``APITestCase``
subclass across the suite is switched to ``AuthenticatedAPITestCase`` (a thin
subclass, see the sed-driven rename in the P-2 completion report) and every
ORM-level Project factory defaults new Projects to the SAME shared
``default_owner()`` — so ``self.client`` and the Projects those factories
build always agree on who owns them, and every existing test keeps testing
exactly what it tested before, just inside an authenticated, ownership-
consistent context.

Cross-user authorization tests (new in P-2) create a second, distinct user
and call ``self.client.force_authenticate(user=other_user)`` for that one
test method — this never leaks between tests since ``self.client`` is
recreated per test method by Django's test runner.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

User = get_user_model()


def default_owner():
    """The shared owner every existing (pre-P-2) test fixture defaults to.
    ``get_or_create`` is cheap and safe to call once per test — each test
    method runs inside its own transaction/savepoint that's rolled back
    afterward, so there's no cross-test state to worry about beyond this."""
    user, _ = User.objects.get_or_create(
        username="dev@example.com",
        defaults={"email": "dev@example.com", "is_active": True},
    )
    return user


class AuthenticatedAPITestCase(APITestCase):
    """
    Authenticates ``self.client`` as ``default_owner()`` before every test.
    Overrides ``_pre_setup`` (not ``setUp``) deliberately: many existing test
    classes define their own ``setUp`` without calling ``super().setUp()``,
    which would silently skip authentication if it lived there. DRF's
    ``APITestCase`` builds ``self.client`` inside ``_pre_setup``, so this
    runs immediately after that, before any subclass's ``setUp`` at all.
    """

    def _pre_setup(self):
        super()._pre_setup()
        self.client.force_authenticate(user=default_owner())
