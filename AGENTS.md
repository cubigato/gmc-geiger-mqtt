Always read README.md and ARCHITECTURE.md before doing anything.

Write tests but don't overuse them.
When asked to write web code you can use puppeteer to verify the UI, but don't overuse it as it uses a lot of resources.
When changing something that changes what the software does or how it works make sure to update documentation and tests.

## Python Setup

We use a venv in `.venv` and `uv` for Python package management.

The project uses modern `pyproject.toml` structure (PEP 621):
- Package name: `gmc-geiger-mqtt` (distribution) vs `gmc_geiger_mqtt` (import)
- Source code is in `src/gmc_geiger_mqtt/`
- Dependencies are defined in `pyproject.toml`

## Installing Dependencies

NEVER install anything without asking the user for approval.

When dependencies need to be added:
1. Add them to `pyproject.toml` under `[project.dependencies]` or `[project.optional-dependencies.dev]`
2. Tell the user to apply changes with: `uv pip install -e ".[dev]"`

## Development Workflow

Common tasks are available via Makefile:
- `make test` - Run tests
- `make lint` - Check code quality
- `make format` - Format code with ruff
- `make check-all` - Run all checks (lint + format + test)