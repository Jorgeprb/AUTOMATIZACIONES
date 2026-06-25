.PHONY: dev test lint migrate revision seed calendar-demo simulate simulate-google purge-calls

dev:
	docker compose up --build

test:
	docker compose run --rm app pytest

lint:
	docker compose run --rm app ruff check .
	docker compose run --rm app ruff format --check .
	docker compose run --rm app mypy app scripts tests

migrate:
	docker compose run --rm app alembic upgrade head

seed:
	docker compose run --rm app python -m scripts.seed_demo

calendar-demo:
	docker compose run --rm app python -m scripts.create_demo_calendars

simulate:
	docker compose run --rm app python -m app.simulate_call --no-google

simulate-google:
	docker compose run --rm app python -m app.simulate_call --google-real

purge-calls:
	docker compose run --rm app python -m scripts.purge_calls

revision:
	@test -n "$(MESSAGE)" || (echo "Usage: make revision MESSAGE='description'" && exit 1)
	docker compose run --rm app alembic revision --autogenerate -m "$(MESSAGE)"
