"""Test that _ensure_dspy() guards against multiple configure_dspy() calls."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure project root is in sys.path for lib imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def _load_explain_math_only():
    """Load explain_math_only module using importlib."""
    module_path = project_root / "explain_math_only.py"
    spec = importlib.util.spec_from_file_location("explain_math_only_test", module_path)
    module = importlib.util.module_from_spec(spec)
    # Patch configure_dspy during module execution to intercept the import
    with patch("lib.dspy_config.configure_dspy"):
        spec.loader.exec_module(module)
    return module


def _load_summarize_papers():
    """Load summarize_papers module using importlib."""
    module_path = project_root / "summarize_papers.py"
    spec = importlib.util.spec_from_file_location("summarize_papers_test", module_path)
    module = importlib.util.module_from_spec(spec)
    # Patch configure_dspy during module execution to intercept the import
    with patch("lib.dspy_config.configure_dspy"):
        spec.loader.exec_module(module)
    return module


def test_ensure_dspy_calls_configure_once():
    """Verify _ensure_dspy() calls configure_dspy() exactly once per process."""
    module = _load_explain_math_only()

    # Patch configure_dspy after loading but before calling _ensure_dspy()
    with patch("lib.dspy_config.configure_dspy") as mock_configure:
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
    module = _load_explain_math_only()

    with patch("lib.dspy_config.configure_dspy") as mock_configure:
        # Call it multiple times
        for _ in range(5):
            module._ensure_dspy()

        # Should only call once
        assert mock_configure.call_count == 1


def test_summarize_papers_ensure_dspy_calls_configure_once():
    """Verify summarize_papers._ensure_dspy() calls configure_dspy() exactly once per process."""
    module = _load_summarize_papers()

    with patch("lib.dspy_config.configure_dspy") as mock_configure:
        # First call should invoke configure_dspy()
        module._ensure_dspy()
        assert mock_configure.call_count == 1

        # Second call should NOT invoke configure_dspy()
        module._ensure_dspy()
        assert mock_configure.call_count == 1

        # Third call should still NOT invoke configure_dspy()
        module._ensure_dspy()
        assert mock_configure.call_count == 1


def test_summarize_papers_ensure_dspy_guard_persists():
    """Verify summarize_papers guard flag prevents repeated configuration."""
    module = _load_summarize_papers()

    with patch("lib.dspy_config.configure_dspy") as mock_configure:
        # Call it multiple times
        for _ in range(5):
            module._ensure_dspy()

        # Should only call once
        assert mock_configure.call_count == 1
