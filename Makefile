# Test commands. Each layer has its own target; `make test` runs them all.
# Everything runs in Docker (see docker-compose.test.yml), so only Docker is required.
#
# Extra pytest options go in ARGS, for example:
#   make test-api ARGS="-k pagination"        only tests whose name contains "pagination"
#   make test-api ARGS="--random-order"       shuffle the order
#   make test-unit ARGS="-x -vv"              stop at the first failure, verbose

COMPOSE_TEST = docker compose -f docker-compose.test.yml
ARGS ?=

# Runs one service's tests, then removes the test containers (and the in-memory test
# database with them) whether the tests passed or not, and reports the tests' result.
define run_layer
	@$(COMPOSE_TEST) run --rm --build --quiet-pull $(1) $(2) $(ARGS); \
	status=$$?; \
	$(COMPOSE_TEST) down --volumes --remove-orphans >/dev/null 2>&1; \
	exit $$status
endef

.PHONY: test test-unit test-api test-security test-concurrency

# Run every layer, fastest first, stopping at the first layer that fails.
test: test-unit test-api test-security test-concurrency

# Layer 1: backend unit tests (no database, no network).
test-unit:
	$(call run_layer,unit,pytest tests/unit)

# Layer 2: backend API tests (FastAPI + a throwaway Postgres).
test-api:
	$(call run_layer,api,pytest tests/api)

# Layer 3: security tests (the sign-in, CSRF, access and secrecy rules; same throwaway Postgres).
test-security:
	$(call run_layer,api,pytest tests/security)

# Layer 4: concurrency tests (many requests at the same instant; same throwaway Postgres).
test-concurrency:
	$(call run_layer,api,pytest tests/concurrency)
