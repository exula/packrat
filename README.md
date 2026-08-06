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

Everything is click-driven, with keyboard equivalents for everything:

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

Every save writes to a temp file and atomically replaces the real one, so
a crash or a synced-file conflict mid-write can't corrupt your data. Since
it's still a flat JSON file with no locking, avoid editing it from two
machines within the same iCloud/Dropbox sync cycle — if you do, you'll get
a conflicted-copy file instead of a merge, and you'd need to reconcile by
hand.

## Backing it up

It's one JSON file — `cp gear_data.json gear_data_backup_$(date +%F).json`
whenever you want a snapshot, or let iCloud/Dropbox/OneDrive version
history handle it.
