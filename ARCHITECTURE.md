# Architektur: GMC Geigerzähler zu MQTT Bridge

## 1. Überblick

Das System fungiert als Bridge zwischen einem GMC Geigerzähler (USB/TTY) und einem MQTT Broker. Es liest kontinuierlich Messwerte vom Geigerzähler aus und publiziert diese über MQTT, mit automatischer Home Assistant Discovery-Unterstützung.

### 1.1 Hauptanforderungen

- **Gerät**: GMC-800 v1.10 (primär), kompatibel mit neueren GMC Geräten (GMC-500/600 Serie)
- **Protokoll**: GQ-RFC1801
- **Messintervall**: 1 Sekunde (CPS-Wert)
- **Reporting**: 
  - Echtzeit: Jede Sekunde den aktuellen CPS-Wert
  - Aggregiert: Alle 10 Minuten gleitender Durchschnitt
- **Integration**: Home Assistant Auto-Discovery
- **Deployment**: Lang laufender Service (kein One-Shot-Script)

## 2. Komponentenarchitektur

### 2.1 Modulstruktur

```
gmc_geiger_mqtt/
├── __init__.py
├── __main__.py              # Entry point
├── config.py                # Configuration management
├── device/
│   ├── __init__.py
│   ├── protocol.py          # GQ-RFC1801 Protokoll-Implementation
│   ├── connection.py        # Serielle Verbindung zum GMC Gerät
│   └── reader.py            # Kontinuierliches Auslesen der Werte
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
  - `<GETVER>>`: Hardware-Modell und Version abrufen
  - `<HEARTBEAT1>>`: Aktiviert kontinuierliches Senden von CPS-Werten (1 Hz)
  - `<HEARTBEAT0>>`: Deaktiviert Heartbeat-Modus
  - `<GETCPS>>`: Manuelles Abrufen von CPS-Werten (Polling-Modus Fallback)
- Kapselung der Low-Level Protokoll-Details
- Bytestring-Handling und Response-Parsing

**connection.py**
- Verwaltet serielle Verbindung zum Gerät
- Serial Port Setup (115200 baud, 8N1)
- DTR/RTS Pin-Management (für CH340 Chips)
- Connection Health Monitoring
- Automatische Reconnect-Logik mit Backoff
- Thread-safe Operations

**reader.py**
- **HEARTBEAT-Modus (Standard)**: Kontinuierliches Lesen von Push-Daten
  - Gerät sendet automatisch alle 1s einen 4-Byte CPS-Wert
  - Blocking Read mit Timeout-Handling
  - Buffer-Overflow Protection
- **Polling-Modus (Fallback)**: Periodisches Senden von `<GETCPS>>`
  - Timer-basiert (1 Hz)
  - Request-Response Handling
- Asynchrone Event-basierte Architektur oder Threading
- Queue für gemessene Werte
- Error Recovery bei Lesefehler
- Modus-Switch bei wiederholten Read-Fehlern

```
┌──────────────────┐
│  GMC Geigerzähler │
│    (USB/TTY)      │
└─────────┬─────────┘
          │ 1. Startup: <HEARTBEAT1>>
          │ Serial (115200 baud)
          │ 2. Push: 4 Bytes CPS (1 Hz)
          ▼
┌──────────────────────┐
│   Device Reader      │
│  (reader.py)         │
│  HEARTBEAT Mode      │
└─────────┬────────────┘
          │ CPS Value
          ├──────────────────────────────┐
          │                              │
          ▼                              ▼
┌──────────────────────┐    ┌────────────────────────┐
│  MQTT Publisher      │    │   Aggregator           │
│  (Echtzeit)          │    │   (10 Min Window)      │
└─────────┬────────────┘    └────────────┬───────────┘
          │                              │
          │ Every 1s                     │ Every 10 min
          │                              │
          ▼                              ▝
┌──────────────────────────────────────────────────────┐
│              MQTT Broker                              │
└─────────┬────────────────────────────────────────────┘
          │
          │ Subscribe
          ▼
┌──────────────────────┐
│  Home Assistant      │
└──────────────────────┘

Shutdown: <HEARTBEAT0>> → Clean State
```

#### 2.2.2 Processing Layer (`processing/`)

**aggregator.py**
- Sammelt CPS-Messungen in einem Zeitfenster
- Berechnet gleitenden Durchschnitt
- Zeitfenster: 10 Minuten (600 Messwerte bei 1 Hz)
- Implementierung: Sliding Window mit Circular Buffer oder deque
- Statistische Zusatzwerte (optional):
  - Minimum, Maximum
  - Standardabweichung
  - Median

#### 2.2.3 MQTT Layer (`mqtt/`)

**client.py**
- Paho-MQTT Client Wrapper
- Connection Management
- Last Will & Testament (LWT) für Verfügbarkeitsstatus
- Reconnect-Logik
- QoS Management

**publisher.py**
- Publish von Echtzeit-Messwerten (jede Sekunde)
- Publish von aggregierten Werten (alle 10 Minuten)
- Publish von Gerätestatus (online/offline)
- JSON Payload Formatierung

**discovery.py**
- Home Assistant MQTT Discovery Implementation
- Discovery-Nachrichten für:
  - Echtzeit CPS Sensor
  - Durchschnitts CPS Sensor
  - Geräte-Informationen (Modell, Version, Hersteller)
- Retain-Flag für Discovery-Nachrichten

#### 2.2.4 Configuration (`config.py`)

- Laden der `config.yaml`
- Validation der Konfiguration
- Default-Werte
- Environment Variable Overrides (optional, für Secrets)

#### 2.2.5 Service Orchestrierung (`service.py`)

- Hauptevent-Loop
- Lifecycle Management:
  - Startup: Initialisierung aller Komponenten
  - Running: Koordination zwischen Device Reader, Aggregator und MQTT
  - Shutdown: Graceful Cleanup
- Signal Handling (SIGTERM, SIGINT)
- Logging Setup

## 3. Datenfluss

```
┌──────────────────┐
│  GMC Geigerzähler │
│    (USB/TTY)      │
└─────────┬─────────┘
          │ Serial (115200 baud)
          │ <GETCPS>> (1 Hz)
          ▼
┌──────────────────────┐
│   Device Reader      │
│  (reader.py)         │
└─────────┬────────────┘
          │ CPS Value
          ├──────────────────────────────┐
          │                              │
          ▼                              ▼
┌──────────────────────┐    ┌────────────────────────┐
│  MQTT Publisher      │    │   Aggregator           │
│  (Echtzeit)          │    │   (10 Min Window)      │
└─────────┬────────────┘    └────────────┬───────────┘
          │                              │
          │ Every 1s                     │ Every 10 min
          │                              │
          ▼                              ▼
┌──────────────────────────────────────────────────────┐
│              MQTT Broker                              │
└─────────┬────────────────────────────────────────────┘
          │
          │ Subscribe
          ▼
┌──────────────────────┐
│  Home Assistant      │
└──────────────────────┘
```

## 4. MQTT Topics und Payloads

### 4.1 Topic-Schema

Base Topic: `gmc_geiger/{device_id}/`

- `gmc_geiger/{device_id}/cps` - Echtzeit CPS Werte
- `gmc_geiger/{device_id}/cps_avg` - Durchschnitts CPS (10 Min)
- `gmc_geiger/{device_id}/availability` - Online/Offline Status
- `gmc_geiger/{device_id}/device_info` - Geräte-Informationen

`{device_id}` wird entweder aus Config gelesen oder aus Serial Number / MAC-Address generiert.

### 4.2 Payload-Format

**Echtzeit CPS:**
```json
{
  "cps": 28,
  "timestamp": "2024-01-15T10:30:45Z",
  "unit": "cps"
}
```

**Durchschnitts CPS:**
```json
{
  "cps_avg": 25.4,
  "cps_min": 18,
  "cps_max": 35,
  "window_minutes": 10,
  "sample_count": 600,
  "timestamp": "2024-01-15T10:30:00Z",
  "unit": "cps"
}
```

**Availability:**
```
online / offline
```
(Simple String, nicht JSON)

**Device Info:**
```json
{
  "model": "GMC-800",
  "firmware": "Re 1.10",
  "manufacturer": "GQ Electronics"
}
```

### 4.3 QoS Levels

- CPS Echtzeit: QoS 0 (at most once) - bei 1 Hz ist Verlust akzeptabel
- CPS Durchschnitt: QoS 1 (at least once) - wichtigere Daten
- Availability: QoS 1, Retain=True
- Discovery: QoS 1, Retain=True

## 5. Home Assistant Discovery

### 5.1 Discovery Topics

Home Assistant verwendet das Schema:
```
homeassistant/{component}/{device_id}/{object_id}/config
```

Unsere Discovery-Nachrichten:
- `homeassistant/sensor/gmc_geiger_{device_id}/cps/config`
- `homeassistant/sensor/gmc_geiger_{device_id}/cps_avg/config`

### 5.2 Discovery Payload Beispiel

**CPS Sensor:**
```json
{
  "name": "Radiation CPS",
  "unique_id": "gmc_geiger_{device_id}_cps",
  "state_topic": "gmc_geiger/{device_id}/cps",
  "value_template": "{{ value_json.cps }}",
  "unit_of_measurement": "cps",
  "icon": "mdi:radioactive",
  "device": {
    "identifiers": ["gmc_geiger_{device_id}"],
    "name": "GMC Geigerzähler",
    "model": "GMC-800",
    "manufacturer": "GQ Electronics",
    "sw_version": "Re 1.10"
  },
  "availability_topic": "gmc_geiger/{device_id}/availability"
}
```

**CPS Average Sensor:**
```json
{
  "name": "Radiation CPS (10min avg)",
  "unique_id": "gmc_geiger_{device_id}_cps_avg",
  "state_topic": "gmc_geiger/{device_id}/cps_avg",
  "value_template": "{{ value_json.cps_avg }}",
  "unit_of_measurement": "cps",
  "icon": "mdi:radioactive",
  "device": {
    "identifiers": ["gmc_geiger_{device_id}"],
    "name": "GMC Geigerzähler",
    "model": "GMC-800",
    "manufacturer": "GQ Electronics",
    "sw_version": "Re 1.10"
  },
  "availability_topic": "gmc_geiger/{device_id}/availability"
}
```

### 5.3 Discovery Timing

- Discovery-Nachrichten beim Startup senden
- Mit Retain-Flag, damit Home Assistant sie nach Neustart wiederfindet
- Erneut senden nach MQTT-Reconnect

## 6. Konfiguration

### 6.1 config.yaml Schema

```yaml
# Serial Port Konfiguration
device:
  port: /dev/ttyUSB0
  baud_rate: 115200  # Optional, default: 115200
  timeout: 2  # Sekunden, optional
  mode: heartbeat  # 'heartbeat' oder 'polling', default: heartbeat
  # read_interval: 1.0  # Nur für Polling-Mode, Sekunden, optional

### 7.1 Device Connection Errors

**Problem**: Serial Device nicht erreichbar, USB getrennt, Gerät antwortet nicht

**Strategie**:
- Exponential Backoff Reconnect (1s, 2s, 4s, 8s, max 60s)
- Logging aller Connection-Fehler
- MQTT Availability auf "offline" setzen
- Weiterlaufen des Services (nicht crashen)

# MQTT Broker Konfiguration
mqtt:
  host: localhost
  port: 1883  # Optional, default: 1883
  username: mqtt_user  # Optional
  password: mqtt_password  # Optional
  client_id: gmc_geiger_bridge  # Optional, default: auto-generated
  
  # Topic Konfiguration
  base_topic: gmc_geiger  # Optional, default: gmc_geiger
  device_id: sensor_01  # Optional, default: auto-generated from device
  
  # Home Assistant Discovery
  discovery_prefix: homeassistant  # Optional, default: homeassistant
  discovery_enabled: true  # Optional, default: true

# Aggregation Einstellungen
aggregation:
  window_minutes: 10  # Optional, default: 10
  publish_interval_seconds: 600  # Optional, default: 600 (10 min)

# Logging
logging:
  level: INFO  # DEBUG, INFO, WARNING, ERROR
  file: null  # Optional, für File-Logging
```

### 6.2 Umgebungsvariablen (Optional)

Für Secrets, mit Vorrang vor config.yaml:
- `GMC_MQTT_USERNAME`
- `GMC_MQTT_PASSWORD`
- `GMC_DEVICE_PORT`

## 7. Device Startup und Shutdown Sequenzen

### 7.1 Startup-Sequenz (HEARTBEAT Mode)

**Ziel**: Gerät in definierten, sauberen Zustand versetzen, auch nach unsauberem Shutdown

```python
def initialize_device():
    # 1. Serial Port öffnen
    serial_port = open_serial_port(port, baud=115200)
    
    # 2. DTR/RTS aktivieren (für CH340)
    serial_port.setDTR(True)
    serial_port.setRTS(True)
    time.sleep(0.1)  # Hardware settle time
    
    # 3. HEARTBEAT stoppen (falls von früher noch aktiv)
    serial_port.write(b"<HEARTBEAT0>>")
    time.sleep(0.2)  # Warten bis Gerät Command verarbeitet hat
    
    # 4. Serial Buffer leeren (alte/ungelesene Daten)
    serial_port.reset_input_buffer()
    serial_port.reset_output_buffer()
    
    # 5. Verbindungstest und Device Info abrufen
    serial_port.write(b"<GETVER>>")
    version_response = serial_port.read(64)
    if not version_response:
        raise DeviceConnectionError("No response from device")
    
    # 6. Parse Device Info
    model, firmware = parse_version(version_response)
    logger.info(f"Connected to {model} {firmware}")
    
    # 7. HEARTBEAT aktivieren
    serial_port.write(b"<HEARTBEAT1>>")
    time.sleep(0.1)
    
    # 8. Erste Messung zur Validierung
    first_reading = serial_port.read(4)
    if len(first_reading) != 4:
        raise DeviceConnectionError("Invalid heartbeat data")
    
    return serial_port, model, firmware
```

**Wichtige Punkte**:
- `<HEARTBEAT0>>` VOR Buffer-Clear verhindert Race-Conditions
- Kurze Sleeps geben dem Gerät Zeit zur Verarbeitung
- `<GETVER>>` als Health-Check statt blind `<HEARTBEAT1>>` zu aktivieren
- Erste Messung validieren (4 Bytes erwartet)

### 7.2 Shutdown-Sequenz

**Ziel**: Gerät in Clean State hinterlassen, keine hängenden Heartbeats

```python
def shutdown_device():
    # 1. Signal Reading-Thread zum Stop
    stop_reading_flag.set()
    
    # 2. Warte auf Thread-Ende (mit Timeout)
    reading_thread.join(timeout=5.0)
    
    # 3. HEARTBEAT deaktivieren (KRITISCH!)
    try:
        serial_port.write(b"<HEARTBEAT0>>")
        serial_port.flush()  # Ensure command is sent
        time.sleep(0.2)  # Warten bis verarbeitet
    except Exception as e:
        logger.error(f"Failed to disable heartbeat: {e}")
    
    # 4. MQTT: Offline-Status publizieren
    mqtt_client.publish(
        f"{base_topic}/availability",
        "offline",
        qos=1,
        retain=True
    )
    
    # 5. MQTT Message Queue flushen
    mqtt_client.loop_stop()
    
    # 6. MQTT Disconnect
    mqtt_client.disconnect()
    
    # 7. Serial Port schließen
    serial_port.close()
    
    logger.info("Clean shutdown completed")
```

**Wichtige Punkte**:
- `<HEARTBEAT0>>` mit Retry-Logik (best effort)
- Auch bei Fehlern weitermachen (Shutdown darf nicht hängen)
- MQTT Offline NACH Heartbeat-Stop (konsistenter State)
- Timeout für alle Blocking-Operationen

### 7.3 Polling-Mode Startup (Fallback)

```python
def initialize_device_polling():
    # 1-4: Identisch zu Heartbeat-Mode
    # ...
    
    # 5. Sicherstellen dass kein Heartbeat läuft
    serial_port.write(b"<HEARTBEAT0>>")
    time.sleep(0.2)
    serial_port.reset_input_buffer()
    
    # 6. Device Info abrufen
    serial_port.write(b"<GETVER>>")
    version_response = serial_port.read(64)
    
    # 7. Test-Reading
    serial_port.write(b"<GETCPS>>")
    cps_response = serial_port.read(4)
    if len(cps_response) != 4:
        raise DeviceConnectionError("Invalid CPS response")
    
    return serial_port, model, firmware
```

## 8. Error Handling und Resilienz

### 8.1 Device Connection Errors

**Problem**: Serial Device nicht erreichbar, USB getrennt, Gerät antwortet nicht

**Strategie**:
- Bei Reconnect: Vollständige Startup-Sequenz ausführen (siehe 7.1)
- Exponential Backoff Reconnect (1s, 2s, 4s, 8s, max 60s)
- Logging aller Connection-Fehler
- MQTT Availability auf "offline" setzen
- Weiterlaufen des Services (nicht crashen)

### 8.2 MQTT Connection Errors

**Problem**: MQTT Broker nicht erreichbar, Netzwerk-Unterbrechung

**Strategie**:
- Automatisches Reconnect durch Paho-MQTT Library
- Buffering von Messwerten (begrenzte Queue)
- Bei Reconnect: Discovery-Nachrichten erneut senden
- LWT (Last Will Testament) für saubere Offline-Meldung

### 8.3 Invalid Readings (HEARTBEAT Mode)

**Problem**: Timeout beim Lesen, ungültige Antwort, Buffer-Desync (HEARTBEAT)

**Strategie**:
- **Read-Timeout** (keine Daten nach 5s):
  - 3 Versuche mit Re-Sync: `<HEARTBEAT0>>` → Buffer clear → `<HEARTBEAT1>>`
  - Danach: Full Reconnect mit Startup-Sequenz
- **Buffer-Desync** (z.B. 3 statt 4 Bytes gelesen):
  - Attempt Recovery: Rest-Bytes lesen bis Sync gefunden
  - Max 100 Bytes durchsuchen, dann Re-Sync wie oben
- **Invalid Values** (z.B. alle 0xFF):
  - Einzelne Messung skippen, loggen
  - Nach 10 konsekutiven Fehlern: Re-Sync
- **Fallback zu Polling-Mode** (optional):
  - Nach 5 fehlgeschlagenen Heartbeat-Recoveries
  - Config-Flag: `device.allow_polling_fallback: true`

**Beispiel Recovery-Logik**:
```python
consecutive_errors = 0
while running:
    try:
        data = serial_port.read(4)
        if len(data) != 4:
            consecutive_errors += 1
            if consecutive_errors >= 3:
                resync_heartbeat()
                consecutive_errors = 0
            continue
        
        cps_value = parse_cps(data)
        consecutive_errors = 0  # Reset on success
        process_value(cps_value)
        
    except serial.SerialTimeoutException:
        handle_timeout()
```

**Aktionen**:
1. Stop des Reading-Loops
2. Flush der MQTT Message Queue
3. Publish "offline" zu Availability Topic
4. Close Serial Connection
5. Disconnect MQTT Client
6. Exit mit Code 0

### 8.4 Signal Handling

**Signale**: SIGTERM, SIGINT, SIGHUP (optional: reload config)

**Handler-Implementation**:
```python
import signal

def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
```

**Shutdown-Ablauf**: Siehe Abschnitt 7.2

**Timeout-Protection**: Gesamter Shutdown max. 10 Sekunden, dann Force-Exit

### 8.5 Heartbeat State Protection

**Problem**: Nach unsauberem Shutdown (kill -9, Stromausfall) sendet Gerät weiter

**Mitigation**:
- **Startup**: IMMER `<HEARTBEAT0>>` vor `<HEARTBEAT1>>`
- **Monitoring**: Watchdog erkennt hängende Prozesse und restartlet sauber
- **Alternative**: Systemd mit `Restart=always` + `KillMode=mixed`
  - Sendet SIGTERM, wartet `TimeoutStopSec`, dann SIGKILL
  - Nächster Start führt wieder `<HEARTBEAT0>>` aus

**Best Practice**: Serial Port exklusiv öffnen (verhindert mehrere Instanzen)
```python
# Linux: flock() für exclusive access
import fcntl
fcntl.flock(serial_port.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
```

## 9. Paket-Struktur und Deployment

### 9.1 pyproject.toml

```toml
[project]
name = "gmc-geiger-mqtt"
version = "0.1.0"
description = "MQTT Bridge for GMC Geiger Counters"
requires-python = ">=3.9"
dependencies = [
    "paho-mqtt>=1.6.0",
    "pyserial>=3.5",
    "pyyaml>=6.0",
    "python-dateutil>=2.8"
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "black>=23.0",
    "ruff>=0.1"
]

[project.scripts]
gmc-geiger-mqtt = "gmc_geiger_mqtt.__main__:main"

[build-system]
requires = ["setuptools>=65.0", "wheel"]
build-backend = "setuptools.build_meta"
```

### 9.2 Systemd Service (Linux)

```ini
[Unit]
Description=GMC Geiger Counter MQTT Bridge
After=network.target

[Service]
Type=simple
User=gmc
Group=dialout
ExecStart=/usr/local/bin/gmc-geiger-mqtt --config /etc/gmc-geiger-mqtt/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 9.3 Docker Support (Optional)

- Dockerfile für Container-Deployment
- Device Passthrough für USB (`--device=/dev/ttyUSB0`)
- Volume Mount für Config

## 10. Testing-Strategie (sparsam)

### 10.1 Unit Tests

**Fokus**: Kritische Business-Logik, kein Over-Engineering

- `test_protocol.py`: GQ-RFC1801 Kommando-Parsing (inkl. HEARTBEAT)
- `test_connection.py`: Startup/Shutdown Sequenzen, Re-Sync Logik
- `test_aggregator.py`: Gleitender Durchschnitt Berechnung
- `test_config.py`: Config Loading und Validation
- `test_discovery.py`: Home Assistant Discovery Payload Generation
- `test_recovery.py`: Error Recovery Szenarien (Buffer-Desync, Timeouts)

**Mocking**:
- Serial Device: Mock mit vorgefertigten Responses
- MQTT Client: Mock für Publishing-Tests

**Mocking**:
- Serial Device: Mock mit vorgefertigten Responses
- MQTT Client: Mock für Publishing-Tests

### 10.2 Integration Tests (Optional, minimal)

- End-to-End Test mit Mock Serial und Mock MQTT Broker
- Nur für kritische Happy-Path Szenarien

### 10.3 Keine Tests für

- Einfache Getter/Setter
- Triviale Wrapper-Funktionen
- Framework-Code (paho-mqtt, pyserial)

## 11. Logging

### 11.1 Log Levels

- **DEBUG**: Alle Serial Commands/Responses, MQTT Messages
- **INFO**: Startup, Connections etabliert, Aggregierte Statistiken
- **WARNING**: Reconnects, einzelne fehlerhafte Readings
- **ERROR**: Connection-Fehler, Config-Probleme

### 11.2 Strukturiertes Logging

```python
logger.info("Device connected", extra={
    "device_model": "GMC-800",
    "firmware": "Re 1.10",
    "port": "/dev/ttyUSB0"
})
```

## 12. Erweiterbarkeit

### 12.1 Zukünftige Features

**Mehrfach-Consumer Support**:
- Bereits durch MQTT-Architektur gegeben
- Jeder Client kann Topics subscriben

**Zusätzliche Metriken**:
- CPM (Counts Per Minute) zusätzlich zu CPS
- Dosisrate (µSv/h) - benötigt Umrechnungsfaktor
- Temperatur (falls vom Gerät unterstützt)
- Dynamischer Mode-Switch (Heartbeat ↔ Polling bei Problemen)


**Alternative Geräte**:
- `device/protocol.py` kann erweitert werden für andere GMC Modelle
- Factory Pattern für verschiedene Device-Typen

**Web-UI / Status-Dashboard** (optional):
- Minimaler HTTP-Server für Health-Check Endpoint
- Prometheus Metrics Export

### 12.2 Plugin-Architektur (Future)

Falls weitere Publisher gewünscht:
- Abstract Publisher Base Class
- Dynamisches Laden von Publishern
- Z.B. InfluxDB Publisher, File Logger, etc.

## 13. Deployment-Checklist

1. ✓ Python 3.9+ installiert
2. ✓ User in `dialout` Gruppe (für `/dev/ttyUSB*` Zugriff)
3. ✓ GMC Gerät verbunden und unter `/dev/ttyUSB*` sichtbar
4. ✓ `config.yaml` erstellt und validiert
5. ✓ MQTT Broker erreichbar
6. ✓ Systemd Service installiert (optional)
7. ✓ Logs überwacht nach Startup
8. ✓ Home Assistant zeigt Sensoren an

---

**Status**: Architecture Draft v1.0 - Ready for Review