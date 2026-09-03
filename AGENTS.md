# Packrat Repository Guide

This file is the authoritative guidance for coding agents working in this repository.

## Project Overview

Packrat is a Python 3.9+ terminal application for maintaining a backpacking gear inventory and building trip-specific pack lists. The UI uses Textual. User data is stored in a portable JSON library selected during onboarding; it is not normally the repository's `gear_data.json`.

## Commands

Use `uv` for the project environment.

```bash
# Run the application
uv run python main.py

# Run the committed unittest suite (including headless Textual tests)
uv run python -m unittest discover -s tests -v

# Run all pytest-style and unittest-style tests when pytest is available
uv run pytest
```

For a disposable library during manual testing, pass an exact file path:

```bash
uv run python main.py --data /tmp/packrat-test/gear_data.json
```

Do not use a developer's remembered personal library for automated or destructive testing.

## Architecture and Ownership

- `main.py`: minimal entry point; delegates to `gear_tui.main()`.
- `gear_core.py`: UI-independent data model, validation, calculations, persistence, backups, comparisons, audits, and Markdown rendering. Keep it free of Textual imports and terminal I/O.
- `packrat_preferences.py`: cross-platform config/data paths, atomic preference persistence, and startup-path precedence.
- `gear_tui.py`: Textual screens, widgets, bindings, application state, and CSS (`APP_CSS`). UI handlers should delegate domain logic and persistence to `gear_core.py`.
- `tests/test_core.py`, `tests/test_preferences.py`, `tests/test_tui.py`: current behavioral and headless workflow coverage.
- `tests/unit/`: additional unit coverage; preserve compatibility with it when changing core behavior.

Maintain the boundary between the pure core and the UI. If behavior can be expressed without Textual widgets, implement it in `gear_core.py` and test it there.

## Data and Persistence Invariants

- `gear_core.DATA_VERSION` is the current schema version. `validate_data()` accepts supported older data, supplies backward-compatible defaults, rejects ambiguous/invalid values, and upgrades the in-memory version.
- Gear and trip IDs are non-empty strings and unique within their collection. Generate sequential IDs with `next_id()` (`G001`, `T001`, and so on).
- All stored weights are ounces. Convert to pounds only for display or export.
- Inventory quantity and trip-specific quantity are distinct. A trip item contains `gear_id`, `qty`, and `note`; calculations must use the trip quantity.
- Trip audit values must use `AUDIT_STATUSES`; categories and weight types must use the canonical constants.
- Validate the complete model before saving. Preserve atomic writes, `.bak` creation, file signatures, conflict detection, and rollback-on-failure behavior.
- Exports belong in the `exports/` directory beside the active data file, as determined by `export_dir_for_data()`.
- The `--data` option is a one-launch exact-file override and must not update remembered preferences.
- The selected persistent storage directory always contains a library named `gear_data.json`.

When adding or changing persisted fields, update all affected layers together:

1. `blank_data()`, `example_data()`, validation/defaulting, and schema version/migration behavior as appropriate.
2. Calculations, duplication/comparison/audit logic, and Markdown renderers that consume the field.
3. The relevant Textual form and save/read paths.
4. Core tests plus headless UI coverage for user-visible workflows.

Never silently coerce malformed persisted values when doing so could change pack weights or meaning.

## UI Conventions

- Keep visual styling centralized in `APP_CSS`.
- Preserve keyboard and mouse parity. Existing global bindings include `1`/`2`/`3`, `/`, `?`, `Ctrl+B`, `Ctrl+P`, `q`, and `Ctrl+C`.
- Use `@on(...)` handlers and typed `query_one(selector, WidgetClass)` calls where practical.
- Strip text input, parse numeric fields explicitly, and notify with `severity="error"` rather than dismissing a form with invalid data.
- Modal forms use `Ctrl+S` to save and `Esc` to cancel. Confirmations must remain explicit for destructive actions.
- After a mutation, persist through `GearTrackerApp.save()` and refresh the affected view. Do not bypass its conflict handling or rollback behavior.

## Testing Expectations

- Add or update tests with every behavioral change.
- Prefer focused core tests for calculations, validation, migration, persistence, and Markdown output.
- Use Textual Pilot tests for navigation, bindings, dialogs, and complete keyboard workflows; do not rely only on manual UI checks.
- Use temporary directories and injected preference paths for filesystem tests. Tests must not read or modify real user preferences or libraries.
- Run at least `uv run python -m unittest discover -s tests -v` before handing off a change. Run `uv run pytest` too when modifying behavior covered by `tests/unit/`.
- Maintain Python 3.9 compatibility; avoid syntax and standard-library APIs introduced later.

## Dependencies and Style

- Add runtime dependencies to `pyproject.toml` with `uv add`; commit the resulting `uv.lock` change. Keep `requirements.txt` aligned for pip users when runtime dependencies change.
- Use clear names and small, focused functions. Comment rationale and non-obvious constraints, not mechanics visible from the code.
- Preserve unrelated working-tree changes. Generated caches, logs, personal data, and exports should not be committed unless the task explicitly requires a fixture or artifact.
