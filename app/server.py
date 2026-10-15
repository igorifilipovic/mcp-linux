from __future__ import annotations

import hmac
from typing import Callable

import uvicorn
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import MCP_BEARER_TOKEN_FILE, MCP_PORT, TLS_CERT_FILE, TLS_KEY_FILE, read_secret
from .tools import mcp


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "ito-linux-monitor-mcp", "version": "2.0.0"})


class BearerTokenMiddleware:
    """Raw ASGI middleware so Streamable HTTP/SSE bodies are not buffered."""

    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self.token = token

    @staticmethod
    def _header(scope: Scope, name: bytes) -> str:
        for key, value in scope.get("headers", []):
            if key.lower() == name:
                return value.decode("latin-1")
        return ""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Health is deliberately non-sensitive and is used by Docker healthcheck.
        if scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return

        authorization = self._header(scope, b"authorization")
        expected = f"Bearer {self.token}"

        if not authorization or not hmac.compare_digest(authorization, expected):
            response = JSONResponse(
                {"error": "unauthorized", "detail": "Valid Bearer token required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


TOKEN = read_secret(MCP_BEARER_TOKEN_FILE)
if len(TOKEN) < 32:
    raise RuntimeError("Bearer token must contain at least 32 characters")

inner_app = mcp.streamable_http_app(streamable_http_path="/mcp", host="0.0.0.0")
inner_app.router.routes.append(Route("/health", health, methods=["GET"]))
app = BearerTokenMiddleware(inner_app, TOKEN)


def main() -> None:
    if not TLS_CERT_FILE.exists():
        raise RuntimeError(f"TLS certificate not found: {TLS_CERT_FILE}")
    if not TLS_KEY_FILE.exists():
        raise RuntimeError(f"TLS private key not found: {TLS_KEY_FILE}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=MCP_PORT,
        ssl_certfile=str(TLS_CERT_FILE),
        ssl_keyfile=str(TLS_KEY_FILE),
        log_level="info",
        server_header=False,
    )


if __name__ == "__main__":
    main()
