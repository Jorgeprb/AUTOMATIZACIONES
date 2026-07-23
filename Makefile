.PHONY: test test-backend test-gateway test-frontend typecheck compile release

test: test-backend test-gateway test-frontend

test-backend:
	cd clinic-voice-agent && python -m pytest

test-gateway:
	cd sip-gateway && PYTHONPATH=src python -m pytest

test-frontend:
	cd frontend && npm test -- --run

typecheck:
	cd frontend && npm run typecheck
	cd clinic-voice-agent && python -m mypy app
	cd sip-gateway && python -m mypy src

compile:
	cd clinic-voice-agent && PYTHONPATH=. python -m compileall -q app tests alembic/versions
	cd sip-gateway && PYTHONPATH=src python -m compileall -q src tests

release:
	bash scripts/package_release.sh
