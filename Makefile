.PHONY: help install install-dev test test-cov lint format clean build run

# Use virtual environment if it exists
VENV := .venv
ifeq ($(shell test -d $(VENV) && echo yes),yes)
	PYTHON := $(VENV)/bin/python
	PYTEST := $(VENV)/bin/pytest
	RUFF := $(VENV)/bin/ruff
	UV := uv
else
	PYTHON := python3
	PYTEST := pytest
	RUFF := ruff
	UV := uv
endif

help:
	@echo "GMC Geiger MQTT - Development Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  install       - Install package in editable mode"
	@echo "  install-dev   - Install package with development dependencies"
	@echo "  test          - Run tests"
	@echo "  test-cov      - Run tests with coverage report"
	@echo "  lint          - Run code linting (ruff check)"
	@echo "  format        - Format code (ruff format)"
	@echo "  format-check  - Check if code is formatted correctly"
	@echo "  clean         - Remove build artifacts and cache files"
	@echo "  build         - Build distribution packages"
	@echo "  run           - Run the application"
	@echo "  check-all     - Run all checks (lint, format-check, test)"
	@echo ""

install:
	$(UV) pip install -e .

install-dev:
	$(UV) pip install -e ".[dev]"

test:
	$(PYTEST)

test-cov:
	$(PYTEST) --cov=src --cov-report=term-missing --cov-report=html

lint:
	$(RUFF) check src/ tests/

format:
	$(RUFF) format src/ tests/

format-check:
	$(RUFF) format --check src/ tests/

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

build: clean
	$(PYTHON) -m build

run:
	$(VENV)/bin/gmc-geiger-mqtt

check-all: lint format-check test
	@echo ""
	@echo "✓ All checks passed!"
