# Manual Tests

This directory contains **manual hardware tests** that require a physical GMC Geiger counter device connected via USB/serial. These tests are **not** run automatically by pytest and are excluded from CI/CD pipelines.

## Purpose

These tests are used for:
- **Hardware debugging** - Verify serial communication with the GMC device
- **Protocol testing** - Test different baudrates and command sequences
- **CPM reading validation** - Verify correct parsing of device responses
- **MQTT integration testing** - Test MQTT message publishing (requires running broker)

## Available Tests

### `test_serial.py`
Tests basic serial communication with different baudrates.

**Usage:**
```bash
sg dialout -c "python3 manual_tests/test_serial.py"
```

**Requirements:**
- GMC device connected to `/dev/ttyUSB0`
- User in `dialout` group

---

### `test_cpm_debug.py`
Detailed debugging of CPM reading with byte-level analysis.

**Usage:**
```bash
sg dialout -c "python3 manual_tests/test_cpm_debug.py"
```

**Shows:**
- Raw bytes from device
- CPM parsing step-by-step
- Timing information

---

### `test_cpm_debug2.py`
Alternative CPM reading test with different approach.

**Usage:**
```bash
sg dialout -c "python3 manual_tests/test_cpm_debug2.py"
```

---

### `test_mqtt_messages.py`
Tests MQTT message publishing and Home Assistant discovery.

**Usage:**
```bash
sg dialout -c "python3 manual_tests/test_mqtt_messages.py"
```

**Requirements:**
- GMC device connected
- MQTT broker running (e.g., Mosquitto)
- Valid `config.yaml` with MQTT settings

**What it tests:**
- Device info publishing
- Realtime CPM publishing
- Aggregated readings
- Home Assistant MQTT discovery

---

## Running Manual Tests

**Important:** These tests are **NOT** run by `pytest` automatically. You must run them explicitly:

```bash
# Run a specific manual test
python3 manual_tests/test_serial.py

# With serial port access (if not in dialout group)
sg dialout -c "python3 manual_tests/test_serial.py"
```

**Do not run:**
```bash
pytest manual_tests/  # Will fail without hardware!
```

---

## Why Separate from Automated Tests?

1. **CI/CD Compatibility** - Automated tests must run without hardware
2. **Permission Requirements** - Need `/dev/ttyUSB0` access
3. **Device Availability** - Physical device might be in use
4. **Non-deterministic** - Hardware responses can vary
5. **Timing Sensitive** - Serial communication timing is critical

---

## Automated Tests

For **automated unit tests** that run in CI/CD without hardware, see:
```bash
pytest tests/
```

These test:
- Domain models (`test_models.py`)
- Aggregator logic (`test_aggregator.py`)
- Pure business logic (no hardware dependencies)

---

## Adding New Manual Tests

When creating new hardware-dependent tests:

1. Place them in `manual_tests/` directory
2. Name them `test_*.py` (pytest convention)
3. Document hardware requirements
4. Add usage instructions to this README
5. **Do NOT** expect them to run in CI/CD

---

## Troubleshooting

### Permission denied on /dev/ttyUSB0
```bash
sudo usermod -a -G dialout $USER
# Then logout/login or use: sg dialout -c "command"
```

### Device not found
```bash
# Check if device is connected
ls -l /dev/ttyUSB*

# Check dmesg for USB events
dmesg | grep tty
```

### Wrong baudrate
- GMC-800: `115200` baud
- Older models: `57600` baud (check GQ-RFC1801.txt)