"""Interactive local call simulator.

Run with:
    python -m app.simulate_call --no-google
    python -m app.simulate_call --google-real
"""

from __future__ import annotations

import argparse
import uuid
from collections.abc import Sequence
from datetime import datetime

from app.config import get_settings
from app.db import get_session_factory
from app.simulation import SimulationEngine, SimulationMode
from app.utils.logging import configure_logging


def _parser() -> argparse.ArgumentParser:
    """Build command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Simula una llamada sin usar SIP ni OpenAI Realtime.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--no-google",
        action="store_true",
        help="Usa un calendario falso en memoria. Es el modo por defecto.",
    )
    mode.add_argument(
        "--google-real",
        action="store_true",
        help="Usa la cuenta Google OAuth y calendarios vinculados.",
    )
    parser.add_argument(
        "--clinic-id",
        type=uuid.UUID,
        help="UUID de clínica. Si falta, usa la clínica configurada.",
    )
    parser.add_argument(
        "--now",
        type=datetime.fromisoformat,
        help="Reloj ISO 8601 opcional para pruebas deterministas.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run an interactive deterministic conversation."""
    args = _parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    mode: SimulationMode = "google-real" if args.google_real else "no-google"
    engine = SimulationEngine(
        settings=settings,
        session_factory=get_session_factory(),
        mode=mode,
        now=args.now,
    )
    try:
        call = engine.create_call(clinic_id=args.clinic_id)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Simulación iniciada. Modo: {mode}.")
    print(f"CallSession: {call.id}")
    print("Escribe /salir para terminar.")
    print("Agente: Hola. Soy el asistente virtual. ¿En qué puedo ayudarte?")

    while True:
        try:
            message = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        if message.casefold() in {"/salir", "salir", "exit", "quit"}:
            break
        try:
            result = engine.turn(message, call_session_id=call.id)
        except Exception as exc:
            print(f"Error: {exc}")
            continue
        print(f"Agente: {result.reply}")
        if result.tool_calls:
            names = ", ".join(str(tool_call["name"]) for tool_call in result.tool_calls)
            print(f"Tools: {names}")

    print("Simulación terminada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
