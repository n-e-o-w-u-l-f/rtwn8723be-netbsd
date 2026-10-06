#!/usr/bin/env python3
"""Validate source provenance before source-shared calibration checks."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(ROOT / 'tools/validate_calibration_sources.py')], check=True)
