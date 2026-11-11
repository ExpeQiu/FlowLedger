"""可选内网令牌：配置 INTERNAL_TOKEN / DATA_INTERNAL_TOKEN 后拒绝无令牌访问。"""

from __future__ import annotations

import logging
import os
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("flowledger.auth_internal")

PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


def _expected_token() -> str:
    return (
        (os.environ.get("INTERNAL_TOKEN") or "").strip()
        or (os.environ.get("DATA_INTERNAL_TOKEN") or "").strip()
    )


class InternalTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        token = _expected_token()
        if not token:
            return await call_next(request)

        path = request.url.path
        if path in PUBLIC_PATHS:
            return await call_next(request)

        provided = (request.headers.get("x-internal-token") or "").strip()
        if not provided:
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                provided = auth[7:].strip()
        if not provided:
            provided = (request.headers.get("x-api-token") or "").strip()

        if provided != token:
            logger.warning("auth_reject method=%s path=%s", request.method, path)
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)
