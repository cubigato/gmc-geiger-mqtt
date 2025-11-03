# Architektur: GMC Geigerzähler zu MQTT Bridge

> **Hinweis**: Diese Dokumentation wurde zuletzt aktualisiert, um die tatsächliche Implementierung widerzuspiegeln. Die beschriebene Architektur entspricht dem aktuellen Stand des Codes.

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
gmc-geiger-mqtt/
├── run.py                   # Entry point (startet die Anwendung)
├── config.yaml              # Konfigurationsdatei
├── requirements.txt         # Python-Abhängigkeiten
├── pytest.ini               # Pytest-Konfiguration (nur tests/ durchsuchen)
├── src/
│   ├── __init__.py
│   ├── main.py              # Hauptlogik (Service Mode & Test Mode)
│   ├── config.py            # Configuration management
│   ├── models.py            # Domain models (Reading, DeviceInfo, DeviceConfig, MQTTConfig, AggregatedReading)
│   ├── gmc_device.py        # GMC Geräte-Kommunikation (monolithisch: Protocol + Connection + Reader)
│   ├── mqtt/
│   │   ├── __init__.py
│   │   ├── client.py        # MQTT Client Wrapper mit Auto-Reconnect
│   │   ├── publisher.py     # Publishing Logik
│   │   └── discovery.py     # Home Assistant Discovery
│   └── processing/
│       ├── __init__.py
│       └── aggregator.py    # Gleitender Durchschnitt (MovingAverageAggregator)
├── tests/
│   ├── conftest.py          # Pytest-Konfiguration und Fixtures
│   ├── test_models.py       # Unit Tests für Domain Models
│   └── test_aggregator.py   # Unit Tests für Aggregator
└── manual_tests/            # Manuelle Hardware-Tests (nicht in CI/CD)
    ├── README.md            # Dokumentation für manuelle Tests
    ├── test_serial.py       # Serielle Verbindung testen
    ├── test_cpm_debug.py    # CPM-Reading debuggen
    ├── test_cpm_debug2.py   # Alternative CPM-Tests
    └── test_mqtt_messages.py # MQTT-Integration testen
```

**Hinweis**: Die Implementierung verwendet eine **monolithische Struktur** für die Device-Kommunikation (`gmc_device.py`), anstatt in separate Module aufzuteilen. Dies ist für die Projektgröße angemessen und reduziert unnötige Komplexität.

### 2.2 Komponenten-Beschreibung

#### 2.2.1 Device Layer (`gmc_device.py`)

Die Device-Kommunikation ist in einer **monolithischen Klasse** `GMCDevice` implementiert, die alle Aspekte der seriellen Kommunikation mit dem GMC-Geigerzähler verwaltet. Dies ist für die Projektgröße angemessen und vermeidet Over-Engineering.

**gmc_device.py**
- Implementiert GQ-RFC1801 Protokoll direkt in der `GMCDevice`-Klasse
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
class GMCDevice:
    """Handler for GMC Geiger counter device communication.
    
    Kombiniert Protokoll-Implementation, Connection Management und Reading-Logik
    in einer einzigen Klasse für einfachere Wartung.
    """
    
    # Command constants from GQ-RFC1801.txt
    CMD_GET_VER = b"<GETVER>>"
    CMD_GET_CPM = b"<GETCPM>>"
    CMD_GET_SERIAL = b"<GETSERIAL>>"
    
    def __init__(self, config: DeviceConfig):
        """
        Initialize the GMC device handler.

        Args:
            config: Device configuration including port, baudrate, and timeout
        """
        self.config = config
        self.serial: Optional[serial.Serial] = None
        self._device_info: Optional[DeviceInfo] = None
    
    def connect(self) -> None:
        """
        Establish connection to the GMC device.
        
        - Konfiguriert serielle Verbindung (115200 Baud für GMC-800)
        - Aktiviert DTR/RTS für CH340 USB-Serial Chips
        - Liest Device-Informationen aus
        
        Raises:
            GMCConnectionError: If connection fails
        """
        self.serial = serial.Serial(
            port=self.config.port,
            baudrate=self.config.baudrate,
            timeout=self.config.timeout,
            write_timeout=self.config.timeout,
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
        
        # Fetch device info
        self._device_info = self._get_device_info()
    
    def disconnect(self) -> None:
        """Close the connection to the GMC device."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.serial = None
    
    def is_connected(self) -> bool:
        """Check if the device is connected."""
        return self.serial is not None and self.serial.is_open
    
    def _send_command(self, command: bytes) -> None:
        """
        Send a command to the device.
        
        Wichtig: Leert den Input-Buffer VOR dem Senden, um stale data zu vermeiden.
        
        Args:
            command: Command bytes to send

        Raises:
            GMCCommandError: If sending fails
        """
        self._ensure_connected()
        self.serial.reset_input_buffer()  # Prevent stale data!
        self.serial.write(command)
        self.serial.flush()
    
    def _read_response(self, num_bytes: int) -> bytes:
        """
        Read a fixed number of bytes from the device.

        Args:
            num_bytes: Number of bytes to read

        Returns:
            Bytes read from device

        Raises:
            GMCCommandError: If reading fails or timeout occurs
        """
        self._ensure_connected()
        data = self.serial.read(num_bytes)
        if len(data) != num_bytes:
            raise GMCCommandError(
                f"Expected {num_bytes} bytes, got {len(data)} bytes"
            )
        return data
    
    def _read_until(self, terminator: bytes = b"\x00", max_bytes: int = 256) -> bytes:
        """
        Read bytes until a terminator is found or max_bytes is reached.
        
        Verwendet für variable-length Responses wie Version-String.

        Args:
            terminator: Byte sequence that marks end of data
            max_bytes: Maximum number of bytes to read

        Returns:
            Bytes read (excluding terminator)

        Raises:
            GMCCommandError: If reading fails
        """
        self._ensure_connected()
        data = bytearray()
        while len(data) < max_bytes:
            byte = self.serial.read(1)
            if not byte:
                break
            if byte == terminator:
                break
            data.extend(byte)
        return bytes(data)
    
    def _get_device_info(self) -> DeviceInfo:
        """
        Retrieve device information (version and model).
        
        Parsed Version-String (z.B. "GMC-800Re1.10") in Model und Version.

        Returns:
            DeviceInfo object with device details

        Raises:
            GMCCommandError: If command fails
        """
        # Get version string
        self._send_command(self.CMD_GET_VER)
        time.sleep(0.2)  # Wait for device to prepare response
        
        version_data = self._read_until(terminator=b"\x00", max_bytes=20)
        version_str = version_data.decode("ascii", errors="ignore").strip()
        
        # Parse version string (format is typically "GMC-800Re1.10")
        import re
        match = re.search(r"^(.*?)(\d+\.\d+)$", version_str)
        if match:
            model = match.group(1)
            version = match.group(2)
        else:
            model = version_str
            version = "unknown"
        
        # Try to get serial number (not all devices support this)
        serial_num = None
        try:
            self._send_command(self.CMD_GET_SERIAL)
            time.sleep(0.05)
            serial_data = self._read_response(7)
            serial_num = serial_data.hex().upper()
        except GMCCommandError:
            pass  # Device does not support serial number query
        
        return DeviceInfo(model=model, version=version, serial=serial_num)
    
    def get_cpm(self) -> Reading:
        """
        Get the current CPM (counts per minute) reading from the device.
        
        Sendet <GETCPM>> Kommando und liest 4 Bytes (32-bit unsigned integer, big-endian).

        Returns:
            Reading object with CPM value and timestamp

        Raises:
            GMCCommandError: If reading fails
        """
        self._ensure_connected()
        
        self._send_command(self.CMD_GET_CPM)
        time.sleep(0.1)  # Small delay for device to prepare response
        
        # CPM is returned as 4 bytes (32-bit unsigned integer, big-endian)
        data = self._read_response(4)
        cpm = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]
        
        timestamp = datetime.now()
        
        return Reading(cpm=cpm, timestamp=timestamp)
    
    @property
    def device_info(self) -> Optional[DeviceInfo]:
        """Get cached device information."""
        return self._device_info
    
    def __enter__(self):
        """Context manager entry - connects to device."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnects from device."""
        self.disconnect()
        return False
```

**Hinweis zum Polling**: Die Polling-Loop ist **nicht** in der `GMCDevice`-Klasse implementiert, sondern in `main.py` im Service Mode. Dies folgt dem Prinzip der Separation of Concerns - die Device-Klasse ist nur für die Kommunikation zuständig, während die Orchestrierung in der Main-Funktion stattfindet.

#### 2.2.2 Processing Layer (`processing/`)

**aggregator.py**
- Berechnet gleitenden Durchschnitt über ein konfigurierbares Zeitfenster
- Automatisches Entfernen alter Samples außerhalb des Zeitfensters
- Unterstützt konfigurierbare Publikations-Intervalle

```python
class MovingAverageAggregator:
    """
    Aggregates readings over a time window and calculates statistics.
    
    Maintains a sliding window of readings and can calculate:
    - Average CPM
    - Minimum CPM
    - Maximum CPM
    - Average µSv/h
    - Sample count
    """
    
    def __init__(
        self,
        window_seconds: int = 600,
        conversion_factor: float = 0.0065,
    ):
        """
        Initialize the aggregator.
        
        Args:
            window_seconds: Time window in seconds (default: 600 = 10 minutes)
            conversion_factor: CPM to µSv/h conversion factor
        """
        self.window_seconds = window_seconds
        self.conversion_factor = conversion_factor
        self._samples: deque[Reading] = deque()
        self._last_aggregation_time: Optional[datetime] = None
    
    def add_reading(self, reading: Reading) -> None:
        """
        Add a reading to the aggregator.
        
        Automatically removes old readings outside the time window.
        
        Args:
            reading: Reading to add
        """
        self._samples.append(reading)
        self._clean_old_samples(reading.timestamp)
    
    def _clean_old_samples(self, current_time: datetime) -> None:
        """
        Remove samples older than the time window.
        
        Args:
            current_time: Current timestamp to calculate window from
        """
        cutoff_time = current_time - timedelta(seconds=self.window_seconds)
        
        # Remove old samples from the left (oldest)
        while self._samples and self._samples[0].timestamp < cutoff_time:
            self._samples.popleft()
    
    def get_aggregated(self) -> Optional[AggregatedReading]:
        """
        Calculate and return aggregated statistics.
        
        Returns:
            AggregatedReading with statistics, or None if no samples available
        """
        if not self._samples:
            return None
        
        # Calculate statistics
        cpm_values = [reading.cpm for reading in self._samples]
        cpm_avg = sum(cpm_values) / len(cpm_values)
        cpm_min = min(cpm_values)
        cpm_max = max(cpm_values)
        
        # Calculate average µSv/h
        usv_h_avg = cpm_avg * self.conversion_factor
        
        # Use the timestamp of the most recent sample
        timestamp = self._samples[-1].timestamp
        
        return AggregatedReading(
            cpm_avg=cpm_avg,
            cpm_min=cpm_min,
            cpm_max=cpm_max,
            usv_h_avg=usv_h_avg,
            window_seconds=self.window_seconds,
            sample_count=len(self._samples),
            timestamp=timestamp,
            samples=list(self._samples),
        )
    
    def should_publish(self, current_time: datetime, interval_seconds: int) -> bool:
        """
        Check if enough time has passed since last aggregation to publish.
        
        Args:
            current_time: Current timestamp
            interval_seconds: Minimum interval between publications
        
        Returns:
            True if should publish, False otherwise
        """
        if self._last_aggregation_time is None:
            return True
        
        elapsed = (current_time - self._last_aggregation_time).total_seconds()
        return elapsed >= interval_seconds
    
    def mark_published(self, timestamp: datetime) -> None:
        """
        Mark that an aggregation was published at the given time.
        
        Args:
            timestamp: Timestamp of publication
        """
        self._last_aggregation_time = timestamp
    
    def get_sample_count(self) -> int:
        """
        Get the current number of samples in the window.
        
        Returns:
            Number of samples
        """
        return len(self._samples)
    
    def get_window_age(self) -> Optional[timedelta]:
        """
        Get the age of the oldest sample in the window.
        
        Returns:
            Timedelta of oldest sample age, or None if no samples
        """
        if not self._samples:
            return None
        
        oldest = self._samples[0]
        newest = self._samples[-1]
        return newest.timestamp - oldest.timestamp
    
    def clear(self) -> None:
        """Clear all samples from the aggregator."""
        self._samples.clear()
        self._last_aggregation_time = None
```

**Hinweis**: Die Methoden `should_publish()` und `mark_published()` sind wichtig für die Aggregations-Logik im Service Mode. Sie stellen sicher, dass aggregierte Daten nur in regelmäßigen Intervallen publiziert werden (z.B. alle 10 Minuten), unabhängig davon, wie oft neue Samples hinzugefügt werden.

#### 2.2.3 MQTT Layer (`mqtt/`)

**client.py**
- Wrapper um paho-mqtt mit auto-reconnect
- Callback-System für Connection-Events
- Context Manager Support

```python
class MQTTClient:
    """
    MQTT client wrapper with automatic reconnection and error handling.
    """
    
    def __init__(self, config: MQTTConfig):
        """Initialize MQTT client."""
        self.config = config
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._on_connect_callback: Optional[Callable] = None
        self._on_disconnect_callback: Optional[Callable] = None
    
    def connect(self) -> None:
        """
        Connect to MQTT broker.
        
        - Setzt Last Will and Testament (LWT) für Availability
        - Startet Network Loop in Background Thread
        - Wartet auf erfolgreiche Verbindung
        
        Raises:
            MQTTClientError: If connection fails
        """
        # Create MQTT client with LWT
        self._client = mqtt.Client(
            client_id=self.config.client_id,
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )
        
        # Set callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        
        # Set username/password if provided
        if self.config.username:
            self._client.username_pw_set(self.config.username, self.config.password)
        
        # Connect and start loop
        self._client.connect(self.config.broker, self.config.port, keepalive=60)
        self._client.loop_start()
    
    def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
    
    def publish(
        self,
        topic: str,
        payload: str,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        """
        Publish a message to MQTT broker.
        
        Args:
            topic: MQTT topic
            payload: Message payload (JSON string)
            qos: Quality of Service level (0, 1, or 2)
            retain: Whether to retain the message
        """
        if not self.is_connected():
            raise MQTTClientError("Not connected to MQTT broker")
        
        self._client.publish(topic, payload, qos=qos, retain=retain)
    
    def subscribe(self, topic: str, qos: int = 0) -> None:
        """Subscribe to an MQTT topic."""
        self._client.subscribe(topic, qos=qos)
    
    def set_on_connect_callback(self, callback: Callable) -> None:
        """Set callback to be called when connection is established."""
        self._on_connect_callback = callback
    
    def set_on_disconnect_callback(self, callback: Callable) -> None:
        """Set callback to be called when connection is lost."""
        self._on_disconnect_callback = callback
    
    def __enter__(self):
        """Context manager entry - connects to broker."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnects from broker."""
        self.disconnect()
        return False
```

**publisher.py**
- Publiziert Readings als JSON
- Managed QoS und Retained Messages
- Startup/Shutdown Sequenzen

```python
class MQTTPublisher:
    """
    Publisher for GMC Geiger counter readings via MQTT.
    
    Handles publishing of:
    - Realtime CPM readings
    - Aggregated readings (averages over time windows)
    - Device information
    - Availability status
    """
    
    def __init__(
        self,
        mqtt_client: MQTTClient,
        config: MQTTConfig,
        device_info: DeviceInfo,
        conversion_factor: float = 0.0065,
    ):
        """Initialize MQTT publisher."""
        self.client = mqtt_client
        self.config = config
        self.device_info = device_info
        self.conversion_factor = conversion_factor
        
        # Determine device ID from serial or use fallback
        self.device_id = self._get_device_id()
    
    def startup(self) -> None:
        """
        Perform startup sequence.
        
        Publishes:
        - Availability (online)
        - Device information
        """
        self.publish_availability(online=True)
        self.publish_device_info()
    
    def shutdown(self) -> None:
        """
        Perform shutdown sequence.
        
        Publishes:
        - Availability (offline)
        """
        self.publish_availability(online=False)
    
    def publish_realtime(self, reading: Reading) -> None:
        """Publish realtime CPM reading."""
        topic = self.config.get_topic(self.device_id, "state")
        
        payload = {
            "cpm": reading.cpm,
            "usv_h": round(reading.to_usv_per_hour(self.conversion_factor), 4),
            "timestamp": reading.timestamp.isoformat(),
            "unit": "CPM",
        }
        
        self.client.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=self.config.qos_realtime,
            retain=False,
        )
    
    def publish_aggregated(self, aggregated: AggregatedReading) -> None:
        """Publish aggregated reading (average over time window)."""
        topic = self.config.get_topic(self.device_id, "state_avg")
        
        payload = aggregated.to_dict(self.conversion_factor)
        
        self.client.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=self.config.qos_aggregate,
            retain=False,
        )
    
    def publish_availability(self, online: bool = True) -> None:
        """Publish availability status."""
        topic = self.config.get_topic(self.device_id, "availability")
        payload = "online" if online else "offline"
        
        self.client.publish(
            topic=topic,
            payload=payload,
            qos=1,
            retain=self.config.retain_availability,
        )
    
    def publish_device_info(self) -> None:
        """Publish device information (retained message)."""
        topic = self.config.get_topic(self.device_id, "info")
        
        payload = {
            "model": self.device_info.model,
            "firmware": self.device_info.version,
            "serial": self.device_info.serial,
            "manufacturer": "GQ Electronics",
        }
        
        self.client.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=self.config.qos_info,
            retain=self.config.retain_info,
        )
```

**discovery.py**
- Home Assistant MQTT Discovery
- Registriert Sensoren automatisch
- Unterstützt Entfernen von Discovery-Nachrichten

```python
class HomeAssistantDiscovery:
    """
    Home Assistant MQTT Discovery implementation.
    
    Automatically registers sensors in Home Assistant via MQTT discovery protocol.
    """
    
    def __init__(
        self,
        mqtt_client: MQTTClient,
        config: MQTTConfig,
        device_info: DeviceInfo,
        device_id: str,
    ):
        """Initialize Home Assistant discovery."""
        self.client = mqtt_client
        self.config = config
        self.device_info = device_info
        self.device_id = device_id
    
    def publish_discovery(self) -> None:
        """
        Publish all discovery messages for Home Assistant.
        
        Creates sensors for:
        - Realtime CPM (counts per minute)
        - Realtime radiation level (µSv/h)
        - Average CPM
        - Average radiation level
        """
        self._publish_cpm_sensor()
        self._publish_radiation_sensor()
        self._publish_avg_cpm_sensor()
        self._publish_avg_radiation_sensor()
    
    def remove_discovery(self) -> None:
        """
        Remove discovery messages (publish empty payloads).
        
        This removes the sensors from Home Assistant.
        """
        sensors = ["cpm", "radiation", "cpm_avg", "radiation_avg"]
        for sensor in sensors:
            discovery_topic = (
                f"{self.config.homeassistant_prefix}/sensor/"
                f"{self.device_id}/{sensor}/config"
            )
            self.client.publish(
                topic=discovery_topic,
                payload="",
                qos=1,
                retain=True,
            )
```

## 3. Datenfluss

```
┌─────────────────────┐
│   GMC Device        │
│   (Serial/USB)      │
└──────────┬──────────┘
           │ GMCDevice.get_cpm()
           │ <GETCPM>> → 4 bytes
           ▼
┌─────────────────────────────────────────────────┐
│   Main Loop (main.py:service_mode)              │
│   - Polling every 1s                            │
│   - Orchestriert alle Komponenten               │
│                                                 │
│   while not shutdown_requested:                 │
│       reading = device.get_cpm()                │
│       publisher.publish_realtime(reading)       │
│       aggregator.add_reading(reading)           │
│       if aggregator.should_publish(...):        │
│           publisher.publish_aggregated(...)     │
└──────────┬──────────────────────────────────────┘
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
1. **Main Loop** (`main.py:service_mode()`) orchestriert den gesamten Ablauf
2. Pollt `GMCDevice.get_cpm()` jede Sekunde mit `<GETCPM>>`
3. Parsed Response → `Reading(cpm, timestamp)`
4. Reading wird verarbeitet:
   - MQTT Publisher publiziert sofort (Realtime-Topic)
   - Aggregator fügt Reading zum Zeitfenster hinzu
5. Aggregator prüft via `should_publish()`, ob 10 Minuten vergangen sind
6. Falls ja: Aggregierte Werte werden publiziert
7. Home Assistant empfängt beide Topics via MQTT Integration

**Hinweis**: Die Polling-Loop ist in `main.py` implementiert, nicht in einer separaten `GMCReader`-Klasse. Dies folgt dem Prinzip der Separation of Concerns - die Device-Klasse ist nur für die Kommunikation zuständig, während die Orchestrierung in der Main-Funktion stattfindet.

### 3.1 Test Mode (ohne MQTT)

Die Anwendung unterstützt einen **Test Mode**, um die serielle Kommunikation mit dem GMC-Gerät ohne MQTT-Verbindung zu testen. Dies ist nützlich für:
- Ersteinrichtung und Hardware-Debugging
- Überprüfung der seriellen Verbindung
- Testen verschiedener Baudrates
- Verifizierung der CPM-Werte

**Aktivierung**: In `config.yaml` `mqtt.enabled: false` setzen

**Ablauf im Test Mode** (`main.py:test_device_reading()`):
```
┌─────────────────────┐
│   GMC Device        │
│   (Serial/USB)      │
└──────────┬──────────┘
           │ get_cpm() every 2s
           ▼
┌─────────────────────┐
│   Test Loop         │
│   - Liest CPM       │
│   - Loggt zu stdout │
│   - Keine MQTT      │
└─────────────────────┘
```

**Beispiel-Output**:
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

**Verwendung**: `python3 run.py` (mit `mqtt.enabled: false` in config.yaml)

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
  enabled: true              # Set to false for test mode (no MQTT)
  broker: localhost
  port: 1883
  username: null             # Leave empty for anonymous
  password: null             # Leave empty for anonymous
  client_id: gmc-geiger-mqtt
  topic_prefix: gmc/geiger
  qos_realtime: 0            # QoS for realtime readings (0 = fire and forget)
  qos_aggregate: 1           # QoS for aggregated readings (1 = at least once)
  qos_info: 1                # QoS for device info (1 = at least once)
  retain_info: true          # Retain device info messages
  retain_availability: true  # Retain availability messages
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

## 7. Service Startup und Shutdown Sequenzen

Die Startup- und Shutdown-Logik ist in `main.py` in der `service_mode()` Funktion implementiert.

### 7.1 Startup-Sequenz (Service Mode)

```python
def service_mode(config: Config) -> int:
    """Service mode: Read from device, aggregate, and publish via MQTT."""
    
    # 1. Load configuration
    device_config = config.get_device_config()
    mqtt_config = config.get_mqtt_config()
    sampling_config = config.get_sampling_config()
    conversion_factor = config.get_conversion_factor()
    
    # 2. Connect to GMC device
    device = GMCDevice(device_config)
    device.connect()
    # Device info is fetched automatically in connect()
    
    # 3. Connect to MQTT broker
    mqtt_client = MQTTClient(mqtt_config)
    mqtt_client.connect()
    
    # 4. Initialize publisher
    publisher = MQTTPublisher(
        mqtt_client=mqtt_client,
        config=mqtt_config,
        device_info=device.device_info,
        conversion_factor=conversion_factor,
    )
    
    # 5. Perform startup sequence (publish availability + device info)
    publisher.startup()
    
    # 6. Initialize Home Assistant Discovery (if enabled)
    if mqtt_config.homeassistant_discovery:
        discovery = HomeAssistantDiscovery(
            mqtt_client=mqtt_client,
            config=mqtt_config,
            device_info=device.device_info,
            device_id=publisher.device_id,
        )
        discovery.publish_discovery()
    
    # 7. Initialize aggregator
    aggregator = MovingAverageAggregator(
        window_seconds=sampling_config.get("aggregation_window", 600),
        conversion_factor=conversion_factor,
    )
    
    # 8. Start main polling loop
    # (siehe Abschnitt 3 - Datenfluss)
```

**Key Points:**
- Alle Komponenten werden einzeln initialisiert
- Device Info wird automatisch beim Connect geholt
- Publisher ruft `startup()` auf, um Availability und Device Info zu publizieren
- Home Assistant Discovery wird nach Device-Connect publiziert (damit korrekte Device Info vorhanden)
- Aggregator wird mit konfigurierbarem Zeitfenster initialisiert
- Keine separate Reader-Klasse - Polling direkt in Main Loop

### 7.2 Shutdown-Sequenz

```python
def service_mode(config: Config) -> int:
    """Service mode with cleanup in finally block."""
    
    try:
        # ... main loop ...
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C)")
    
    finally:
        # Cleanup sequence
        logger.info("Performing shutdown sequence...")
        
        # 1. Publish offline status
        if publisher:
            try:
                publisher.shutdown()  # Publishes availability=offline
            except Exception as e:
                logger.error(f"Error during publisher shutdown: {e}")
        
        # 2. Disconnect MQTT
        if mqtt_client:
            try:
                mqtt_client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting MQTT: {e}")
        
        # 3. Disconnect device
        if device:
            try:
                device.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting device: {e}")
        
        logger.info("Shutdown complete")
    
    return 0
```

**Key Points:**
- Shutdown wird im `finally` Block durchgeführt (garantiert Ausführung)
- Reihenfolge: Publisher (offline status) → MQTT → Device
- Jeder Schritt ist in try/except, damit ein Fehler nicht den Rest blockiert
- Kein spezieller Device-Cleanup notwendig (kein Heartbeat zu deaktivieren)
- Publisher.shutdown() publiziert "offline" Status mit retained flag

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

### 9.1 Dependency Management

**Aktuell**: Die Anwendung verwendet `requirements.txt` für Dependency Management:

```txt
# Core dependencies
pyserial>=3.5
pyyaml>=6.0
paho-mqtt>=1.6.1

# Testing dependencies (optional)
pytest>=7.4.0
pytest-cov>=4.1.0
```

**Installation mit uv**:
```bash
# Create virtual environment
uv venv

# Activate venv
source .venv/bin/activate  # Linux/Mac
# Or: .venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -r requirements.txt
```

**Entry Point**: Die Anwendung wird über `run.py` gestartet:
```bash
python3 run.py
```

**Zukünftig (optional)**: Migration zu `pyproject.toml` für moderneren Python-Paketbau:

```toml
[project]
name = "gmc-geiger-mqtt"
version = "0.1.0"
description = "MQTT bridge for GMC Geiger counters"
requires-python = ">=3.8"
dependencies = [
    "pyserial>=3.5",
    "pyyaml>=6.0",
    "paho-mqtt>=1.6.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
]

[project.scripts]
gmc-geiger-mqtt = "src.main:main"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
```

Dies würde ermöglichen:
```bash
pip install -e .
gmc-geiger-mqtt  # Direkt ausführbar
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

Die Anwendung hat Unit Tests für kritische Business Logic:

**Vorhandene Tests** (in `tests/`):

- **`conftest.py`**: Pytest-Konfiguration und gemeinsame Fixtures
- **`test_models.py`**: Tests für Domain Models
  - `Reading` Validierung
  - `DeviceInfo` Parsing
  - `DeviceConfig` Validierung
  - `MQTTConfig` Validierung
  - `AggregatedReading.to_dict()` Format
  
- **`test_aggregator.py`**: Tests für `MovingAverageAggregator`
  - `add_reading()` - Hinzufügen von Samples
  - `get_aggregated()` - Berechnung von Durchschnitt, Min, Max
  - `_clean_old_samples()` - Automatisches Entfernen alter Samples
  - `should_publish()` - Publikations-Timing
  - `mark_published()` - Tracking der letzten Publikation
  - `get_sample_count()` - Sample-Anzahl
  - `get_window_age()` - Fenster-Alter
  - `clear()` - Zurücksetzen des Aggregators
  - `to_dict()` Format-Validierung

**Test-Ausführung**:
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

**Keine Tests für:**
- Serial Communication (Integration Test Territory, benötigt Hardware)
- MQTT Publishing (würde Mock-Broker benötigen)
- Service Orchestrierung (zu komplex, manuelles Testing ausreichend)
- `GMCDevice`-Klasse (benötigt echtes Hardware-Device)

### 10.2 Integration Tests (Optional, minimal)

**Manuelle Hardware-Tests** (in `manual_tests/`):

Die folgenden Tests benötigen ein physisches GMC-Gerät und sind **nicht** Teil der automatisierten Test-Suite:

- `test_serial.py`: Test serielle Verbindung mit verschiedenen Baudrates
- `test_cpm_debug.py`: Detailliertes CPM-Reading-Debugging
- `test_cpm_debug2.py`: Alternative CPM-Reading-Tests
- `test_mqtt_messages.py`: Testen von MQTT-Nachrichten (benötigt laufenden Broker)

**Ausführung manueller Tests**:
```bash
# Direkt ausführen (benötigt Hardware)
python3 manual_tests/test_serial.py

# Mit sg für serial port access
sg dialout -c "python3 manual_tests/test_serial.py"
```

**Wichtig**: Diese Tests werden durch `pytest` **nicht** automatisch ausgeführt, da sie Hardware benötigen. Die `pytest.ini` Konfiguration schließt `manual_tests/` explizit aus und durchsucht nur `tests/`.

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