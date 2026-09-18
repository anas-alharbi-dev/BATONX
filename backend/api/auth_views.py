"""
Auth surface (Phase P-2) — Sign Up / Login / Logout / current-user.

First-party only: Django's own ``auth.User`` + session framework + DRF's
``SessionAuthentication``. No JWT, no third-party identity SaaS, no new
dependency — see the P-2 report for why this fits BATONX's local-first,
"keep it simple" mandate better than the alternatives.

Login identity: the user-facing identity is email; Django's own User model
keeps its stock ``username`` field (no custom user model — avoids a risky
auth rewrite), and every account's ``username`` is simply set to its
(lowercased) email at signup time. The API and every frontend surface only
ever say "email" — ``username`` is an internal storage detail nobody sees.
"""
from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.exceptions import ProjectWorkflowError

User = get_user_model()


def _serialize_me(user) -> dict:
    """Only user-facing fields — never password/session internals. ``plan``
    is a fixed literal, not a stored field: every account is Free today (see
    the P-2 report's Free Account Foundation section) and a real entitlement
    system can attach a real field later without shape-breaking this."""
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.first_name or None,
        "plan": "free",
    }


def _normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = _normalize_email(request.data.get("email"))
        password = request.data.get("password") or ""
        confirm_password = request.data.get("confirm_password") or ""
        display_name = (request.data.get("display_name") or "").strip()

        if not email:
            raise ProjectWorkflowError("email_required", "Enter an email address.", status.HTTP_400_BAD_REQUEST)
        try:
            validate_email(email)
        except DjangoValidationError:
            raise ProjectWorkflowError("invalid_email", "Enter a valid email address.", status.HTTP_400_BAD_REQUEST)
        if len(email) > 150:
            # Django's stock username column caps at 150 chars; we reuse it
            # to store the email (see module docstring) rather than adding a
            # custom user model for this edge case.
            raise ProjectWorkflowError("invalid_email", "That email address is too long.", status.HTTP_400_BAD_REQUEST)

        if not password:
            raise ProjectWorkflowError("password_required", "Choose a password.", status.HTTP_400_BAD_REQUEST)
        if password != confirm_password:
            raise ProjectWorkflowError(
                "password_mismatch", "Passwords do not match.", status.HTTP_400_BAD_REQUEST
            )
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise ProjectWorkflowError(
                "weak_password", " ".join(exc.messages), status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(username=email).exists():
            raise ProjectWorkflowError(
                "email_taken", "An account with that email already exists.", status.HTTP_409_CONFLICT
            )

        user = User.objects.create_user(
            username=email, email=email, password=password, first_name=display_name
        )
        login(request, user)
        return Response(_serialize_me(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = _normalize_email(request.data.get("email"))
        password = request.data.get("password") or ""
        if not email or not password:
            raise ProjectWorkflowError(
                "invalid_credentials", "Enter your email and password.", status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(request, username=email, password=password)
        if user is None or not user.is_active:
            raise ProjectWorkflowError(
                "invalid_credentials", "Incorrect email or password.", status.HTTP_401_UNAUTHORIZED
            )

        login(request, user)
        return Response(_serialize_me(user), status=status.HTTP_200_OK)


class LogoutView(APIView):
    # Logging out an already-anonymous session is a harmless no-op, not an
    # error the frontend needs to special-case — allow it unconditionally.
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)  # flushes the session server-side; not just a client-side clear
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(APIView):
    """
    IsAuthenticated (the DRF-wide default — see settings.REST_FRAMEWORK) is
    exactly the behavior wanted here: an unauthenticated call correctly 401s
    rather than returning a fabricated "no user" body, so the frontend auth
    provider can tell "still loading" apart from "confirmed signed out."
    ``ensure_csrf_cookie`` primes the CSRF cookie on every call (even a 401)
    so the very first page load already has what's needed for the next
    unsafe request (login/signup).
    """

    def get(self, request):
        return Response(_serialize_me(request.user))
