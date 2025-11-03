#!/usr/bin/env python3
"""Executable script to run the GMC Geiger MQTT bridge."""

import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from src.main import main

if __name__ == "__main__":
    sys.exit(main())
