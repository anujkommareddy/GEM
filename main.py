#!/usr/bin/env python3
"""Main entry point for GEM autoresearch."""

import sys
import os

# Load .env file
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from cli import main

if __name__ == "__main__":
    main()
