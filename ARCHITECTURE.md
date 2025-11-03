# Architektur: GMC Geigerzähler zu MQTT Bridge

## 1. Überblick

Das System fungiert als Bridge zwischen einem GMC Geigerzähler (USB/TTY) und einem MQTT Broker. Es liest kontinuierlich Messwerte vom Geigerzähler aus und publiziert diese über MQTT, mit automatischer Home Assistant Discovery-Unterstützung.

### 1.1 Hauptanforderungen

- **Gerät**: GMC-800 v1.10 (primär), kompatibel mit neueren GMC Geräten (GMC-500/600 Serie)
- **Protokoll**: GQ-RFC1801
- **Messintervall**: 1 Sekunde (CPM-Wert)
- **Reporting**: 
  - Echtzeit: Jede Sekunde den aktuellen CPM-Wert
  - Aggregiert: Alle 10 Minuten gleitender Durchschnitt
- **Integration**: Home Assistant Auto-Discovery
- **Deployment**: Lang laufender Service (kein One-Shot-Script)
- **Mode**: Polling-Only (kein Heartbeat)

## 2. Komponentenarchitektur

### 2.1 Modulstruktur

```
gmc_geiger_mqtt/
├── __init__.py
├── __main__.py              # Entry point
├── config.py                # Configuration management
├── models.py                # Domain models (Reading, DeviceInfo, DeviceConfig)
├── device/
│   ├── __init__.py
│   ├── protocol.py          # GQ-RFC1801 Protokoll-Implementation
│   ├── connection.py        # Serielle Verbindung zum GMC Gerät
│   └── reader.py            # Polling-basiertes Auslesen der Werte
├── mqtt/
│   ├── __init__.py
│   ├── client.py            # MQTT Client Wrapper
│   ├── publisher.py         # Publishing Logik
│   └── discovery.py         # Home Assistant Discovery
├── processing/
│   ├── __init__.py
│   └── aggregator.py        # Gleitender Durchschnitt
├── service.py               # Haupt-Service Orchestrierung
└── exceptions.py            # Custom Exceptions
```

### 2.2 Komponenten-Beschreibung

#### 2.2.1 Device Layer (`device/`)

**protocol.py**
- Implementiert GQ-RFC1801 Kommandos
- Wichtigste Kommandos:
  - `<GETVER>>`: Device Info (Model, Version)
  - `<GETCPM>>`: Liest CPM-Wert (32-bit unsigned integer, 4 bytes)
  - `<GETSERIAL>>`: Seriennummer (falls unterstützt)

**Wichtig**: CPM wird als 4 Bytes zurückgegeben (MSB first):
```python
# Response: 4 bytes
# Example: 0x00 0x00 0x00 0x1C = 28 CPM
data = serial.read(4)
cpm = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]
```

```python
class GMCProtocol:
    """GQ-RFC1801 Protocol implementation."""
    
    CMD_GET_VER = b"<GETVER>>"
    CMD_GET_CPM = b"<GETCPM>>"
    CMD_GET_SERIAL = b"<GETSERIAL>>"
    
    @staticmethod
    def parse_version(response: bytes) -> tuple[str, str]:
        """Parse version response into (model, version)."""
        # Response format: "GMC-800Re1.10" (variable length, no null terminator guaranteed)
        version_str = response.decode('ascii', errors='ignore').strip()
        # Parse: model + version number
        match = re.search(r'^(.*?)(\d+\.\d+)$', version_str)
        if match:
            return match.group(1), match.group(2)
        return version_str, "unknown"
    
    @staticmethod
    def parse_cpm(response: bytes) -> int:
        """Parse CPM response (4 bytes, MSB first)."""
        if len(response) != 4:
            raise ValueError(f"Expected 4 bytes, got {len(response)}")
        return (response[0] << 24) | (response[1] << 16) | (response[2] << 8) | response[3]
    
    @staticmethod
    def parse_serial(response: bytes) -> str:
        """Parse serial number (7 bytes)."""
        if len(response) != 7:
            raise ValueError(f"Expected 7 bytes, got {len(response)}")
        return response.hex().upper()
```

**connection.py**
- Managed serielle Verbindung
- Connection pooling und auto-reconnect
- DTR/RTS Aktivierung für CH340 Chips

```python
class GMCConnection:
    """Manages serial connection to GMC device."""
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 5.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None
    
    def connect(self) -> None:
        """Establish connection with proper initialization."""
        self.serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout,
            write_timeout=self.timeout,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            rtscts=False,
            dsrdtr=False,
            xonxoff=False,
        )
        
        # DTR/RTS activation required for CH340 chips
        self.serial.setDTR(True)
        self.serial.setRTS(True)
        
        # Wait for device initialization
        time.sleep(0.5)
        
        # Clear buffers
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
    
    def send_command(self, command: bytes) -> None:
        """Send command and flush, clearing input buffer first."""
        self.serial.reset_input_buffer()  # Prevent stale data
        self.serial.write(command)
        self.serial.flush()
    
    def read_response(self, num_bytes: int, wait_ms: int = 100) -> bytes:
        """Read exact number of bytes after waiting."""
        time.sleep(wait_ms / 1000.0)
        data = self.serial.read(num_bytes)
        if len(data) != num_bytes:
            raise TimeoutError(f"Expected {num_bytes} bytes, got {len(data)}")
        return data
```

**reader.py**
- Polling-basierter Reader
- Kein Heartbeat, aktives Pollen alle N Sekunden

```python
class GMCReader:
    """Polling-based reader for GMC device."""
    
    def __init__(self, connection: GMCConnection, poll_interval: float = 1.0):
        self.connection = connection
        self.poll_interval = poll_interval
        self.protocol = GMCProtocol()
        self._stop_event = threading.Event()
        self._reading_callback: Optional[Callable[[Reading], None]] = None
    
    def start(self, callback: Callable[[Reading], None]) -> None:
        """Start polling loop in background thread."""
        self._reading_callback = callback
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        """Stop polling loop."""
        self._stop_event.set()
        if hasattr(self, '_thread'):
            self._thread.join(timeout=5.0)
    
    def _poll_loop(self) -> None:
        """Main polling loop."""
        logger.info("Starting polling loop")
        
        while not self._stop_event.is_set():
            try:
                # Send GETCPM command
                self.connection.send_command(self.protocol.CMD_GET_CPM)
                
                # Read 4-byte response
                response = self.connection.read_response(4, wait_ms=200)
                
                # Parse CPM value
                cpm = self.protocol.parse_cpm(response)
                
                # Create reading
                reading = Reading(cpm=cpm, timestamp=datetime.now())
                
                # Deliver to callback
                if self._reading_callback:
                    self._reading_callback(reading)
                
            except Exception as e:
                logger.error(f"Error reading CPM: {e}")
                # Continue polling even on error
            
            # Wait for next poll interval
            self._stop_event.wait(self.poll_interval)
        
        logger.info("Polling loop stopped")
```

#### 2.2.2 Processing Layer (`processing/`)

**aggregator.py**
- Berechnet gleitenden Durchschnitt über ein konfigurierbares Zeitfenster
- Thread-safe für concurrent access

```python
class MovingAverageAggregator:
    """Calculates moving average over a time window."""
    
    def __init__(self, window_size: int = 600):  # 10 minutes at 1 sample/sec
        self.window_size = window_size
        self.samples: deque[Reading] = deque(maxlen=window_size)
        self.lock = threading.Lock()
    
    def add_sample(self, reading: Reading) -> None:
        """Add a new reading to the window."""
        with self.lock:
            self.samples.append(reading)
    
    def get_average(self) -> Optional[AggregatedReading]:
        """Calculate current moving average."""
        with self.lock:
            if not self.samples:
                return None
            
            cpm_values = [r.cpm for r in self.samples]
            
            return AggregatedReading(
                cpm_avg=statistics.mean(cpm_values),
                cpm_min=min(cpm_values),
                cpm_max=max(cpm_values),
                sample_count=len(cpm_values),
                window_minutes=self.window_size / 60,
                timestamp=datetime.now()
            )
```

#### 2.2.3 MQTT Layer (`mqtt/`)

**client.py**
- Wrapper um paho-mqtt mit auto-reconnect

**publisher.py**
- Publiziert Readings als JSON
- Managed QoS und Retained Messages

**discovery.py**
- Home Assistant MQTT Discovery
- Registriert Sensoren automatisch

## 3. Datenfluss

```
┌─────────────────────┐
│   GMC Device        │
│   (Serial/USB)      │
└──────────┬──────────┘
           │ Polling every 1s
           │ <GETCPM>> → 4 bytes
           ▼
┌─────────────────────┐
│   GMCReader         │
│   (Polling Loop)    │
└──────────┬──────────┘
           │ Reading(cpm, timestamp)
           │
           ├──────────────────────────┐
           │                          │
           ▼                          ▼
┌─────────────────────┐    ┌─────────────────────┐
│  MQTT Publisher     │    │  Aggregator         │
│  (Realtime)         │    │  (Moving Avg)       │
│                     │    │                     │
│  Publish every 1s   │    │  Publish every 10m  │
└──────────┬──────────┘    └──────────┬──────────┘
           │                          │
           └────────┬─────────────────┘
                    ▼
           ┌─────────────────────┐
           │   MQTT Broker       │
           └──────────┬──────────┘
                      │
                      ▼
           ┌─────────────────────┐
           │  Home Assistant     │
           │  (MQTT Integration) │
           └─────────────────────┘
```

**Flow Details:**
1. GMCReader pollt Device jede Sekunde mit `<GETCPM>>`
2. Parsed Response → `Reading(cpm, timestamp)`
3. Reading wird an zwei Konsumenten weitergegeben:
   - MQTT Publisher (sofort publizieren)
   - Aggregator (für gleitenden Durchschnitt sammeln)
4. Aggregator berechnet alle 10 Minuten Durchschnitt und publiziert

## 4. MQTT Topics und Payloads

### 4.1 Topic-Schema

```
gmc/geiger/<device_id>/state          # Realtime CPM
gmc/geiger/<device_id>/state_avg      # 10-min average
gmc/geiger/<device_id>/availability   # Online/Offline
gmc/geiger/<device_id>/info           # Device info (retained)
```

`device_id` = Seriennummer oder `gmc800` als Fallback

### 4.2 Payload-Format

**Realtime State (`state`)**:
```json
{
  "cpm": 28,
  "usv_h": 0.182,
  "timestamp": "2024-01-15T10:30:45Z",
  "unit": "CPM"
}
```

**Averaged State (`state_avg`)**:
```json
{
  "cpm_avg": 25.4,
  "cpm_min": 18,
  "cpm_max": 35,
  "usv_h_avg": 0.1651,
  "window_minutes": 10,
  "sample_count": 600,
  "timestamp": "2024-01-15T10:30:00Z",
  "unit": "CPM"
}
```

**Device Info (`info`)** - Retained:
```json
{
  "model": "GMC-800Re",
  "firmware": "1.10",
  "serial": "05004D323533AB",
  "manufacturer": "GQ Electronics"
}
```

### 4.3 QoS Levels

- **State (realtime)**: QoS 0 (fire and forget, hohe Frequenz)
- **State (average)**: QoS 1 (at least once, wichtige Aggregation)
- **Device Info**: QoS 1, Retained
- **Availability**: QoS 1, Retained

## 5. Home Assistant Discovery

### 5.1 Discovery Topics

```
homeassistant/sensor/<device_id>/cpm/config
homeassistant/sensor/<device_id>/cpm_avg/config
homeassistant/sensor/<device_id>/usv_h/config
homeassistant/sensor/<device_id>/usv_h_avg/config
```

### 5.2 Discovery Payload Beispiel

**CPM Sensor (Realtime)**:
```json
{
  "name": "GMC-800 Radiation CPM",
  "unique_id": "gmc800_05004D323533AB_cpm",
  "state_topic": "gmc/geiger/05004D323533AB/state",
  "value_template": "{{ value_json.cpm }}",
  "unit_of_measurement": "CPM",
  "icon": "mdi:radioactive",
  "device": {
    "identifiers": ["gmc_05004D323533AB"],
    "name": "GMC-800 Geiger Counter",
    "model": "GMC-800Re",
    "manufacturer": "GQ Electronics",
    "sw_version": "1.10"
  },
  "availability_topic": "gmc/geiger/05004D323533AB/availability"
}
```

**µSv/h Sensor (Average)**:
```json
{
  "name": "GMC-800 Radiation (10min avg)",
  "unique_id": "gmc800_05004D323533AB_usv_h_avg",
  "state_topic": "gmc/geiger/05004D323533AB/state_avg",
  "value_template": "{{ value_json.usv_h_avg }}",
  "unit_of_measurement": "µSv/h",
  "icon": "mdi:radioactive",
  "device": {
    "identifiers": ["gmc_05004D323533AB"],
    "name": "GMC-800 Geiger Counter",
    "model": "GMC-800Re",
    "manufacturer": "GQ Electronics",
    "sw_version": "1.10"
  },
  "availability_topic": "gmc/geiger/05004D323533AB/availability"
}
```

### 5.3 Discovery Timing

- Discovery Messages werden beim Start publiziert
- Retained, damit HA sie bei einem Restart findet
- Nach Device Info Fetch (um korrekte Model/Version zu haben)

## 6. Konfiguration

### 6.1 config.yaml Schema

```yaml
device:
  port: /dev/ttyUSB0
  baudrate: 115200  # GMC-800 uses 115200, other models may vary
  timeout: 5.0      # seconds

sampling:
  interval: 1.0              # seconds between polls
  aggregation_window: 600    # seconds (10 minutes)
  aggregation_interval: 600  # publish average every 10 minutes

mqtt:
  broker: localhost
  port: 1883
  username: null
  password: null
  client_id: gmc-geiger-mqtt
  topic_prefix: gmc/geiger
  qos_realtime: 0
  qos_aggregate: 1
  homeassistant_discovery: true
  homeassistant_prefix: homeassistant

conversion:
  cpm_to_usv_factor: 0.0065  # Conversion factor CPM → µSv/h (device-specific)

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

### 6.2 Umgebungsvariablen (Optional)

Alle Config-Werte können per Env-Var überschrieben werden:
- `GMC_DEVICE_PORT`
- `GMC_MQTT_BROKER`
- `GMC_MQTT_USERNAME`
- `GMC_MQTT_PASSWORD`

## 7. Device Startup und Shutdown Sequenzen

### 7.1 Startup-Sequenz (Polling Mode)

```python
def initialize_device(config: DeviceConfig) -> GMCDevice:
    """Initialize GMC device with polling mode."""
    
    # 1. Open serial connection
    connection = GMCConnection(
        port=config.port,
        baudrate=config.baudrate,
        timeout=config.timeout
    )
    connection.connect()
    
    # 2. Get device info
    connection.send_command(GMCProtocol.CMD_GET_VER)
    version_data = connection.read_response(14, wait_ms=200)
    model, version = GMCProtocol.parse_version(version_data)
    
    # 3. Try to get serial (optional)
    try:
        connection.send_command(GMCProtocol.CMD_GET_SERIAL)
        serial_data = connection.read_response(7, wait_ms=100)
        serial = GMCProtocol.parse_serial(serial_data)
    except Exception:
        serial = None
    
    # 4. Create device info
    device_info = DeviceInfo(model=model, version=version, serial=serial)
    
    # 5. Create device with reader
    device = GMCDevice(connection, device_info)
    
    return device
```

**Key Points:**
- Einfacher Startup, keine komplexe State-Machine
- Buffer wird vor jedem Command gecleart
- Device Info als erstes holen für Discovery

### 7.2 Shutdown-Sequenz

```python
def shutdown_device(device: GMCDevice) -> None:
    """Clean shutdown of device."""
    
    logger.info("Shutting down GMC device")
    
    # 1. Stop reader
    if device.reader:
        device.reader.stop()
    
    # 2. Close serial connection
    if device.connection and device.connection.serial:
        try:
            device.connection.serial.close()
            logger.info("Serial connection closed")
        except Exception as e:
            logger.error(f"Error closing serial: {e}")
```

**Key Points:**
- Kein spezieller Cleanup notwendig (kein Heartbeat zu deaktivieren)
- Einfach Reader stoppen und Serial schließen

## 8. Error Handling und Resilienz

### 8.1 Device Connection Errors

- **Initial Connect Failure**: Retry mit exponential backoff (max 5 Versuche)
- **Read Timeout during polling**: Log error, continue polling
- **Serial Disconnect**: Versuche Reconnect, publiziere "offline" Status

### 8.2 MQTT Connection Errors

- Auto-reconnect via paho-mqtt
- Republish availability auf reconnect
- Buffer Readings falls MQTT down (max 1000 samples)

### 8.3 Invalid Readings

```python
def validate_reading(reading: Reading) -> bool:
    """Validate if reading is plausible."""
    # CPM should be reasonable (not hardware glitch)
    if reading.cpm > 100000:  # 100k CPM is extreme
        logger.warning(f"Suspicious reading: {reading.cpm} CPM")
        return False
    return True
```

### 8.4 Signal Handling

```python
def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    service.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
```

## 9. Paket-Struktur und Deployment

### 9.1 pyproject.toml

```toml
[project]
name = "gmc-geiger-mqtt"
version = "0.1.0"
description = "MQTT bridge for GMC Geiger counters"
requires-python = ">=3.8"
dependencies = [
    "pyserial>=3.5",
    "pyyaml>=6.0",
    "paho-mqtt>=1.6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "black>=23.0.0",
    "mypy>=1.0.0",
]

[project.scripts]
gmc-geiger-mqtt = "gmc_geiger_mqtt.__main__:main"

[build-system]
requires = ["setuptools>=65.0"]
build-backend = "setuptools.build_meta"
```

### 9.2 Systemd Service (Linux)

```ini
[Unit]
Description=GMC Geiger Counter MQTT Bridge
After=network.target

[Service]
Type=simple
User=geiger
Group=dialout
WorkingDirectory=/opt/gmc-geiger-mqtt
ExecStart=/opt/gmc-geiger-mqtt/.venv/bin/gmc-geiger-mqtt --config /etc/gmc-geiger-mqtt/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 9.3 Docker Support (Optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
CMD ["gmc-geiger-mqtt", "--config", "/config/config.yaml"]
```

## 10. Testing-Strategie (sparsam)

### 10.1 Unit Tests

Nur für kritische Business Logic:
- `GMCProtocol.parse_cpm()` - CPM Parsing
- `GMCProtocol.parse_version()` - Version Parsing
- `MovingAverageAggregator` - Durchschnittsberechnung
- Config Validation

**Keine Tests für:**
- Serial Communication (Integration Test Territory)
- MQTT Publishing (würde Mock-Broker brauchen)
- Service Orchestrierung (zu komplex)

### 10.2 Integration Tests (Optional, minimal)

- `test_device_connection.py`: Test mit echtem Device (manuell)
- `test_mqtt_flow.py`: Test mit lokalem Mosquitto (optional)

## 11. Logging

### 11.1 Log Levels

- **DEBUG**: Jede Command/Response, Buffer States
- **INFO**: Startup, Shutdown, Connection Events, jede 10. Reading
- **WARNING**: Ungültige Readings, Reconnects
- **ERROR**: Connection Failures, MQTT Errors

### 11.2 Strukturiertes Logging

```python
logger.info(
    "Reading received",
    extra={
        "cpm": reading.cpm,
        "usv_h": reading.to_usv_per_hour(),
        "timestamp": reading.timestamp.isoformat()
    }
)
```

## 12. Erweiterbarkeit

### 12.1 Zukünftige Features

**Web UI (Phase 2)**:
- Echtzeit-Chart der CPM-Werte
- Historische Daten (SQLite Backend)
- Konfiguration über Web Interface

**Multiple Devices**:
- Support für mehrere Geigerzähler parallel
- Aggregierte Ansicht über alle Devices

**Advanced Analytics**:
- Anomalie-Detektion (plötzliche Spikes)
- Langzeit-Trends
- Export zu InfluxDB/Prometheus

### 12.2 Plugin-Architektur (Future)

```python
class ReadingHandler(ABC):
    @abstractmethod
    def handle_reading(self, reading: Reading) -> None:
        pass

# Plugins
class MQTTHandler(ReadingHandler): ...
class InfluxDBHandler(ReadingHandler): ...
class WebSocketHandler(ReadingHandler): ...
```

## 13. Deployment-Checklist

- [ ] Config file angelegt und angepasst
- [ ] User hat Zugriff auf Serial Port (dialout Gruppe)
- [ ] Baudrate korrekt für Device-Modell (GMC-800 = 115200)
- [ ] MQTT Broker erreichbar
- [ ] Home Assistant MQTT Integration konfiguriert
- [ ] Systemd Service installiert (falls Linux)
- [ ] Logs rotieren konfiguriert
- [ ] CPM → µSv/h Conversion Factor korrekt für Tube-Typ

## 14. Known Issues und Workarounds

### 14.1 GMC-800 v1.10 Spezifika

- **Baudrate**: Verwendet 115200, nicht 57600 wie im RFC spezifiziert
- **CPM Response**: 4 Bytes (korrekt nach RFC), aber viele Beispiele zeigen 2 Bytes
- **Version String**: Kein Null-Terminator, variable Länge

### 14.2 CH340 USB-Serial Chip

- **DTR/RTS Required**: Muss explizit aktiviert werden
- **Buffer Clearing**: Input Buffer vor jedem Command clearen

### 14.3 Timing

- **Wait after command**: Mindestens 100ms vor Read
- **Connection init**: 500ms warten nach Serial Open
- **Poll interval**: Nicht unter 1 Sekunde (Device braucht Zeit)