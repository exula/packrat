#!/usr/bin/env python3
"""
gear_tui.py — mouse-and-keyboard terminal UI for the Backpacking Gear
Tracker, built on Textual (https://textual.textualize.io).

Run:
    python3 gear_tui.py
    python3 gear_tui.py --data /path/to/gear_data.json

Requires: pip install textual (see requirements.txt)
"""

import argparse
import copy
import os
from datetime import date
from typing import Optional

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
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
            yield Label("Trip-specific note (optional, applies to the item you add)")
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
        note = self.query_one("#gp-note", Input).value.strip()
        self.dismiss((event.row_key.value, note))

    @on(Button.Pressed, "#gp-add")
    def _add(self) -> None:
        gear_id = self._current_row_key()
        if gear_id is None:
            self.app.notify("No gear left to add (or nothing matches your search)", severity="warning")
            return
        note = self.query_one("#gp-note", Input).value.strip()
        self.dismiss((gear_id, note))


class ShortcutHelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("question_mark", "close", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        help_text = """[b]Keyboard shortcuts[/b]

[b]Anywhere[/b]       1 / 2 / 3  Switch tabs     /  Search     ?  This help
                 Ctrl+B  Backup data   Q  Quit

[b]Gear[/b]           A  Add      E  Edit      Delete  Delete      R  Review filter
[b]Trips[/b]          A  Add      Enter  Open  Delete  Delete
[b]Trip dashboard[/b] A  Add item E  Edit trip Delete  Remove     X  Export
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
        Binding("e", "edit_trip", "Edit trip"),
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
                yield Button("Remove Selected", id="dash-remove-item", variant="error")
                yield Button("Edit Trip Info", id="dash-edit-trip", variant="primary")
                yield Button("Export to Markdown", id="dash-export", variant="primary")
                yield Button("← Back", id="dash-back")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#dash-cat-table", DataTable).add_columns(
            "Category", "Wt (oz)", "Wt (lb)", "Distribution")
        self.query_one("#dash-items-table", DataTable).add_columns(
            "ID", "Category", "Item", "Wt (oz)", "Flag", "Note")
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
            items_table.add_row(g["id"], g["category"], g["name"], f"{row['total_oz']:.1f}",
                                flag, row["trip_note"], key=g["id"])

    def action_go_back(self) -> None:
        self.dismiss()

    def action_add_item(self) -> None:
        self._add_item()

    def action_edit_trip(self) -> None:
        self._edit_trip()

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
                gear_id, note = result
                trip["items"].append({"gear_id": gear_id, "note": note})
                if not app.save():
                    return
                self.refresh_dashboard()
                self.app.notify("Added to trip", severity="information", timeout=2)

        self.app.push_screen(GearPickerScreen(app.data["gear"], exclude), handle)

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
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, data_path: str):
        super().__init__()
        self.data_path = os.path.abspath(os.path.expanduser(data_path))
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


def main():
    parser = argparse.ArgumentParser(description="Backpacking Gear Tracker (Textual TUI)")
    parser.add_argument("--data", default=gc.DEFAULT_DATA_PATH,
                        help="Path to the JSON data file (default: gear_data.json next to this script)")
    args = parser.parse_args()
    try:
        app = GearTrackerApp(args.data)
    except (OSError, gc.DataValidationError) as exc:
        parser.error(f"could not load data file: {exc}")
    app.run()


if __name__ == "__main__":
    main()
