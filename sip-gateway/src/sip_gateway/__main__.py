"""CLI entrypoint for the SIP gateway service."""

from __future__ import annotations

import asyncio
import logging
import signal

from sip_gateway.config import GatewaySettings
from sip_gateway.logging import configure_logging
from sip_gateway.server import SipGateway

logger = logging.getLogger(__name__)


async def main() -> None:
    """Run the UDP SIP gateway with graceful drain on SIGINT/SIGTERM."""
    settings = GatewaySettings()
    if not settings.openai_api_key.get_secret_value().strip():
        raise RuntimeError("OPENAI_API_KEY is required for sip-gateway")
    configure_logging(settings.log_level)
    gateway = SipGateway(settings)
    loop = asyncio.get_running_loop()
    shutdown_started = asyncio.Event()

    async def request_shutdown(reason: str) -> None:
        if shutdown_started.is_set():
            return
        shutdown_started.set()
        logger.info("sip_gateway_shutdown_requested", extra={"reason": reason})
        await gateway.shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda caught=sig: asyncio.create_task(request_shutdown(caught.name)),
            )
        except NotImplementedError:
            pass

    try:
        await gateway.serve_forever()
    finally:
        await request_shutdown("main_finally")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("sip_gateway_interrupted")
