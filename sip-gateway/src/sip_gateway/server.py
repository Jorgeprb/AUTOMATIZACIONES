"""Async UDP SIP server."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
import zlib
from collections import defaultdict, deque

from sip_gateway.backend import BackendClient, BackendRequestError
from sip_gateway.config import GatewaySettings
from sip_gateway.rtp import RTPPortPool
from sip_gateway.sdp import build_sdp_answer, parse_sdp_offer
from sip_gateway.session import GatewayCallSession, select_called_number
from sip_gateway.sip import SipMessage, build_response

logger = logging.getLogger(__name__)


def openai_hosted_sip_target(
    settings: GatewaySettings,
    *,
    project_id: str | None = None,
) -> str:
    """Build the OpenAI Hosted SIP target URI."""
    effective_project_id = (project_id or settings.openai_project_id).strip()
    domain = (settings.openai_hosted_sip_domain or "sip.api.openai.com").strip()
    transport = (settings.openai_hosted_sip_transport or "tls").strip().lower()
    return f"sip:{effective_project_id}@{domain};transport={transport}"


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
        """Handle one inbound INVITE.

        Important ordering:
        1. Resolve backend context first.
        2. Route OpenAI Hosted SIP calls with SIP 302 before leasing RTP.
        3. Lease/bind RTP only for VPS media bridge calls.

        This prevents OpenAI Hosted SIP attempts from consuming local RTP ports
        and prevents leaked ports when prepare() fails after lease().
        """
        self._send(message, 100, "Trying", addr)

        caller = message.caller
        callee = message.callee
        sip_to = message.header("to") or message.header("t")
        sip_from = message.header("from") or message.header("f")
        provider_call_id = message.call_id or str(uuid.uuid4())
        openai_call_id = f"vps-{provider_call_id}"
        called_number = select_called_number(
            message,
            self.settings.fallback_called_number,
        )

        logger.info(
            "sip_invite_received",
            extra={
                "call_id": provider_call_id,
                "caller": caller,
                "callee": callee,
                "called_number": called_number,
                "sip_to": sip_to,
                "sip_from": sip_from,
                "source_ip": addr[0],
            },
        )

        try:
            context = await self.backend.resolve_voice_context(
                called_number=called_number,
                caller_phone=caller,
                caller=caller,
                callee=callee,
                sip_to=sip_to,
                sip_from=sip_from,
                openai_call_id=openai_call_id,
                provider_call_id=provider_call_id,
            )
        except BackendRequestError as exc:
            self.invite_failures += 1
            self.provider_errors += 1
            logger.warning(
                "sip_invite_backend_context_failed",
                extra={
                    "call_id": provider_call_id,
                    "caller": caller,
                    "callee": callee,
                    "called_number": called_number,
                    "sip_to": sip_to,
                    "sip_from": sip_from,
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
                "sip_invite_context_failed",
                extra={
                    "call_id": provider_call_id,
                    "caller": caller,
                    "callee": callee,
                    "called_number": called_number,
                    "sip_to": sip_to,
                },
            )
            self._send(message, 488, "Not Acceptable Here", addr)
            return

        route = (context.call_audio_mode or "vps_media_bridge").strip().casefold()
        voice_provider = (context.voice_provider or "").strip().casefold()
        if voice_provider != "openai":
            route = "vps_media_bridge"

        logger.info(
            "voice_context_resolved",
            extra={
                "call_id": provider_call_id,
                "clinic_id": context.clinic_id,
                "caller": caller,
                "callee": callee,
                "called_number": called_number,
                "voice_provider": context.voice_provider,
                "call_audio_mode": context.call_audio_mode,
                "route": route,
            },
        )
        logger.info(
            "call_route_selected",
            extra={"call_id": provider_call_id, "route": route},
        )

        if route == "openai_hosted_sip":
            project_id = (
                getattr(context, "openai_project_id", None)
                or getattr(self.settings, "openai_project_id", "")
                or ""
            ).strip()
            if not project_id:
                self.invite_failures += 1
                self.provider_errors += 1
                logger.error(
                    "openai_hosted_sip_project_id_missing",
                    extra={"call_id": provider_call_id, "clinic_id": context.clinic_id},
                )
                self._send(message, 488, "Not Acceptable Here", addr)
                return
            target = openai_hosted_sip_target(self.settings, project_id=project_id)
            if self.settings.openai_hosted_sip_strategy != "redirect":
                self.invite_failures += 1
                logger.error(
                    "sip_b2bua_unavailable",
                    extra={
                        "call_id": provider_call_id,
                        "clinic_id": context.clinic_id,
                        "target": target,
                        "strategy": self.settings.openai_hosted_sip_strategy,
                        "reason": (
                            "VoIP Studio does not reliably follow UDP to TLS "
                            "302 redirects. B2BUA/TLS proxy is not enabled."
                        ),
                    },
                )
                self._send(
                    message,
                    488,
                    "OpenAI Hosted SIP B2BUA Not Implemented",
                    addr,
                    extra_headers={
                        "X-Autogal-Route": "openai_hosted_sip_blocked",
                        "X-Autogal-OpenAI-SIP-Target": target,
                    },
                )
                return
            logger.info(
                "route=openai_hosted_sip_redirect",
                extra={
                    "call_id": provider_call_id,
                    "clinic_id": context.clinic_id,
                    "target": target,
                    "stable_call_established": False,
                    "reason": "redirect_only_no_b2bua",
                },
            )
            self._send(
                message,
                302,
                "Moved Temporarily",
                addr,
                contact=f"<{target}>",
                extra_headers={"X-Autogal-Route": "openai_hosted_sip_redirect"},
            )
            logger.info(
                "sip_redirect_sent",
                extra={
                    "call_id": provider_call_id,
                    "clinic_id": context.clinic_id,
                    "target": target,
                    "stable_call_established": False,
                },
            )
            return

        if route != "vps_media_bridge":
            self.invite_failures += 1
            self.provider_errors += 1
            logger.error(
                "unsupported_call_route",
                extra={
                    "call_id": provider_call_id,
                    "clinic_id": context.clinic_id,
                    "route": route,
                    "voice_provider": context.voice_provider,
                },
            )
            self._send(message, 488, "Not Acceptable Here", addr)
            return

        logger.info(
            "route=vps_media_bridge",
            extra={"call_id": provider_call_id, "clinic_id": context.clinic_id},
        )

        if len(self.calls_by_id) >= self.settings.max_concurrent_calls:
            self._send(message, 486, "Busy Here", addr)
            return

        call: GatewayCallSession | None = None
        rtp_port: int | None = None
        try:
            offer = parse_sdp_offer(message.body)
            preferred_codec = context.telephony_codec or self.settings.telephony_codec
            payload_type = offer.choose_payload(preferred_codec)
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
            # Avoid resolving /api/internal/voice/context twice. prepare() will
            # bind RTP and reuse this context when present.
            call.context = context
            await call.prepare()
        except Exception:
            self.invite_failures += 1
            self.provider_errors += 1
            logger.exception(
                "sip_invite_failed",
                extra={
                    "call_id": provider_call_id,
                    "caller": caller,
                    "callee": callee,
                    "called_number": called_number,
                    "sip_to": sip_to,
                    "rtp_port": rtp_port,
                    "rtp_ports_available": self.port_pool.available_count,
                },
            )
            if call is not None:
                await call.close("invite_failed")
            elif rtp_port is not None:
                self.port_pool.release(rtp_port)
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
            contact=f"<sip:bot@{self.settings.advertised_sip_host}:{self.settings.sip_port};transport=udp>",
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
