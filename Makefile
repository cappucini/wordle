# Test commands. Each layer has its own target; `make test` runs them all.
# Everything runs in Docker (see docker-compose.test.yml), so only Docker is required.

COMPOSE_TEST = docker compose -f docker-compose.test.yml

.PHONY: test test-unit

# Run every layer, fastest first, stopping at the first layer that fails.
test: test-unit

# Layer 1: backend unit tests (no database, no network).
test-unit:
	$(COMPOSE_TEST) run --rm --build unit
