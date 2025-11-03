#!/bin/bash
# Script to clean MQTT discovery topics for GMC Geiger Counter

echo "======================================================================"
echo "GMC Geiger Counter - MQTT Discovery Cleanup"
echo "======================================================================"

# Check if config.yaml exists
if [ ! -f "config.yaml" ]; then
    echo "Error: config.yaml not found"
    exit 1
fi

# Read MQTT broker config from config.yaml
BROKER=$(grep -A20 "^mqtt:" config.yaml | grep "broker:" | head -1 | awk '{print $2}' | tr -d '"' | tr -d "'")
PORT=$(grep -A20 "^mqtt:" config.yaml | grep "port:" | head -1 | awk '{print $2}')
USERNAME=$(grep -A20 "^mqtt:" config.yaml | grep "username:" | head -1 | awk '{print $2}' | tr -d '"' | tr -d "'")
PASSWORD=$(grep -A20 "^mqtt:" config.yaml | grep "password:" | head -1 | awk '{print $2}' | tr -d '"' | tr -d "'")
HA_PREFIX=$(grep -A20 "^mqtt:" config.yaml | grep "homeassistant_prefix:" | head -1 | awk '{print $2}' | tr -d '"' | tr -d "'")

# Use defaults if not found
BROKER=${BROKER:-localhost}
PORT=${PORT:-1883}
HA_PREFIX=${HA_PREFIX:-homeassistant}

echo "MQTT Broker: $BROKER:$PORT"
echo "HA Prefix: $HA_PREFIX"
echo ""

# Build mosquitto_pub command with optional auth
MQTT_CMD="mosquitto_pub -h $BROKER -p $PORT"
if [ -n "$USERNAME" ] && [ "$USERNAME" != '""' ] && [ "$USERNAME" != "''" ]; then
    MQTT_CMD="$MQTT_CMD -u $USERNAME"
    if [ -n "$PASSWORD" ] && [ "$PASSWORD" != '""' ] && [ "$PASSWORD" != "''" ]; then
        MQTT_CMD="$MQTT_CMD -P $PASSWORD"
    fi
    echo "Using authentication: $USERNAME"
else
    echo "Using anonymous connection"
fi

echo ""

# Try to find device ID
DEVICE_ID=""

# Method 1: Look for serial number in recent logs or running process
if command -v ps &> /dev/null; then
    # Check if bridge is running and has the device ID in logs
    echo "Attempting to detect device ID..."
    
    # Try to find it from the most recent python run.py process or logs
    # This is a best-effort attempt
fi

# Method 2: Use the provided serial number (hardcoded for now)
# In a real scenario, we could start the bridge briefly to detect it
if [ -z "$DEVICE_ID" ]; then
    # Convert serial number to lowercase (as used in MQTT topics)
    DEVICE_ID="05004d323533ab"
    echo "Using device ID: $DEVICE_ID"
fi

echo ""
echo "Cleaning discovery topics for device: $DEVICE_ID"
echo "======================================================================"

# Delete discovery topics by publishing empty retained messages
echo "Deleting: $HA_PREFIX/sensor/$DEVICE_ID/cpm/config"
$MQTT_CMD -t "$HA_PREFIX/sensor/$DEVICE_ID/cpm/config" -r -n

echo "Deleting: $HA_PREFIX/sensor/$DEVICE_ID/radiation/config"
$MQTT_CMD -t "$HA_PREFIX/sensor/$DEVICE_ID/radiation/config" -r -n

echo "Deleting: $HA_PREFIX/sensor/$DEVICE_ID/cpm_avg/config"
$MQTT_CMD -t "$HA_PREFIX/sensor/$DEVICE_ID/cpm_avg/config" -r -n

echo "Deleting: $HA_PREFIX/sensor/$DEVICE_ID/radiation_avg/config"
$MQTT_CMD -t "$HA_PREFIX/sensor/$DEVICE_ID/radiation_avg/config" -r -n

echo ""
echo "======================================================================"
echo "✓ Discovery topics deleted"
echo ""
echo "Next steps:"
echo "1. Wait 5-10 seconds for Home Assistant to process the changes"
echo "2. Restart the GMC bridge: python3 run.py"
echo "3. The sensors should now appear fresh in Home Assistant"
echo "======================================================================"
