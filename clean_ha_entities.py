#!/usr/bin/env python3
"""Clean Home Assistant entities for GMC Geiger Counter.

This script removes entities from Home Assistant's entity registry by:
1. Publishing empty retained discovery messages (deletes from MQTT)
2. Waiting for HA to process the deletions
3. Optionally republishing fresh discovery messages

This forces HA to completely forget about the old entities and accept new ones.

Usage:
    python3 clean_ha_entities.py           # Interactive mode
    python3 clean_ha_entities.py --force   # Skip confirmation
"""

import argparse
import json
import sys
import time
import yaml

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt not installed")
    print("Run: uv pip install paho-mqtt")
    sys.exit(1)


def load_config():
    """Load configuration from config.yaml."""
    try:
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: config.yaml not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)


def get_mqtt_client(config):
    """Create and connect MQTT client."""
    mqtt_config = config.get("mqtt", {})
    broker = mqtt_config.get("broker", "localhost")
    port = mqtt_config.get("port", 1883)
    username = mqtt_config.get("username")
    password = mqtt_config.get("password")

    print(f"Connecting to MQTT broker: {broker}:{port}")

    client = mqtt.Client(client_id="gmc-cleanup", clean_session=True)

    if username:
        client.username_pw_set(username, password)
        print(f"Using authentication: {username}")

    try:
        client.connect(broker, port, keepalive=60)
        client.loop_start()
        time.sleep(1)  # Give it time to connect
        print("✓ Connected to MQTT broker")
        return client, mqtt_config
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        sys.exit(1)


def delete_discovery(client, mqtt_config, device_id):
    """Delete discovery messages (empty retained messages)."""
    ha_prefix = mqtt_config.get("homeassistant_prefix", "homeassistant")
    sensors = ["cpm", "radiation", "cpm_avg", "radiation_avg"]

    print(f"\n{'=' * 70}")
    print("Deleting discovery messages (this removes entities from HA)")
    print(f"{'=' * 70}")

    for sensor in sensors:
        topic = f"{ha_prefix}/sensor/{device_id}/{sensor}/config"
        print(f"Deleting: {topic}")
        client.publish(topic, payload="", qos=1, retain=True)
        time.sleep(0.1)

    print("\n✓ Discovery messages deleted")
    print("\nWaiting 10 seconds for Home Assistant to process deletions...")

    # Show countdown
    for i in range(10, 0, -1):
        print(f"  {i}...", end="\r")
        time.sleep(1)
    print("  Done!   ")


def confirm_action(force=False):
    """Ask user to confirm the action."""
    print(f"\n{'=' * 70}")
    print("WARNING: This will DELETE all GMC Geiger sensors from Home Assistant!")
    print(f"{'=' * 70}")
    print("\nThis script will:")
    print("  1. Delete discovery messages (removes entities from HA)")
    print("  2. Wait 10 seconds")
    print("  3. You then need to RESTART the bridge to republish")
    print("\nThe sensors will be recreated fresh when you restart the bridge.")
    print()

    if force:
        print("--force flag provided, skipping confirmation")
        return True

    try:
        response = input("Continue? (yes/no): ").strip().lower()
        return response in ["yes", "y"]
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled")
        return False


def main():
    """Main function."""
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Clean GMC Geiger entities from Home Assistant"
    )
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    print(f"{'=' * 70}")
    print("GMC Geiger Counter - Home Assistant Entity Cleanup")
    print(f"{'=' * 70}\n")

    # Load config
    config = load_config()

    # Get device ID (serial number in lowercase)
    device_id = "05004d323533ab"
    print(f"Device ID: {device_id}")

    # Confirm
    if not confirm_action(force=args.force):
        print("\nCancelled by user")
        sys.exit(0)

    # Connect to MQTT
    client, mqtt_config = get_mqtt_client(config)

    try:
        # Delete discovery messages
        delete_discovery(client, mqtt_config, device_id)

        print(f"\n{'=' * 70}")
        print("✓ Cleanup complete!")
        print(f"{'=' * 70}")
        print("\nNext steps:")
        print("  1. Go to Home Assistant → Settings → Devices & Services → MQTT")
        print("  2. The 'GMC Geiger GMC-800Re' device should now be GONE")
        print("  3. Restart the bridge: python3 run.py")
        print("  4. The device will be recreated with ALL 4 sensors (CPM + µSv/h)")
        print(f"{'=' * 70}\n")

    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
