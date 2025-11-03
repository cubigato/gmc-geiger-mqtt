# GMC Geiger Counter to MQTT Bridge

A Python application for reading radiation data from GMC Geiger counters and publishing it via MQTT.

## Status

**Current Phase:** ✅ Fully functional MQTT bridge!

✅ Implemented:
- Serial communication with GMC devices (GQ-RFC1801 protocol)
- **CPM reading (4-byte, 32-bit)** - correctly implemented
- µSv/h conversion
- Device info retrieval (model, version, serial)
- Configuration system (YAML-based)
- Polling-only mode (no heartbeat)
- **MQTT publishing** (realtime and aggregated)
- **Moving average calculation** (configurable time window)
- **Service mode** with automatic reconnection
- **Home Assistant MQTT discovery**
- Graceful shutdown handling

🚧 Not yet implemented:
- Web UI
- Additional output plugins (InfluxDB, etc.)

## Requirements

- Python 3.8+
- GMC Geiger counter (tested with GMC-800 v1.10, should work with GMC-500/600 series)
- USB connection to the device
- MQTT broker (e.g., Mosquitto) - optional for MQTT features

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd gmc-geiger-mqtt
```

2. Install dependencies using uv:
```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Linux/Mac
# Or: .venv\Scripts\activate  # On Windows

uv pip install -r requirements.txt
```

3. Ensure your user has access to the serial port:
```bash
sudo usermod -a -G dialout $USER
```
Then logout and login, or use `sg dialout -c "command"`.

## Configuration

Edit `config.yaml`:

```yaml
# Serial device configuration
device:
  port: "/dev/ttyUSB0"
  baudrate: 115200      # GMC-800 uses 115200!
  timeout: 5.0

# Sampling configuration
sampling:
  interval: 1           # Seconds between readings
  aggregation_window: 600    # Moving average window (10 minutes)
  aggregation_interval: 600  # Publish aggregated data every 10 minutes

# MQTT configuration
mqtt:
  enabled: true         # Set to false for test mode (no MQTT)
  broker: "localhost"
  port: 1883
  username: ""          # Leave empty for anonymous
  password: ""
  topic_prefix: "gmc/geiger"
  homeassistant_discovery: true

# Conversion factor
conversion:
  cpm_to_usv_factor: 0.0065  # Adjust for your device/tube
```

**Critical:** Baudrate is **115200** for GMC-800, not 57600 as specified in GQ-RFC1801!

## Usage

### Service Mode (with MQTT)

Run the bridge in service mode with MQTT publishing:

```bash
# Make sure MQTT broker is running (e.g., mosquitto)
# and mqtt.enabled is set to true in config.yaml

# If already in dialout group:
python3 run.py

# Otherwise:
sg dialout -c "python3 run.py"
```

The service will:
- Connect to the GMC device and MQTT broker
- Publish realtime CPM readings every second to `gmc/geiger/<device_id>/state`
- Publish 10-minute averaged readings to `gmc/geiger/<device_id>/state_avg`
- Register sensors in Home Assistant (if enabled)
- Handle graceful shutdown on Ctrl+C or SIGTERM

### Test Mode (without MQTT)

Test serial communication without MQTT (set `mqtt.enabled: false` in config.yaml):

```bash
sg dialout -c "python3 run.py"
```

Expected output:
```
======================================================================
Starting GMC Geiger test mode
Device: /dev/ttyUSB0 @ 115200 baud
======================================================================
Connected to device: GMC Device: GMC-800Re (v1.10, serial=05004D323533AB)
======================================================================
Starting continuous reading mode (Ctrl+C to stop)...
======================================================================
[   1] 03:09:11 | CPM:   19 | µSv/h: 0.1235
[   2] 03:09:13 | CPM:   22 | µSv/h: 0.1430
[   3] 03:09:15 | CPM:   21 | µSv/h: 0.1365
...
```

Press Ctrl+C to stop.

## Project Structure

```
gmc-geiger-mqtt/
├── config.yaml           # Configuration file
├── requirements.txt      # Python dependencies
├── run.py               # Main executable
├── src/
│   ├── __init__.py
│   ├── main.py          # Application entry point (service & test mode)
│   ├── config.py        # Configuration loader
│   ├── gmc_device.py    # GMC device communication (polling-only)
│   ├── models.py        # Domain models (Reading, DeviceInfo, MQTTConfig, etc.)
│   ├── mqtt/            # MQTT client and publishing
│   │   ├── client.py    # MQTT client wrapper with auto-reconnect
│   │   ├── publisher.py # Publishing logic for readings
│   │   └── discovery.py # Home Assistant MQTT discovery
│   └── processing/      # Data processing
│       └── aggregator.py # Moving average aggregator
├── tests/               # Unit tests
│   ├── test_models.py
│   └── test_aggregator.py
├── ARCHITECTURE.md      # Detailed architecture documentation
└── GQ-RFC1801.txt       # GMC protocol specification
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed documentation.

**Key Points:**
- **Polling-only mode** - No heartbeat command (not supported by GMC-800)
- **4-byte CPM reading** - 32-bit unsigned integer, MSB first
- **Clean separation** - Device, Processing, MQTT layers
- **Configuration-driven** - All settings in config.yaml
- **Moving average** - Configurable time window for noise reduction
- **Home Assistant integration** - Automatic sensor discovery via MQTT
- **Graceful shutdown** - Publishes offline status on exit

## Important Implementation Details

### CPM Reading (4 bytes!)

The GMC device returns CPM as **4 bytes** (32-bit unsigned integer):

```python
# Send command
serial.write(b"<GETCPM>>")

# Read 4 bytes (MSB first)
data = serial.read(4)

# Parse: data[0] = MSB, data[3] = LSB
cpm = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]
```

Example: `0x00 0x00 0x00 0x1C` = 28 CPM

### No Heartbeat Mode

The GMC-800 v1.10 **does not support** the `<HEARTBEAT>>` command. We use **polling-only**:
- Send `<GETCPM>>` every N seconds
- Wait ~100-200ms for response
- Parse and process

### Buffer Management

**Critical:** Clear input buffer before each command:
```python
serial.reset_input_buffer()  # Prevent stale data!
serial.write(command)
serial.flush()
```

### DTR/RTS Activation

Required for CH340 USB-Serial chips:
```python
serial.setDTR(True)
serial.setRTS(True)
```

## Known Issues

1. **GMC-800 baudrate**: Uses 115200, not 57600 (contrary to GQ-RFC1801)
2. **CPM is 4 bytes**: Many examples incorrectly show 2 bytes
3. **No heartbeat support**: GMC-800 v1.10 doesn't respond to `<HEARTBEAT>>`
4. **Version string**: No guaranteed null terminator, variable length

## Troubleshooting

### Permission denied on /dev/ttyUSB0
```bash
sudo usermod -a -G dialout $USER
# Then logout/login or use: sg dialout -c "python3 run.py"
```

### Reading 0 CPM when device shows higher value
- Check baudrate (GMC-800 = 115200)
- Verify 4-byte reading (not 2-byte)
- Check buffer clearing before commands

### Wrong baudrate
Try `test_serial.py` to test different baudrates:
```bash
sg dialout -c "python3 test_serial.py"
```

## MQTT Topics

When running in service mode, the following MQTT topics are published:

- `gmc/geiger/<device_id>/state` - Realtime CPM readings (every 1s)
  ```json
  {"cpm": 28, "usv_h": 0.182, "timestamp": "2024-01-15T10:30:45Z", "unit": "CPM"}
  ```

- `gmc/geiger/<device_id>/state_avg` - 10-minute averaged readings
  ```json
  {
    "cpm_avg": 25.4, "cpm_min": 18, "cpm_max": 35,
    "usv_h_avg": 0.1651, "window_minutes": 10,
    "sample_count": 600, "timestamp": "2024-01-15T10:30:00Z", "unit": "CPM"
  }
  ```

- `gmc/geiger/<device_id>/availability` - Online/offline status (retained)
- `gmc/geiger/<device_id>/info` - Device information (retained)

## Home Assistant Integration

When `homeassistant_discovery: true` is set, the bridge automatically registers four sensors:

1. **CPM** - Realtime counts per minute
2. **Radiation Level** - Realtime radiation in µSv/h
3. **CPM (10-min avg)** - Averaged counts per minute
4. **Radiation Level (10-min avg)** - Averaged radiation in µSv/h

No manual configuration needed - sensors appear automatically in Home Assistant!

## Next Steps

1. ✅ Test serial communication
2. ✅ Implement MQTT publishing
3. ✅ Implement moving average calculation
4. ✅ Add continuous service mode
5. ✅ Add Home Assistant MQTT discovery
6. Create proper Python package (pyproject.toml)
7. Add systemd service for autostart
8. Add additional output plugins (InfluxDB, etc.)
9. Add Web UI (future)

## Testing

### Unit Tests

Run the unit test suite:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src tests/

# Run specific test file
pytest tests/test_models.py
pytest tests/test_aggregator.py
```

### Manual Testing

Test individual components:

```bash
# Test serial with different baudrates
sg dialout -c "python3 test_serial.py"

# Test CPM reading details
sg dialout -c "python3 test_cpm_debug.py"
```

### MQTT Testing

Monitor MQTT messages:

```bash
# Subscribe to all topics
mosquitto_sub -h localhost -t "gmc/geiger/#" -v

# Subscribe to realtime readings only
mosquitto_sub -h localhost -t "gmc/geiger/+/state"

# Subscribe to averaged readings only
mosquitto_sub -h localhost -t "gmc/geiger/+/state_avg"
```

## License

TBD
