"""Small in-process fixed-window limiter for public MVP endpoints."""

from __future__ import annotations

import asyncio
import ipaddress
import time
from collections import OrderedDict
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import Settings


@dataclass(slots=True)
class RateBucket:
    """Counter for one client and one public route."""

    window_started_at: float
    count: int


class PublicRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply basic abuse protection to unauthenticated routes."""

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._settings = settings
        self._buckets: OrderedDict[tuple[str, str], RateBucket] = OrderedDict()
        self._lock = asyncio.Lock()
        self._trusted_proxies = tuple(
            ipaddress.ip_network(item.strip(), strict=False)
            for item in settings.trusted_proxy_ips.split(",")
            if item.strip()
        )

    def _client_ip(self, request: Request) -> str:
        """Use forwarded IP only when the direct peer is an approved proxy."""
        direct = request.client.host if request.client is not None else "unknown"
        try:
            direct_address = ipaddress.ip_address(direct)
            trusted = any(direct_address in network for network in self._trusted_proxies)
        except ValueError:
            trusted = False
        forwarded = request.headers.get("x-forwarded-for")
        if trusted and forwarded:
            candidate = forwarded.split(",", maxsplit=1)[0].strip()
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                return direct
            return candidate
        return direct

    def _route_limit(self, path: str) -> int | None:
        """Return a limit only for public mutable/integration routes."""
        if path == "/webhooks/openai/realtime":
            return self._settings.webhook_rate_limit_per_minute
        if path in {"/auth/login", "/auth/register", "/auth/forgot-password", "/auth/resend-verification", "/auth/reset-password"}:
            return min(20, self._settings.public_rate_limit_per_minute)
        if path == "/api/webhooks/stripe":
            return self._settings.webhook_rate_limit_per_minute
        if path.startswith("/auth/google/"):
            return self._settings.public_rate_limit_per_minute
        if path == "/api/billing/checkout":
            return min(20, self._settings.public_rate_limit_per_minute)
        return None

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Reject requests over the current one-minute bucket."""
        limit = self._route_limit(request.url.path)
        if limit is None:
            return await call_next(request)

        now = time.monotonic()
        key = (self._client_ip(request), request.url.path)
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or now - bucket.window_started_at >= 60:
                bucket = RateBucket(window_started_at=now, count=0)
                self._buckets[key] = bucket
            self._buckets.move_to_end(key)
            while len(self._buckets) > self._settings.rate_limit_max_buckets:
                self._buckets.popitem(last=False)
            bucket.count += 1
            if bucket.count > limit:
                retry_after = max(
                    1,
                    int(60 - (now - bucket.window_started_at)),
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded."},
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)
