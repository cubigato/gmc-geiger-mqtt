# GMC Geiger Counter to MQTT Bridge

A Python application for reading radiation data from GMC Geiger counters and publishing it via MQTT.

## Status

**Current Phase:** ✅ Serial communication tested and working!

✅ Implemented:
- Serial communication with GMC devices (GQ-RFC1801 protocol)
- **CPM reading (4-byte, 32-bit)** - correctly implemented
- µSv/h conversion
- Device info retrieval (model, version, serial)
- Configuration system (YAML-based)
- Polling-only mode (no heartbeat)
- Basic logging and test mode

🚧 Not yet implemented:
- MQTT publishing
- Moving average calculation
- Continuous service mode
- Home Assistant MQTT discovery
- Web UI

## Requirements

- Python 3.8+
- GMC Geiger counter (tested with GMC-800 v1.10, should work with GMC-500/600 series)
- USB connection to the device

## Installation

1. Install dependencies:
```bash
cd gmc-geiger-mqtt
uv pip install -r requirements.txt
```

2. Ensure your user has access to the serial port:
```bash
sudo usermod -a -G dialout $USER
```
Then logout and login, or use `sg dialout -c "command"`.

## Configuration

Edit `config.yaml`:

```yaml
device:
  port: "/dev/ttyUSB0"
  baudrate: 115200      # GMC-800 uses 115200!
  timeout: 5.0
```

**Critical:** Baudrate is **115200** for GMC-800, not 57600 as specified in GQ-RFC1801!

## Testing

Test serial communication:

```bash
# If already in dialout group:
python3 run.py

# Otherwise:
sg dialout -c "python3 run.py"
```

Expected output:
```
2025-11-03 03:09:11 - src.gmc_device - INFO - Device info: GMC Device: GMC-800Re (v1.10, serial=05004D323533AB)
======================================================================
2025-11-03 03:09:11 - src.main - INFO - Connected to device: GMC Device: GMC-800Re (v1.10, serial=05004D323533AB)
======================================================================
2025-11-03 03:09:11 - src.main - INFO - Starting continuous reading mode (Ctrl+C to stop)...
======================================================================
2025-11-03 03:09:11 - src.main - INFO - [   1] 03:09:11 | CPM:   19 | µSv/h: 0.1235
2025-11-03 03:09:13 - src.main - INFO - [   2] 03:09:13 | CPM:   22 | µSv/h: 0.1430
2025-11-03 03:09:15 - src.main - INFO - [   3] 03:09:15 | CPM:   21 | µSv/h: 0.1365
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
│   ├── main.py          # Application entry point
│   ├── config.py        # Configuration loader
│   ├── gmc_device.py    # GMC device communication (polling-only)
│   └── models.py        # Domain models (Reading, DeviceInfo, etc.)
├── tests/               # Unit tests
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

## Next Steps

1. ✅ Test serial communication
2. ⏭️ Implement MQTT publishing
3. Implement moving average calculation
4. Add continuous service mode
5. Add Home Assistant MQTT discovery
6. Create proper Python package (pyproject.toml)
7. Add systemd service
8. Add Web UI (future)

## Testing During Development

You can test individual components:

```bash
# Test serial with different baudrates
sg dialout -c "python3 test_serial.py"

# Test CPM reading details
sg dialout -c "python3 test_cpm_debug.py"

# Run unit tests
pytest tests/
```

## License

TBD
