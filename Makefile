# Test commands. Each layer has its own target; `make test` runs them all.
# The backend layers run in Docker (see docker-compose.test.yml); the frontend component
# tests run with npm, like the rest of the frontend.
#
# Extra pytest options go in ARGS, for example:
#   make test-api ARGS="-k pagination"        only tests whose name contains "pagination"
#   make test-api ARGS="--random-order"       shuffle the order
#   make test-unit ARGS="-x -vv"              stop at the first failure, verbose
#   make test-frontend ARGS="Keyboard"        only test files whose name contains "Keyboard"

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

.PHONY: test test-unit test-frontend test-api test-security test-concurrency test-e2e

# Run every layer, fastest first, stopping at the first layer that fails.
test: test-unit test-frontend test-api test-security test-concurrency test-e2e

# Layer 1: backend unit tests (no database, no network).
test-unit:
	$(call run_layer,unit,pytest tests/unit)

# Frontend component tests (React components, hooks and the API client; no backend, no browser).
# Installs the frontend's packages first if they are not there yet.
test-frontend:
	@test -x frontend/node_modules/.bin/vitest || (cd frontend && npm install --no-audit --no-fund)
	@cd frontend && npm test -- $(ARGS)

# Layer 2: backend API tests (FastAPI + a throwaway Postgres).
test-api:
	$(call run_layer,api,pytest tests/api)

# Layer 3: security tests (the sign-in, CSRF, access and secrecy rules; same throwaway Postgres).
test-security:
	$(call run_layer,api,pytest tests/security)

# Layer 4: concurrency tests (many requests at the same instant; same throwaway Postgres).
test-concurrency:
	$(call run_layer,api,pytest tests/concurrency)

# Layer 5: end-to-end tests (headless Chromium against the real frontend and backend).
# A failed test leaves a screenshot, the browser console log and the page source in e2e/artifacts/.
test-e2e:
	@$(COMPOSE_TEST) build --quiet e2e-backend e2e-frontend e2e
	$(call run_layer,e2e,pytest)
