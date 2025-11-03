#!/usr/bin/env python3
"""Debug CPM reading from GMC device."""

import serial
import time
import sys

def test_cpm_reading():
    """Test CPM reading with detailed debugging."""
    print("Testing CPM reading from GMC device...")
    print("=" * 70)
    
    try:
        # Open serial connection
        print("Opening /dev/ttyUSB0 at 115200 baud...")
        s = serial.Serial(
            "/dev/ttyUSB0",
            115200,
            timeout=2,
            write_timeout=2,
            rtscts=False,
            dsrdtr=False,
            xonxoff=False,
        )
        
        # DTR/RTS aktivieren
        s.setDTR(True)
        s.setRTS(True)
        time.sleep(0.5)
        
        # Test multiple times
        for i in range(5):
            print(f"\n--- Reading attempt {i+1} ---")
            
            # Clear buffer
            s.reset_input_buffer()
            
            # Send GETCPM command
            print("Sending <GETCPM>>...")
            s.write(b"<GETCPM>>")
            s.flush()
            
            # Wait a bit
            time.sleep(0.2)
            
            # Check how many bytes are waiting
            waiting = s.in_waiting
            print(f"Bytes waiting in buffer: {waiting}")
            
            # Read 2 bytes
            data = s.read(2)
            print(f"Read {len(data)} bytes: {repr(data)}")
            
            if len(data) == 2:
                cpm = (data[0] << 8) | data[1]
                print(f"CPM value: {cpm}")
            else:
                print("ERROR: Not enough data received")
            
            time.sleep(1)
        
        s.close()
        print("\n" + "=" * 70)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_cpm_reading()
