#!/usr/bin/env python3
"""Debug CPM reading - read all available bytes."""

import serial
import time

def test_cpm_reading():
    """Test CPM reading with all bytes."""
    print("Testing CPM reading from GMC device...")
    print("=" * 70)
    
    s = serial.Serial(
        "/dev/ttyUSB0",
        115200,
        timeout=2,
        write_timeout=2,
        rtscts=False,
        dsrdtr=False,
        xonxoff=False,
    )
    
    s.setDTR(True)
    s.setRTS(True)
    time.sleep(0.5)
    
    # Test multiple times
    for i in range(5):
        print(f"\n--- Reading attempt {i+1} ---")
        
        s.reset_input_buffer()
        
        print("Sending <GETCPM>>...")
        s.write(b"<GETCPM>>")
        s.flush()
        
        time.sleep(0.2)
        
        # Read ALL available bytes
        waiting = s.in_waiting
        print(f"Bytes waiting: {waiting}")
        
        all_data = s.read(waiting)
        print(f"All bytes: {repr(all_data)}")
        print(f"All bytes hex: {all_data.hex()}")
        
        # Try different interpretations
        if len(all_data) >= 2:
            # First 2 bytes
            cpm1 = (all_data[0] << 8) | all_data[1]
            print(f"First 2 bytes as CPM: {cpm1}")
            
        if len(all_data) >= 4:
            # Last 2 bytes
            cpm2 = (all_data[2] << 8) | all_data[3]
            print(f"Last 2 bytes as CPM: {cpm2}")
            
            # Maybe bytes 1 and 2 (0-indexed)
            cpm3 = (all_data[1] << 8) | all_data[2]
            print(f"Bytes 1-2 as CPM: {cpm3}")
        
        time.sleep(1)
    
    s.close()

if __name__ == "__main__":
    test_cpm_reading()
