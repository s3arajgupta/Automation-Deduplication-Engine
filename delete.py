#!/usr/bin/env python3
"""
Legacy entrypoint for file deletion in Duplicate-Folders.
Delegates to the modern, safe Deduplication Engine clean command.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dedup_engine.cli import app

if __name__ == "__main__":
    # If run directly without arguments, show help for clean
    if len(sys.argv) == 1:
        sys.argv.extend(["clean", "--help"])
    app()
