# Backpacking Gear Tracker

A mouse-and-keyboard terminal app for tracking backpacking gear and
building per-trip pack lists, built with [Textual](https://textual.textualize.io).
Data lives in one JSON file in a folder you choose on first launch. Packrat
remembers that folder in your operating system's standard application-config
location, so the code and your personal data remain separate. Choose an
iCloud Drive, Dropbox, or OneDrive folder if you want the library synced
between Windows, macOS, and Linux computers.

## Requirements

- Python 3.9+
- [`uv`](https://docs.astral.sh/uv/) (recommended) — or plain `pip`

## Running it

With `uv` (installs the right Python packages automatically, no manual venv):

```bash
uv run python main.py
```

The first launch opens a short setup screen. Accept the suggested
platform-specific folder or enter another folder; Packrat creates
`gear_data.json` there with clearly labeled example items.

Without `uv`:

```bash
pip install -r requirements.txt   # or: pip install textual platformdirs
python3 main.py
```

To use an exact data file for one launch without changing the remembered
preference:

```bash
uv run python main.py --data "/Users/you/Library/Mobile Documents/com~apple~CloudDocs/Gear/gear_data.json"
```

## Files

- `main.py` — entry point.
- `gear_tui.py` — the Textual UI: screens, forms, tables, styling.
- `gear_core.py` — data model, JSON persistence, and Markdown rendering.
  Pure functions, no UI code — this is what generates the pack-list exports.
- `packrat_preferences.py` — cross-platform preference paths and persistence.
- `gear_data.json` — created in your selected storage folder and seeded with
  a few example items/trip (clearly labeled) so the format is obvious. The
  repository copy is not used as the runtime default.
- `pyproject.toml` / `uv.lock` — project + locked dependencies for `uv`.
- `requirements.txt` — plain-pip fallback if you're not using `uv`.

## Using the app

Everything is click-driven, with keyboard equivalents for everything. Press
`?` in the app for the complete shortcut overlay. The most useful shortcuts
are:

- **1 / 2 / 3** switches between Gear, Trips, and Reports.
- **/** focuses the search box; **Esc** clears search and returns to the table.
- **A** adds, **E** edits, **Delete** deletes/removes, and **R** toggles review
  candidates when the relevant table is focused.
- In Trips, **D** duplicates and **C** compares. In a trip dashboard, **I**
  edits an item's quantity/note and **P** opens the pack audit.
- **Ctrl+S** saves forms and picker dialogs; **Enter** confirms confirmations.
- **Ctrl+B** writes a manual `.bak` snapshot beside your data file.
- **Ctrl+P** opens Storage Preferences to open another library or copy the
  current library to a new folder and switch to it.

- **Click a table row** to select it; **click it again** (or press Enter)
  to open/edit it. This two-step click mirrors how most file browsers work
  — a highlight first, then an activation — so you never open the wrong
  item by accident.
- **Gear Inventory tab** — search, add, edit, delete gear. The "Review
  Candidates" button filters to items rated low usefulness (<3/5) *and*
  over 8 oz — good first candidates to cut.
- **Trips tab** — click a trip to open its dashboard: live weight summary,
  a colored category-weight bar chart, and the assigned-gear list. Add or
  remove items right there; the same gear item can be on any number of
  trips without affecting the others. Quantities and notes are trip-specific,
  so a two-night plan can carry fewer consumables than a week-long plan
  without changing Gear Inventory.
- **Loadout variants** — select a trip and choose **Duplicate** (`D`) to make
  an independent copy. Choose **Compare** (`C`) to see base/skin-out weight,
  category, gear, and quantity differences between two trip plans.
- **Pack audit** — open a trip and choose **Pack Audit** (`P`). Categories
  represented by assigned gear are automatic; absent categories can be marked
  covered elsewhere, intentionally omitted, or left unresolved. This is a
  planning aid, not a universal safety prescription.
- **Trip history** — every trip you've planned stays in the file until you
  delete it; duplicating and editing a loadout never overwrites its source.
- **Reports tab** — export any trip's pack list, or the whole inventory,
  to a polished Markdown file (weight summary, category breakdown with a
  bar chart, heaviest items, review candidates, and a checkbox pack list)
  written to `exports/`.
- **Esc** cancels any dialog. **q** quits from the main screen.

## Data safety

Every save validates the complete data model, writes and flushes a temporary
file, and atomically replaces the real one. The previous version is retained
as `gear_data.json.bak`. Packrat also checks whether another process or sync
client changed the file after it was opened; if so, it refuses to overwrite
that newer copy and rolls the in-memory edit back.

It is still a flat JSON file rather than a mergeable database. If Packrat
reports an external-change conflict, restart it to load the newer file before
editing again.

## Storage preferences

The setup screen and Storage Preferences select a folder; the library inside
that folder is always named `gear_data.json`. **Open / Create** opens an
existing valid library or creates a new example library. **Copy Current &
Switch** copies the active library to an unused destination and leaves the
original file intact. It will not overwrite an existing destination library.

If the saved preference is damaged or its library cannot be opened, Packrat
returns to setup with the error instead of silently using another data file.
The `--data` option remains useful for scripts and one-off libraries and never
changes the remembered folder by itself.

## Backing it up

Press **Ctrl+B** for an on-demand snapshot, copy the JSON file whenever you
want a dated archive, or use iCloud/Dropbox/OneDrive version history.

## Development

Run the core and headless Textual tests with:

```bash
uv run python -m unittest discover -s tests -v
```

The suite covers JSON migration and validation, persistence, trip-specific
weight calculations, duplication, comparisons, pack-audit logic, Markdown
exports, and headless keyboard workflows.

The same suite runs on Python 3.9 and 3.12 for every pull request.
