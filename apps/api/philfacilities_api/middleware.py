from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .errors import ApiError

settings = get_settings()
access_logger = logging.getLogger("philfacilities.api.access")

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        candidate = request.headers.get("x-request-id", "")
        request.state.request_id = (
            candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else str(uuid.uuid4())
        )
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.1f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        access_logger.info(
            "request method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request.state.request_id,
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Small in-process fixed-window limiter. Replace with an edge limiter at scale."""

    MAX_TRACKED_CLIENTS = 20_000

    def __init__(self, app, limit: int) -> None:
        super().__init__(app)
        self.limit = limit
        self.windows: dict[str, deque[float]] = defaultdict(deque)

    def _evict_if_needed(self, now: float) -> None:
        if len(self.windows) <= self.MAX_TRACKED_CLIENTS:
            return
        stale = [key for key, window in self.windows.items() if not window or now - window[-1] > 60]
        for key in stale:
            del self.windows[key]
        while len(self.windows) > self.MAX_TRACKED_CLIENTS:
            self.windows.pop(next(iter(self.windows)))

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/healthz", "/openapi.json", "/docs", "/redoc"}:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        self._evict_if_needed(now)
        window = self.windows[client]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.limit:
            request_id = getattr(request.state, "request_id", "unknown")
            return JSONResponse(
                status_code=429,
                content={
                    "code": "rate_limit_exceeded",
                    "message": "Too many requests. Retry after the current window.",
                    "details": {"limit": self.limit, "window_seconds": 60},
                    "request_id": request_id,
                },
                headers={"Retry-After": "60"},
            )
        window.append(now)
        return await call_next(request)


def install_error_handlers(app: FastAPI) -> None:
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "One or more query parameters are invalid.",
                "details": exc.errors(),
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        code = {
            404: "not_found",
            405: "method_not_allowed",
        }.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": code,
                "message": str(exc.detail),
                "details": None,
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "details": None,
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )


def conditional_json(request: Request, payload, max_age: int = 60):
    """Return a JSON response with an ETag and optional 304 when unchanged."""
    body = json.dumps(payload, default=str, separators=(",", ":"), sort_keys=True).encode()
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": f"public, max-age={max_age}"}
    if request.headers.get("if-none-match") == etag:
        # State the empty body explicitly. Without a framing header some HTTP
        # clients keep the connection in a state where the next streaming
        # response (for example a bulk CSV download) is read as a continuation.
        return Response(
            status_code=304,
            content=b"",
            headers={**headers, "Content-Length": "0"},
        )
    return JSONResponse(content=json.loads(body), headers=headers)
