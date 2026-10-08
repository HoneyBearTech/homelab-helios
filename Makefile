.PHONY: test lint check config smoke kometa

PYTHON ?= python3
VENV := .venv

# Check and test tools, pinned with hashes; the venv is rebuilt when the requirements change
$(VENV)/.installed: requirements-dev.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes --no-deps -r requirements-dev.txt
	touch $@

# Unit tests for the policy checker, with the coverage floor from pyproject.toml (no Docker, no network)
test: $(VENV)/.installed
	$(VENV)/bin/coverage run -m pytest -q
	$(VENV)/bin/coverage report

# The Python, YAML and shell linters CI runs (the workflow and secret scanners run in containers; see ci.yml)
lint: $(VENV)/.installed
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .
	$(VENV)/bin/yamllint --strict .
	$(VENV)/bin/shellcheck -x scripts/*.sh

# The stack's policy check: every image pinned by digest, nothing privileged, the tools included (needs Docker and .env)
check: $(VENV)/.installed
	docker compose --profile tools config --format json | $(VENV)/bin/python scripts/check_compose.py

# Start every service with throwaway settings, wait until all are healthy, remove it all (needs Docker and
# network; never touches an existing installation: scripts/smoke-test.sh)
smoke:
	scripts/smoke-test.sh

# Validate kometa/ with the pinned Kometa image and its JSON schemas, without secrets (needs Docker and network;
# scripts/kometa-validate.sh). The same check CI runs as "Kometa config".
kometa:
	scripts/kometa-validate.sh

# Print the resolved Compose file, with .env applied (the tools started on demand included)
config:
	docker compose --profile tools config
