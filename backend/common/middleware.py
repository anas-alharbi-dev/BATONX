"""Catch unhandled exceptions on /api/ routes and return a JSON envelope.

This guarantees the frontend never receives an HTML stack trace from the API,
even in DEBUG mode.
"""
import logging

from django.http import JsonResponse

logger = logging.getLogger("vyra.api")


class ApiJsonErrorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not request.path.startswith("/api/"):
            return None
        logger.exception("Unhandled API exception: %s", exception)
        return JsonResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong on the server.",
                    "retryable": True,
                }
            },
            status=500,
        )
