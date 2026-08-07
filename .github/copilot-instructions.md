# Copilot Instructions — Packrat

## Quick Start

Install dependencies and run:
```bash
uv run python main.py
```

The app auto-creates `gear_data.json` with seeded example data on first run, so you can immediately see the full workflow. Use `uv` (recommended) for automatic environment management; fall back to `pip install -r requirements.txt` if needed.

---

## Architecture

**Two-layer separation:**

- **`gear_core.py`** — Pure data layer (no `input()`, `print()`, or Textual imports). Handles:
  - JSON load/save via atomic temp-file writes
  - Trip weight calculations and category breakdowns
  - Markdown rendering for exports (pack lists and inventory reports)
  - Constants: `CATEGORIES`, `CATEGORY_EMOJI`, `BIG_THREE`, `WEIGHT_TYPES`, thresholds
  - Helper functions: `find_gear()`, `find_trip()`, `compute_trip_summary()`, `total_weight_oz()`, etc.

- **`gear_tui.py`** — Textual UI layer. Handles:
  - Screens (gear inventory, trips tab, reports tab) and modal dialogs (forms, pickers, confirmations)
  - DataTable widgets, search filtering, keyboard + mouse bindings
  - CSS styling in `APP_CSS` (dark palette: forest green on very dark background)
  - All event handlers delegate persistence to `gear_core` functions

- **`main.py`** — Entry point; just invokes `gear_tui.main()`.

**Key principle:** Logic in `gear_core` is testable and reusable; all UI state lives in Textual widgets.

---

## Data Model & Schema

**Core structure** (defined in `gear_core.blank_data()`):
```python
{
  "meta": {"created": ISO_DATE, "version": 1},
  "gear": [  # list of items
    {
      "id": "G001", "category": "Shelter", "name": "...",
      "brand": "...", "weight_oz": float, "weight_type": "Base Weight|Worn Weight|Consumable",
      "qty": int, "usefulness": 1-5, "cost": float, "notes": str, "added": ISO_DATE
    },
    ...
  ],
  "trips": [  # list of trips
    {
      "id": "T001", "name": "...", "dates": str, "target_base_weight_lb": float,
      "notes": str, "created": ISO_DATE,
      "items": [{"gear_id": "G001", "note": "trip-specific note"}, ...]
    },
    ...
  ]
}
```

**Adding a new data field:**
1. Update `gear_core.blank_data()` and `example_data()` to include the field
2. Update relevant Markdown render functions (`render_trip_markdown()` or `render_inventory_markdown()`)
3. Add a form field in the corresponding `*FormScreen` class in `gear_tui.py`
4. Wire up the field read/write in form's `_save()` method

---

## Key Conventions

### Constants & Thresholds
- `CATEGORIES` — 15 predefined gear categories (Shelter, Sleep System, etc.)
- `WEIGHT_TYPES` — ["Base Weight", "Worn Weight", "Consumable"] (not weight units; OZ is assumed)
- `BIG_THREE` — {"Shelter", "Sleep System", "Pack"} — special tracking for ultralight metrics
- `REVIEW_WEIGHT_THRESHOLD_OZ = 8.0` and `REVIEW_USEFULNESS_THRESHOLD = 3` — flags for "Review Candidates"

### ID Generation
- `next_id(items, prefix)` — generates sequential IDs: G001, G002, ... and T001, T002, ...
- IDs are strings; always use them as strings in data structures

### Weight Math
- Everything is in **ounces** internally; conversions to lb happen only in display/export
- `total_weight_oz(item)` — single item total = `weight_oz * qty`
- `compute_trip_summary()` — aggregates all trip items into base/worn/consumable oz and category breakdown

### Data Persistence
- `load_data(path)` — reads JSON; auto-seeds with `example_data()` if file missing
- `save_data(path, data)` — atomic writes via temp file (`path + ".tmp"`, then `os.replace()`)
- **No locking** — avoid editing from multiple machines simultaneously or sync conflicts will create backup files

### Markdown Export
- `render_trip_markdown(data, trip)` — polished pack list with weights, charts, review flags, checkboxes
- `render_inventory_markdown(data)` — full inventory report with category breakdown
- Both use `bar(percent, width)` for ASCII bar charts; output must be readable as plain text

---

## UI Patterns (Textual)

### Screens & Navigation
- **`InventoryScreen`** — tables gear, search filter, add/edit/delete, "Review Candidates" button
- **`TripsScreen`** — lists trips, click to open trip dashboard (summary + assigned items + assign/remove)
- **`ReportsScreen`** — buttons to export trip pack lists or full inventory to `exports/` folder
- Modals: `GearFormScreen`, `TripFormScreen`, `GearPickerScreen`, `ConfirmScreen`

### Form Validation
- Do **not** save if required fields empty; use `self.app.notify(..., severity="error")`
- Cast numeric inputs in `_save()` with try/except; show error if invalid
- Always `.strip()` text inputs before saving

### Styling
- **All CSS is in `APP_CSS`** at top of `gear_tui.py` — one place to change colors
- Accent green: `#6EE7B7` (mint); sage: `#4A7856`; text: `#E7F5DA`; muted: `#9AAE8C`
- DataTable cursor highlight, button states, and dialog borders use these colors

### DataTable Rows & Events
- Use `@on(DataTable.RowSelected)` to highlight; double-click or Enter to open/edit
- Keyboard binding: `q` to quit, `Esc` to cancel dialogs
- Search filtering: live as user types (rebuild table from filtered list)

---

## Development Workflow

### Running the App
```bash
uv run python main.py
```

### Testing in the UI
- No unit test suite in the root; use headless Textual Pilot tests if available in dev branch
- Manually test: add gear, create trip, assign items, verify weights, export Markdown
- Terminal must be ≥130 × 42 characters for forms to display fully

### Adding a New Feature

**New data field:**
- Edit `blank_data()` → add field with default value
- Edit `example_data()` → add field to example item
- Edit `render_trip_markdown()` or similar → include new field in output
- Add form widget in `gear_tui.py` (label + Input/Select)

**New screen:**
- Subclass `Screen` in `gear_tui.py`
- Add `compose()` to build widgets, bindings, CSS classes
- Add action methods for keyboard shortcuts
- Wire from main app or existing screen via `self.app.push_screen(NewScreen())`

**Export format changes:**
- Edit `render_trip_markdown()` or `render_inventory_markdown()` in `gear_core.py`
- Test by running export in the UI and checking the generated `.md` file
- Keep output plain-text readable (no fancy Unicode that breaks on older terminals)

### Dependency Changes
- Modify `pyproject.toml` manually or install new package via `uv add <package>`
- Commit both `pyproject.toml` and `uv.lock` to ensure reproducible builds
- Fallback: run `pip freeze > requirements.txt` for pip-only users

---

## Common Gotchas

- **Modal dialogs cut off:** Terminal too small (need ≥130×42). Zoom or expand window.
- **Data file not created:** Check write permissions in the working directory.
- **Markdown export missing:** Files go to `exports/` subdirectory auto-created next to `gear_data.json`.
- **Weight calculations wrong:** Verify `qty` is set (defaults to 1) and `weight_type` matches the calculation logic (base/worn/consumable are summed separately).
- **Stale UI after edit:** Modal dismisses and returns updated dict; catch with `@on(SomeScreen.ScreenType.Submitted)` or similar pattern.

---

## Code Style Notes

- Keep `gear_core.py` free of side effects — it must be testable without mocking filesystem or terminal
- Comment only where logic is non-obvious; code is self-documenting otherwise
- Use descriptive variable names; e.g., `rows_sorted_by_weight`, not `r`
- Textual widgets: prefer `@on()` decorators over manual event binding
- Always use `self.query_one(selector, WidgetClass)` with type hint for safety

