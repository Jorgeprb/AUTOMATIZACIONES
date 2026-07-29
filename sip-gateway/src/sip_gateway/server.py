"""Async UDP SIP server."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
import zlib
from collections import OrderedDict, deque

from sip_gateway.backend import BackendClient, BackendRequestError
from sip_gateway.config import GatewaySettings
from sip_gateway.rtp import RTPPortPool
from sip_gateway.sdp import build_sdp_answer, parse_sdp_offer
from sip_gateway.session import GatewayCallSession, select_called_number
from sip_gateway.sip import SipMessage, build_request, build_response

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
    """Bounded per-IP sliding-window limiter for new INVITE transactions."""

    def __init__(self, limit_per_minute: int, *, max_keys: int = 10000) -> None:
        self.limit = limit_per_minute
        self.max_keys = max_keys
        self._events: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        events = self._events.setdefault(key, deque())
        self._events.move_to_end(key)
        while events and now - events[0] > 60:
            events.popleft()
        while len(self._events) > self.max_keys:
            self._events.popitem(last=False)
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
        """Queue a datagram without creating an unbounded task per packet."""
        self.gateway.enqueue_datagram(data, addr)


class SipGateway:
    """Main SIP gateway service."""

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings
        self.backend = BackendClient(settings)
        self.port_pool = RTPPortPool(settings.rtp_port_min, settings.rtp_port_max)
        self.rate_limiter = SlidingWindowRateLimiter(
            settings.invite_rate_limit_per_minute,
            max_keys=settings.rate_limiter_max_keys,
        )
        self.transport: asyncio.DatagramTransport | None = None
        self.calls_by_id: dict[str, GatewayCallSession] = {}
        self.calls_by_branch: dict[str, GatewayCallSession] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._datagram_queue: asyncio.Queue[tuple[bytes, tuple[str, int]]] = (
            asyncio.Queue(maxsize=settings.sip_datagram_queue_size)
        )
        self._workers: list[asyncio.Task[None]] = []
        self._accepting = True
        self._stopped = asyncio.Event()
        self._health_server: asyncio.Server | None = None
        self.invite_failures = 0
        self.provider_errors = 0

    def track_task(self, task: asyncio.Task[None]) -> None:
        """Keep background datagram tasks referenced until done."""
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def enqueue_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        if not self._accepting:
            return
        try:
            self._datagram_queue.put_nowait((data, addr))
        except asyncio.QueueFull:
            logger.warning("sip_datagram_queue_full", extra={"source_ip": addr[0]})

    async def _datagram_worker(self) -> None:
        while True:
            data, addr = await self._datagram_queue.get()
            try:
                await self.handle_datagram(data, addr)
            except Exception:
                logger.exception(
                    "sip_datagram_handler_failed", extra={"source_ip": addr[0]}
                )
            finally:
                self._datagram_queue.task_done()

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
        self._workers = [
            asyncio.create_task(self._datagram_worker(), name=f"sip-worker-{index}")
            for index in range(self.settings.sip_worker_count)
        ]
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
        """Stop accepting new calls, drain resources, and close pools."""
        self._accepting = False
        for call in list(self.calls_by_id.values()):
            await self._remove_call(call, "gateway_shutdown")
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        await self.backend.close()
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
            "ok": self._accepting,
            "accepting_new_calls": self._accepting,
            "sip_datagram_queue_depth": self._datagram_queue.qsize(),
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

    def prometheus_metrics(self) -> str:
        """Render dependency-free OpenMetrics counters and gauges."""
        snapshot = self.metrics_snapshot()
        lines = [
            "# HELP sip_gateway_up Whether the gateway is accepting new calls.",
            "# TYPE sip_gateway_up gauge",
            f"sip_gateway_up {1 if snapshot['ok'] else 0}",
            "# TYPE sip_gateway_active_calls gauge",
            f"sip_gateway_active_calls {snapshot['active_calls']}",
            "# TYPE sip_gateway_sip_datagram_queue_depth gauge",
            f"sip_gateway_sip_datagram_queue_depth {snapshot['sip_datagram_queue_depth']}",
            "# TYPE sip_gateway_rtp_ports_available gauge",
            f"sip_gateway_rtp_ports_available {snapshot['rtp_ports_available']}",
            "# TYPE sip_gateway_invite_failures_total counter",
            f"sip_gateway_invite_failures_total {snapshot['invite_failures']}",
            "# TYPE sip_gateway_provider_errors_total counter",
            f"sip_gateway_provider_errors_total {snapshot['provider_errors']}",
            "# EOF",
        ]
        return "\n".join(lines) + "\n"

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
            if path == "/metrics":
                body = self.prometheus_metrics()
                status = "200 OK"
                content_type = (
                    "application/openmetrics-text; version=1.0.0; charset=utf-8"
                )
            elif path in {"/health/live", "/health/ready"}:
                snapshot = self.metrics_snapshot()
                body = json.dumps(snapshot, separators=(",", ":"))
                status = (
                    "503 Service Unavailable"
                    if path == "/health/ready" and not snapshot["ok"]
                    else "200 OK"
                )
                content_type = "application/json"
            else:
                body = json.dumps({"ok": False, "error": "not_found"})
                status = "404 Not Found"
                content_type = "application/json"
            payload = body.encode("utf-8")
            writer.write(
                (
                    f"HTTP/1.1 {status}\r\n"
                    f"Content-Type: {content_type}\r\n"
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
        if not self.settings.sip_ip_allowed(ip):
            logger.warning("sip_rejected_ip", extra={"source_ip": ip})
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
            if not self._accepting:
                self._send(
                    message,
                    503,
                    "Service Unavailable",
                    addr,
                    extra_headers={"Retry-After": "30"},
                )
                return
            if not self.rate_limiter.allow(ip):
                logger.warning("sip_rate_limited", extra={"source_ip": ip})
                self._send(
                    message,
                    503,
                    "Service Unavailable",
                    addr,
                    extra_headers={"Retry-After": "60"},
                )
                return
            await self._handle_invite(message, addr)
        elif method == "ACK":
            await self._handle_ack(message, addr)
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
        existing = self.calls_by_id.get(message.call_id) or self.calls_by_branch.get(
            message.branch
        )
        if existing is not None:
            if existing.sip_addr != addr:
                logger.warning(
                    "sip_dialog_source_mismatch",
                    extra={"call_id": message.call_id, "source_ip": addr[0]},
                )
                return
            if existing.last_invite_response is not None and self.transport is not None:
                self.transport.sendto(existing.last_invite_response, addr)
            else:
                self._send(message, 100, "Trying", addr)
            logger.info("sip_invite_retransmission", extra={"call_id": message.call_id})
            return
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

        if (
            sum(not call._closed.is_set() for call in self.calls_by_id.values())
            >= self.settings.max_concurrent_calls
        ):
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
                on_closed=self._on_call_closed,
                on_hangup_requested=self._send_bye_and_close,
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
        call.last_invite_response = self._send(
            message,
            200,
            "OK",
            addr,
            body=sdp_answer,
            to_tag=call.local_tag,
            contact=f"<sip:bot@{self.settings.advertised_sip_host}:{self.settings.sip_port};transport=udp>",
        )
        self.track_task(asyncio.create_task(self._ack_timeout(call)))

    def _dialog_matches(
        self,
        call: GatewayCallSession,
        message: SipMessage,
    ) -> bool:
        """Validate an in-dialog request without requiring the same SBC IP.

        VoIP providers may send the initial INVITE and subsequent ACK/BYE
        through different signalling nodes. Source access is already checked
        against SIP_ALLOWED_IPS in handle_datagram().
        """
        if message.call_id != call.call_id:
            return False

        invite_from_tag = call.invite.from_tag
        if invite_from_tag and message.from_tag and message.from_tag != invite_from_tag:
            return False

        if message.to_tag and message.to_tag != call.local_tag:
            return False

        cseq_parts = message.cseq.split()
        return not (len(cseq_parts) >= 2 and message.method and cseq_parts[1].upper() != message.method)

    async def _handle_ack(self, message: SipMessage, addr: tuple[str, int]) -> None:
        call = self.calls_by_id.get(message.call_id)
        if call is None:
            logger.warning(
                "sip_ack_unknown_call",
                extra={"call_id": message.call_id, "source_ip": addr[0]},
            )
            return

        if not self._dialog_matches(call, message):
            logger.warning(
                "sip_ack_dialog_mismatch",
                extra={
                    "call_id": message.call_id,
                    "source_ip": addr[0],
                    "from_tag": message.from_tag,
                    "to_tag": message.to_tag,
                },
            )
            return

        call.dialog_remote_addr = addr
        logger.info(
            "sip_ack_accepted",
            extra={
                "call_id": message.call_id,
                "source_ip": addr[0],
                "invite_source_ip": call.sip_addr[0],
            },
        )

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

        if call is not None and not self._dialog_matches(call, message):
            logger.warning(
                "sip_teardown_dialog_mismatch",
                extra={
                    "call_id": message.call_id,
                    "source_ip": addr[0],
                    "method": method,
                    "from_tag": message.from_tag,
                    "to_tag": message.to_tag,
                },
            )
            self._send(message, 481, "Call/Transaction Does Not Exist", addr)
            return

        self._send(message, 200, "OK", addr)

        if call is not None:
            logger.info(
                "sip_teardown_accepted",
                extra={
                    "call_id": message.call_id,
                    "source_ip": addr[0],
                    "method": method,
                    "invite_source_ip": call.sip_addr[0],
                },
            )
        if call is not None:
            if method == "CANCEL" and not call.media_started:
                self._send(
                    call.invite,
                    487,
                    "Request Terminated",
                    call.sip_addr,
                    to_tag=call.local_tag,
                )
            await self._remove_call(call, method.lower())

    async def _ack_timeout(self, call: GatewayCallSession) -> None:
        await asyncio.sleep(self.settings.ack_timeout_seconds)
        if not call.media_started and not call._closed.is_set():
            logger.warning("sip_ack_timeout", extra={"call_id": call.call_id})
            await self._remove_call(call, "ack_timeout")

    @staticmethod
    def _header_uri(value: str) -> str:
        """Extract the first SIP URI from a Contact/From/To header."""
        match = re.search(r"sip:[^>;\s]+(?:;[^>\s]+)?", value or "", re.IGNORECASE)
        return match.group(0) if match else ""

    async def _send_bye_and_close(
        self,
        call: GatewayCallSession,
        reason: str,
    ) -> None:
        """Terminate an established inbound dialog after assistant playout."""
        if call._closed.is_set():
            return
        if self.transport is not None:
            remote_uri = self._header_uri(call.invite.header("contact"))
            if not remote_uri:
                remote_uri = (
                    f"sip:{call.invite.caller}@{call.dialog_remote_addr[0]}:"
                    f"{call.dialog_remote_addr[1]}"
                )
            original_to = call.invite.header("to") or call.invite.header("t")
            if "tag=" not in original_to.casefold():
                original_to = f"{original_to};tag={call.local_tag}"
            original_from = call.invite.header("from") or call.invite.header("f")
            try:
                invite_cseq = int(call.invite.cseq.split()[0])
            except (ValueError, IndexError):
                invite_cseq = 1
            branch = f"z9hG4bK-{uuid.uuid4().hex[:16]}"
            local_host = self.settings.advertised_sip_host
            bye = build_request(
                "BYE",
                remote_uri,
                {
                    "Via": (
                        f"SIP/2.0/UDP {local_host}:{self.settings.sip_port};"
                        f"branch={branch};rport"
                    ),
                    "Max-Forwards": "70",
                    "From": original_to,
                    "To": original_from,
                    "Call-ID": call.call_id,
                    "CSeq": f"{invite_cseq + 1} BYE",
                    "Contact": (
                        f"<sip:bot@{local_host}:{self.settings.sip_port};transport=udp>"
                    ),
                    "User-Agent": "Autogal-SIP-Gateway",
                    "Reason": f'SIP;cause=200;text="{reason}"',
                },
            )
            self.transport.sendto(bye, call.dialog_remote_addr)
            logger.info(
                "sip_bye_sent",
                extra={
                    "call_id": call.call_id,
                    "reason": reason,
                    "target": remote_uri,
                    "source_ip": call.dialog_remote_addr[0],
                },
            )
            await asyncio.sleep(0.15)
        await self._remove_call(call, f"assistant_{reason}")

    async def _on_call_closed(self, call: GatewayCallSession, reason: str) -> None:
        del reason
        self.calls_by_id.pop(call.call_id, None)
        if call.invite.branch:
            self.calls_by_branch.pop(call.invite.branch, None)

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
    ) -> bytes | None:
        if self.transport is None or addr[1] == 0:
            return None
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
        return response

    @staticmethod
    def _allow() -> str:
        return "INVITE, ACK, BYE, CANCEL, OPTIONS"
