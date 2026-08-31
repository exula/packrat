# Backpacking Gear Tracker

A mouse-and-keyboard terminal app for tracking backpacking gear and
building per-trip pack lists, built with [Textual](https://textual.textualize.io).
Data lives in one JSON file next to the code, so the whole thing is
portable — drop the folder in iCloud Drive / Dropbox / OneDrive and run it
from any Mac or Windows machine.

## Requirements

- Python 3.9+
- [`uv`](https://docs.astral.sh/uv/) (recommended) — or plain `pip`

## Running it

With `uv` (installs the right Python packages automatically, no manual venv):

```bash
uv run python main.py
```

Without `uv`:

```bash
pip install -r requirements.txt   # or: pip install textual
python3 main.py
```

To point at a data file somewhere else (e.g. a specific iCloud folder):

```bash
uv run python main.py --data "/Users/you/Library/Mobile Documents/com~apple~CloudDocs/Gear/gear_data.json"
```

## Files

- `main.py` — entry point.
- `gear_tui.py` — the Textual UI: screens, forms, tables, styling.
- `gear_core.py` — data model, JSON persistence, and Markdown rendering.
  Pure functions, no UI code — this is what generates the pack-list exports.
- `gear_data.json` — your data. Created automatically on first run if it
  doesn't exist, seeded with a few example items/trip (clearly labeled) so
  the format is obvious.
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
- **Ctrl+S** saves forms and picker dialogs; **Enter** confirms confirmations.
- **Ctrl+B** writes a manual `.bak` snapshot beside your data file.

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
  trips without affecting the others. Every trip you've ever planned stays
  in the file — full history, nothing gets overwritten.
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

## Backing it up

Press **Ctrl+B** for an on-demand snapshot, copy the JSON file whenever you
want a dated archive, or use iCloud/Dropbox/OneDrive version history.

## Development

Run the core and headless Textual tests with:

```bash
uv run python -m unittest discover -s tests -v
```

The same suite runs on Python 3.9 and 3.12 for every pull request.
