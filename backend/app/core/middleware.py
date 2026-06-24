"""Request ID middleware — adds a unique request ID to every request.

The request ID is injected into structlog context vars so all logs
from a single request carry the same trace identifier.
"""

import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that assigns a unique request ID per request.

    Set via ``X-Request-ID`` header if the client provides one;
    otherwise generates a UUID4.  The ID is bound to structlog
    context vars so that all log entries during the request include it.
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(self._header_name, str(uuid.uuid4()))

        # Bind to structlog context for the duration of this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)

        # Echo the request ID back in the response header
        response.headers[self._header_name] = request_id
        return response
