"""Cross-platform preference storage and startup path resolution for Packrat."""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlsplit

from platformdirs import user_config_path, user_data_path


APP_NAME = "Packrat"
PREFERENCES_VERSION = 2
PREFERENCES_FILENAME = "preferences.json"
DATA_FILENAME = "gear_data.json"

PathLike = Union[str, os.PathLike]


class PreferencesError(ValueError):
    """Raised when saved Packrat preferences are unreadable or invalid."""


DEFAULT_INSIGHTS_SETTINGS = {
    "primary_provider": "openai",
    "providers": {
        "openai": {
            "enabled": False,
            "model": "",
            "base_url": "https://api.openai.com/v1",
        },
        "anthropic": {
            "enabled": False,
            "model": "",
            "base_url": "https://api.anthropic.com/v1",
        },
        "gemini": {
            "enabled": False,
            "model": "",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
        },
        "local": {
            "enabled": False,
            "model": "",
            "base_url": "http://localhost:11434/v1",
        },
    },
}


def validate_provider_base_url(value: str, provider: str = "provider") -> str:
    """Return a safe normalized HTTP(S) provider URL or raise a user-facing error."""
    normalized = value.strip().rstrip("/")
    try:
        parsed = urlsplit(normalized)
        parsed.port
    except ValueError as exc:
        raise PreferencesError(f"{provider.title()} base URL is invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PreferencesError(f"{provider.title()} base URL must use http:// or https://")
    if parsed.username is not None or parsed.password is not None:
        raise PreferencesError(f"{provider.title()} base URL cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise PreferencesError(f"{provider.title()} base URL cannot contain a query or fragment")
    return normalized


def default_settings():
    return {
        "version": PREFERENCES_VERSION,
        "data_directory": None,
        "insights": json.loads(json.dumps(DEFAULT_INSIGHTS_SETTINGS)),
    }


def _validate_insights(value):
    if value is None:
        return json.loads(json.dumps(DEFAULT_INSIGHTS_SETTINGS))
    if not isinstance(value, dict):
        raise PreferencesError("preferences.insights must be an object")
    result = json.loads(json.dumps(DEFAULT_INSIGHTS_SETTINGS))
    primary = value.get("primary_provider", result["primary_provider"])
    if primary not in result["providers"]:
        raise PreferencesError("preferences.insights.primary_provider is invalid")
    result["primary_provider"] = primary
    providers = value.get("providers", {})
    if not isinstance(providers, dict):
        raise PreferencesError("preferences.insights.providers must be an object")
    for name, defaults in result["providers"].items():
        configured = providers.get(name, {})
        if not isinstance(configured, dict):
            raise PreferencesError(f"preferences provider {name} must be an object")
        enabled = configured.get("enabled", defaults["enabled"])
        model = configured.get("model", defaults["model"])
        base_url = configured.get("base_url", defaults["base_url"])
        if not isinstance(enabled, bool):
            raise PreferencesError(f"preferences provider {name}.enabled must be boolean")
        if not isinstance(model, str) or not isinstance(base_url, str):
            raise PreferencesError(f"preferences provider {name} text values must be strings")
        normalized_url = base_url.strip().rstrip("/")
        if enabled:
            normalized_url = validate_provider_base_url(normalized_url, name)
        result["providers"][name] = {
            "enabled": enabled,
            "model": model.strip(),
            "base_url": normalized_url,
        }
    return result


def normalize_path(path: PathLike) -> str:
    """Return an expanded absolute path without requiring it to exist."""
    value = os.fspath(path).strip()
    if not value:
        raise PreferencesError("the storage folder cannot be blank")
    return os.path.abspath(os.path.expanduser(value))


def preferences_file() -> Path:
    return user_config_path(APP_NAME, appauthor=False) / PREFERENCES_FILENAME


def suggested_data_directory() -> Path:
    return user_data_path(APP_NAME, appauthor=False)


def data_path_for_directory(directory: PathLike) -> str:
    return os.path.join(normalize_path(directory), DATA_FILENAME)


def load_settings(path: Optional[PathLike] = None):
    """Load all machine-local settings, migrating version 1 in memory."""
    preferences_path = Path(path) if path is not None else preferences_file()
    if not preferences_path.exists():
        return default_settings()
    try:
        with preferences_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise PreferencesError(
            f"invalid preferences JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise PreferencesError(f"could not read preferences: {exc}") from exc

    if not isinstance(payload, dict):
        raise PreferencesError("preferences must contain a JSON object")
    version = payload.get("version")
    if version not in (1, PREFERENCES_VERSION):
        raise PreferencesError(
            f"unsupported preferences version {version!r}; expected 1 or {PREFERENCES_VERSION}"
        )
    directory = payload.get("data_directory")
    if directory is not None and (not isinstance(directory, str) or not directory.strip()):
        raise PreferencesError("preferences.data_directory must be a non-empty string")
    return {
        "version": PREFERENCES_VERSION,
        "data_directory": normalize_path(directory) if directory is not None else None,
        "insights": _validate_insights(payload.get("insights")),
    }


def load_preferences(path: Optional[PathLike] = None) -> Optional[str]:
    """Load and return the remembered data directory, or ``None`` if absent."""
    return load_settings(path)["data_directory"]


def _write_settings(settings, path: Optional[PathLike] = None):
    preferences_path = Path(path) if path is not None else preferences_file()
    preferences_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{preferences_path.name}.", suffix=".tmp", dir=preferences_path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, preferences_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def save_preferences(directory: PathLike, path: Optional[PathLike] = None) -> str:
    """Atomically remember a normalized data directory and return it."""
    normalized = normalize_path(directory)
    settings = load_settings(path)
    settings["data_directory"] = normalized
    _write_settings(settings, path)
    return normalized


def load_insights_settings(path: Optional[PathLike] = None):
    return load_settings(path)["insights"]


def save_insights_settings(insights, path: Optional[PathLike] = None):
    settings = load_settings(path)
    settings["insights"] = _validate_insights(insights)
    _write_settings(settings, path)
    return settings["insights"]


def resolve_startup_data_path(
    cli_data: Optional[PathLike] = None,
    preferences_path: Optional[PathLike] = None,
) -> Optional[str]:
    """Resolve CLI precedence, returning ``None`` when onboarding is required."""
    if cli_data is not None:
        return normalize_path(cli_data)
    directory = load_preferences(preferences_path)
    if directory is None:
        return None
    return data_path_for_directory(directory)
