"""Cross-platform preference storage and startup path resolution for Packrat."""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Union

from platformdirs import user_config_path, user_data_path


APP_NAME = "Packrat"
PREFERENCES_VERSION = 1
PREFERENCES_FILENAME = "preferences.json"
DATA_FILENAME = "gear_data.json"

PathLike = Union[str, os.PathLike]


class PreferencesError(ValueError):
    """Raised when saved Packrat preferences are unreadable or invalid."""


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


def load_preferences(path: Optional[PathLike] = None) -> Optional[str]:
    """Load and return the remembered data directory, or ``None`` if absent."""
    preferences_path = Path(path) if path is not None else preferences_file()
    if not preferences_path.exists():
        return None
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
    if version != PREFERENCES_VERSION:
        raise PreferencesError(
            f"unsupported preferences version {version!r}; expected {PREFERENCES_VERSION}"
        )
    directory = payload.get("data_directory")
    if not isinstance(directory, str) or not directory.strip():
        raise PreferencesError("preferences.data_directory must be a non-empty string")
    return normalize_path(directory)


def save_preferences(directory: PathLike, path: Optional[PathLike] = None) -> str:
    """Atomically remember a normalized data directory and return it."""
    normalized = normalize_path(directory)
    preferences_path = Path(path) if path is not None else preferences_file()
    preferences_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        {"version": PREFERENCES_VERSION, "data_directory": normalized},
        indent=2,
        ensure_ascii=False,
    ) + "\n"
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
    return normalized


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
