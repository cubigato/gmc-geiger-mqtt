#!/usr/bin/env python3
"""
Manual test to display MQTT discovery payloads.

This script shows the discovery messages that will be sent to Home Assistant.
Useful for debugging and verifying the payload structure.

Run with:
    python3 manual_tests/test_discovery_payloads.py
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gmc_geiger_mqtt.models import DeviceInfo, MQTTConfig


def print_discovery_payload(sensor_name: str, payload: dict) -> None:
    """Pretty print a discovery payload."""
    print(f"\n{'=' * 80}")
    print(f"Sensor: {sensor_name}")
    print(f"{'=' * 80}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main():
    """Generate and display all discovery payloads."""
    print("=" * 80)
    print("MQTT Discovery Payloads for Home Assistant")
    print("=" * 80)
    print("\nThese payloads are compatible with Home Assistant 2025.11+")
    print("Note: 'device_class: irradiance' has been REMOVED from radiation sensors")
    print("      (irradiance only supports W/m², not µSv/h)")

    # Mock device info
    device_info = DeviceInfo(
        model="GMC-800Re",
        version="1.10",
        serial="05004D323533AB",
    )

    # Mock MQTT config
    config = MQTTConfig(
        enabled=True,
        broker="localhost",
        port=1883,
        homeassistant_discovery=True,
        homeassistant_prefix="homeassistant",
        topic_prefix="gmc/geiger",
    )

    device_id = device_info.serial.lower()

    # Device dict (shared)
    device_dict = {
        "identifiers": [f"gmc_geiger_{device_id}"],
        "name": f"GMC Geiger {device_info.model}",
        "model": device_info.model,
        "manufacturer": "GQ Electronics",
        "sw_version": device_info.version,
    }

    # 1. CPM Sensor (realtime)
    cpm_payload = {
        "name": "CPM",
        "unique_id": f"{device_id}_cpm",
        "state_topic": f"{config.topic_prefix}/{device_id}/state",
        "value_template": "{{ value_json.cpm }}",
        "unit_of_measurement": "CPM",
        "icon": "mdi:radioactive",
        "state_class": "measurement",
        "device": device_dict,
        "availability_topic": f"{config.topic_prefix}/{device_id}/availability",
    }
    print_discovery_payload("CPM (realtime)", cpm_payload)

    # 2. Radiation Level Sensor (realtime) - NO device_class!
    radiation_payload = {
        "name": "Radiation Level",
        "unique_id": f"{device_id}_radiation",
        "state_topic": f"{config.topic_prefix}/{device_id}/state",
        "value_template": "{{ value_json.usv_h }}",
        "unit_of_measurement": "µSv/h",
        "icon": "mdi:radioactive",
        "state_class": "measurement",
        # NOTE: NO "device_class": "irradiance" here!
        "device": device_dict,
        "availability_topic": f"{config.topic_prefix}/{device_id}/availability",
    }
    print_discovery_payload("Radiation Level (realtime)", radiation_payload)

    # 3. CPM Sensor (average)
    cpm_avg_payload = {
        "name": "CPM (10-min avg)",
        "unique_id": f"{device_id}_cpm_avg",
        "state_topic": f"{config.topic_prefix}/{device_id}/state_avg",
        "value_template": "{{ value_json.cpm_avg }}",
        "unit_of_measurement": "CPM",
        "icon": "mdi:radioactive",
        "state_class": "measurement",
        "device": device_dict,
        "availability_topic": f"{config.topic_prefix}/{device_id}/availability",
    }
    print_discovery_payload("CPM (10-min avg)", cpm_avg_payload)

    # 4. Radiation Level Sensor (average) - NO device_class!
    radiation_avg_payload = {
        "name": "Radiation Level (10-min avg)",
        "unique_id": f"{device_id}_radiation_avg",
        "state_topic": f"{config.topic_prefix}/{device_id}/state_avg",
        "value_template": "{{ value_json.usv_h_avg }}",
        "unit_of_measurement": "µSv/h",
        "icon": "mdi:radioactive",
        "state_class": "measurement",
        # NOTE: NO "device_class": "irradiance" here!
        "device": device_dict,
        "availability_topic": f"{config.topic_prefix}/{device_id}/availability",
    }
    print_discovery_payload("Radiation Level (10-min avg)", radiation_avg_payload)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("\n✅ Key Changes for Home Assistant 2025.11+ Compatibility:")
    print("   - Removed 'device_class: irradiance' from radiation sensors")
    print("   - Kept 'state_class: measurement' for historical data tracking")
    print("   - Kept 'icon: mdi:radioactive' for visual identification")
    print("   - Custom unit 'µSv/h' is now treated as generic numeric unit")
    print("\n✅ What Still Works:")
    print("   - Historical data (same unique_id and state_topic)")
    print("   - Graphing and statistics (state_class: measurement)")
    print("   - Automations (same entity IDs)")
    print("   - Device grouping (all 4 sensors under one device)")
    print("\n❌ What Changed:")
    print("   - Sensors appear as 'generic' instead of 'irradiance' type")
    print("   - No automatic unit conversion (but µSv/h doesn't need it)")
    print("\n📝 MQTT Topics:")
    print(
        f"   - Discovery prefix: {config.homeassistant_prefix}/sensor/{device_id}/<sensor>/config"
    )
    print(f"   - State (realtime): {config.topic_prefix}/{device_id}/state")
    print(f"   - State (average):  {config.topic_prefix}/{device_id}/state_avg")
    print(f"   - Availability:     {config.topic_prefix}/{device_id}/availability")
    print()


if __name__ == "__main__":
    main()
