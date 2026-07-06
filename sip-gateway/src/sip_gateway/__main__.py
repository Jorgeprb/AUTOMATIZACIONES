"""CLI entrypoint for the SIP gateway service."""

from __future__ import annotations

import asyncio
import logging

from sip_gateway.config import GatewaySettings
from sip_gateway.logging import configure_logging
from sip_gateway.server import SipGateway


async def main() -> None:
    """Run the UDP SIP gateway until interrupted."""
    settings = GatewaySettings()
    if not settings.openai_api_key.get_secret_value().strip():
        raise RuntimeError("OPENAI_API_KEY is required for sip-gateway")
    configure_logging(settings.log_level)
    gateway = SipGateway(settings)
    await gateway.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("sip_gateway_interrupted")
