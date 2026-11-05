"""Bound request bodies even when Content-Length is absent (chunked uploads)."""
from fastapi import HTTPException


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes=6 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        consumed = 0

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_bytes:
                    raise HTTPException(413, "La solicitud excede el tamaño permitido.")
            return message

        await self.app(scope, limited_receive, send)
