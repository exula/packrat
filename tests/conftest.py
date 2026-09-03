"""Pytest configuration."""

import pytest


@pytest.fixture(autouse=True)
def reset_env_vars(monkeypatch):
    """Reset environment variables that might affect tests."""
    monkeypatch.delenv("TEXTUAL_LOG_FILE", raising=False)
    monkeypatch.delenv("TEXTUAL_LOG_LEVEL", raising=False)
