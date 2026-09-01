#!/usr/bin/env python3
"""
gear_tui.py — mouse-and-keyboard terminal UI for the Backpacking Gear
Tracker, built on Textual (https://textual.textualize.io).

Run:
    python3 gear_tui.py
    python3 gear_tui.py --data /path/to/gear_data.json

Requires: pip install textual platformdirs (see requirements.txt)
"""

import argparse
import copy
import os
import tempfile
from datetime import date
from typing import Optional, Tuple

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

import gear_core as gc
import packrat_preferences as preferences

# ---------------------------------------------------------------------------
# Styling — dark, outdoors-y palette; mouse hover states come free from
# Textual's `:hover` pseudo-class on interactive widgets.
# ---------------------------------------------------------------------------

APP_CSS = """
Screen {
    background: #10140F;
}

Header {
    background: #1B2A1D;
    color: #D8E8CE;
}

Footer {
    background: #1B2A1D;
}

TabbedContent {
    background: #10140F;
}

Tabs {
    background: #14190F;
}

Tab {
    color: #9AAE8C;
}

Tab.-active {
    color: #E7F5DA;
    text-style: bold;
}

.toolbar {
    height: auto;
    padding: 1 1 0 1;
    align: left middle;
}

.toolbar Input {
    width: 1fr;
    margin-right: 1;
}

.toolbar Button {
    margin-right: 1;
}

.status {
    width: auto;
    color: #7C8C71;
    padding: 0 1;
}

DataTable {
    height: 1fr;
    margin: 1;
    border: round #3A4A32;
}

DataTable > .datatable--header {
    background: #24331F;
    color: #E7F5DA;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #4A7856;
    color: #FFFFFF;
}

Button {
    min-width: 12;
}

Button.-success {
    background: #3E7A44;
}

Button.-error {
    background: #8A3A32;
}

ModalScreen {
    align: center middle;
    background: rgba(0, 0, 0, 0.6);
}

#dialog {
    background: #182015;
    border: thick #4A7856;
    padding: 1 2;
    width: 90%;
    max-width: 64;
    height: auto;
    max-height: 90%;
    overflow-y: auto;
}

#setup-dialog {
    background: #182015;
    border: thick #4A7856;
    padding: 2 3;
    width: 90%;
    max-width: 76;
    height: auto;
}

#setup-dialog Label, #preferences-dialog Label {
    color: #9AAE8C;
    padding-top: 1;
}

#setup-error, #preferences-error {
    color: #F2A29B;
    padding: 1 0;
}

#preferences-dialog {
    background: #182015;
    border: thick #4A7856;
    padding: 1 2;
    width: 90%;
    max-width: 76;
    height: auto;
}

.picker-dialog {
    width: 95%;
    max-width: 76;
    height: 34;
}

.picker-dialog DataTable {
    height: 1fr;
}

.dialog-title {
    text-style: bold;
    color: #E7F5DA;
    padding-bottom: 1;
}

.dialog-buttons {
    height: auto;
    padding-top: 1;
    align: right middle;
}

.dialog-buttons Button {
    margin-left: 1;
}

.form-dialog Label {
    color: #9AAE8C;
    padding-top: 1;
}

.field-row {
    height: auto;
}

.field-col {
    height: auto;
    width: 1fr;
}

.section-title {
    text-style: bold;
    color: #E7F5DA;
    padding: 1 1 0 1;
}

.dash-title {
    padding: 1 1 0 1;
    text-style: bold;
    color: #E7F5DA;
}

.panel {
    padding: 1;
    margin: 0 1;
    background: #182015;
    border: round #3A4A32;
}
"""


def fmt_id(item_id: Optional[str]) -> str:
    return item_id if item_id else "-"


def gear_search_blob(g: dict) -> str:
    return f"{g['name']} {g.get('brand','')} {g['category']} {g.get('notes','')}".lower()


def colored_bar(percent: float, width: int = 20) -> Text:
    """A two-tone Rich Text bar (accent green filled, muted empty) for use
    directly as a DataTable cell."""
    percent = max(0.0, min(100.0, percent))
    filled = round(percent / 100 * width)
    text = Text()
    text.append("█" * filled, style="#6EE7B7")
    text.append("░" * (width - filled), style="#3A4A32")
    return text


# ---------------------------------------------------------------------------
# Modal dialogs
# ---------------------------------------------------------------------------


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, message: str, danger: bool = False):
        super().__init__()
        self.message = message
        self.danger = danger

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.message)
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="c-cancel")
                yield Button("Confirm", id="c-confirm", variant="error" if self.danger else "success")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#c-cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#c-confirm")
    def _confirm(self) -> None:
        self.dismiss(True)


class GearFormScreen(ModalScreen[Optional[dict]]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, mode: str = "add", initial: Optional[dict] = None):
        super().__init__()
        self.mode = mode
        self.initial = initial or {}

    def compose(self) -> ComposeResult:
        title = "Add Gear Item" if self.mode == "add" else f"Edit: {self.initial.get('name','')}"
        with Vertical(id="dialog", classes="form-dialog"):
            yield Label(title, classes="dialog-title")
            yield Label("Category")
            yield Select([(c, c) for c in gc.CATEGORIES], id="f-category", allow_blank=False,
                         value=self.initial.get("category", gc.CATEGORIES[0]))
            yield Label("Item Name")
            yield Input(value=self.initial.get("name", ""), id="f-name", placeholder="e.g. Solo Tent")
            yield Label("Brand / Model")
            yield Input(value=self.initial.get("brand", ""), id="f-brand", placeholder="e.g. Big Agnes Copper Spur")
            with Horizontal(classes="field-row"):
                with Vertical(classes="field-col"):
                    yield Label("Weight (oz)")
                    yield Input(value=str(self.initial.get("weight_oz", "")), id="f-weight", type="number")
                with Vertical(classes="field-col"):
                    yield Label("Qty")
                    yield Input(value=str(self.initial.get("qty", 1)), id="f-qty", type="integer")
            yield Label("Weight Type")
            yield Select([(t, t) for t in gc.WEIGHT_TYPES], id="f-type", allow_blank=False,
                         value=self.initial.get("weight_type", "Base Weight"))
            with Horizontal(classes="field-row"):
                with Vertical(classes="field-col"):
                    yield Label("Usefulness (1-5)")
                    yield Select([(str(i), i) for i in range(1, 6)], id="f-usefulness", allow_blank=False,
                                 value=self.initial.get("usefulness", 3))
                with Vertical(classes="field-col"):
                    yield Label("Cost ($)")
                    yield Input(value=str(self.initial.get("cost", 0)), id="f-cost", type="number")
            yield Label("Notes")
            yield Input(value=self.initial.get("notes", ""), id="f-notes")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="f-cancel")
                yield Button("Save", id="f-save", variant="success")

    def on_mount(self) -> None:
        self.query_one("#f-name", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        self._save()

    @on(Button.Pressed, "#f-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#f-save")
    def _save(self) -> None:
        name = self.query_one("#f-name", Input).value.strip()
        if not name:
            self.app.notify("Item name is required", severity="error")
            return
        try:
            weight = float(self.query_one("#f-weight", Input).value or 0)
            qty = int(self.query_one("#f-qty", Input).value or 1)
            cost = float(self.query_one("#f-cost", Input).value or 0)
        except ValueError:
            self.app.notify("Weight, quantity, and cost must be numbers", severity="error")
            return
        if weight < 0 or cost < 0 or qty < 1:
            self.app.notify("Weight/cost cannot be negative and quantity must be at least 1", severity="error")
            return
        result = {
            "category": self.query_one("#f-category", Select).value,
            "name": name,
            "brand": self.query_one("#f-brand", Input).value.strip(),
            "weight_oz": weight,
            "weight_type": self.query_one("#f-type", Select).value,
            "qty": qty,
            "usefulness": self.query_one("#f-usefulness", Select).value,
            "cost": cost,
            "notes": self.query_one("#f-notes", Input).value.strip(),
        }
        if self.mode == "add":
            result["id"] = self.initial.get("id") or None  # set by caller
            result["added"] = date.today().isoformat()
        self.dismiss(result)


class TripFormScreen(ModalScreen[Optional[dict]]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, mode: str = "add", initial: Optional[dict] = None):
        super().__init__()
        self.mode = mode
        self.initial = initial or {}

    def compose(self) -> ComposeResult:
        title = "Add Trip" if self.mode == "add" else f"Edit: {self.initial.get('name','')}"
        with Vertical(id="dialog", classes="form-dialog"):
            yield Label(title, classes="dialog-title")
            yield Label("Trip Name")
            yield Input(value=self.initial.get("name", ""), id="t-name", placeholder="e.g. VA Triple Crown")
            yield Label("Dates / Season")
            yield Input(value=self.initial.get("dates", ""), id="t-dates", placeholder="e.g. Late October")
            yield Label("Target Base Weight (lb)")
            yield Input(value=str(self.initial.get("target_base_weight_lb") or ""), id="t-target", type="number")
            yield Label("Notes")
            yield Input(value=self.initial.get("notes", ""), id="t-notes")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="t-cancel")
                yield Button("Save", id="t-save", variant="success")

    def on_mount(self) -> None:
        self.query_one("#t-name", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        self._save()

    @on(Button.Pressed, "#t-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#t-save")
    def _save(self) -> None:
        name = self.query_one("#t-name", Input).value.strip()
        if not name:
            self.app.notify("Trip name is required", severity="error")
            return
        target_raw = self.query_one("#t-target", Input).value.strip()
        try:
            target = float(target_raw) if target_raw else None
        except ValueError:
            self.app.notify("Target base weight must be a number", severity="error")
            return
        if target is not None and target < 0:
            self.app.notify("Target base weight cannot be negative", severity="error")
            return
        result = {
            "name": name,
            "dates": self.query_one("#t-dates", Input).value.strip(),
            "target_base_weight_lb": target,
            "notes": self.query_one("#t-notes", Input).value.strip(),
        }
        self.dismiss(result)


class GearPickerScreen(ModalScreen[Optional[tuple]]):
    """Search + pick a gear item to add to a trip. Clicking a row adds it
    immediately (using whatever note text is currently typed); the button
    is there for keyboard users too."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "add", "Add selected"),
    ]

    def __init__(self, all_gear: list, exclude_ids: list):
        super().__init__()
        self.all_gear = all_gear
        self.exclude_ids = set(exclude_ids)

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog", classes="form-dialog picker-dialog"):
            yield Label("Add Gear to Trip — click a row to add it", classes="dialog-title")
            yield Input(placeholder="Search gear...", id="gp-search")
            yield DataTable(id="gp-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(classes="field-row"):
                with Vertical(classes="field-col"):
                    yield Label("Trip quantity")
                    yield Input(value="1", id="gp-qty", type="integer")
                with Vertical(classes="field-col"):
                    yield Label("Trip-specific note (optional)")
                    yield Input(id="gp-note", placeholder="e.g. borrowed, worn not packed")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="gp-cancel")
                yield Button("Add Selected", id="gp-add", variant="success")

    def on_mount(self) -> None:
        table = self.query_one("#gp-table", DataTable)
        table.add_columns("ID", "Category", "Item", "Wt (oz)")
        self._refresh("")
        self.query_one("#gp-search", Input).focus()

    def _refresh(self, text: str) -> None:
        table = self.query_one("#gp-table", DataTable)
        table.clear()
        t = text.lower().strip()
        for g in self.all_gear:
            if g["id"] in self.exclude_ids:
                continue
            if t and t not in gear_search_blob(g):
                continue
            table.add_row(g["id"], g["category"], g["name"], f"{gc.total_weight_oz(g):.1f}", key=g["id"])

    @on(Input.Changed, "#gp-search")
    def _search(self, event: Input.Changed) -> None:
        self._refresh(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_add(self) -> None:
        self._add()

    @on(Button.Pressed, "#gp-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    def _current_row_key(self) -> Optional[str]:
        table = self.query_one("#gp-table", DataTable)
        if table.row_count == 0:
            return None
        try:
            return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:
            return None

    @on(DataTable.RowSelected, "#gp-table")
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        self._dismiss_selection(event.row_key.value)

    @on(Button.Pressed, "#gp-add")
    def _add(self) -> None:
        gear_id = self._current_row_key()
        if gear_id is None:
            self.app.notify("No gear left to add (or nothing matches your search)", severity="warning")
            return
        self._dismiss_selection(gear_id)

    def _dismiss_selection(self, gear_id: str) -> None:
        try:
            qty = int(self.query_one("#gp-qty", Input).value or 1)
        except ValueError:
            qty = 0
        if qty < 1:
            self.app.notify("Trip quantity must be at least 1", severity="error")
            return
        note = self.query_one("#gp-note", Input).value.strip()
        self.dismiss((gear_id, qty, note))


class TripItemFormScreen(ModalScreen[Optional[dict]]):
    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("ctrl+s", "save", "Save")]

    def __init__(self, gear: dict, entry: dict):
        super().__init__()
        self.gear = gear
        self.entry = entry

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog", classes="form-dialog"):
            yield Label(f"Edit trip item: {self.gear['name']}", classes="dialog-title")
            yield Label(f"Inventory weight per unit: {self.gear['weight_oz']:.1f} oz")
            yield Label("Trip quantity")
            yield Input(value=str(self.entry.get("qty", self.gear.get("qty", 1))),
                        id="ti-qty", type="integer")
            yield Label("Trip-specific note")
            yield Input(value=self.entry.get("note", ""), id="ti-note")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="ti-cancel")
                yield Button("Save", id="ti-save", variant="success")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        self._save()

    @on(Button.Pressed, "#ti-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#ti-save")
    def _save(self) -> None:
        try:
            qty = int(self.query_one("#ti-qty", Input).value or 0)
        except ValueError:
            qty = 0
        if qty < 1:
            self.app.notify("Trip quantity must be at least 1", severity="error")
            return
        self.dismiss({"qty": qty, "note": self.query_one("#ti-note", Input).value.strip()})


class PackAuditScreen(ModalScreen[Optional[dict]]):
    """Let the user resolve categories that are not represented by gear."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("space", "cycle", "Cycle status"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, data: dict, trip: dict):
        super().__init__()
        self.data = data
        self.trip = trip
        self.audit = copy.deepcopy(trip.get("audit", {}))

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog", classes="picker-dialog"):
            yield Label("Pack Audit", classes="dialog-title")
            yield Static("Packed categories are automatic. For anything absent, mark it covered "
                         "elsewhere, intentionally omitted, or leave it unresolved.")
            yield DataTable(id="audit-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cycle Status", id="audit-cycle", variant="primary")
                yield Button("Cancel", id="audit-cancel")
                yield Button("Save", id="audit-save", variant="success")

    def on_mount(self) -> None:
        self.query_one("#audit-table", DataTable).add_columns("Category", "Status")
        self._refresh()

    def _audit_summary(self) -> dict:
        temporary = copy.deepcopy(self.trip)
        temporary["audit"] = self.audit
        return gc.compute_pack_audit(self.data, temporary)

    def _refresh(self) -> None:
        table = self.query_one("#audit-table", DataTable)
        selected = None
        if table.row_count:
            try:
                selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
            except Exception:
                pass
        table.clear()
        for row in self._audit_summary()["rows"]:
            table.add_row(row["category"], row["status"].replace("_", " ").title(),
                          key=row["category"])
        if selected:
            table.move_cursor(row=table.get_row_index(selected), animate=False)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_cycle(self) -> None:
        self._cycle()

    def action_save(self) -> None:
        self.dismiss({key: value for key, value in self.audit.items() if value != "unresolved"})

    @on(Button.Pressed, "#audit-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#audit-save")
    def _save(self) -> None:
        self.action_save()

    @on(Button.Pressed, "#audit-cycle")
    @on(DataTable.RowSelected, "#audit-table")
    def _cycle(self) -> None:
        table = self.query_one("#audit-table", DataTable)
        if not table.row_count:
            return
        category = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        row = next(row for row in self._audit_summary()["rows"] if row["category"] == category)
        if row["status"] == "packed":
            self.app.notify("This category is represented by assigned gear", timeout=2)
            return
        cycle = {"unresolved": "covered", "covered": "omitted", "omitted": "unresolved"}
        self.audit[category] = cycle[row["status"]]
        self._refresh()


class TripComparisonScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back"), Binding("b", "go_back", "Back")]

    def __init__(self, data: dict, left_trip_id: str):
        super().__init__()
        self.data = data
        self.left_trip_id = left_trip_id
        self.other_trips = [trip for trip in data["trips"] if trip["id"] != left_trip_id]

    def compose(self) -> ComposeResult:
        left = gc.find_trip(self.data, self.left_trip_id)
        options = [(trip["name"], trip["id"]) for trip in self.other_trips]
        yield Header(show_clock=True, time_format="%I:%M %p")
        with VerticalScroll(id="dash-scroll"):
            yield Static(f"Compare against: {left['name']}", classes="dash-title")
            yield Select(options, value=options[0][1], allow_blank=False, id="compare-trip")
            yield Static(id="compare-summary", classes="panel")
            yield Static("Category Changes (comparison minus baseline)", classes="section-title")
            yield DataTable(id="compare-categories", cursor_type="none", zebra_stripes=True)
            yield Static("Gear Changes", classes="section-title")
            yield DataTable(id="compare-items", cursor_type="none", zebra_stripes=True)
            with Horizontal(classes="toolbar"):
                yield Button("← Back", id="compare-back")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#compare-categories", DataTable).add_columns("Category", "Delta (oz)")
        self.query_one("#compare-items", DataTable).add_columns(
            "Change", "Category", "Item", "Qty", "Delta (oz)")
        self._refresh(self.other_trips[0]["id"])

    @on(Select.Changed, "#compare-trip")
    def _selection_changed(self, event: Select.Changed) -> None:
        if event.value != Select.BLANK:
            self._refresh(str(event.value))

    def _refresh(self, right_trip_id: str) -> None:
        left = gc.find_trip(self.data, self.left_trip_id)
        right = gc.find_trip(self.data, right_trip_id)
        comparison = gc.compare_trips(self.data, left, right)
        self.query_one("#compare-summary", Static).update(
            f"[b]{right['name']}[/b] compared with [b]{left['name']}[/b]\n"
            f"Base: {comparison['left']['base_lb']:.2f} → {comparison['right']['base_lb']:.2f} lb "
            f"({comparison['base_delta_lb']:+.2f} lb)   "
            f"Skin-out: {comparison['left']['total_lb']:.2f} → "
            f"{comparison['right']['total_lb']:.2f} lb ({comparison['total_delta_lb']:+.2f} lb)")
        categories = self.query_one("#compare-categories", DataTable)
        categories.clear()
        for category, delta in sorted(comparison["category_deltas"].items(),
                                      key=lambda item: -abs(item[1])):
            categories.add_row(category, f"{delta:+.1f}")
        items = self.query_one("#compare-items", DataTable)
        items.clear()
        for row in comparison["added"]:
            items.add_row("Added", row["category"], row["name"], str(row["qty"]),
                          f"+{row['total_oz']:.1f}")
        for row in comparison["removed"]:
            items.add_row("Removed", row["category"], row["name"], str(row["qty"]),
                          f"-{row['total_oz']:.1f}")
        for row in comparison["changed"]:
            items.add_row("Quantity", row["category"], row["name"],
                          f"{row['left_qty']}→{row['right_qty']}", f"{row['delta_oz']:+.1f}")

    def action_go_back(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#compare-back")
    def _back(self) -> None:
        self.dismiss()


class ShortcutHelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("question_mark", "close", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        help_text = """[b]Keyboard shortcuts[/b]

[b]Anywhere[/b]       1 / 2 / 3  Switch tabs     /  Search     ?  This help
                 Ctrl+B  Backup data   Ctrl+P  Preferences   Q  Quit

[b]Gear[/b]           A  Add      E  Edit      Delete  Delete      R  Review filter
[b]Trips[/b]          A  Add      Enter  Open  D  Duplicate  C  Compare  Delete  Delete
[b]Trip dashboard[/b] A  Add item I  Edit qty/note E  Edit trip P  Pack audit
                 Delete  Remove     X  Export
[b]Dialogs[/b]        Ctrl+S  Save/add          Esc  Cancel
[b]Confirmations[/b]  Enter  Confirm            Esc  Cancel

[dim]Arrow keys move through tables. Enter activates the selected row.[/dim]"""
        with Vertical(id="dialog"):
            yield Static(help_text)
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", id="help-close", variant="primary")

    def action_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#help-close")
    def _close(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Trip dashboard (full screen, pushed when a trip is opened)
# ---------------------------------------------------------------------------


class TripDashboardScreen(Screen):
    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("b", "go_back", "Back"),
        Binding("a", "add_item", "Add item"),
        Binding("i", "edit_item", "Edit item"),
        Binding("e", "edit_trip", "Edit trip"),
        Binding("p", "pack_audit", "Pack audit"),
        Binding("delete", "remove_item", "Remove"),
        Binding("x", "export", "Export"),
    ]

    def __init__(self, trip_id: str):
        super().__init__()
        self.trip_id = trip_id

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, time_format="%I:%M %p")
        with VerticalScroll(id="dash-scroll"):
            yield Static(id="dash-title", classes="dash-title")
            yield Static(id="dash-summary", classes="panel")
            yield Static("Category Breakdown", classes="section-title")
            yield DataTable(id="dash-cat-table", zebra_stripes=True, cursor_type="none")
            yield Static("Assigned Gear — select a row, then Remove to take it off this trip",
                         classes="section-title")
            yield DataTable(id="dash-items-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(classes="toolbar"):
                yield Button("+ Add Item", id="dash-add-item", variant="success")
                yield Button("Edit Qty/Note", id="dash-edit-item", variant="primary")
                yield Button("Remove Selected", id="dash-remove-item", variant="error")
                yield Button("Pack Audit", id="dash-audit", variant="primary")
                yield Button("Edit Trip Info", id="dash-edit-trip", variant="primary")
                yield Button("Export to Markdown", id="dash-export", variant="primary")
                yield Button("← Back", id="dash-back")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#dash-cat-table", DataTable).add_columns(
            "Category", "Wt (oz)", "Wt (lb)", "Distribution")
        self.query_one("#dash-items-table", DataTable).add_columns(
            "ID", "Category", "Item", "Qty", "Wt (oz)", "Flag", "Note")
        self.refresh_dashboard()

    def refresh_dashboard(self) -> None:
        app: "GearTrackerApp" = self.app  # type: ignore
        trip = gc.find_trip(app.data, self.trip_id)
        if not trip:
            self.app.pop_screen()
            return
        s = gc.compute_trip_summary(app.data, trip)

        self.query_one("#dash-title", Static).update(
            f"🏔️  {trip['name']}" + (f"  ·  {trip['dates']}" if trip.get("dates") else ""))

        lines = [
            f"Base [b]{s['base_lb']:.2f} lb[/b] ({s['base_oz']:.1f} oz)   "
            f"Worn {s['worn_oz']:.1f} oz   Consumable {s['consumable_oz']:.1f} oz   "
            f"Total [b]{s['total_lb']:.2f} lb[/b] skin-out"
        ]
        if s["target_lb"]:
            if s["delta_lb"] <= 0:
                lines.append(f"[#7CD992]{abs(s['delta_lb']):.2f} lb under target "
                             f"({s['target_lb']:.1f} lb)[/#7CD992]")
            else:
                lines.append(f"[#E08B6A]{s['delta_lb']:.2f} lb OVER target "
                             f"({s['target_lb']:.1f} lb)[/#E08B6A]")
        else:
            lines.append("[dim]No target base weight set for this trip.[/dim]")
        if s["category_oz"] and s["total_oz"]:
            big3_pct = s["big_three_oz"] / s["total_oz"] * 100
            lines.append(f"Big Three (shelter + sleep + pack): {s['big_three_lb']:.2f} lb "
                         f"({big3_pct:.0f}% of total)")
        if trip.get("notes"):
            lines.append(f"[dim]{trip['notes']}[/dim]")
        audit = s["audit"]
        if audit["unresolved"]:
            lines.append(f"[#E0B46A]Pack audit: {audit['unresolved']} unresolved categories[/#E0B46A]")
        else:
            lines.append("[#7CD992]Pack audit resolved[/#7CD992]")
        self.query_one("#dash-summary", Static).update("\n".join(lines))

        cat_table = self.query_one("#dash-cat-table", DataTable)
        cat_table.clear()
        if s["category_oz"]:
            max_oz = max(s["category_oz"].values())
            for cat, oz in sorted(s["category_oz"].items(), key=lambda kv: -kv[1]):
                pct = (oz / max_oz * 100) if max_oz else 0
                cat_table.add_row(cat, f"{oz:.1f}", f"{oz/16:.2f}", colored_bar(pct, width=20))

        items_table = self.query_one("#dash-items-table", DataTable)
        items_table.clear()
        for row in sorted(s["rows"], key=lambda r: -r["total_oz"]):
            g = row["gear"]
            flag = "REVIEW" if row["review_flag"] else ""
            items_table.add_row(g["id"], g["category"], g["name"], str(row["trip_qty"]),
                                f"{row['total_oz']:.1f}",
                                flag, row["trip_note"], key=g["id"])

    def action_go_back(self) -> None:
        self.dismiss()

    def action_add_item(self) -> None:
        self._add_item()

    def action_edit_item(self) -> None:
        self._edit_item()

    def action_edit_trip(self) -> None:
        self._edit_trip()

    def action_pack_audit(self) -> None:
        self._pack_audit()

    def action_remove_item(self) -> None:
        self._remove_item()

    def action_export(self) -> None:
        self._export()

    @on(Button.Pressed, "#dash-back")
    def _back(self) -> None:
        self.dismiss()

    def _current_item_gear_id(self) -> Optional[str]:
        table = self.query_one("#dash-items-table", DataTable)
        if table.row_count == 0:
            return None
        try:
            return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:
            return None

    @on(Button.Pressed, "#dash-add-item")
    def _add_item(self) -> None:
        app: "GearTrackerApp" = self.app  # type: ignore
        trip = gc.find_trip(app.data, self.trip_id)
        exclude = [i["gear_id"] for i in trip["items"]]

        def handle(result):
            if result:
                gear_id, qty, note = result
                trip["items"].append({"gear_id": gear_id, "qty": qty, "note": note})
                if not app.save():
                    return
                self.refresh_dashboard()
                self.app.notify("Added to trip", severity="information", timeout=2)

        self.app.push_screen(GearPickerScreen(app.data["gear"], exclude), handle)

    @on(Button.Pressed, "#dash-edit-item")
    def _edit_item(self) -> None:
        gear_id = self._current_item_gear_id()
        if gear_id is None:
            return
        app: "GearTrackerApp" = self.app  # type: ignore
        trip = gc.find_trip(app.data, self.trip_id)
        gear = gc.find_gear(app.data, gear_id)
        entry = next(item for item in trip["items"] if item["gear_id"] == gear_id)

        def handle(result):
            if result:
                entry.update(result)
                if not app.save():
                    self.refresh_dashboard()
                    return
                self.refresh_dashboard()

        self.app.push_screen(TripItemFormScreen(gear, entry), handle)

    @on(Button.Pressed, "#dash-audit")
    def _pack_audit(self) -> None:
        app: "GearTrackerApp" = self.app  # type: ignore
        trip = gc.find_trip(app.data, self.trip_id)

        def handle(result):
            if result is not None:
                trip["audit"] = result
                if not app.save():
                    self.refresh_dashboard()
                    return
                self.refresh_dashboard()

        self.app.push_screen(PackAuditScreen(app.data, trip), handle)

    @on(Button.Pressed, "#dash-remove-item")
    def _remove_item(self) -> None:
        gear_id = self._current_item_gear_id()
        if gear_id is None:
            return
        app: "GearTrackerApp" = self.app  # type: ignore
        trip = gc.find_trip(app.data, self.trip_id)
        gear = gc.find_gear(app.data, gear_id)
        name = gear["name"] if gear else gear_id

        def handle(confirmed):
            if confirmed:
                trip["items"] = [i for i in trip["items"] if i["gear_id"] != gear_id]
                if not app.save():
                    self.refresh_dashboard()
                    return
                self.refresh_dashboard()

        self.app.push_screen(ConfirmScreen(f"Remove '{name}' from this trip?", danger=True), handle)

    @on(Button.Pressed, "#dash-edit-trip")
    def _edit_trip(self) -> None:
        app: "GearTrackerApp" = self.app  # type: ignore
        trip = gc.find_trip(app.data, self.trip_id)

        def handle(result):
            if result:
                trip.update(result)
                if not app.save():
                    self.refresh_dashboard()
                    return
                self.refresh_dashboard()

        self.app.push_screen(TripFormScreen(mode="edit", initial=trip), handle)

    @on(Button.Pressed, "#dash-export")
    def _export(self) -> None:
        app: "GearTrackerApp" = self.app  # type: ignore
        trip = gc.find_trip(app.data, self.trip_id)
        md = gc.render_trip_markdown(app.data, trip)
        fname = f"{gc.safe_filename(trip['name'])}_{date.today().isoformat()}.md"
        app.write_export(fname, md)


# ---------------------------------------------------------------------------
# Gear Inventory pane
# ---------------------------------------------------------------------------


class GearPane(Vertical):
    BINDINGS = [
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("delete", "delete", "Delete"),
        Binding("r", "review", "Review"),
        Binding("escape", "clear_search", "Clear search", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(classes="toolbar"):
            yield Input(placeholder="Search gear (name, brand, category, notes)...", id="gear-search")
            yield Button("+ Add Item", id="gear-add", variant="success")
        yield DataTable(id="gear-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(classes="toolbar"):
            yield Button("Edit", id="gear-edit", variant="primary")
            yield Button("Delete", id="gear-delete", variant="error")
            yield Button("Review Candidates", id="gear-review")
            yield Static(id="gear-status", classes="status")

    def on_mount(self) -> None:
        table = self.query_one("#gear-table", DataTable)
        table.add_columns("ID", "Category", "Item", "Wt (oz)", "Type", "Qty", "Use", "Flag")
        self.refresh_table()

    def refresh_table(self, filter_text: str = "", review_only: bool = False) -> None:
        app: "GearTrackerApp" = self.app  # type: ignore
        table = self.query_one("#gear-table", DataTable)
        selected_id = self._current_gear_id()
        table.clear()
        gear = sorted(app.data["gear"], key=lambda g: (g["category"], -gc.total_weight_oz(g)))
        t = filter_text.lower().strip()
        count = 0
        visible_ids = set()
        for g in gear:
            if review_only and not gc.is_review_flagged(g):
                continue
            if t and t not in gear_search_blob(g):
                continue
            flag = "REVIEW" if gc.is_review_flagged(g) else ""
            table.add_row(g["id"], g["category"], g["name"], f"{gc.total_weight_oz(g):.1f}",
                         g["weight_type"], str(g["qty"]), f"{g['usefulness']}/5", flag, key=g["id"])
            count += 1
            visible_ids.add(g["id"])
        if selected_id in visible_ids:
            table.move_cursor(row=table.get_row_index(selected_id), animate=False)
        label = f"{count} item(s)" + (" · review filter on" if review_only else "")
        self.query_one("#gear-status", Static).update(label)

    @on(Input.Changed, "#gear-search")
    def _search_changed(self, event: Input.Changed) -> None:
        self.refresh_table(event.value, review_only=getattr(self, "_review_only", False))

    def _refresh_current(self) -> None:
        self.refresh_table(
            self.query_one("#gear-search", Input).value,
            review_only=getattr(self, "_review_only", False),
        )

    def action_add(self) -> None:
        self._add()

    def action_edit(self) -> None:
        self._edit_button()

    def action_delete(self) -> None:
        self._delete()

    def action_review(self) -> None:
        self._toggle_review()

    def action_clear_search(self) -> None:
        search = self.query_one("#gear-search", Input)
        search.value = ""
        self.query_one("#gear-table", DataTable).focus()

    @on(Button.Pressed, "#gear-add")
    def _add(self) -> None:
        def handle(result):
            if result:
                result["id"] = gc.next_id(self.app.data["gear"], "G")  # type: ignore
                self.app.data["gear"].append(result)  # type: ignore
                if not self.app.save():  # type: ignore
                    self._refresh_current()
                    return
                self._refresh_current()
                self.app.notify(f"Added {result['name']}", timeout=2)

        self.app.push_screen(GearFormScreen(mode="add"), handle)

    def _current_gear_id(self) -> Optional[str]:
        table = self.query_one("#gear-table", DataTable)
        if table.row_count == 0:
            return None
        try:
            return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:
            return None

    def _edit_gear(self, gear_id: Optional[str]) -> None:
        app: "GearTrackerApp" = self.app  # type: ignore
        if gear_id is None:
            return
        gear = gc.find_gear(app.data, gear_id)
        if not gear:
            return

        def handle(result):
            if result:
                result.pop("id", None)
                result.pop("added", None)
                gear.update(result)
                if not app.save():
                    self._refresh_current()
                    return
                self._refresh_current()

        self.app.push_screen(GearFormScreen(mode="edit", initial=gear), handle)

    @on(DataTable.RowSelected, "#gear-table")
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        self._edit_gear(event.row_key.value)

    @on(Button.Pressed, "#gear-edit")
    def _edit_button(self) -> None:
        self._edit_gear(self._current_gear_id())

    @on(Button.Pressed, "#gear-delete")
    def _delete(self) -> None:
        gear_id = self._current_gear_id()
        if gear_id is None:
            return
        app: "GearTrackerApp" = self.app  # type: ignore
        gear = gc.find_gear(app.data, gear_id)
        if not gear:
            return
        refs = gc.trips_referencing_gear(app.data, gear_id)
        msg = f"Delete '{gear['name']}'?"
        if refs:
            msg += "\n\nAlso removes it from: " + ", ".join(t["name"] for t in refs)

        def handle(confirmed):
            if confirmed:
                for t in refs:
                    t["items"] = [i for i in t["items"] if i["gear_id"] != gear_id]
                app.data["gear"] = [g for g in app.data["gear"] if g["id"] != gear_id]
                if not app.save():
                    self._refresh_current()
                    return
                self._refresh_current()

        self.app.push_screen(ConfirmScreen(msg, danger=True), handle)

    @on(Button.Pressed, "#gear-review")
    def _toggle_review(self) -> None:
        btn = self.query_one("#gear-review", Button)
        self._review_only = not getattr(self, "_review_only", False)
        btn.variant = "warning" if self._review_only else "default"
        self.refresh_table(self.query_one("#gear-search", Input).value, review_only=self._review_only)


# ---------------------------------------------------------------------------
# Trips pane
# ---------------------------------------------------------------------------


class TripsPane(Vertical):
    BINDINGS = [
        Binding("a", "add", "Add"),
        Binding("enter", "open", "Open"),
        Binding("d", "duplicate", "Duplicate"),
        Binding("c", "compare", "Compare"),
        Binding("delete", "delete", "Delete"),
        Binding("escape", "clear_search", "Clear search", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(classes="toolbar"):
            yield Input(placeholder="Search trips...", id="trip-search")
            yield Button("+ Add Trip", id="trip-add", variant="success")
        yield DataTable(id="trip-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(classes="toolbar"):
            yield Button("Open Dashboard", id="trip-open", variant="primary")
            yield Button("Duplicate", id="trip-duplicate", variant="primary")
            yield Button("Compare", id="trip-compare", variant="primary")
            yield Button("Delete", id="trip-delete", variant="error")
            yield Static(id="trip-status", classes="status")

    def on_mount(self) -> None:
        table = self.query_one("#trip-table", DataTable)
        table.add_columns("ID", "Name", "Dates", "Items", "Base (lb)", "Target (lb)", "vs Target")
        self.refresh_table()

    def refresh_table(self, filter_text: str = "") -> None:
        app: "GearTrackerApp" = self.app  # type: ignore
        table = self.query_one("#trip-table", DataTable)
        selected_id = self._current_trip_id()
        table.clear()
        t = filter_text.lower().strip()
        count = 0
        visible_ids = set()
        for trip in app.data["trips"]:
            blob = f"{trip['name']} {trip.get('dates','')}".lower()
            if t and t not in blob:
                continue
            s = gc.compute_trip_summary(app.data, trip)
            target = f"{s['target_lb']:.1f}" if s["target_lb"] else "-"
            if s["delta_lb"] is None:
                delta = "-"
            elif s["delta_lb"] <= 0:
                delta = f"{s['delta_lb']:+.2f} ok"
            else:
                delta = f"{s['delta_lb']:+.2f} over"
            table.add_row(trip["id"], trip["name"], trip.get("dates", ""), str(len(trip["items"])),
                         f"{s['base_lb']:.2f}", target, delta, key=trip["id"])
            count += 1
            visible_ids.add(trip["id"])
        if selected_id in visible_ids:
            table.move_cursor(row=table.get_row_index(selected_id), animate=False)
        self.query_one("#trip-status", Static).update(f"{count} trip(s)")

    @on(Input.Changed, "#trip-search")
    def _search_changed(self, event: Input.Changed) -> None:
        self.refresh_table(event.value)

    def action_add(self) -> None:
        self._add()

    def action_open(self) -> None:
        self._open_button()

    def action_delete(self) -> None:
        self._delete()

    def action_duplicate(self) -> None:
        self._duplicate()

    def action_compare(self) -> None:
        self._compare()

    def action_clear_search(self) -> None:
        search = self.query_one("#trip-search", Input)
        search.value = ""
        self.query_one("#trip-table", DataTable).focus()

    @on(Button.Pressed, "#trip-add")
    def _add(self) -> None:
        def handle(result):
            if result:
                result["id"] = gc.next_id(self.app.data["trips"], "T")  # type: ignore
                result["created"] = date.today().isoformat()
                result["items"] = []
                self.app.data["trips"].append(result)  # type: ignore
                if not self.app.save():  # type: ignore
                    self.refresh_table()
                    return
                self.refresh_table()
                self.app.notify(f"Added trip {result['name']}", timeout=2)

        self.app.push_screen(TripFormScreen(mode="add"), handle)

    def _current_trip_id(self) -> Optional[str]:
        table = self.query_one("#trip-table", DataTable)
        if table.row_count == 0:
            return None
        try:
            return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:
            return None

    def _open_dashboard(self, trip_id: Optional[str]) -> None:
        if trip_id is None:
            return
        self.app.push_screen(TripDashboardScreen(trip_id), lambda _: self.refresh_table(
            self.query_one("#trip-search", Input).value))

    @on(DataTable.RowSelected, "#trip-table")
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        self._open_dashboard(event.row_key.value)

    @on(Button.Pressed, "#trip-open")
    def _open_button(self) -> None:
        self._open_dashboard(self._current_trip_id())

    @on(Button.Pressed, "#trip-duplicate")
    def _duplicate(self) -> None:
        trip_id = self._current_trip_id()
        if trip_id is None:
            return
        app: "GearTrackerApp" = self.app  # type: ignore
        source = gc.find_trip(app.data, trip_id)
        duplicate = gc.duplicate_trip(app.data, source)
        app.data["trips"].append(duplicate)
        if not app.save():
            self.refresh_table()
            return
        self.refresh_table(self.query_one("#trip-search", Input).value)
        self.query_one("#trip-table", DataTable).move_cursor(
            row=self.query_one("#trip-table", DataTable).get_row_index(duplicate["id"]), animate=False)
        self.app.notify(f"Created {duplicate['name']}", timeout=3)

    @on(Button.Pressed, "#trip-compare")
    def _compare(self) -> None:
        trip_id = self._current_trip_id()
        if trip_id is None:
            return
        app: "GearTrackerApp" = self.app  # type: ignore
        if len(app.data["trips"]) < 2:
            self.app.notify("Duplicate or add another trip before comparing", severity="warning")
            return
        self.app.push_screen(TripComparisonScreen(app.data, trip_id))

    @on(Button.Pressed, "#trip-delete")
    def _delete(self) -> None:
        trip_id = self._current_trip_id()
        if trip_id is None:
            return
        app: "GearTrackerApp" = self.app  # type: ignore
        trip = gc.find_trip(app.data, trip_id)

        def handle(confirmed):
            if confirmed:
                app.data["trips"] = [t for t in app.data["trips"] if t["id"] != trip_id]
                if not app.save():
                    self.refresh_table()
                    return
                self.refresh_table()

        self.app.push_screen(
            ConfirmScreen(f"Delete trip '{trip['name']}'? Gear Inventory is unaffected.", danger=True), handle)


# ---------------------------------------------------------------------------
# Reports pane
# ---------------------------------------------------------------------------


class ReportsPane(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("Export a trip's pack list, or the full inventory, to Markdown.", classes="section-title")
        yield DataTable(id="report-trip-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(classes="toolbar"):
            yield Button("Export Selected Trip", id="report-export-trip", variant="success")
            yield Button("Export Full Inventory", id="report-export-inventory", variant="primary")
        yield Static(id="report-status", classes="status panel")

    def on_mount(self) -> None:
        self.query_one("#report-trip-table", DataTable).add_columns("ID", "Name", "Dates", "Items")
        self.refresh_table()
        app: "GearTrackerApp" = self.app  # type: ignore
        self.query_one("#report-status", Static).update(f"Exports are written to: {app.export_dir}")

    def refresh_table(self) -> None:
        app: "GearTrackerApp" = self.app  # type: ignore
        table = self.query_one("#report-trip-table", DataTable)
        table.clear()
        for trip in app.data["trips"]:
            table.add_row(trip["id"], trip["name"], trip.get("dates", ""), str(len(trip["items"])), key=trip["id"])

    @on(Button.Pressed, "#report-export-trip")
    def _export_trip(self) -> None:
        table = self.query_one("#report-trip-table", DataTable)
        if table.row_count == 0:
            self.app.notify("No trips to export yet", severity="warning")
            return
        trip_id = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        app: "GearTrackerApp" = self.app  # type: ignore
        trip = gc.find_trip(app.data, trip_id)
        md = gc.render_trip_markdown(app.data, trip)
        fname = f"{gc.safe_filename(trip['name'])}_{date.today().isoformat()}.md"
        path = app.write_export(fname, md)
        if path:
            self.query_one("#report-status", Static).update(f"Wrote {path}")

    @on(Button.Pressed, "#report-export-inventory")
    def _export_inventory(self) -> None:
        app: "GearTrackerApp" = self.app  # type: ignore
        md = gc.render_inventory_markdown(app.data)
        fname = f"gear_inventory_{date.today().isoformat()}.md"
        path = app.write_export(fname, md)
        if path:
            self.query_one("#report-status", Static).update(f"Wrote {path}")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


def _prepare_library(directory: str) -> Tuple[str, dict, bool]:
    """Validate a folder and load or create its Packrat library."""
    normalized_directory = preferences.normalize_path(directory)
    if os.path.exists(normalized_directory) and not os.path.isdir(normalized_directory):
        raise OSError(f"not a folder: {normalized_directory}")
    os.makedirs(normalized_directory, exist_ok=True)

    descriptor, probe_path = tempfile.mkstemp(prefix=".packrat-write-test.", dir=normalized_directory)
    os.close(descriptor)
    os.unlink(probe_path)

    data_path = preferences.data_path_for_directory(normalized_directory)
    created = not os.path.exists(data_path)
    if created:
        data = gc.example_data()
        gc.save_data(data_path, data)
    else:
        data = gc.load_data(data_path)
    return data_path, data, created


class SetupApp(App):
    """Small bootstrap app shown before a first Packrat library exists."""

    CSS = APP_CSS + "\nScreen { align: center middle; }"
    TITLE = "Packrat Setup"
    AUTO_FOCUS = "#setup-folder"

    def __init__(self, initial_error: str = "", preferences_path: Optional[str] = None):
        super().__init__()
        self.initial_error = initial_error
        self.preferences_path = preferences_path

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-dialog"):
            yield Static("🎒 Welcome to Packrat", classes="dialog-title")
            yield Static(
                "Choose where Packrat should keep your gear library. "
                "New libraries start with clearly labeled example gear."
            )
            yield Label("Gear storage folder")
            yield Input(value=str(preferences.suggested_data_directory()), id="setup-folder")
            yield Static(self.initial_error, id="setup-error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Quit", id="setup-quit")
                yield Button("Use This Folder", id="setup-use", variant="success")

    def on_mount(self) -> None:
        self.call_after_refresh(self._select_folder)

    def _select_folder(self) -> None:
        try:
            self.query_one("#setup-folder", Input).select_all()
        except NoMatches:
            pass

    @on(Input.Submitted, "#setup-folder")
    def _submit_folder(self) -> None:
        self._use_folder()

    @on(Button.Pressed, "#setup-use")
    def _use_folder(self) -> None:
        directory = self.query_one("#setup-folder", Input).value
        try:
            data_path, _data, created = _prepare_library(directory)
            try:
                preferences.save_preferences(
                    os.path.dirname(data_path), path=self.preferences_path
                )
            except Exception:
                if created:
                    try:
                        os.unlink(data_path)
                    except OSError:
                        pass
                raise
        except (OSError, preferences.PreferencesError, gc.DataValidationError) as exc:
            self.query_one("#setup-error", Static).update(f"Could not use that folder: {exc}")
            return
        self.exit(data_path)

    @on(Button.Pressed, "#setup-quit")
    def _quit_setup(self) -> None:
        self.exit(None)


class PreferencesScreen(ModalScreen[Optional[Tuple[str, str]]]):
    """Choose whether to open another library or copy the current one."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    AUTO_FOCUS = "#preferences-folder"

    def __init__(self, current_directory: str, initial_error: str = ""):
        super().__init__()
        self.current_directory = current_directory
        self.initial_error = initial_error

    def compose(self) -> ComposeResult:
        with Vertical(id="preferences-dialog"):
            yield Static("⚙ Storage Preferences", classes="dialog-title")
            yield Static(
                "Open a library in another folder, or copy the current library there. "
                "Packrat never overwrites an existing destination when copying."
            )
            yield Label("Gear storage folder")
            yield Input(value=self.current_directory, id="preferences-folder")
            yield Static(self.initial_error, id="preferences-error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="preferences-cancel")
                yield Button("Open / Create", id="preferences-open", variant="success")
                yield Button("Copy Current & Switch", id="preferences-copy")

    def on_mount(self) -> None:
        self.call_after_refresh(self._select_folder)

    def _select_folder(self) -> None:
        try:
            self.query_one("#preferences-folder", Input).select_all()
        except NoMatches:
            pass

    @on(Input.Submitted, "#preferences-folder")
    def _submit_folder(self) -> None:
        self._open()

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#preferences-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#preferences-open")
    def _open(self) -> None:
        self.dismiss(("open", self.query_one("#preferences-folder", Input).value))

    @on(Button.Pressed, "#preferences-copy")
    def _copy(self) -> None:
        self.dismiss(("copy", self.query_one("#preferences-folder", Input).value))


class GearTrackerApp(App):
    CSS = APP_CSS
    TITLE = "Backpacking Gear Tracker"
    BINDINGS = [
        Binding("1", "show_tab('gear')", "Gear"),
        Binding("2", "show_tab('trips')", "Trips"),
        Binding("3", "show_tab('reports')", "Reports"),
        Binding("slash", "search", "Search"),
        Binding("question_mark", "show_help", "Help"),
        Binding("ctrl+b", "backup", "Backup"),
        Binding("ctrl+p", "preferences", "Preferences", priority=True),
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, data_path: str, preferences_path: Optional[str] = None):
        super().__init__()
        self.data_path = os.path.abspath(os.path.expanduser(data_path))
        self.preferences_path = preferences_path
        self.export_dir = gc.export_dir_for_data(self.data_path)
        self.data = gc.load_data(self.data_path)
        if not os.path.exists(self.data_path):
            gc.save_data(self.data_path, self.data)
        self._data_signature = gc.file_signature(self.data_path)
        self._last_saved_data = copy.deepcopy(self.data)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, time_format="%I:%M %p")
        with TabbedContent(initial="gear"):
            with TabPane("🎒 Gear Inventory", id="gear"):
                yield GearPane()
            with TabPane("🥾 Trips", id="trips"):
                yield TripsPane()
            with TabPane("📄 Reports", id="reports"):
                yield ReportsPane()
        yield Footer()

    def action_show_tab(self, tab_id: str) -> None:
        tabs = self.query_one(TabbedContent)
        tabs.active = tab_id
        self._refresh_tab(tab_id)

    def action_search(self) -> None:
        active = self.query_one(TabbedContent).active
        selector = "#gear-search" if active == "gear" else "#trip-search" if active == "trips" else None
        if selector:
            search = self.query_one(selector, Input)
            search.focus()
            search.select_all()
        else:
            self.notify("Search is available in Gear and Trips", severity="information", timeout=2)

    def action_show_help(self) -> None:
        self.push_screen(ShortcutHelpScreen())

    def action_preferences(self) -> None:
        self.push_screen(
            PreferencesScreen(os.path.dirname(self.data_path)),
            self._change_library,
        )

    def _change_library(self, result: Optional[Tuple[str, str]]) -> None:
        if result is None:
            return
        operation, directory = result
        created_path: Optional[str] = None
        try:
            normalized_directory = preferences.normalize_path(directory)
            destination_path = preferences.data_path_for_directory(normalized_directory)
            if operation == "copy":
                if os.path.exists(destination_path):
                    raise FileExistsError(
                        f"{destination_path} already exists; use Open / Create to open it"
                    )
                if os.path.exists(normalized_directory) and not os.path.isdir(normalized_directory):
                    raise OSError(f"not a folder: {normalized_directory}")
                os.makedirs(normalized_directory, exist_ok=True)
                gc.save_data(destination_path, copy.deepcopy(self.data))
                created_path = destination_path
                new_data = gc.load_data(destination_path)
            elif operation == "open":
                destination_path, new_data, created = _prepare_library(normalized_directory)
                if created:
                    created_path = destination_path
            else:
                raise ValueError(f"unknown preference operation: {operation}")

            preferences.save_preferences(
                normalized_directory, path=self.preferences_path
            )
        except (OSError, ValueError, preferences.PreferencesError, gc.DataValidationError) as exc:
            if created_path is not None:
                try:
                    os.unlink(created_path)
                except OSError:
                    pass
            self.push_screen(
                PreferencesScreen(directory, initial_error=f"Library switch failed: {exc}"),
                self._change_library,
            )
            return

        self.data_path = destination_path
        self.export_dir = gc.export_dir_for_data(destination_path)
        self.data = new_data
        self._data_signature = gc.file_signature(destination_path)
        self._last_saved_data = copy.deepcopy(new_data)
        self._refresh_tab(self.query_one(TabbedContent).active)
        self.notify(f"Now using {destination_path}", title="Library changed", timeout=5)

    def action_backup(self) -> None:
        try:
            path = gc.backup_data(self.data_path)
        except OSError as exc:
            self.notify(f"Backup failed: {exc}", severity="error", timeout=5)
            return
        self.notify(f"Wrote {path}", title="Backup complete", timeout=4)

    @on(TabbedContent.TabActivated)
    def _tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._refresh_tab(event.pane.id or "")

    def _refresh_tab(self, tab_id: str) -> None:
        if tab_id == "gear":
            pane = self.query_one(GearPane)
            pane.refresh_table(
                pane.query_one("#gear-search", Input).value,
                review_only=getattr(pane, "_review_only", False),
            )
        elif tab_id == "trips":
            pane = self.query_one(TripsPane)
            pane.refresh_table(pane.query_one("#trip-search", Input).value)
        elif tab_id == "reports":
            self.query_one(ReportsPane).refresh_table()

    def save(self) -> bool:
        try:
            self._data_signature = gc.save_data(
                self.data_path,
                self.data,
                expected_signature=self._data_signature,
            )
        except (OSError, gc.DataValidationError) as exc:
            self.data = copy.deepcopy(self._last_saved_data)
            self.notify(f"Save failed; changes were rolled back: {exc}", severity="error", timeout=7)
            return False
        self._last_saved_data = copy.deepcopy(self.data)
        return True

    def write_export(self, filename: str, content: str) -> Optional[str]:
        path = os.path.join(self.export_dir, filename)
        try:
            gc.write_export(path, content)
        except OSError as exc:
            self.notify(f"Export failed: {exc}", severity="error", timeout=6)
            return None
        self.notify(f"Wrote {path}", title="Export complete", timeout=4)
        return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Backpacking Gear Tracker (Textual TUI)")
    parser.add_argument(
        "--data",
        default=None,
        help="Path to a JSON data file for this launch only (does not change preferences)",
    )
    args = parser.parse_args(argv)

    setup_error = ""
    try:
        data_path = preferences.resolve_startup_data_path(args.data)
    except preferences.PreferencesError as exc:
        data_path = None
        setup_error = f"Your saved preference could not be read: {exc}"

    if data_path is not None:
        try:
            app = GearTrackerApp(data_path)
        except (OSError, gc.DataValidationError) as exc:
            if args.data is not None:
                parser.error(f"could not load data file: {exc}")
            data_path = None
            setup_error = f"Your remembered library could not be opened: {exc}"

    if data_path is None:
        data_path = SetupApp(initial_error=setup_error).run()
        if data_path is None:
            return
        try:
            app = GearTrackerApp(data_path)
        except (OSError, gc.DataValidationError) as exc:
            parser.error(f"could not load data file after setup: {exc}")
    app.run()


if __name__ == "__main__":
    main()
