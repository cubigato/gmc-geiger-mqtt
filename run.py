#!/usr/bin/env python3
"""Executable script to run the GMC Geiger MQTT bridge.

This is a backwards-compatible wrapper for the installed package.
For production use, install the package and use the 'gmc-geiger-mqtt' command instead.
"""

import sys
from pathlib import Path

# Add src directory to Python path for development mode
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from gmc_geiger_mqtt.main import main

if __name__ == "__main__":
    sys.exit(main())
