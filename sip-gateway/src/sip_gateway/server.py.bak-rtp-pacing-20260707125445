"""Async UDP SIP server."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import zlib
from collections import defaultdict, deque

from sip_gateway.backend import BackendClient, BackendRequestError
from sip_gateway.config import GatewaySettings
from sip_gateway.rtp import RTPPortPool
from sip_gateway.sdp import build_sdp_answer, parse_sdp_offer
from sip_gateway.session import GatewayCallSession
from sip_gateway.sip import SipMessage, build_response

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Simple per-IP sliding-window limiter."""

    def __init__(self, limit_per_minute: int) -> None:
        self.limit = limit_per_minute
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """Return whether one event is allowed."""
        now = time.monotonic()
        events = self._events[key]
        while events and now - events[0] > 60:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        return True


class SipProtocol(asyncio.DatagramProtocol):
    """Datagram protocol wrapper that delegates SIP messages to gateway."""

    def __init__(self, gateway: SipGateway) -> None:
        self.gateway = gateway

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Store UDP transport."""
        self.gateway.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Dispatch datagram asynchronously."""
        task = asyncio.create_task(self.gateway.handle_datagram(data, addr))
        self.gateway.track_task(task)


class SipGateway:
    """Main SIP gateway service."""

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings
        self.backend = BackendClient(settings)
        self.port_pool = RTPPortPool(settings.rtp_port_min, settings.rtp_port_max)
        self.rate_limiter = SlidingWindowRateLimiter(
            settings.invite_rate_limit_per_minute
        )
        self.transport: asyncio.DatagramTransport | None = None
        self.calls_by_id: dict[str, GatewayCallSession] = {}
        self.calls_by_branch: dict[str, GatewayCallSession] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._stopped = asyncio.Event()
        self._health_server: asyncio.Server | None = None
        self.invite_failures = 0
        self.provider_errors = 0

    def track_task(self, task: asyncio.Task[None]) -> None:
        """Keep background datagram tasks referenced until done."""
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def serve_forever(self) -> None:
        """Bind SIP UDP socket and serve forever."""
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(
            lambda: SipProtocol(self),
            local_addr=(self.settings.sip_bind_host, self.settings.sip_port),
        )
        self._health_server = await asyncio.start_server(
            self._handle_health_http,
            host=self.settings.health_bind_host,
            port=self.settings.health_port,
        )
        logger.info(
            "sip_gateway_started",
            extra={
                "sip_bind_host": self.settings.sip_bind_host,
                "sip_port": self.settings.sip_port,
                "rtp_port_min": self.settings.rtp_port_min,
                "rtp_port_max": self.settings.rtp_port_max,
                "health_port": self.settings.health_port,
            },
        )
        await self._stopped.wait()

    async def shutdown(self) -> None:
        """Close all calls and SIP transport."""
        for call in list(self.calls_by_id.values()):
            await call.close("gateway_shutdown")
        if self.transport is not None:
            self.transport.close()
        if self._health_server is not None:
            self._health_server.close()
            await self._health_server.wait_closed()
        self._stopped.set()

    def metrics_snapshot(self) -> dict[str, object]:
        """Return current health and observability counters."""
        active_calls = [
            call for call in self.calls_by_id.values() if not call._closed.is_set()
        ]
        tts_latencies = [
            call.stats.tts_latency_ms
            for call in active_calls
            if call.stats.tts_latency_ms is not None
        ]
        first_audio_latencies = [
            call.stats.first_audio_latency_ms
            for call in active_calls
            if call.stats.first_audio_latency_ms is not None
        ]
        return {
            "ok": True,
            "active_calls": len(active_calls),
            "rtp_active": sum(call.rtp_transport is not None for call in active_calls),
            "sessions_orphaned": sum(
                call.context is None or call.rtp_transport is None
                for call in active_calls
            ),
            "max_concurrent_calls": self.settings.max_concurrent_calls,
            "rtp_ports_available": self.port_pool.available_count,
            "rtp_port_min": self.settings.rtp_port_min,
            "rtp_port_max": self.settings.rtp_port_max,
            "tts_latency_ms_latest": tts_latencies[-1] if tts_latencies else None,
            "first_audio_latency_ms_latest": (
                first_audio_latencies[-1] if first_audio_latencies else None
            ),
            "invite_failures": self.invite_failures,
            "provider_errors": self.provider_errors,
            "sip_port": self.settings.sip_port,
            "health_port": self.settings.health_port,
        }

    async def _handle_health_http(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Serve tiny HTTP health/metrics responses without extra dependencies."""
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=2)
            parts = request_line.decode("latin-1", errors="ignore").split()
            path = parts[1] if len(parts) >= 2 else "/"
            while True:
                line = await reader.readline()
                if line in {b"\r\n", b"\n", b""}:
                    break
            if path in {"/health/live", "/health/ready", "/metrics"}:
                body = json.dumps(self.metrics_snapshot(), separators=(",", ":"))
                status = "200 OK"
            else:
                body = json.dumps({"ok": False, "error": "not_found"})
                status = "404 Not Found"
            payload = body.encode("utf-8")
            writer.write(
                (
                    f"HTTP/1.1 {status}\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(payload)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ).encode("ascii")
                + payload
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        """Parse and route one SIP UDP datagram."""
        ip = addr[0]
        if self.settings.allowed_ip_set and ip not in self.settings.allowed_ip_set:
            logger.warning("sip_rejected_ip", extra={"source_ip": ip})
            return
        if not self.rate_limiter.allow(ip):
            logger.warning("sip_rate_limited", extra={"source_ip": ip})
            return
        try:
            message = SipMessage.parse(data)
        except ValueError:
            logger.warning("sip_parse_failed", extra={"source_ip": ip})
            return
        if not message.is_request:
            return
        method = message.method
        if method == "INVITE":
            await self._handle_invite(message, addr)
        elif method == "ACK":
            await self._handle_ack(message)
        elif method in {"BYE", "CANCEL"}:
            await self._handle_teardown(message, method, addr)
        elif method == "OPTIONS":
            self._send(message, 200, "OK", addr, extra_headers={"Allow": self._allow()})
        else:
            self._send(message, 405, "Method Not Allowed", addr)

    async def _handle_invite(
        self,
        message: SipMessage,
        addr: tuple[str, int],
    ) -> None:
        self._send(message, 100, "Trying", addr)
        if len(self.calls_by_id) >= self.settings.max_concurrent_calls:
            self._send(message, 486, "Busy Here", addr)
            return
        try:
            offer = parse_sdp_offer(message.body)
            payload_type = offer.choose_payload(self.settings.telephony_codec)
            rtp_port = self.port_pool.lease()
            call = GatewayCallSession(
                settings=self.settings,
                backend=self.backend,
                port_pool=self.port_pool,
                invite=message,
                sip_addr=addr,
                offer=offer,
                payload_type=payload_type,
                rtp_port=rtp_port,
            )
            await call.prepare()
        except BackendRequestError as exc:
            self.invite_failures += 1
            self.provider_errors += 1
            logger.warning(
                "sip_invite_backend_context_failed",
                extra={
                    "call_id": message.call_id,
                    "caller": message.caller,
                    "callee": message.callee,
                    "sip_to": message.header("to") or message.header("t"),
                    "sip_from": message.header("from") or message.header("f"),
                    "backend_endpoint": exc.endpoint,
                    "backend_status_code": exc.status_code,
                    "backend_detail": exc.detail,
                },
            )
            self._send(message, 488, "Not Acceptable Here", addr)
            return
        except Exception:
            self.invite_failures += 1
            self.provider_errors += 1
            logger.exception(
                "sip_invite_failed",
                extra={
                    "call_id": message.call_id,
                    "caller": message.caller,
                    "callee": message.callee,
                    "sip_to": message.header("to") or message.header("t"),
                },
            )
            self._send(message, 488, "Not Acceptable Here", addr)
            return
        self.calls_by_id[call.call_id] = call
        if message.branch:
            self.calls_by_branch[message.branch] = call
        self._send(message, 180, "Ringing", addr, to_tag=call.local_tag)
        sdp_answer = build_sdp_answer(
            ip=self.settings.advertised_rtp_ip,
            port=call.rtp_port,
            payload_type=payload_type,
            session_id=zlib.crc32(call.call_id.encode("utf-8")),
        )
        self._send(
            message,
            200,
            "OK",
            addr,
            body=sdp_answer,
            to_tag=call.local_tag,
            contact=f"<sip:bot@{self.settings.advertised_sip_host or addr[0]}:"
            f"{self.settings.sip_port}>",
        )

    async def _handle_ack(self, message: SipMessage) -> None:
        call = self.calls_by_id.get(message.call_id)
        if call is None:
            return
        try:
            await call.start_media()
        except Exception:
            logger.exception("sip_ack_media_failed", extra={"call_id": call.call_id})
            await self._remove_call(call, "media_start_failed")

    async def _handle_teardown(
        self,
        message: SipMessage,
        method: str,
        addr: tuple[str, int],
    ) -> None:
        call = self.calls_by_id.get(message.call_id)
        if call is not None:
            await self._remove_call(call, method.lower())
        self._send(message, 200, "OK", addr)

    async def _remove_call(self, call: GatewayCallSession, reason: str) -> None:
        self.calls_by_id.pop(call.call_id, None)
        if call.invite.branch:
            self.calls_by_branch.pop(call.invite.branch, None)
        await call.close(reason)

    def _send(
        self,
        request: SipMessage,
        status_code: int,
        reason: str,
        addr: tuple[str, int],
        *,
        body: str = "",
        to_tag: str | None = None,
        contact: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if self.transport is None or addr[1] == 0:
            return
        response = build_response(
            request,
            status_code,
            reason,
            body=body,
            to_tag=to_tag,
            contact=contact,
            extra_headers=extra_headers,
        )
        self.transport.sendto(response, addr)

    @staticmethod
    def _allow() -> str:
        return "INVITE, ACK, BYE, CANCEL, OPTIONS"
