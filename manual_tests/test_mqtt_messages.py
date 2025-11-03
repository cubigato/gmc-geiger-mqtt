#!/usr/bin/env python3
"""Test script to verify MQTT messages and Home Assistant discovery payloads.

This script connects to the MQTT broker and subscribes to all relevant topics
to show what messages are being published.
"""

import json
import time
import sys

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt not installed. Run: uv pip install paho-mqtt")
    sys.exit(1)


def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker."""
    if rc == 0:
        print("✓ Connected to MQTT broker")
        print("-" * 70)

        # Subscribe to all GMC topics
        client.subscribe("gmc/geiger/#")
        print("✓ Subscribed to: gmc/geiger/#")

        # Subscribe to Home Assistant discovery
        client.subscribe("homeassistant/#")
        print("✓ Subscribed to: homeassistant/#")

        print("-" * 70)
        print("Waiting for messages... (Ctrl+C to exit)")
        print("=" * 70)
    else:
        print(f"✗ Connection failed with code {rc}")


def on_message(client, userdata, message):
    """Callback when message is received."""
    topic = message.topic
    payload = message.payload.decode("utf-8", errors="ignore")

    print(f"\n📨 Topic: {topic}")
    print(f"   QoS: {message.qos}, Retained: {message.retain}")

    # Try to pretty-print JSON payloads
    try:
        data = json.loads(payload)
        print(f"   Payload (JSON):")
        print(json.dumps(data, indent=6))
    except json.JSONDecodeError:
        print(f"   Payload (raw): {payload}")

    # Highlight specific message types
    if "homeassistant" in topic and "config" in topic:
        print("   ⭐ HOME ASSISTANT DISCOVERY MESSAGE")
    elif "state" in topic and "state_avg" not in topic:
        print("   ⚡ REALTIME READING")
    elif "state_avg" in topic:
        print("   📊 AGGREGATED READING")
    elif "availability" in topic:
        print("   💚 AVAILABILITY STATUS")
    elif "info" in topic:
        print("   ℹ️  DEVICE INFO")

    print("-" * 70)


def main():
    """Main function."""
    print("=" * 70)
    print("GMC Geiger MQTT Message Monitor")
    print("=" * 70)

    # Read broker from config.yaml or use default
    broker = "localhost"
    port = 1883

    try:
        import yaml

        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
            broker = config.get("mqtt", {}).get("broker", "localhost")
            port = config.get("mqtt", {}).get("port", 1883)
            print(f"Using broker from config.yaml: {broker}:{port}")
    except Exception as e:
        print(f"Could not read config.yaml: {e}")
        print(f"Using default: {broker}:{port}")

    print("-" * 70)

    # Create MQTT client
    client = mqtt.Client(client_id="gmc-test-monitor", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        # Connect to broker
        print(f"Connecting to {broker}:{port}...")
        client.connect(broker, port, keepalive=60)

        # Start loop
        client.loop_forever()

    except KeyboardInterrupt:
        print("\n" + "=" * 70)
        print("Stopped by user")
        print("=" * 70)
    except ConnectionRefusedError:
        print(f"\n✗ Error: Could not connect to MQTT broker at {broker}:{port}")
        print("  Make sure the broker is running (e.g., mosquitto)")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
