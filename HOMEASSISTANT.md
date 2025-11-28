# Home Assistant Integration Guide

This guide explains how to integrate the GMC Geiger Counter MQTT Bridge with Home Assistant.

## Overview

The bridge automatically discovers and registers 4 sensors in Home Assistant:

1. **CPM** - Realtime counts per minute (updates every second)
2. **Radiation Level** - Realtime radiation dose in µSv/h (updates every second)
3. **CPM (10-min avg)** - 10-minute moving average of CPM
4. **Radiation Level (10-min avg)** - 10-minute moving average in µSv/h

> **Note:** Since Home Assistant 2025.11, the radiation level sensors no longer use the `irradiance` device class, as it only supports solar irradiance units (W/m²), not ionizing radiation units (µSv/h). The sensors now appear as generic numeric sensors with the radioactive icon.

All sensors include:
- ✅ Availability tracking (online/offline)
- ✅ Device information (model, firmware, serial number)
- ✅ Proper icons (`mdi:radioactive`)
- ✅ State classes for historical tracking
- ✅ Device grouping (all sensors under one device)

## Migration from Home Assistant 2025.10 → 2025.11

If you upgraded Home Assistant from 2025.10.x to 2025.11.x and your radiation level sensors show "Unavailable":

### Quick Fix

1. **Update the gmc-geiger-mqtt bridge**:
   ```bash
   cd gmc-geiger-mqtt
   git pull
   # Or manually update src/gmc_geiger_mqtt/mqtt/discovery.py
   ```

2. **Restart the bridge**:
   ```bash
   # Stop the running bridge (Ctrl+C)
   # Start it again
   gmc-geiger-mqtt
   ```

3. **Wait for discovery** (automatic):
   - The bridge will republish MQTT discovery messages on startup
   - Home Assistant will update the sensor definitions automatically
   - Sensors should become available within 30 seconds

4. **Check sensors in Home Assistant**:
   - Navigate to: Settings → Devices & Services → MQTT
   - Find your GMC Geiger device
   - Both radiation level sensors should now show values

**What changed?**
- Removed `device_class: "irradiance"` from radiation sensors (incompatible with µSv/h)
- Sensors now appear as generic numeric sensors with `state_class: measurement`
- Your historical data is preserved (same entity IDs and state topics)
- CPM sensors were unaffected

**No manual configuration needed!** The MQTT discovery system handles everything automatically.

---

## Prerequisites

1. **MQTT Integration** must be installed and configured in Home Assistant
   - Go to Settings → Devices & Services → Add Integration → MQTT
   - Configure your MQTT broker (e.g., Mosquitto)

2. **MQTT Broker** must be running and accessible
   - Built-in HA Mosquitto add-on, or
   - External Mosquitto broker, or
   - Any other MQTT broker

3. **GMC Bridge** must be running with MQTT enabled
   - Set `mqtt.enabled: true` in config.yaml
   - Set `mqtt.homeassistant_discovery: true` in config.yaml

## Setup

### 1. Configure the Bridge

Edit `config.yaml`:

```yaml
mqtt:
  enabled: true
  broker: "your-broker-address"  # e.g., "homeassistant.local" or "192.168.1.100"
  port: 1883
  username: ""  # If required by your broker
  password: ""  # If required by your broker
  homeassistant_discovery: true
  homeassistant_prefix: "homeassistant"  # Default HA discovery prefix
```

### 2. Start the Bridge

```bash
gmc-geiger-mqtt
```

You should see in the logs:

```
INFO - Publishing Home Assistant MQTT discovery messages...
INFO - Published discovery to homeassistant/sensor/.../cpm/config
INFO - Published discovery to homeassistant/sensor/.../radiation/config
INFO - Published discovery to homeassistant/sensor/.../cpm_avg/config
INFO - Published discovery to homeassistant/sensor/.../radiation_avg/config
INFO - Home Assistant discovery complete
```

### 3. Find the Device in Home Assistant

1. Navigate to: **Settings → Devices & Services → MQTT**
2. Look for a device named: **GMC Geiger GMC-800Re** (or your model name)
3. Click on the device to see all 4 sensors

Alternatively, you can search for "GMC" or "Geiger" in the device list.

## Sensors Explained

### 1. CPM (Realtime)

- **Entity ID**: `sensor.<device_id>_cpm`
- **Unit**: CPM (Counts Per Minute)
- **Update**: Every 1 second
- **Use**: Raw measurement from the Geiger counter tube
- **MQTT Topic**: `gmc/geiger/<device_id>/state`

**Example value**: 28 CPM

### 2. Radiation Level (Realtime)

- **Entity ID**: `sensor.<device_id>_radiation`
- **Unit**: µSv/h (microsieverts per hour)
- **Update**: Every 1 second
- **Use**: Converted radiation dose rate
- **MQTT Topic**: `gmc/geiger/<device_id>/state`
- **Device Class**: None (generic numeric sensor)

**Example value**: 0.182 µSv/h

**Conversion**: Uses the factor from `config.yaml` (default: 0.0065 for M4011 tube)

### 3. CPM (10-min avg)

- **Entity ID**: `sensor.<device_id>_cpm_avg`
- **Unit**: CPM (Counts Per Minute)
- **Update**: Every 10 minutes
- **Use**: Smoothed average to reduce noise
- **MQTT Topic**: `gmc/geiger/<device_id>/state_avg`

**Example value**: 25.4 CPM (with min=18, max=35)

### 4. Radiation Level (10-min avg)

- **Entity ID**: `sensor.<device_id>_radiation_avg`
- **Unit**: µSv/h (microsieverts per hour)
- **Update**: Every 10 minutes
- **Use**: Smoothed radiation dose average
- **MQTT Topic**: `gmc/geiger/<device_id>/state_avg`
- **Device Class**: None (generic numeric sensor)

**Example value**: 0.1651 µSv/h (averaged over 10 minutes)

## Creating Dashboards

### Simple Card

Add a simple entity card to your dashboard:

```yaml
type: entities
title: Radiation Monitor
entities:
  - entity: sensor.05004d323533ab_radiation
    name: Current Radiation
  - entity: sensor.05004d323533ab_radiation_avg
    name: 10-min Average
  - entity: sensor.05004d323533ab_cpm
    name: Current CPM
```

### Gauge Card

Show radiation level as a gauge:

```yaml
type: gauge
entity: sensor.05004d323533ab_radiation
name: Radiation Level
unit: µSv/h
min: 0
max: 1
needle: true
severity:
  green: 0
  yellow: 0.3
  red: 0.5
```

### History Graph

Track radiation over time:

```yaml
type: history-graph
title: Radiation History
entities:
  - entity: sensor.05004d323533ab_radiation_avg
    name: Average µSv/h
hours_to_show: 24
refresh_interval: 60
```

### Statistics Card (Long-term)

```yaml
type: statistics-graph
title: Daily Radiation Statistics
entities:
  - sensor.05004d323533ab_radiation_avg
stat_types:
  - mean
  - min
  - max
period: day
days_to_show: 7
```

## Automations

### Alert on High Radiation

```yaml
automation:
  - alias: "Alert: High Radiation Detected"
    trigger:
      - platform: numeric_state
        entity_id: sensor.05004d323533ab_radiation_avg
        above: 0.5  # 0.5 µSv/h threshold
        for:
          minutes: 5
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ High Radiation Detected"
          message: "Radiation level: {{ states('sensor.05004d323533ab_radiation_avg') }} µSv/h"
          data:
            priority: high
```

### Daily Summary Notification

```yaml
automation:
  - alias: "Radiation: Daily Summary"
    trigger:
      - platform: time
        at: "20:00:00"
    action:
      - service: notify.mobile_app
        data:
          title: "📊 Daily Radiation Summary"
          message: >
            Average: {{ states('sensor.05004d323533ab_radiation_avg') }} µSv/h
            CPM: {{ states('sensor.05004d323533ab_cpm_avg') }}
```

### Offline Alert

```yaml
automation:
  - alias: "Alert: Geiger Counter Offline"
    trigger:
      - platform: state
        entity_id: sensor.05004d323533ab_cpm
        to: "unavailable"
        for:
          minutes: 5
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Geiger Counter Offline"
          message: "The radiation monitor has gone offline"
```

## Advanced: Manual Configuration (Optional)

If automatic discovery doesn't work, you can manually configure sensors in `configuration.yaml`:

```yaml
mqtt:
  sensor:
    - name: "GMC Radiation Level"
      state_topic: "gmc/geiger/05004d323533ab/state"
      value_template: "{{ value_json.usv_h }}"
      unit_of_measurement: "µSv/h"
      icon: "mdi:radioactive"
      state_class: "measurement"
      availability_topic: "gmc/geiger/05004d323533ab/availability"
      
    - name: "GMC CPM"
      state_topic: "gmc/geiger/05004d323533ab/state"
      value_template: "{{ value_json.cpm }}"
      unit_of_measurement: "CPM"
      icon: "mdi:radioactive"
      availability_topic: "gmc/geiger/05004d323533ab/availability"
      
    - name: "GMC Radiation (10-min avg)"
      state_topic: "gmc/geiger/05004d323533ab/state_avg"
      value_template: "{{ value_json.usv_h_avg }}"
      unit_of_measurement: "µSv/h"
      icon: "mdi:radioactive"
      state_class: "measurement"
      availability_topic: "gmc/geiger/05004d323533ab/availability"
      
    - name: "GMC CPM (10-min avg)"
      state_topic: "gmc/geiger/05004d323533ab/state_avg"
      value_template: "{{ value_json.cpm_avg }}"
      unit_of_measurement: "CPM"
      icon: "mdi:radioactive"
      availability_topic: "gmc/geiger/05004d323533ab/availability"
```

**Note**: Replace `05004d323533ab` with your device's serial number or device ID.

## Troubleshooting

### Sensors not appearing

1. **Check MQTT integration is enabled**:
   - Settings → Devices & Services → MQTT should show "Configured"

2. **Verify discovery messages are sent**:
   ```bash
   mosquitto_sub -h localhost -t "homeassistant/#" -v
   ```
   You should see discovery payloads for each sensor.

3. **Check bridge logs**:
   Look for "Publishing Home Assistant MQTT discovery messages..."

4. **Restart Home Assistant**:
   Sometimes HA needs a restart to pick up new devices.

5. **Check MQTT broker connection**:
   Verify the bridge can connect to the broker (check logs).

### Sensors show "Unavailable"

1. **Check bridge is running**:
   ```bash
   ps aux | grep gmc-geiger-mqtt
   ```

2. **Check MQTT availability topic**:
   ```bash
   mosquitto_sub -h localhost -t "gmc/geiger/+/availability" -v
   ```
   Should show "online".

3. **Check device connection**:
   Verify the GMC device is connected via USB and the bridge can read from it.

### Values don't match device display

The µSv/h values might differ slightly from the device display because:

1. **Different conversion factors**: The device might use a different CPM→µSv/h conversion
2. **Rounding differences**: The device may round differently
3. **Averaging windows**: The device might use a different averaging period

**Solution**: Adjust `cpm_to_usv_factor` in `config.yaml`:

```yaml
conversion:
  cpm_to_usv_factor: 0.0065  # Adjust this value
```

Compare the CPM values (they should match exactly) and calculate the correct factor:
```
factor = device_usv_h / serial_cpm
```

### Device appears twice

If you change the device ID (serial number) or reinstall, you might get duplicate devices.

**Solution**:
1. Stop the bridge
2. In HA: Settings → Devices & Services → MQTT → Find old device → Delete
3. Restart the bridge (it will re-register with the new ID)

## MQTT Message Formats

### Realtime State

Topic: `gmc/geiger/<device_id>/state`

```json
{
  "cpm": 28,
  "usv_h": 0.182,
  "timestamp": "2024-01-15T10:30:45Z",
  "unit": "CPM"
}
```

### Aggregated State

Topic: `gmc/geiger/<device_id>/state_avg`

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

### Device Info (Retained)

Topic: `gmc/geiger/<device_id>/info`

```json
{
  "model": "GMC-800Re",
  "firmware": "1.10",
  "serial": "05004D323533AB",
  "manufacturer": "GQ Electronics"
}
```

### Availability (Retained)

Topic: `gmc/geiger/<device_id>/availability`

Payload: `"online"` or `"offline"`

## Reference Radiation Levels

For context, here are typical radiation levels:

- **0.05-0.20 µSv/h**: Normal background radiation
- **0.20-1.00 µSv/h**: Elevated but generally safe
- **1.00-10.0 µSv/h**: Medical X-ray range (short exposure)
- **>10.0 µSv/h**: Potentially hazardous with prolonged exposure

**Note**: These are rough guidelines. Always consult radiation safety resources for your specific situation.

## Further Reading

- [Home Assistant MQTT Integration](https://www.home-assistant.io/integrations/mqtt/)
- [MQTT Discovery Documentation](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)
- [GQ Electronics GMC Devices](https://www.gqelectronicsllc.com/)
- [GQ-RFC1801 Protocol Specification](GQ-RFC1801.txt)