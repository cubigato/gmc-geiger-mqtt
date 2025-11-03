# Changelog

All notable changes to the GMC Geiger Counter MQTT Bridge project.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.2.0] - 2025-11-03

### Changed
- **BREAKING**: Migrated to modern `pyproject.toml` structure (PEP 517/518/621)
- Package name convention: `gmc-geiger-mqtt` (distribution) vs `gmc_geiger_mqtt` (import)
- Moved source from `src/` to `src/gmc_geiger_mqtt/` for proper package structure
- Updated all imports from `src.*` to `gmc_geiger_mqtt.*`
- Replaced `pytest.ini` with `[tool.pytest.ini_options]` in `pyproject.toml`
- Build system changed from setuptools to hatchling (faster, modern)

### Added
- Entry point: `gmc-geiger-mqtt` command available after installation
- Development dependencies as optional extras: `pip install -e ".[dev]"`
- Ruff for fast linting and code formatting
- Makefile with common development tasks (test, lint, format, build, etc.)
- `.editorconfig` for consistent code style across editors
- Comprehensive migration guide: `MIGRATION.md`
- Development section in README.md
- Integrated tool configuration in pyproject.toml (pytest, coverage, ruff)

### Fixed
- Exception chaining in config.py for better error tracing
- Import sorting and organization across all modules
- Code formatting standardized with ruff

### Improved
- Installation process: `uv pip install -e .` instead of `requirements.txt`
- Distribution-ready: can be built and uploaded to PyPI
- Better IDE and tool integration with modern package structure
- Cleaner imports without `sys.path` manipulation

### Backwards Compatibility
- `run.py` wrapper script still works for existing workflows
- `requirements.txt` maintained for backwards compatibility
- All existing functionality preserved

## [0.1.0] - 2025-11-03

### Added
- Serial communication with GMC devices (GQ-RFC1801 protocol)
- Support for GMC-800, GMC-500/600 series
- 4-byte CPM reading (32-bit unsigned integer)
- Device info retrieval (model, version, serial)
- CPM to µSv/h conversion with configurable factors
- MQTT client with auto-reconnect
- Realtime CPM publishing (1s interval, QoS 0)
- 10-minute moving average aggregation
- Aggregated readings publishing (10min interval, QoS 1)
- Device info publishing (retained)
- Availability tracking with Last Will Testament
- Home Assistant MQTT Discovery (4 sensors: CPM, µSv/h, both realtime and averaged)
- Service mode with graceful shutdown (SIGINT, SIGTERM)
- Test mode without MQTT
- YAML-based configuration
- 41 unit tests (models, aggregator)
- Documentation: README.md, HOMEASSISTANT.md, ARCHITECTURE.md

### Dependencies
- pyserial >= 3.5
- pyyaml >= 6.0
- paho-mqtt >= 1.6.1
- pytest >= 7.4.0
- pytest-cov >= 4.1.0

### Known Issues
- GMC-800 uses baudrate 115200 (not 57600 per GQ-RFC1801)
- HEARTBEAT command not supported on GMC-800 v1.10
- User must be in `dialout` group for serial access
