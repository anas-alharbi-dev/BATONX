"""
Phase P-2 — a thin ``SessionAuthentication`` subclass that returns a proper
401 for an unauthenticated request instead of DRF's default 403.

DRF's own ``SessionAuthentication`` deliberately omits ``authenticate_header``
(it isn't a challenge-based scheme like Basic/Token auth), which makes
``IsAuthenticated`` raise ``PermissionDenied`` (403) rather than
``NotAuthenticated`` (401) whenever no authenticator on the request supplies
one — see DRF's ``exceptions.NotAuthenticated`` vs ``PermissionDenied``
selection in ``APIView.permission_denied``. For BATONX, "you're not signed
in" (401 — the frontend auth provider redirects to /login) and "you're
signed in but not allowed" (403) are meaningfully different signals, so this
class supplies a header value purely to make DRF choose 401.
"""
from rest_framework.authentication import SessionAuthentication


class BatonxSessionAuthentication(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"
