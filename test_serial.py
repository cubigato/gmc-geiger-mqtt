#!/usr/bin/env python3
"""Test script to debug serial communication with GMC device."""

import serial
import time
import sys


def test_serial_with_baudrate(baudrate):
    """Test serial connection with specific baudrate."""
    print(f"\nTesting with baudrate: {baudrate}")
    print("=" * 70)

    try:
        # Open serial connection
        print(f"Opening /dev/ttyUSB0 at {baudrate} baud...")
        s = serial.Serial(
            "/dev/ttyUSB0",
            baudrate,
            timeout=2,
            write_timeout=2,
            rtscts=False,
            dsrdtr=False,
            xonxoff=False,
        )

        # DTR/RTS aktivieren (wie im Beispiel)
        print("Setting DTR/RTS to True...")
        s.setDTR(True)
        s.setRTS(True)

        # Wait for device to be ready
        print("Waiting 0.5s for device to be ready...")
        time.sleep(0.5)

        # Clear buffers
        print("Clearing input buffer...")
        s.reset_input_buffer()

        # Send command
        print("Sending <GETVER>> command...")
        s.write(b"<GETVER>>")
        s.flush()

        # Wait for response
        print("Waiting 0.2s for response...")
        time.sleep(0.2)

        # Read response
        print("Reading response...")
        reply = s.read(64)

        print("=" * 70)
        print(f"Reply bytes: {repr(reply)}")
        print(f"Reply length: {len(reply)}")

        if reply:
            decoded = reply.decode("ascii", errors="ignore")
            print(f"Reply decoded: '{decoded}'")

            # Try to find null terminator
            if b"\x00" in reply:
                null_pos = reply.index(b"\x00")
                print(f"Null terminator found at position {null_pos}")
                clean_reply = reply[:null_pos].decode("ascii", errors="ignore")
                print(f"Clean reply: '{clean_reply}'")
        else:
            print("ERROR: No reply received!")
            s.close()
            return False

        print("=" * 70)

        # Test CPM reading
        print("\nTesting CPM reading...")
        s.reset_input_buffer()
        s.write(b"<GETCPM>>")
        s.flush()
        time.sleep(0.2)

        cpm_data = s.read(2)
        print(f"CPM bytes: {repr(cpm_data)}")
        if len(cpm_data) == 2:
            cpm = (cpm_data[0] << 8) | cpm_data[1]
            print(f"CPM value: {cpm}")
        else:
            print(f"ERROR: Expected 2 bytes, got {len(cpm_data)}")

        print("=" * 70)

        # Close connection
        s.close()
        print("\nSerial port closed successfully")
        return True

    except serial.SerialException as e:
        print(f"ERROR: Serial exception: {e}")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected exception: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_serial_connection():
    """Test with multiple baudrates."""
    print("Testing serial connection to GMC device...")
    print("Trying different baudrates...")

    # Try common baudrates
    baudrates = [115200, 57600, 9600, 19200, 38400]

    for baudrate in baudrates:
        if test_serial_with_baudrate(baudrate):
            print(f"\n✓ SUCCESS with baudrate {baudrate}!")
            return True
        time.sleep(1)  # Wait between attempts

    print("\n✗ FAILED: No baudrate worked")
    return False


if __name__ == "__main__":
    success = test_serial_connection()
    sys.exit(0 if success else 1)
