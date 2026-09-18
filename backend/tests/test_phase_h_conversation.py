"""
Phase H verification — the Conversational Layer.

The conversation reads / explains / proposes; it never mutates authoritative
project state. Only an explicitly approved Proposal applies a change, and only
through the existing domain services. The live conversation_response round trip
is PENDING an ANTHROPIC_API_KEY; every AI-touching test uses a fake provider.
"""
import unittest.mock as mock

from tests.base import AuthenticatedAPITestCase

from ai.models import AIRequestLog
from ai.operations.conversation_response import (
    CONVERSATION_RESPONSE,
    ConversationTurn,
)
from ai.providers.base import StructuredResult
from projects.conversation_context import build_conversation_context
from projects.models import (
    Conversation,
    ConversationMessage,
    GeneratedPrompt,
    Project,
    ProjectStage,
    Proposal,
)
from tests.test_phase3 import make_approved_blueprint_project
from tests.test_phase4 import APPROVED_DT, NOW, make_roadmap_project
from tests.test_phase_d_business_logic import bl_content


class FakeProvider:
    name = "fake"

    def __init__(self, payload):
        self.payload = payload
        self.last_user = None
        self.last_system = None
        self.calls = 0

    def ensure_ready(self):
        pass

    def generate_structured(self, *, system, user, json_schema, timeout, prior_attempt=None):
        self.calls += 1
        self.last_user = user
        self.last_system = system
        return StructuredResult(
            data=self.payload, provider=self.name, model="fake-1",
            input_tokens=1, output_tokens=1,
        )


INFO_TURN = {
    "response": "This project is a produce marketplace connecting restaurants and suppliers.",
    "intent": "informational",
    "referenced_artifacts": ["blueprint", "idea"],
    "proposed_change": None,
}

LIE_TURN = {
    "response": "Done — I have updated the Blueprint and approved it.",
    "intent": "informational",
    "referenced_artifacts": ["blueprint"],
    "proposed_change": None,
}


def blueprint_proposal_turn(sections):
    return {
        "response": "I can propose that change to the Blueprint for your review.",
        "intent": "proposal",
        "referenced_artifacts": ["blueprint"],
        "proposed_change": {
            "target_artifact": "blueprint",
            "summary": "Add a refund-approval business rule",
            "rationale": "The user wants refunds gated on a manager.",
            "sections": sections,
        },
    }


def bl_proposal_turn(sections):
    return {
        "response": "Here is a proposed Business Logic change for your review.",
        "intent": "proposal",
        "referenced_artifacts": ["business_logic"],
        "proposed_change": {
            "target_artifact": "business_logic",
            "summary": "Record an open question about order caps",
            "rationale": "The user raised a policy gap.",
            "sections": sections,
        },
    }


def make_conversation(project):
    return Conversation.objects.create(project=project)


def bl_stage_project_with_downstream():
    """
    Approved blueprint + business_logic + architecture + roadmap, but stage
    forced back to BUSINESS_LOGIC so a BL proposal can be applied and its
    downstream stale propagation observed. (Artificial: real stage locks prevent
    this, but it exercises mark_downstream_stale end to end.)
    """
    project = make_roadmap_project(approved=True)  # bp+arch+roadmap approved
    project.business_logic = {
        "content": bl_content(), "generated_at": NOW, "updated_at": NOW,
        "approved_at": NOW,
    }
    project.business_logic_approved_at = APPROVED_DT
    project.stage = ProjectStage.BUSINESS_LOGIC
    project.save(update_fields=["business_logic", "business_logic_approved_at", "stage"])
    return project


# --- schema -------------------------------------------------------------


class ConversationSchemaTests(AuthenticatedAPITestCase):
    def test_proposal_without_change_downgrades_to_informational(self):
        turn = ConversationTurn.model_validate(
            {"response": "x", "intent": "proposal", "proposed_change": None}
        )
        self.assertEqual(turn.intent, "informational")
        self.assertIsNone(turn.proposed_change)

    def test_informational_drops_any_change(self):
        turn = ConversationTurn.model_validate(
            {
                "response": "x",
                "intent": "informational",
                "proposed_change": {
                    "target_artifact": "blueprint",
                    "summary": "s",
                    "sections": {},
                },
            }
        )
        self.assertIsNone(turn.proposed_change)

    def test_operation_wiring(self):
        self.assertEqual(CONVERSATION_RESPONSE.name, "conversation_response")
        self.assertEqual(CONVERSATION_RESPONSE.prompt_version, "conversation/v1")


# --- conversation lifecycle + messaging -------------------------------


class ConversationLifecycleTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.project = make_approved_blueprint_project()

    def _url(self):
        return f"/api/projects/{self.project.slug}/conversations/"

    def test_create_and_read(self):
        res = self.client.post(self._url())
        self.assertEqual(res.status_code, 201)
        cid = res.json()["id"]
        got = self.client.get(f"{self._url()}{cid}/")
        self.assertEqual(got.status_code, 200)
        body = got.json()
        self.assertEqual(body["id"], cid)
        self.assertEqual(body["project"], self.project.slug)
        self.assertEqual(body["messages"], [])
        self.assertEqual(body["proposals"], [])

    def test_unknown_project_returns_404_envelope(self):
        res = self.client.post("/api/projects/nope/conversations/")
        self.assertEqual(res.status_code, 404)
        body = res.json()
        self.assertEqual(set(body.keys()), {"error"})
        self.assertEqual(body["error"]["code"], "project_not_found")

    def test_unknown_conversation_returns_404(self):
        import uuid

        res = self.client.get(f"{self._url()}{uuid.uuid4()}/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "conversation_not_found")

    def test_conversation_scoped_to_project(self):
        other = make_approved_blueprint_project()
        conv = make_conversation(self.project)
        res = self.client.get(
            f"/api/projects/{other.slug}/conversations/{conv.id}/"
        )
        self.assertEqual(res.status_code, 404)

    def test_message_persists_and_returns_assistant_reply(self):
        conv = make_conversation(self.project)
        fake = FakeProvider(INFO_TURN)
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                f"{self._url()}{conv.id}/messages/",
                {"content": "What is this project building?"},
                format="json",
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["message"]["role"], "assistant")
        self.assertIn("produce marketplace", body["message"]["content"])
        self.assertIsNone(body["proposal"])
        roles = list(conv.messages.values_list("role", flat=True))
        self.assertEqual(roles, ["user", "assistant"])

    def test_empty_message_rejected(self):
        conv = make_conversation(self.project)
        res = self.client.post(
            f"{self._url()}{conv.id}/messages/", {"content": "   "}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "empty_message")

    def test_missing_api_key_returns_502_and_no_assistant_message(self):
        conv = make_conversation(self.project)
        res = self.client.post(
            f"{self._url()}{conv.id}/messages/",
            {"content": "Why PostgreSQL?"},
            format="json",
        )
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "missing_api_key")
        # user message kept; no assistant turn, no proposal, no log row
        self.assertEqual(
            list(conv.messages.values_list("role", flat=True)), ["user"]
        )
        self.assertEqual(Proposal.objects.count(), 0)
        self.assertFalse(
            AIRequestLog.objects.filter(operation="conversation_response").exists()
        )

    def test_ai_lie_about_applying_change_does_not_mutate_project(self):
        conv = make_conversation(self.project)
        before = Project.objects.get(pk=self.project.pk)
        fake = FakeProvider(LIE_TURN)
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                f"{self._url()}{conv.id}/messages/",
                {"content": "Change the database to MySQL and approve it."},
                format="json",
            )
        after = Project.objects.get(pk=self.project.pk)
        self.assertEqual(after.blueprint, before.blueprint)
        self.assertEqual(after.architecture, before.architecture)
        self.assertEqual(after.stage, before.stage)
        self.assertEqual(Proposal.objects.count(), 0)

    def test_informational_turn_records_prompt_version(self):
        conv = make_conversation(self.project)
        fake = FakeProvider(INFO_TURN)
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                f"{self._url()}{conv.id}/messages/",
                {"content": "What are the requirements?"},
                format="json",
            )
        log = AIRequestLog.objects.filter(
            operation="conversation_response"
        ).latest("id")
        self.assertEqual(log.prompt_version, "conversation/v1")
        self.assertEqual(log.provider, "fake")
        msg = conv.messages.get(role="assistant")
        self.assertEqual(msg.metadata["prompt_version"], "conversation/v1")
        self.assertEqual(msg.metadata["intent"], "informational")


# --- project awareness / context ------------------------------------


class ConversationContextTests(AuthenticatedAPITestCase):
    def test_context_is_project_scoped_and_from_approved_state(self):
        project = make_roadmap_project(approved=True)
        ctx = build_conversation_context(project, "what tasks are blocked?")
        self.assertEqual(ctx["project"]["idea"], project.original_idea)
        self.assertIn("blueprint", ctx["slices"])
        self.assertIn("architecture", ctx["slices"])
        self.assertIn("roadmap", ctx["slices"])
        self.assertIn("progress", ctx["status"])
        self.assertIn("ship", ctx["status"])
        self.assertIn("roadmap", ctx["focus"])

    def test_unapproved_artifacts_are_absent(self):
        project = make_approved_blueprint_project()  # only blueprint approved
        ctx = build_conversation_context(project, "explain the architecture")
        self.assertIn("blueprint", ctx["slices"])
        self.assertNotIn("architecture", ctx["slices"])
        self.assertNotIn("roadmap", ctx["slices"])

    def test_relevant_context_reaches_the_prompt(self):
        project = make_roadmap_project(approved=True)
        conv = make_conversation(project)
        fake = FakeProvider(INFO_TURN)
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                f"/api/projects/{project.slug}/conversations/{conv.id}/messages/",
                {"content": "Why did we choose the database?"},
                format="json",
            )
        self.assertIn("PROJECT CONTEXT", fake.last_user)
        self.assertIn("[architecture]", fake.last_user)
        self.assertIn("PostgreSQL", fake.last_user)
        self.assertIn("project intelligence layer", fake.last_system)

    def test_history_is_bounded(self):
        project = make_approved_blueprint_project()
        conv = make_conversation(project)
        for i in range(12):
            ConversationMessage.objects.create(
                conversation=conv, role="user", content=f"OLD-MESSAGE-{i}"
            )
        fake = FakeProvider(INFO_TURN)
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                f"/api/projects/{project.slug}/conversations/{conv.id}/messages/",
                {"content": "latest question"},
                format="json",
            )
        # only the last 10 prior messages are sent (0 and 1 dropped)
        self.assertNotIn("OLD-MESSAGE-0\n", fake.last_user)
        self.assertNotIn("OLD-MESSAGE-1\n", fake.last_user)
        self.assertIn("OLD-MESSAGE-2\n", fake.last_user)
        self.assertIn("OLD-MESSAGE-11\n", fake.last_user)
        self.assertEqual(fake.last_user.count("OLD-MESSAGE-"), 10)

    def test_conversation_summary_is_not_project_memory(self):
        project = make_approved_blueprint_project()
        conv = make_conversation(project)
        digest_before = Project.objects.get(pk=project.pk).context_digest
        fake = FakeProvider(INFO_TURN)
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                f"/api/projects/{project.slug}/conversations/{conv.id}/messages/",
                {"content": "summarise the project"},
                format="json",
            )
        conv.refresh_from_db()
        self.assertEqual(conv.summary, "")  # not populated in Phase H
        self.assertEqual(
            Project.objects.get(pk=project.pk).context_digest, digest_before
        )


# --- proposals: creation, approval, rejection -----------------------


class ProposalFlowTests(AuthenticatedAPITestCase):
    def _msg_url(self, project, conv):
        return f"/api/projects/{project.slug}/conversations/{conv.id}/messages/"

    def test_proposal_intent_creates_pending_proposal_only(self):
        project = make_approved_blueprint_project()
        conv = make_conversation(project)
        before = Project.objects.get(pk=project.pk).blueprint
        fake = FakeProvider(
            blueprint_proposal_turn(
                {"business_rules": ["Pricing is private.", "Refunds need a manager."]}
            )
        )
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                self._msg_url(project, conv),
                {"content": "Refunds should need manager approval."},
                format="json",
            )
        self.assertEqual(res.status_code, 200)
        proposal = res.json()["proposal"]
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(proposal["target_artifact"], "blueprint")
        self.assertIn("downstream_review_candidates", proposal["impact_summary"])
        self.assertEqual(Proposal.objects.get().status, "pending")
        # nothing applied
        self.assertEqual(Project.objects.get(pk=project.pk).blueprint, before)

    def test_approve_blueprint_proposal_applies_through_domain_layer(self):
        project = make_approved_blueprint_project()
        conv = make_conversation(project)
        fake = FakeProvider(
            blueprint_proposal_turn(
                {"business_rules": ["Pricing is private.", "Refunds need a manager."]}
            )
        )
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                self._msg_url(project, conv),
                {"content": "Refunds need manager approval."},
                format="json",
            )
        proposal = Proposal.objects.get()
        res = self.client.post(
            f"/api/projects/{project.slug}/proposals/{proposal.id}/approve/"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["proposal"]["status"], "applied")
        self.assertIsNotNone(body["proposal"]["applied_at"])
        project.refresh_from_db()
        self.assertIn(
            "Refunds need a manager.",
            project.blueprint["content"]["business_rules"],
        )
        # applied through update_blueprint -> reverted to draft
        self.assertIsNone(project.blueprint_approved_at)

    def test_approve_business_logic_proposal_applies_and_marks_downstream_stale(self):
        project = bl_stage_project_with_downstream()
        prompt_count = GeneratedPrompt.objects.count()
        # a task in progress, to prove progress is preserved
        project.roadmap["content"]["phases"][0]["tasks"][0]["status"] = "in_progress"
        project.save(update_fields=["roadmap"])

        conv = make_conversation(project)
        fake = FakeProvider(
            bl_proposal_turn({"open_questions": ["Is there a maximum order value?", "Who owns disputes?"]})
        )
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                self._msg_url(project, conv),
                {"content": "Add an open question about order caps."},
                format="json",
            )
        proposal = Proposal.objects.get()
        res = self.client.post(
            f"/api/projects/{project.slug}/proposals/{proposal.id}/approve/"
        )
        self.assertEqual(res.status_code, 200)

        project.refresh_from_db()
        self.assertIn(
            "Who owns disputes?",
            project.business_logic["content"]["open_questions"],
        )
        # downstream marked stale, not deleted / not unapproved
        self.assertTrue(project.downstream_stale.get("architecture"))
        self.assertTrue(project.downstream_stale.get("roadmap"))
        self.assertIsNotNone(project.architecture_approved_at)
        self.assertIsNotNone(project.roadmap_approved_at)
        self.assertTrue(project.architecture["content"])
        self.assertTrue(project.roadmap["content"])
        # progress + prompt history preserved
        self.assertEqual(
            project.roadmap["content"]["phases"][0]["tasks"][0]["status"],
            "in_progress",
        )
        self.assertEqual(GeneratedPrompt.objects.count(), prompt_count)

    def test_invalid_proposed_change_rejected_by_existing_validator(self):
        project = make_approved_blueprint_project()
        conv = make_conversation(project)
        fake = FakeProvider(
            blueprint_proposal_turn({"totally_made_up_section": ["nope"]})
        )
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                self._msg_url(project, conv),
                {"content": "do a weird thing"},
                format="json",
            )
        proposal = Proposal.objects.get()
        res = self.client.post(
            f"/api/projects/{project.slug}/proposals/{proposal.id}/approve/"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_blueprint")
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "pending")  # not applied

    def test_reject_never_changes_project(self):
        project = make_approved_blueprint_project()
        conv = make_conversation(project)
        before = Project.objects.get(pk=project.pk).blueprint
        fake = FakeProvider(
            blueprint_proposal_turn({"business_rules": ["Pricing is private.", "X"]})
        )
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                self._msg_url(project, conv),
                {"content": "change a rule"},
                format="json",
            )
        proposal = Proposal.objects.get()
        res = self.client.post(
            f"/api/projects/{project.slug}/proposals/{proposal.id}/reject/"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["proposal"]["status"], "rejected")
        self.assertEqual(Project.objects.get(pk=project.pk).blueprint, before)

    def test_proposal_cannot_be_applied_twice(self):
        project = make_approved_blueprint_project()
        conv = make_conversation(project)
        fake = FakeProvider(
            blueprint_proposal_turn({"business_rules": ["Pricing is private.", "Y"]})
        )
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                self._msg_url(project, conv),
                {"content": "change"},
                format="json",
            )
        proposal = Proposal.objects.get()
        url = f"/api/projects/{project.slug}/proposals/{proposal.id}/approve/"
        self.assertEqual(self.client.post(url).status_code, 200)
        res2 = self.client.post(url)
        self.assertEqual(res2.status_code, 409)
        self.assertEqual(res2.json()["error"]["code"], "proposal_not_pending")

    def test_rejected_proposal_cannot_be_applied(self):
        project = make_approved_blueprint_project()
        conv = make_conversation(project)
        fake = FakeProvider(
            blueprint_proposal_turn({"business_rules": ["Pricing is private.", "Z"]})
        )
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                self._msg_url(project, conv), {"content": "c"}, format="json"
            )
        proposal = Proposal.objects.get()
        self.client.post(
            f"/api/projects/{project.slug}/proposals/{proposal.id}/reject/"
        )
        res = self.client.post(
            f"/api/projects/{project.slug}/proposals/{proposal.id}/approve/"
        )
        self.assertEqual(res.status_code, 409)

    def test_proposal_must_belong_to_project(self):
        project = make_approved_blueprint_project()
        other = make_approved_blueprint_project()
        conv = make_conversation(project)
        fake = FakeProvider(
            blueprint_proposal_turn({"business_rules": ["Pricing is private.", "Q"]})
        )
        with mock.patch("ai.base.get_provider", return_value=fake):
            self.client.post(
                self._msg_url(project, conv), {"content": "c"}, format="json"
            )
        proposal = Proposal.objects.get()
        res = self.client.post(
            f"/api/projects/{other.slug}/proposals/{proposal.id}/approve/"
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "proposal_not_found")

    def test_unsupported_target_rejected_on_approval(self):
        project = make_roadmap_project(approved=True)
        conv = make_conversation(project)
        proposal = Proposal.objects.create(
            conversation=conv,
            project=project,
            target_artifact="roadmap",  # not a supported target
            proposed_change={"sections": {}},
            status=Proposal.Status.PENDING,
        )
        res = self.client.post(
            f"/api/projects/{project.slug}/proposals/{proposal.id}/approve/"
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "unsupported_proposal_target")

    def test_ai_failure_persists_no_proposal(self):
        project = make_approved_blueprint_project()
        conv = make_conversation(project)
        fake = FakeProvider({"response": "", "intent": "informational"})  # invalid: response min_length 1
        with mock.patch("ai.base.get_provider", return_value=fake):
            res = self.client.post(
                self._msg_url(project, conv), {"content": "hi"}, format="json"
            )
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "ai_invalid_output")
        self.assertEqual(Proposal.objects.count(), 0)
        self.assertEqual(
            list(conv.messages.values_list("role", flat=True)), ["user"]
        )


# --- provider isolation --------------------------------------------


class ProviderIsolationTests(AuthenticatedAPITestCase):
    def test_operation_has_no_provider_specific_code(self):
        from pathlib import Path
        from ai.operations import conversation_response as op

        src = Path(op.__file__).read_text()
        for token in ("anthropic", "messages.create", "tool_use", "with_options"):
            self.assertNotIn(token, src)

    def test_services_have_no_provider_specific_code(self):
        from pathlib import Path
        from projects import conversation_services as svc

        src = Path(svc.__file__).read_text()
        for token in ("anthropic", "Anthropic", "messages.create"):
            self.assertNotIn(token, src)
