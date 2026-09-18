"""
Uniform API error envelope.

Every handled error response has the shape:

    {"error": {"code": str, "message": str, "retryable": bool, "details": any}}

AI failures map to HTTP 502 with ``retryable: true`` so the frontend can offer a
Retry action. DRF validation / not-found / etc. keep their status code but are
reshaped into the same envelope.
"""
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from ai.exceptions import AIOperationError
from projects.exceptions import ProjectWorkflowError


def envelope_exception_handler(exc, context):
    if isinstance(exc, AIOperationError):
        return Response(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                    "details": exc.details,
                }
            },
            status=502,
        )

    if isinstance(exc, ProjectWorkflowError):
        return Response(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": False,
                    "details": exc.details,
                }
            },
            status=exc.status,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        # Not a DRF-known exception; the ApiJsonErrorMiddleware will turn it into
        # a 500 envelope.
        return None

    detail = response.data
    code = "request_error"
    message = "The request could not be processed."
    if isinstance(detail, dict) and "detail" in detail:
        message = str(detail["detail"])
        code = getattr(detail["detail"], "code", code)
    elif isinstance(detail, list) and detail:
        message = str(detail[0])

    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": False,
                "details": detail,
            }
        },
        status=response.status_code,
    )
