"""Pytest configuration for paper2md tests."""

import sys
from pathlib import Path

# Add project root to sys.path so imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
