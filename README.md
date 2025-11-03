# GMC Geiger Counter to MQTT Bridge

A Python application for reading radiation data from GMC Geiger counters and publishing it via MQTT.

## Status

**Current Phase:** ✅ Serial communication tested and working!

✅ Implemented:
- Serial communication with GMC devices (GQ-RFC1801 protocol)
- CPM reading and µSv/h conversion
- Device info retrieval (model, version, serial)
- Configuration system (YAML-based)
- Basic logging and test mode

🚧 Not yet implemented:
- MQTT publishing
- Moving average calculation
- Continuous service mode
- Home Assistant MQTT discovery
- Web UI

## Requirements

- Python 3.8+
- GMC Geiger counter (tested with GMC-800 v1.10, should work with other GMC models)
- USB connection to the device

## Installation

1. Clone the repository
2. Install dependencies using `uv`:
```bash
cd gmc-geiger-mqtt
uv pip install -r requirements.txt
```

Or with standard pip (in a virtual environment):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Make sure your user has access to the serial port:
```bash
sudo usermod -a -G dialout $USER
```
Then logout and login again, or use `sg dialout -c "your command"` to run commands in the dialout group.

## Configuration

Edit `config.yaml` to match your setup:

```yaml
device:
  port: "/dev/ttyUSB0"  # Change to your device port
  baudrate: 115200      # GMC-800 uses 115200
  timeout: 5.0
```

**Important:** The baudrate is **115200** for GMC-800, not 57600 as specified in GQ-RFC1801. Different models may use different baudrates.

## Testing

To test serial communication with your device:

```bash
# If you're in the dialout group already:
python3 run.py

# If you need to run with dialout permissions:
sg dialout -c "python3 run.py"
```

Or with a custom config file:
```bash
python3 run.py /path/to/config.yaml
```

This will:
1. Connect to the GMC device
2. Display device information (model, version, serial number)
3. Test heartbeat (may not be supported by all devices)
4. Continuously read CPM values every 2 seconds and display them
5. Press Ctrl+C to stop

Expected output:
```
2025-11-03 02:59:10 - src.main - INFO - Starting GMC Geiger test mode
2025-11-03 02:59:10 - src.main - INFO - Device: /dev/ttyUSB0 @ 115200 baud
2025-11-03 02:59:11 - src.gmc_device - INFO - Connecting to GMC device on /dev/ttyUSB0 at 115200 baud
2025-11-03 02:59:11 - src.gmc_device - INFO - Successfully connected to GMC device
2025-11-03 02:59:16 - src.gmc_device - INFO - Device info: GMC Device: GMC-800Re (v1.10, serial=05004D323533AB)
======================================================================
2025-11-03 02:59:16 - src.main - INFO - Connected to device: GMC Device: GMC-800Re (v1.10, serial=05004D323533AB)
======================================================================
2025-11-03 02:59:16 - src.main - INFO - Testing heartbeat...
2025-11-03 02:59:21 - src.main - WARNING - ✗ Heartbeat not supported or failed: Expected 2 bytes, got 0 bytes
2025-11-03 02:59:21 - src.main - INFO - Starting continuous reading mode (Ctrl+C to stop)...
======================================================================
2025-11-03 02:59:21 - src.main - INFO - [   1] 02:59:21 | CPM:    0 | µSv/h: 0.0000
2025-11-03 02:59:23 - src.main - INFO - [   2] 02:59:23 | CPM:    0 | µSv/h: 0.0000
...
```

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
│   ├── gmc_device.py    # GMC device communication
│   └── models.py        # Domain models (Reading, DeviceInfo, etc.)
├── tests/               # Unit tests
├── ARCHITECTURE.md      # Detailed architecture documentation
└── GQ-RFC1801.txt       # GMC protocol specification
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

Key design principles:
- Clean separation of concerns (device communication, data processing, MQTT publishing)
- Configuration-driven
- Extensible for future features (Web UI, etc.)
- Proper error handling and logging

## Known Issues

1. **Heartbeat command not supported**: The GMC-800 v1.10 does not respond to the `<HEARTBEAT>>` command. This is non-fatal and the application continues to work.

2. **Baudrate varies by model**: While GQ-RFC1801 specifies 57600 baud, the GMC-800 uses 115200. Check your device's documentation.

## Troubleshooting

### Device not found
- Check if the device is connected: `ls -l /dev/ttyUSB*`
- Verify user has permission: `sudo usermod -a -G dialout $USER` (then logout/login)
- Try: `sg dialout -c "python3 run.py"`

### Wrong baudrate
- GMC-800 uses 115200 baud (not 57600 as specified in GQ-RFC1801)
- Try different baudrates in `config.yaml` if connection fails
- Use `test_serial.py` to test different baudrates

### No data received
- Ensure no other program is accessing the serial port
- Try unplugging and replugging the device
- Check `dmesg | tail` for USB/serial errors
- Verify baudrate matches your device

## Next Steps

1. ✅ Test serial communication with device
2. ⏭️ Implement MQTT publishing
3. Implement moving average calculation
4. Add continuous service mode with proper signal handling
5. Add Home Assistant MQTT discovery
6. Add more tests
7. Create proper Python package with pyproject.toml
8. Add Web UI (future)

## License

TBD
