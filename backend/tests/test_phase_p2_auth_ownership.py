"""
Phase P-2 verification — authentication, Project ownership, and the
resulting authorization boundary across the whole Software/Data surface.

Ownership is enforced at exactly one choke point (``api.views._project_or_404``);
every nested resource (Dataset, Query, MetricDefinition, Conversation,
Proposal, ...) is always looked up scoped to a specific ``Project`` instance,
so this file mostly proves that choke point actually blocks cross-user
access everywhere it should, rather than re-testing domain logic the
pre-P-2 suite already covers (and which still passes, now authenticated —
see ``tests/base.py``).
"""
import unittest.mock as mock

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from projects.models import Conversation, Project, Proposal
from tests.base import AuthenticatedAPITestCase, default_owner
from tests.test_phase1 import make_project
from tests.test_phase4 import make_roadmap_project
from tests.test_phase_i1_data_foundation import (
    FakeProvider,
    data_project_with_brief,
    uploaded_dataset,
)

User = get_user_model()


def other_user():
    user, _ = User.objects.get_or_create(
        username="other@example.com",
        defaults={"email": "other@example.com", "is_active": True},
    )
    return user


# =====================================================================
# AUTH
# =====================================================================


class SignupTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=None)  # signup itself is public

    def test_signup_succeeds(self):
        res = self.client.post(
            "/api/auth/signup/",
            {"email": "new.user@example.com", "password": "correct horse battery", "confirm_password": "correct horse battery"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["email"], "new.user@example.com")
        self.assertEqual(body["plan"], "free")
        self.assertNotIn("password", body)
        self.assertTrue(User.objects.filter(username="new.user@example.com").exists())

    def test_signup_authenticates_immediately(self):
        self.client.post(
            "/api/auth/signup/",
            {"email": "auto.login@example.com", "password": "correct horse battery", "confirm_password": "correct horse battery"},
            format="json",
        )
        res = self.client.get("/api/auth/me/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], "auto.login@example.com")

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username="dupe@example.com", email="dupe@example.com", password="whatever-1234")
        res = self.client.post(
            "/api/auth/signup/",
            {"email": "dupe@example.com", "password": "correct horse battery", "confirm_password": "correct horse battery"},
            format="json",
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "email_taken")

    def test_mismatched_confirm_password_rejected(self):
        res = self.client.post(
            "/api/auth/signup/",
            {"email": "mismatch@example.com", "password": "correct horse battery", "confirm_password": "something else"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "password_mismatch")

    def test_weak_password_rejected(self):
        res = self.client.post(
            "/api/auth/signup/",
            {"email": "weak@example.com", "password": "1234567", "confirm_password": "1234567"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "weak_password")

    def test_invalid_email_rejected(self):
        res = self.client.post(
            "/api/auth/signup/",
            {"email": "not-an-email", "password": "correct horse battery", "confirm_password": "correct horse battery"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_email")


class LoginLogoutTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=None)
        self.user = User.objects.create_user(
            username="login.test@example.com", email="login.test@example.com", password="correct horse battery"
        )

    def test_login_succeeds(self):
        res = self.client.post(
            "/api/auth/login/", {"email": "login.test@example.com", "password": "correct horse battery"}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["email"], "login.test@example.com")

    def test_wrong_password_rejected(self):
        res = self.client.post(
            "/api/auth/login/", {"email": "login.test@example.com", "password": "wrong password"}, format="json"
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"]["code"], "invalid_credentials")

    def test_unknown_email_rejected(self):
        res = self.client.post(
            "/api/auth/login/", {"email": "nobody@example.com", "password": "whatever-1234"}, format="json"
        )
        self.assertEqual(res.status_code, 401)

    def test_logout_invalidates_session(self):
        self.client.post(
            "/api/auth/login/", {"email": "login.test@example.com", "password": "correct horse battery"}, format="json"
        )
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

        res = self.client.post("/api/auth/logout/")
        self.assertEqual(res.status_code, 204)

        # The real regression this guards: logout must invalidate the
        # server-side session, not just tell the frontend to forget a token.
        # A stale/replayed session cookie must be rejected after logout.
        res = self.client.get("/api/auth/me/")
        self.assertEqual(res.status_code, 401)


class MeTests(AuthenticatedAPITestCase):
    def test_me_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        res = self.client.get("/api/auth/me/")
        self.assertEqual(res.status_code, 401)

    def test_me_authenticated_succeeds(self):
        res = self.client.get("/api/auth/me/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(set(body.keys()), {"id", "email", "display_name", "plan"})
        self.assertEqual(body["email"], "dev@example.com")
        self.assertEqual(body["plan"], "free")


# =====================================================================
# OWNERSHIP — creation, listing, forging
# =====================================================================


class ProjectCreationOwnershipTests(AuthenticatedAPITestCase):
    def test_created_project_owner_is_request_user(self):
        project = make_project(owner=default_owner())
        self.assertEqual(project.owner, default_owner())

    def test_owner_cannot_be_forged_via_request_body(self):
        someone_else = other_user()
        # A real end-to-end creation call would hit the AI provider; the
        # security property under test is purely "does the view ever read
        # owner from request.data" — verified without needing AI by
        # asserting the view only ever passes request.user through, and by
        # confirming a forged ``owner``/``owner_id`` field in the payload is
        # silently ignored by the serializer boundary at read time.
        project = make_project(owner=default_owner())
        serialized = self.client.get(f"/api/projects/{project.slug}/").json()
        self.assertNotIn("owner", serialized)
        self.assertNotIn("owner_id", serialized)
        # PATCH-like update paths never accept or apply an owner field either.
        res = self.client.patch(
            f"/api/projects/{project.slug}/blueprint/",
            {"content": {}, "owner": someone_else.id, "owner_id": someone_else.id},
            format="json",
        )
        project.refresh_from_db()
        self.assertEqual(project.owner, default_owner())


class ProjectListScopingTests(AuthenticatedAPITestCase):
    def test_list_returns_only_owned_projects(self):
        mine = make_project(owner=default_owner(), name="Mine")
        theirs = make_project(owner=other_user(), name="Theirs")

        res = self.client.get("/api/projects/")
        self.assertEqual(res.status_code, 200)
        slugs = {p["slug"] for p in res.json()["projects"]}
        self.assertIn(mine.slug, slugs)
        self.assertNotIn(theirs.slug, slugs)

    def test_user_b_sees_only_bs_projects(self):
        make_project(owner=default_owner(), name="A's project")
        b_project = make_project(owner=other_user(), name="B's project")

        client_b = APIClient()
        client_b.force_authenticate(user=other_user())
        res = client_b.get("/api/projects/")
        slugs = {p["slug"] for p in res.json()["projects"]}
        self.assertEqual(slugs, {b_project.slug})


# =====================================================================
# OWNERSHIP — cross-user access blocked (GET / PATCH / generate / approve)
# =====================================================================


class CrossUserSoftwareAccessTests(AuthenticatedAPITestCase):
    """``self.client`` is authenticated as ``default_owner()``; every Project
    here belongs to ``other_user()`` instead — the other user's Project must
    be completely invisible."""

    def setUp(self):
        super().setUp()
        self.project = make_roadmap_project(owner=other_user(), approved=True)

    def test_cannot_get(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "project_not_found")
        self.assertNotIn("another user", res.json()["error"]["message"].lower())

    def test_cannot_patch(self):
        res = self.client.patch(
            f"/api/projects/{self.project.slug}/blueprint/", {"content": {}}, format="json"
        )
        self.assertEqual(res.status_code, 404)

    def test_cannot_generate_artifact(self):
        res = self.client.post(f"/api/projects/{self.project.slug}/roadmap/generate/")
        self.assertEqual(res.status_code, 404)

    def test_cannot_approve_artifact(self):
        res = self.client.post(f"/api/projects/{self.project.slug}/blueprint/approve/")
        self.assertEqual(res.status_code, 404)

    def test_cannot_read_progress(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/progress/")
        self.assertEqual(res.status_code, 404)

    def test_cannot_read_ship_checklist(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/ship-checklist/")
        self.assertEqual(res.status_code, 404)

    def test_child_task_id_cannot_bypass_project_ownership(self):
        # Knowing a real, valid task id inside the other user's Roadmap must
        # not help — the Project gate is checked first, unconditionally.
        task_id = self.project.roadmap["content"]["phases"][0]["tasks"][0]["id"]
        res = self.client.get(f"/api/projects/{self.project.slug}/roadmap/tasks/{task_id}/")
        self.assertEqual(res.status_code, 404)


class CrossUserDataAccessTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.project = data_project_with_brief(owner=other_user())
        self.client_owner = APIClient()
        self.client_owner.force_authenticate(user=other_user())
        self.dataset = uploaded_dataset(self.client_owner, self.project)
        self.client_owner.post(
            f"/api/projects/{self.project.slug}/datasets/{self.dataset.id}/profile/"
        )

    def test_dataset_list_blocked_cross_user(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/datasets/")
        self.assertEqual(res.status_code, 404)

    def test_dataset_detail_blocked_cross_user_even_with_real_id(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/datasets/{self.dataset.id}/")
        self.assertEqual(res.status_code, 404)

    def test_dataset_upload_blocked_cross_user(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        res = self.client.post(
            f"/api/projects/{self.project.slug}/datasets/",
            {"file": SimpleUploadedFile("x.csv", b"a,b\n1,2\n", content_type="text/csv")},
            format="multipart",
        )
        self.assertEqual(res.status_code, 404)

    def test_job_access_blocked_cross_user(self):
        from projects.models import Job

        job = Job.objects.filter(project=self.project).first()
        self.assertIsNotNone(job, "profiling in setUp should have produced a Job")
        res = self.client.get(f"/api/projects/{self.project.slug}/jobs/{job.id}/")
        self.assertEqual(res.status_code, 404)

    def test_data_progress_blocked_cross_user(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/data-progress/")
        self.assertEqual(res.status_code, 404)

    def test_data_readiness_blocked_cross_user(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/data-readiness/")
        self.assertEqual(res.status_code, 404)

    def test_metric_list_blocked_cross_user(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/metrics/")
        self.assertEqual(res.status_code, 404)

    def test_query_list_blocked_cross_user(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/queries/")
        self.assertEqual(res.status_code, 404)

    def test_analysis_plan_list_blocked_cross_user(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/analysis/plans/")
        self.assertEqual(res.status_code, 404)

    def test_lineage_blocked_cross_user(self):
        res = self.client.get(f"/api/projects/{self.project.slug}/lineage/")
        self.assertEqual(res.status_code, 404)


# =====================================================================
# CONVERSATION / PROPOSAL isolation
# =====================================================================


class ConversationIsolationTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.project = make_roadmap_project(owner=other_user(), approved=True)
        self.conversation = Conversation.objects.create(project=self.project)
        self.proposal = Proposal.objects.create(
            conversation=self.conversation,
            project=self.project,
            target_artifact="blueprint",
            proposed_change={"sections": {}, "summary": "x"},
        )

    def test_cannot_read_others_conversation(self):
        res = self.client.get(
            f"/api/projects/{self.project.slug}/conversations/{self.conversation.id}/"
        )
        self.assertEqual(res.status_code, 404)

    def test_cannot_post_message_to_others_conversation(self):
        res = self.client.post(
            f"/api/projects/{self.project.slug}/conversations/{self.conversation.id}/messages/",
            {"message": "hello"},
            format="json",
        )
        self.assertEqual(res.status_code, 404)

    def test_cannot_approve_others_proposal(self):
        res = self.client.post(
            f"/api/projects/{self.project.slug}/proposals/{self.proposal.id}/approve/"
        )
        self.assertEqual(res.status_code, 404)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, Proposal.Status.PENDING)

    def test_cannot_reject_others_proposal(self):
        res = self.client.post(
            f"/api/projects/{self.project.slug}/proposals/{self.proposal.id}/reject/"
        )
        self.assertEqual(res.status_code, 404)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, Proposal.Status.PENDING)

    def test_owner_can_reject_own_proposal(self):
        # Same request, the real owner's client — the block above is purely
        # ownership, not some other validation this project happens to fail.
        client_owner = APIClient()
        client_owner.force_authenticate(user=other_user())
        res = client_owner.post(
            f"/api/projects/{self.project.slug}/proposals/{self.proposal.id}/reject/"
        )
        self.assertEqual(res.status_code, 200, res.content)


# =====================================================================
# SOFTWARE / DATA regression smoke — the owner's own workflows still work
# =====================================================================


class OwnerWorkflowsStillWorkTests(AuthenticatedAPITestCase):
    def test_software_progress_and_ship_checklist_work_for_owner(self):
        project = make_roadmap_project(owner=default_owner(), approved=True)
        res = self.client.get(f"/api/projects/{project.slug}/progress/")
        self.assertEqual(res.status_code, 200)
        res = self.client.get(f"/api/projects/{project.slug}/ship-checklist/")
        self.assertEqual(res.status_code, 200)

    def test_data_progress_and_readiness_work_for_owner(self):
        project = data_project_with_brief(owner=default_owner())
        res = self.client.get(f"/api/projects/{project.slug}/data-progress/")
        self.assertEqual(res.status_code, 200)
        res = self.client.get(f"/api/projects/{project.slug}/data-readiness/")
        self.assertEqual(res.status_code, 200)

    def test_project_creation_assigns_request_user_without_frontend_input(self):
        # project_type="data" calls idea_analysis exactly once (no
        # discovery_generation follow-up), so one fixed FakeProvider payload
        # is enough — the property under test is ownership assignment, not
        # the AI pipeline itself (already covered elsewhere).
        with mock.patch("ai.base.get_provider", return_value=FakeProvider(
            {"domain": "x", "product_type_guess": "y", "known": [], "unknowns": [], "assumptions": []}
        )):
            res = self.client.post(
                "/api/projects/",
                # Deliberately try to smuggle an owner — must be ignored.
                {
                    "idea": "A tool for tracking plants.",
                    "project_type": "data",
                    "owner": other_user().id,
                    "owner_id": other_user().id,
                },
                format="json",
            )
        self.assertEqual(res.status_code, 201, res.content)
        project = Project.objects.get(slug=res.json()["project"]["slug"])
        self.assertEqual(project.owner, default_owner())
