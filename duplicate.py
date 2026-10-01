#!/usr/bin/env python3
"""
Legacy entrypoint for Duplicate-Folders.
Delegates to the modern, modular Deduplication Engine.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to path so this script can be executed directly without installation
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dedup_engine.cli import app

if __name__ == "__main__":
    app()
