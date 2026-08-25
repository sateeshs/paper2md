"""Test that _ensure_dspy() guards against multiple configure_dspy() calls."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load_explain_math_only():
    """Load explain_math_only module using importlib."""
    module_path = Path(__file__).parent.parent / "explain_math_only.py"
    spec = importlib.util.spec_from_file_location("explain_math_only", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ensure_dspy_calls_configure_once():
    """Verify _ensure_dspy() calls configure_dspy() exactly once per process."""
    with patch("lib.dspy_config.configure_dspy") as mock_configure:
        module = _load_explain_math_only()

        # First call should invoke configure_dspy()
        module._ensure_dspy()
        assert mock_configure.call_count == 1

        # Second call should NOT invoke configure_dspy()
        module._ensure_dspy()
        assert mock_configure.call_count == 1

        # Third call should still NOT invoke configure_dspy()
        module._ensure_dspy()
        assert mock_configure.call_count == 1


def test_ensure_dspy_guard_persists_across_calls():
    """Verify the guard flag prevents repeated configuration."""
    with patch("lib.dspy_config.configure_dspy") as mock_configure:
        module = _load_explain_math_only()

        # Call it multiple times
        for _ in range(5):
            module._ensure_dspy()

        # Should only call once
        assert mock_configure.call_count == 1
